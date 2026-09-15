"""Headless check for DiscoveredServersModel (M40): TXT parsing, and a live zeroconf round trip
with a service this check registers itself (the round trip needs python-zeroconf)."""

import os
import socket
import sys
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from PySide6.QtCore import QCoreApplication, QTimer

from models.discovery_model import DiscoveredServersModel, parse_service

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


SID = "0123456789abcdef0123456789abcdef"
row = parse_service({b"id": SID.encode(), b"name": b"Den Box", b"https": b"1", b"pin": b"sha256/abc="},
                    ["169.254.1.2", "127.0.0.1", "192.168.1.9"], 40204, "Den Box._theden._tcp.local.")
check("parses bytes TXT and skips link-local and loopback addresses",
      row is not None and row["host"] == "192.168.1.9" and row["url"] == "https://192.168.1.9:40204"
      and row["pin"] == "sha256/abc=" and row["name"] == "Den Box")
row = parse_service({"id": SID, "https": "0", "pin": "sha256/abc="}, ["10.0.0.5"], 40204, "Den Box._theden._tcp.local.")
check("a plain http row drops the pin and falls back to the service name",
      row is not None and row["pin"] == "" and row["url"] == "http://10.0.0.5:40204" and row["name"] == "Den Box")
check("a bad server id is rejected", parse_service({"id": "nope"}, ["10.0.0.5"], 40204, "x") is None)
check("no usable address is rejected", parse_service({"id": SID}, ["127.0.0.1", "fe80::1"], 40204, "x") is None)
check("a bad port is rejected", parse_service({"id": SID}, ["10.0.0.5"], 0, "x") is None)
check("a missing name falls back to The Den", (parse_service({"id": SID}, ["10.0.0.5"], 1, "") or {}).get("name") == "The Den")

try:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
except ImportError:
    print("skip: the live zeroconf round trip needs python-zeroconf")
    sys.exit(1 if fails else 0)

app = QCoreApplication(sys.argv)


def wait(cond, ms=15000):
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(app.quit)
    timer.start(ms)
    poll = QTimer()
    poll.timeout.connect(lambda: cond() and app.quit())
    poll.start(50)
    app.exec()
    poll.stop()
    timer.stop()
    return cond()


def lan_ip():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # sends nothing; just picks the outgoing interface
        return probe.getsockname()[0]
    finally:
        probe.close()


def rows(model):
    return [model.get(i) for i in range(model.count)]


ip = lan_ip()
server_id = uuid.uuid4().hex
label = f"Check {server_id[:6]}"
info = ServiceInfo("_theden._tcp.local.", f"{label}._theden._tcp.local.", addresses=[socket.inet_aton(ip)], port=40999,
                   properties={"name": label, "id": server_id, "api": "2", "https": "1", "pin": "sha256/check="})
zc = Zeroconf(ip_version=IPVersion.V4Only)
zc.register_service(info)
model = DiscoveredServersModel()
model.start()
check("browsing started", model.browsing and model.available)
found = wait(lambda: any(r.get("serverId") == server_id for r in rows(model)))
check("the registered server shows up", found)
if found:
    r = next(r for r in rows(model) if r.get("serverId") == server_id)
    check("its row has the https URL and the advertised pin", r["url"] == f"https://{ip}:40999" and r["pin"] == "sha256/check=")
    check("rows expose the QML role names", set(model.roleNames().values()) >= {b"name", b"serverId", b"url", b"pin"})
zc.unregister_service(info)
gone = wait(lambda: not any(r.get("serverId") == server_id for r in rows(model)))
check("the server disappears when it stops advertising", gone)
model.stop()
check("stop clears the list", model.count == 0 and not model.browsing)
zc.close()
sys.exit(1 if fails else 0)