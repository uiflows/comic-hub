#!/usr/bin/env python3
"""Tiny HTTP proxy that converts webp images to jpg on the fly.

Usage: python3 webp2jpg.py [port]
Default port: 8090

Request: GET /path/to/image.webp
Response: converted JPEG image

Used by MC CMS import to serve webp images as jpg.
"""

import http.server
import subprocess
import tempfile
import os
import sys
import urllib.parse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
COMIC_DATA = "/Volumes/SSD/Hermes/Hermes总工作台/项目/comic-hub/data"


class Converter(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # Decode URL path
        path = urllib.parse.unquote(self.path.split("?")[0])
        
        # Map /data/... to COMIC_DATA/...
        if path.startswith("/data/"):
            file_path = os.path.join(COMIC_DATA, path[6:])
        else:
            file_path = os.path.join(COMIC_DATA, path.lstrip("/"))
        
        if not os.path.exists(file_path):
            self.send_error(404, f"Not found: {path}")
            return
        
        # Convert webp to jpg using sips
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            result = subprocess.run(
                ["sips", "-s", "format", "jpeg", file_path, "--out", tmp_path],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                self.send_error(500, "Conversion failed")
                return
            
            file_size = os.path.getsize(tmp_path)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            
            with open(tmp_path, "rb") as f:
                self.wfile.write(f.read())
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def log_message(self, format, *args):
        # Suppress default logging noise
        pass


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), Converter)
    print(f"🖼  WebP→JPG converter running on http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
