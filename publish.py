"""
Guangchen secure release tool.

This script publishes the signed OTA v2 package:
- backend Python source is deployed only to the cloud server
- customers download only app.asar and rpa_engine.zip
- .py source files and .env are not shipped as client OTA artifacts
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import paramiko


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
CLOUD_HOST = "124.223.99.238"
CLOUD_USER = "ubuntu"
CLOUD_PASS = "Abc1234567890"
REMOTE_DIR = "/var/www/guangchen"
REMOTE_UPDATE_DIR = f"{REMOTE_DIR}/update/v2"

LOCAL_BACKEND = ROOT / "douyin-rpa"
LOCAL_DESKTOP = ROOT / "douyin-rpa-desktop"
LOCAL_RELEASE = LOCAL_DESKTOP / "release" / "win-unpacked"
LOCAL_SOFTWARE = ROOT / "\u8f6f\u4ef6"
SECURE_UPDATE_DIR = ROOT / "secure_update" / "v2"

BACKEND_FILES = [
    "rpa_server.py",
    "slot_manager.py",
    "ai_replier.py",
    "lead_extractor.py",
    "db_manager.py",
]


def step(title: str) -> None:
    print(f"\n{'=' * 58}")
    print(f"  {title}")
    print(f"{'=' * 58}")


def _resolve_cmd(cmd):
    if isinstance(cmd, str):
        return cmd
    if not cmd:
        return cmd

    exe = cmd[0]
    resolved = shutil.which(exe)
    if not resolved and os.name == "nt":
        for ext in (".cmd", ".bat", ".exe"):
            resolved = shutil.which(exe + ext)
            if resolved:
                break
    if not resolved:
        raise FileNotFoundError(
            f"找不到命令：{exe}。请确认已安装并加入 PATH，或重启 PowerShell 后再试。"
        )
    return [resolved, *cmd[1:]]


def run(cmd, cwd: Path) -> None:
    print(f"> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    subprocess.check_call(_resolve_cmd(cmd), cwd=str(cwd), shell=isinstance(cmd, str))


def mkdir_p(sftp, remote_path: str) -> None:
    parts = []
    while remote_path not in ("", "/"):
        parts.append(remote_path)
        remote_path = os.path.dirname(remote_path)
    for path in reversed(parts):
        try:
            sftp.stat(path)
        except OSError:
            sftp.mkdir(path)


def upload_file(sftp, local: Path, remote: str) -> None:
    if not local.exists():
        raise FileNotFoundError(local)
    sftp.put(str(local), remote)
    print(f"   uploaded {local.name} -> {remote}")


def find_one(directory: Path, pattern: str, *, exclude_text: str = "") -> Path:
    matches = []
    for path in directory.glob(pattern):
        if exclude_text and exclude_text.lower() in path.name.lower():
            continue
        matches.append(path)
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(f"找不到文件：{directory / pattern}")
    return matches[0]


def main() -> int:
    print("光宸智能客服 - 安全发版工具")
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    step("1/7 构建前端 dist")
    run(["npm", "run", "build"], LOCAL_DESKTOP)

    step("2/7 构建受保护的 rpa_engine")
    run(["py", "-m", "PyInstaller", "build_engine.spec", "--clean", "--noconfirm"], LOCAL_BACKEND)

    step("3/7 构建 Electron 安装包")
    try:
        run(["npx", "electron-builder"], LOCAL_DESKTOP)
    except subprocess.CalledProcessError:
        setup = find_one(LOCAL_DESKTOP / "release", "*Setup 1.0.3.exe")
        app_asar = LOCAL_RELEASE / "resources" / "app.asar"
        engine = LOCAL_RELEASE / "resources" / "rpa_engine" / "rpa_engine.exe"
        if not (setup.exists() and app_asar.exists() and engine.exists()):
            raise
        print("   electron-builder 返回非 0，但核心产物已生成，继续发版。")

    step("4/7 生成签名安全 OTA 包")
    run(["py", str(ROOT / "tools" / "build_secure_update.py")], ROOT)

    step("5/7 上传服务器代码和安全 OTA 包")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(CLOUD_HOST, username=CLOUD_USER, password=CLOUD_PASS, timeout=15, banner_timeout=30)
    sftp = client.open_sftp()
    mkdir_p(sftp, REMOTE_UPDATE_DIR)

    for name in BACKEND_FILES:
        upload_file(sftp, LOCAL_BACKEND / name, f"{REMOTE_DIR}/{name}")

    for name in ("manifest.json", "app.asar", "rpa_engine.zip"):
        upload_file(sftp, SECURE_UPDATE_DIR / name, f"{REMOTE_UPDATE_DIR}/{name}")

    sftp.close()

    step("6/7 重启云端服务")
    stdin, stdout, stderr = client.exec_command(
        "sudo -S systemctl restart guangchen && sleep 2 && sudo systemctl status guangchen | head -5"
    )
    stdin.write(f"{CLOUD_PASS}\n")
    stdin.flush()
    print(stdout.read().decode("utf-8", errors="replace").strip())
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if err:
        print(err)
    client.close()

    step("7/7 同步本地软件目录")
    LOCAL_SOFTWARE.mkdir(exist_ok=True)
    setup_src = find_one(LOCAL_DESKTOP / "release", "*Setup 1.0.3.exe")
    portable_src = find_one(LOCAL_DESKTOP / "release", "* 1.0.3.exe", exclude_text="Setup")
    setup_dst = LOCAL_SOFTWARE / "\u53d1\u7ed9\u5ba2\u6237-\u5149\u5bb8\u667a\u80fd\u5ba2\u670d Setup 1.0.3.exe"
    portable_dst = LOCAL_SOFTWARE / "\u5907\u7528-\u4fbf\u643a\u7248-\u5149\u5bb8\u667a\u80fd\u5ba2\u670d 1.0.3.exe"
    shutil.copy2(setup_src, setup_dst)
    shutil.copy2(portable_src, portable_dst)
    print(f"   {setup_dst}")
    print(f"   {portable_dst}")

    print("\n发版完成：客户下次启动会下载签名后的二进制更新包，不会下载源码。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
