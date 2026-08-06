"""Lightweight HTTP server for viewing TL;DR architecture diagrams."""

from __future__ import annotations

import os
import signal
import time
import shutil
import subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class DiagramHandler(SimpleHTTPRequestHandler):
    """Serves frontend dist + workspace YAML files."""

    workspace: Path
    frontend_dist: Path
    source_root: Path | None = None

    def translate_path(self, path: str) -> str:
        if path in ("/elements.yaml", "/connectors.yaml"):
            return str(self.workspace / path.lstrip("/"))
        rel = path.lstrip("/")
        candidate = self.frontend_dist / rel
        if candidate.exists() and candidate.is_file():
            return str(candidate)
        return str(self.frontend_dist / "index.html")

    def do_GET(self) -> None:
        if self.path == "/config.json":
            import json
            body = json.dumps({"sourceRoot": str(self.source_root) if self.source_root else None}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, format: str, *args) -> None:
        pass


def _kill_port(port: int) -> None:
    """Kill any process already listening on port (macOS/Linux)."""
    lsof = shutil.which("lsof")
    if not lsof:
        return
    try:
        out = subprocess.check_output([lsof, "-ti", f"tcp:{port}"], text=True)
        for pid in out.split():
            try:
                os.kill(int(pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        # Wait for port to actually be released (up to 2s)
        for _ in range(20):
            time.sleep(0.1)
            try:
                subprocess.check_output([lsof, "-ti", f"tcp:{port}"], text=True)
            except subprocess.CalledProcessError:
                break
    except subprocess.CalledProcessError:
        pass  # no process on port


class _ReuseAddrHTTPServer(HTTPServer):
    allow_reuse_address = True


def serve(workspace: Path, frontend_dist: Path, port: int = 8060, open_browser: bool = True, source_root: Path | None = None) -> None:
    """Start the diagram viewer server."""
    if not (workspace / "elements.yaml").exists():
        raise FileNotFoundError(f"No elements.yaml in {workspace}")
    if not (frontend_dist / "index.html").exists():
        raise FileNotFoundError(f"No index.html in {frontend_dist} — build the frontend first")

    _kill_port(port)

    DiagramHandler.workspace = workspace
    DiagramHandler.frontend_dist = frontend_dist
    DiagramHandler.source_root = source_root

    server = _ReuseAddrHTTPServer(("", port), DiagramHandler)
    url = f"http://127.0.0.1:{port}/views"
    print(f"Serving at {url}")
    if open_browser:
        opener = shutil.which("open")
        if opener:
            subprocess.Popen([opener, url])
        else:
            import webbrowser
            webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()
