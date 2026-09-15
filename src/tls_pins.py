"""Certificate pinning for The Den's HTTPS (M40).

A server that listens on the LAN serves HTTPS with one key it keeps for good and a self-signed
certificate (server 0.8.1c). The first time this app reaches such a server it shows the key's pin
and asks whether to trust it; from then on only that key is accepted at that address, and a
server id seen before can't switch to a different key without the person forgetting the old one.
Nothing is ever trusted automatically, including pins that arrive over LAN discovery.

Pins use the server's format: "sha256/" + standard padded base64 of SHA-256 over the
certificate's SubjectPublicKeyInfo DER.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import re
from urllib.parse import quote

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from PySide6.QtCore import QSettings, QUrl

_SERVER_ID = re.compile(r"^[0-9a-f]{32}$")


def pin_for_der(der: bytes) -> str:
    """The pin for a DER-encoded certificate."""
    cert = x509.load_der_x509_certificate(der)
    spki = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return "sha256/" + base64.b64encode(hashlib.sha256(spki).digest()).decode("ascii")


def is_loopback_host(host: str) -> bool:
    host = (host or "").strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def authority_of(url: QUrl) -> str:
    """host:port for a URL, with the scheme's default port filled in and IPv6 hosts in brackets."""
    host = url.host().lower()
    port = url.port(443 if url.scheme() == "https" else 80)
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


class PinStore:
    """Trusted pins by address (what the TLS check uses) and by server id (to catch a key change).
    Kept in QSettings when one is given, else in memory for this process."""

    def __init__(self, settings: QSettings | None = None):
        self._settings = settings
        self._memory: dict[str, str] = {}

    def _get(self, key: str) -> str:
        if self._settings is not None:
            return str(self._settings.value(key, "") or "")
        return self._memory.get(key, "")

    def _put(self, key: str, value: str) -> None:
        if self._settings is not None:
            self._settings.setValue(key, value)
            self._settings.sync()
        else:
            self._memory[key] = value

    def _remove(self, key: str) -> None:
        if self._settings is not None:
            self._settings.remove(key)
            self._settings.sync()
        else:
            self._memory.pop(key, None)

    @staticmethod
    def _address_key(authority: str) -> str:
        return "pins/" + quote(authority.lower(), safe="")

    def for_address(self, authority: str) -> str:
        return self._get(self._address_key(authority))

    def trust_address(self, authority: str, pin: str) -> None:
        self._put(self._address_key(authority), pin)

    def for_server(self, server_id: str) -> str:
        return self._get(f"servers/{server_id}/pin") if _SERVER_ID.match(server_id or "") else ""

    def remember_server(self, server_id: str, pin: str) -> None:
        if _SERVER_ID.match(server_id or ""):
            self._put(f"servers/{server_id}/pin", pin)

    def remember_addresses(self, server_id: str, name: str, lan_url: str = "", public_url: str = "") -> None:
        """Remember how to reach a server (M40): its name and its LAN and public addresses. Only called
        after a /health answer over a connection whose key matched this server's pin."""
        if not _SERVER_ID.match(server_id or ""):
            return
        if name:
            self._put(f"servers/{server_id}/name", name)
        if lan_url:
            self._put(f"servers/{server_id}/lanUrl", lan_url)
        if public_url:
            self._put(f"servers/{server_id}/publicUrl", public_url)

    def addresses(self, server_id: str) -> dict:
        """{"name", "lanUrl", "publicUrl"} remembered for a server id (empty strings when unknown)."""
        if not _SERVER_ID.match(server_id or ""):
            return {"name": "", "lanUrl": "", "publicUrl": ""}
        return {key: self._get(f"servers/{server_id}/{key}") for key in ("name", "lanUrl", "publicUrl")}

    def server_ids(self) -> list[str]:
        if self._settings is not None:
            self._settings.beginGroup("servers")
            ids = list(self._settings.childGroups())
            self._settings.endGroup()
        else:
            ids = sorted({k.split("/")[1] for k in self._memory if k.startswith("servers/")})
        return [i for i in ids if _SERVER_ID.match(i)]

    def known_pin_for_authority(self, authority: str) -> str:
        """The pin of a trusted server that announced this address (host:port) as one of its own, or "".
        A key offered at such an address may be accepted without a prompt only when it equals this pin."""
        wanted = authority.lower()
        for server_id in self.server_ids():
            pin = self.for_server(server_id)
            if not pin:
                continue
            remembered = self.addresses(server_id)
            for url in (remembered["lanUrl"], remembered["publicUrl"]):
                if url and authority_of(QUrl(url)) == wanted:
                    return pin
        return ""

    def forget_server(self, server_id: str) -> None:
        if _SERVER_ID.match(server_id or ""):
            self._remove(f"servers/{server_id}/pin")

    def forget(self, authority: str) -> None:
        """Forget the pin for an address and every server id that was using that same key."""
        pin = self.for_address(authority)
        self._remove(self._address_key(authority))
        if not pin:
            return
        if self._settings is not None:
            self._settings.beginGroup("servers")
            ids = list(self._settings.childGroups())
            self._settings.endGroup()
        else:
            ids = [k.split("/")[1] for k in self._memory if k.startswith("servers/")]
        for server_id in ids:
            if self.for_server(server_id) == pin:
                self._remove(f"servers/{server_id}/pin")
