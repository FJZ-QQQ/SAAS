"""
★ 一键发版脚本 — 同步后端 + 前端到云端 + 更新本地 release 包
用法: py publish.py
"""
import paramiko
import os
import sys
import json
import hashlib
import zipfile
import io
import time

# Fix Windows encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ===== 配置 =====
CLOUD_HOST = '124.223.99.238'
CLOUD_USER = 'ubuntu'
CLOUD_PASS = 'Abc1234567890'
REMOTE_DIR = '/var/www/guangchen'

LOCAL_BACKEND = r"d:\trea ai\Google\GLM\项目2\douyin-rpa"
LOCAL_DESKTOP = r"d:\trea ai\Google\GLM\项目2\douyin-rpa-desktop"
LOCAL_RELEASE = r"d:\trea ai\Google\GLM\项目2\douyin-rpa-desktop\release\win-unpacked"

# 后端可热更新文件
BACKEND_FILES = ["rpa_server.py", "slot_manager.py", "ai_replier.py", "lead_extractor.py", "db_manager.py"]

# ===== 工具函数 =====
def file_md5(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def step(msg):
    print(f"\n{'='*50}")
    print(f"  {msg}")
    print(f"{'='*50}")

# ===== 主流程 =====
def main():
    print("🚀 光宸智能客服 — 一键发版工具")
    print(f"   时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # ---- Step 1: 构建前端 ----
    step("1/5 构建前端...")
    os.system(f'cd /d "{LOCAL_DESKTOP}" && npm run build')
    
    # ---- Step 2: 打包前端 dist 为 zip ----
    step("2/5 打包前端 dist.zip...")
    dist_dir = os.path.join(LOCAL_DESKTOP, "dist")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(dist_dir):
            for fname in files:
                if fname == ".dist_hash":
                    continue
                full = os.path.join(root, fname)
                arcname = os.path.relpath(full, dist_dir)
                zf.write(full, arcname)
    zip_data = zip_buffer.getvalue()
    dist_hash = hashlib.md5(zip_data).hexdigest()
    print(f"   dist.zip 大小: {len(zip_data)//1024} KB")
    
    # 保存到本地
    zip_path = os.path.join(LOCAL_BACKEND, "dist.zip")
    with open(zip_path, 'wb') as f:
        f.write(zip_data)
    with open(os.path.join(dist_dir, ".dist_hash"), 'w', encoding='utf-8') as f:
        f.write(dist_hash)
    
    # ---- Step 3: 上传到云端 ----
    step("3/5 上传到云端...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(CLOUD_HOST, username=CLOUD_USER, password=CLOUD_PASS, timeout=15, banner_timeout=30)
    sftp = client.open_sftp()
    
    # 上传后端文件
    for f in BACKEND_FILES:
        local = os.path.join(LOCAL_BACKEND, f)
        remote = f"{REMOTE_DIR}/{f}"
        sftp.put(local, remote)
        print(f"   ✅ {f}")
    
    # 上传前端 zip
    sftp.put(zip_path, f"{REMOTE_DIR}/dist.zip")
    print(f"   ✅ dist.zip")
    
    sftp.close()
    
    # ---- Step 4: 重启云端服务 ----
    step("4/5 重启云端服务...")
    stdin, stdout, stderr = client.exec_command(
        "sudo systemctl restart guangchen && sleep 2 && sudo systemctl status guangchen | head -5"
    )
    stdin.write(f"{CLOUD_PASS}\n")
    stdin.flush()
    print(stdout.read().decode().strip())
    client.close()
    
    # ---- Step 5: 更新本地 release 包 ----
    step("5/5 更新本地 release 包...")
    release_internal = os.path.join(LOCAL_RELEASE, "resources", "rpa_engine", "_internal")
    release_dist = os.path.join(LOCAL_RELEASE, "resources", "app", "dist")
    release_maincjs = os.path.join(LOCAL_RELEASE, "resources", "app", "electron", "main.cjs")
    
    # 复制后端文件
    for f in BACKEND_FILES:
        src = os.path.join(LOCAL_BACKEND, f)
        dst = os.path.join(release_internal, f)
        if os.path.exists(src) and os.path.exists(os.path.dirname(dst)):
            import shutil
            shutil.copy2(src, dst)
            print(f"   ✅ {f} → release")
    
    # 复制前端 dist
    if os.path.exists(release_dist):
        import shutil
        shutil.rmtree(release_dist, ignore_errors=True)
        shutil.copytree(dist_dir, release_dist)
        with open(os.path.join(release_dist, ".dist_hash"), 'w', encoding='utf-8') as f:
            f.write(dist_hash)
        print(f"   ✅ dist/ → release")
    
    # 复制 main.cjs
    src_main = os.path.join(LOCAL_DESKTOP, "electron", "main.cjs")
    if os.path.exists(src_main) and os.path.exists(os.path.dirname(release_maincjs)):
        import shutil
        shutil.copy2(src_main, release_maincjs)
        print(f"   ✅ main.cjs → release")
    
    # 复制 preload.js
    src_preload = os.path.join(LOCAL_DESKTOP, "electron", "preload.js")
    release_preload = os.path.join(LOCAL_RELEASE, "resources", "app", "electron", "preload.js")
    if os.path.exists(src_preload) and os.path.exists(os.path.dirname(release_preload)):
        import shutil
        shutil.copy2(src_preload, release_preload)
        print(f"   ✅ preload.js → release")
    
    # ---- 完成 ----
    print(f"\n{'🎉'*20}")
    print(f"  发版完成！")
    print(f"  • 云端服务已更新并重启")
    print(f"  • 本地 release 包已同步")
    print(f"  • 客户下次打开软件将自动获取最新版本")
    print(f"{'🎉'*20}\n")

if __name__ == "__main__":
    main()
