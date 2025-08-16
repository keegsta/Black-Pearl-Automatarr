#!/usr/bin/env python3

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

MANIFEST_FILE = Path("/home/user/blackpearl/captains_logs/manifest.json")
HOST = "0.0.0.0"
PORT = 5050

class TorrentAPIHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        response = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_GET(self):
        try:
            if not MANIFEST_FILE.exists():
                self._send_json({"error": "Manifest not found"}, status=404)
                return

            with open(MANIFEST_FILE, "r") as f:
                content = f.read().strip()
                if not content:
                    self._send_json({"error": "Manifest is empty"}, status=500)
                    return
                try:
                    manifest = json.loads(content)
                except json.JSONDecodeError as e:
                    self._send_json({"error": f"JSON error: {str(e)}"}, status=500)
                    return

            if self.path == "/status":
                self._send_json(manifest)
            elif self.path == "/summary":
                summary = {
                    "total": len(manifest),
                    "stalled": sum(1 for t in manifest.values() if t["status"] == "stalledDL"),
                    "seeding": sum(1 for t in manifest.values() if t["status"] == "uploading"),
                    "downloading": sum(1 for t in manifest.values() if t["status"] == "downloading"),
                }
                self._send_json(summary)
            else:
                self._send_json({"error": "Not Found"}, status=404)

        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

def run_server():
    print(f"Starting Torrent API server at http://{HOST}:{PORT}")
    server = HTTPServer((HOST, PORT), TorrentAPIHandler)
    server.serve_forever()

if __name__ == "__main__":
    run_server()
