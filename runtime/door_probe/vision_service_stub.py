import base64
import io
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class VisionHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/infer/door_state":
            self._send_json({"error": "not_found"}, status=404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8", errors="ignore") or "{}")
        except Exception as exc:
            self._send_json({"error": f"bad_request:{exc}"}, status=400)
            return

        camera_key = str(data.get("camera_key") or "main")
        image_b64 = str(data.get("image_b64") or "")
        if not image_b64:
            self._send_json({"error": "missing_image_b64"}, status=400)
            return

        # Stub only: decode to validate payload shape; real model should run here.
        try:
            _ = io.BytesIO(base64.b64decode(image_b64.encode("ascii"), validate=False))
        except Exception:
            self._send_json({"error": "invalid_image_b64"}, status=400)
            return

        # Example protocol response expected by api/door.py
        # Replace status/confidence/people_count/zone_counts with model output.
        self._send_json(
            {
                "camera_key": camera_key,
                "status": "unknown",
                "confidence": 0.0,
                "diff_c": 0.0,
                "diff_o": 0.0,
                "people_count": 0,
                "zone_counts": {},
            }
        )


def run(host="0.0.0.0", port=18080):
    server = HTTPServer((host, int(port)), VisionHandler)
    print(f"[vision_stub] serving on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
