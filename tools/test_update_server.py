import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPDATE_DIR = ROOT / "secure_update" / "v2"
ALLOWED_FILES = {
    "app.asar": "application/octet-stream",
    "rpa_engine.zip": "application/zip",
}


class UpdateHandler(BaseHTTPRequestHandler):
    update_dir: Path = DEFAULT_UPDATE_DIR

    def _send_json(self, status: int, payload: dict, send_body: bool = True):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def _send_file(self, path: Path, content_type: str, download_name: str, send_body: bool = True):
        if not path.exists() or not path.is_file():
            self._send_json(404, {"error": f"{download_name} not found"}, send_body)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if not send_body:
            return
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _handle_request(self, send_body: bool):
        parsed = urlparse(self.path)
        request_path = parsed.path.rstrip("/")

        if request_path in ("", "/"):
            self._send_json(200, {
                "status": "ok",
                "endpoints": [
                    "/api/update/v2/manifest",
                    "/api/update/v2/file/app.asar",
                    "/api/update/v2/file/rpa_engine.zip",
                ],
            }, send_body)
            return

        if request_path == "/api/update/v2/manifest":
            self._send_file(
                self.update_dir / "manifest.json",
                "application/json; charset=utf-8",
                "manifest.json",
                send_body,
            )
            return

        prefix = "/api/update/v2/file/"
        if request_path.startswith(prefix):
            filename = unquote(request_path[len(prefix):])
            if filename not in ALLOWED_FILES:
                self._send_json(403, {"error": "file not allowed"}, send_body)
                return
            self._send_file(self.update_dir / filename, ALLOWED_FILES[filename], filename, send_body)
            return

        self._send_json(404, {"error": "not found"}, send_body)

    def do_GET(self):
        self._handle_request(send_body=True)

    def do_HEAD(self):
        self._handle_request(send_body=False)

    def log_message(self, fmt, *args):
        print(f"[test-update] {self.address_string()} - {fmt % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Local secure OTA v2 test server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--dir", default=str(DEFAULT_UPDATE_DIR), help="Directory containing manifest.json/app.asar/rpa_engine.zip")
    args = parser.parse_args()

    update_dir = Path(args.dir).resolve()
    missing = [name for name in ("manifest.json", "app.asar", "rpa_engine.zip") if not (update_dir / name).exists()]
    if missing:
        raise SystemExit(f"Missing update files in {update_dir}: {', '.join(missing)}")

    UpdateHandler.update_dir = update_dir
    server = ThreadingHTTPServer((args.host, args.port), UpdateHandler)
    print(f"Secure OTA test server: http://{args.host}:{args.port}")
    print(f"Serving update package: {update_dir}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
