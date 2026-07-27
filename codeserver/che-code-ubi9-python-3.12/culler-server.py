#!/usr/bin/env python3
"""Tiny HTTP server on port 8080 that serves the /api/kernels/ culler endpoint."""

import http.server
import subprocess
import sys


class CullerHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") in ("/api/kernels", "/api/kernels/"):
            try:
                result = subprocess.run(
                    ["/opt/app-root/api/kernels/access.cgi"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except subprocess.TimeoutExpired:
                self.send_error(504, "CGI script timed out")
                return
            if result.returncode != 0:
                self.send_error(502, "CGI script failed")
                return
            body = result.stdout
            # CGI output includes headers; split on blank line
            parts = body.split("\n\n", 1)
            payload = parts[1] if len(parts) > 1 else body
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload.encode())
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass  # suppress access logs


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", 8080), CullerHandler)
    print("Culler server listening on 127.0.0.1:8080", file=sys.stderr)
    server.serve_forever()
