import base64
import hashlib
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization


ROOT = Path(__file__).resolve().parents[1]
DESKTOP_RELEASE = ROOT / "douyin-rpa-desktop" / "release" / "win-unpacked"
PRIVATE_KEY_PATH = ROOT / "secrets" / "update_private_key.pem"
OUTPUT_DIR = ROOT / "secure_update" / "v2"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(data) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def zip_dir(source_dir: Path, output_zip: Path) -> None:
    forbidden_names = {
        ".env",
        "rpa_server.py",
        "slot_manager.py",
        "db_manager.py",
        "ai_replier.py",
        "lead_extractor.py",
    }
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(source_dir).as_posix()
            if path.name in forbidden_names:
                raise RuntimeError(f"Refusing to package sensitive source file: {rel}")
            zf.write(path, rel)


def load_private_key():
    if not PRIVATE_KEY_PATH.exists():
        raise FileNotFoundError(
            f"Missing update signing private key: {PRIVATE_KEY_PATH}\n"
            "Do not regenerate this casually; clients trust the matching public key."
        )
    return serialization.load_pem_private_key(PRIVATE_KEY_PATH.read_bytes(), password=None)


def main() -> int:
    app_asar = DESKTOP_RELEASE / "resources" / "app.asar"
    rpa_engine = DESKTOP_RELEASE / "resources" / "rpa_engine"
    if not app_asar.exists():
        raise FileNotFoundError(f"Missing app.asar: {app_asar}")
    if not rpa_engine.exists():
        raise FileNotFoundError(f"Missing rpa_engine directory: {rpa_engine}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_app_asar = OUTPUT_DIR / "app.asar"
    out_engine_zip = OUTPUT_DIR / "rpa_engine.zip"

    shutil.copy2(app_asar, out_app_asar)
    if out_engine_zip.exists():
        out_engine_zip.unlink()
    zip_dir(rpa_engine, out_engine_zip)

    package_json = json.loads((ROOT / "douyin-rpa-desktop" / "package.json").read_text(encoding="utf-8"))
    payload = {
        "schema": 2,
        "version": package_json.get("version", "0.0.0"),
        "build": time.strftime("%Y%m%d%H%M%S"),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "artifacts": {
            "app_asar": {
                "filename": "app.asar",
                "sha256": sha256_file(out_app_asar),
                "size": out_app_asar.stat().st_size,
            },
            "rpa_engine": {
                "filename": "rpa_engine.zip",
                "sha256": sha256_file(out_engine_zip),
                "size": out_engine_zip.stat().st_size,
            },
        },
    }

    private_key = load_private_key()
    signature = private_key.sign(canonical_json(payload))
    manifest = {
        "payload": payload,
        "signature_alg": "ed25519",
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Secure update package written to: {OUTPUT_DIR}")
    print(f"  app.asar      {payload['artifacts']['app_asar']['size'] // 1024} KB")
    print(f"  rpa_engine.zip {payload['artifacts']['rpa_engine']['size'] // 1024} KB")
    print(f"  build         {payload['build']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
