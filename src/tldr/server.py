"""Lightweight HTTP server for viewing TL;DR architecture diagrams."""

from __future__ import annotations

import signal
import shutil
import socket
import subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class DiagramHandler(SimpleHTTPRequestHandler):
    """Serves frontend dist + workspace YAML files."""

    workspace: Path
    frontend_dist: Path

    def translate_path(self, path: str) -> str:
        # Serve YAML files from workspace
        if path in ("/elements.yaml", "/connectors.yaml"):
            return str(self.workspace / path.lstrip("/"))
        # Everything else from frontend dist
        rel = path.lstrip("/")
        candidate = self.frontend_dist / rel
        if candidate.exists() and candidate.is_file():
            return str(candidate)
        # SPA fallback
        return str(self.frontend_dist / "index.html")

    def log_message(self, format: str, *args) -> None:
        # Suppress noisy access logs
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
                signal.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
    except subprocess.CalledProcessError:
        pass  # no process on port


class _ReuseAddrHTTPServer(HTTPServer):
    allow_reuse_address = True


def serve(workspace: Path, frontend_dist: Path, port: int = 8060, open_browser: bool = True) -> None:
    """Start the diagram viewer server."""
    if not (workspace / "elements.yaml").exists():
        raise FileNotFoundError(f"No elements.yaml in {workspace}")
    if not (frontend_dist / "index.html").exists():
        raise FileNotFoundError(f"No index.html in {frontend_dist} — build the frontend first")

    _kill_port(port)

    DiagramHandler.workspace = workspace
    DiagramHandler.frontend_dist = frontend_dist

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
