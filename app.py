"""Dependency-free HTTP host for the Terzaghi Settlement Analysis System."""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from settlement_engine import EngineeringValidationError, analyze_settlement


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"


class ApplicationHandler(BaseHTTPRequestHandler):
    server_version = "TerzaghiAnalysis/1.0"

    def _json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/analyze":
            self._json(404, {"message": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 2_000_000:
                raise EngineeringValidationError({"request": "A valid analysis request is required."})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise EngineeringValidationError({"request": "Analysis request must be a JSON object."})
            self._json(200, analyze_settlement(payload))
        except EngineeringValidationError as error:
            self._json(422, {"message": "Correct the highlighted engineering inputs.", "errors": error.errors})
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json(400, {"message": "Request body is not valid JSON."})
        except Exception as error:  # safe response; retain console diagnostic
            print(f"Unexpected calculation error: {error}")
            self._json(500, {"message": "The analysis could not be completed due to an internal error."})

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        relative = "index.html" if route == "/" else route.lstrip("/")
        candidate = (STATIC / relative).resolve()
        try:
            candidate.relative_to(STATIC.resolve())
        except ValueError:
            self.send_error(403)
            return
        if not candidate.is_file():
            self.send_error(404)
            return
        content = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def main() -> None:
    host, port = "127.0.0.1", 8000
    print(f"Terzaghi Settlement Analysis System: http://{host}:{port}")
    ThreadingHTTPServer((host, port), ApplicationHandler).serve_forever()


if __name__ == "__main__":
    main()
