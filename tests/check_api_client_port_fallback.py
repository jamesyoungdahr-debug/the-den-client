"""Headless check for ApiClient's M34 port fallback: a saved address on the old
port 8686 that no longer answers is retried on 40204, and switched to only if the server
answers there. Uses [::1] so the HoltOS-installed server on 127.0.0.1:8686 can't answer.
Run from the repo root: `QT_QPA_PLATFORM=offscreen python3 tests/check_api_client_port_fallback.py`
"""

import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtCore import QCoreApplication, QTimer

from api_client import ApiClient

OLD_URL = "http://[::1]:8686"
NEW_URL = "http://[::1]:40204"
failures = []


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"FAIL: {msg}")


class HealthyHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = b'{"status":"ok","setup_complete":true}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class IPv6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6


app = QCoreApplication(sys.argv)
server = None


def check_moved_url() -> None:
    print("-- _moved_url rewrites any address on 8686 to the same host on 40204 --")
    cases = {
        "http://127.0.0.1:8686": "http://127.0.0.1:40204",
        "http://localhost:8686": "http://localhost:40204",
        OLD_URL: NEW_URL,
        "http://192.168.0.236:8686": "http://192.168.0.236:40204",
        "http://127.0.0.1:8687": "",
        "http://127.0.0.1:40204": "",
    }
    for base, expected in cases.items():
        got = ApiClient(base_url=base, persist=False)._moved_url()
        if got != expected:
            fail(f"_moved_url({base!r}) = {got!r}, expected {expected!r}")


def step1_no_server() -> None:
    print("-- nothing on 40204: stay on the saved address and report the failure --")
    global client
    client = ApiClient(base_url=OLD_URL, api_token="", persist=False)
    client.checkHealth()
    QTimer.singleShot(3000, step2_verify_no_server)


def step2_verify_no_server() -> None:
    if client.connected:
        fail("connected with no server on either port")
    if client.baseUrl != OLD_URL:
        fail(f"baseUrl changed to {client.baseUrl!r} with no server on 40204")
    if not client.statusText.startswith("Connection failed"):
        fail(f"expected a 'Connection failed' status, got {client.statusText!r}")
    step3_server()


def step3_server() -> None:
    print("-- a server on 40204: switch to it and connect --")
    global client, server
    server = IPv6Server(("::1", 40204), HealthyHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = ApiClient(base_url=OLD_URL, api_token="", persist=False)
    client.checkHealth()
    QTimer.singleShot(3000, step4_verify_server)


def step4_verify_server() -> None:
    if client.baseUrl != NEW_URL:
        fail(f"expected baseUrl {NEW_URL!r}, got {client.baseUrl!r}")
    if not client.connected:
        fail(f"expected connected=True, statusText={client.statusText!r}")
    server.shutdown()
    print("-- done --")
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        sys.exit(1)
    print("ALL CHECKS PASSED")
    app.quit()


client = None
check_moved_url()
QTimer.singleShot(0, step1_no_server)
sys.exit(app.exec())