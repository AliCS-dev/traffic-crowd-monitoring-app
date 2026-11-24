"""Small HTTP fixture for the isolated Nginx/Docker DNS regression, not the API."""

import hashlib
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    submissions = 0
    protocol_version = "HTTP/1.1"

    def reply(self, extra=None):
        body = json.dumps(
            {"status": "ready", "path": self.path, "submissions": self.submissions}
            | (extra or {})
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply()

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Handler.submissions += 1
        if self.path == "/api/disconnect":
            # A submission reached the service, but its response was lost.
            self.close_connection = True
            return
        self.reply({"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
