"""The one connection to a running The Den backend: base URL, the signed-in account and
its API token, and the HTTP helper every model goes through.

Sign-in (U4): a local username/password goes to POST /api/auth/login, which starts a
cookie session; the client then asks POST /api/auth/token for a personal API token and
keeps only that (in QSettings), sending it as X-Api-Key from then on -- no password is
stored. "Sign in with Plex" uses the backend's PIN flow: POST /api/auth/plex/pin gives a
code and a plex.tv URL to open in the system browser; the client polls POST /api/auth/plex
until plex.tv reports the PIN claimed (202 while waiting). Sign-in is always required, and
the server answers nothing but /health until its web setup is finished (M33).

HTTPS (M40): a server that listens on the LAN serves HTTPS with a self-signed certificate.
The first connection shows the key's pin and asks the person to trust it; after that only
that key is accepted (see tls_pins.py). The addresses a trusted server announces over a
pinned connection are remembered, so the app can switch between the LAN and public address."""

from __future__ import annotations

import json
import socket
from typing import Callable

from PySide6.QtCore import Property, QObject, QSettings, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest, QSslError

try:
    from tls_pins import PinStore, authority_of, is_loopback_host, pin_for_der
except ImportError:  # imported as part of a package
    from .tls_pins import PinStore, authority_of, is_loopback_host, pin_for_der

JSON = "application/json"
Callback = Callable[[int, object], None]  # (http status or -1, parsed body or error string)

# TLS errors a pinned self-signed certificate may have. Anything else (expired, not yet valid,
# revoked, a bad signature) fails the connection even when the key matches the pin (M40).
PINNABLE_SSL_ERRORS = frozenset({
    QSslError.SslError.SelfSignedCertificate,
    QSslError.SslError.SelfSignedCertificateInChain,
    QSslError.SslError.HostNameMismatch,
    QSslError.SslError.UnableToGetLocalIssuerCertificate,
    QSslError.SslError.UnableToVerifyFirstCertificate,
    QSslError.SslError.CertificateUntrusted,
})


class ApiClient(QObject):
    baseUrlChanged = Signal()
    connectedChanged = Signal()
    statusTextChanged = Signal()
    sessionChanged = Signal()
    busyChanged = Signal()
    plexPinChanged = Signal()
    pinPromptChanged = Signal()
    loginFailed = Signal(str)

    def __init__(self, base_url: str | None = None, api_token: str | None = None, parent=None, persist: bool = True,
                 pins: PinStore | None = None):
        super().__init__(parent)
        self._settings = QSettings("the-den", "client") if persist else None
        self._base_url = base_url or (self._settings.value("server/baseUrl", "http://127.0.0.1:40204") if self._settings else "http://127.0.0.1:40204")
        self._api_token = api_token if api_token is not None else (self._settings.value("server/apiToken", "") if self._settings else "")
        self._connected = False
        self._status_text = "Not connected"
        self._busy = False
        self._me: dict = {}
        self._server: dict = {}
        self._plex_pin: dict = {}
        self._plex_timer = QTimer(self)
        self._plex_timer.setInterval(2500)
        self._plex_timer.timeout.connect(self._poll_plex)
        self._pins = pins if pins is not None else PinStore(self._settings)
        self._pending: dict = {}  # {"pin", "authority", "url"}: a certificate waiting for the person to trust it
        self._pin_problem = ""
        self._conflict_server_id = ""
        self._manager = QNetworkAccessManager(self)
        self._manager.sslErrors.connect(self._on_ssl_errors)
        self._manager.encrypted.connect(self._on_encrypted)
        self._request_seq = 0

    # ---- properties ----------------------------------------------------------------

    def _get_base_url(self) -> str:
        return self._base_url

    def _set_base_url(self, value: str) -> None:
        value = value.strip().rstrip("/")
        if value and value != self._base_url:
            self._base_url = value
            if self._settings:
                self._settings.setValue("server/baseUrl", value)
            self.baseUrlChanged.emit()

    baseUrl = Property(str, _get_base_url, _set_base_url, notify=baseUrlChanged)

    def _get_api_token(self) -> str:
        return self._api_token

    def _set_api_token(self, value: str) -> None:
        if value != self._api_token:
            self._api_token = value
            if self._settings:
                self._settings.setValue("server/apiToken", value)
            self.sessionChanged.emit()

    apiToken = Property(str, _get_api_token, _set_api_token, notify=sessionChanged)
    hasToken = Property(bool, lambda self: bool(self._api_token), notify=sessionChanged)

    connected = Property(bool, lambda self: self._connected, notify=connectedChanged)
    statusText = Property(str, lambda self: self._status_text, notify=statusTextChanged)
    busy = Property(bool, lambda self: self._busy, notify=busyChanged)

    # Who we are, per GET /api/auth/me
    signedIn = Property(bool, lambda self: bool(self._me), notify=sessionChanged)
    isAdmin = Property(bool, lambda self: bool(self._me.get("is_admin")), notify=sessionChanged)
    username = Property(str, lambda self: self._me.get("username") or "", notify=sessionChanged)
    userInitial = Property(str, lambda self: (self._me.get("username") or "?")[:1].upper(), notify=sessionChanged)
    quota = Property("QVariantMap", lambda self: self._me.get("quota") or {}, notify=sessionChanged)
    me = Property("QVariantMap", lambda self: dict(self._me), notify=sessionChanged)

    # Plex PIN flow state for the login page
    plexCode = Property(str, lambda self: self._plex_pin.get("code", ""), notify=plexPinChanged)
    plexAuthUrl = Property(str, lambda self: self._plex_pin.get("auth_url", ""), notify=plexPinChanged)
    plexWaiting = Property(bool, lambda self: self._plex_timer.isActive(), notify=plexPinChanged)

    # Certificate trust (M40): a server key waiting for the person to trust it, or why a connection was refused
    pendingPin = Property(str, lambda self: self._pending.get("pin", ""), notify=pinPromptChanged)
    pendingServer = Property(str, lambda self: self._pending.get("authority", ""), notify=pinPromptChanged)
    pinProblem = Property(str, lambda self: self._pin_problem, notify=pinPromptChanged)

    # ---- HTTP helper -----------------------------------------------------------------

    def request(self, method: str, path: str, payload: dict | None = None, on_done: Callback | None = None) -> QNetworkReply:
        """Fire an HTTP request and hand the parsed JSON (or an error string) to on_done.
        Every model uses this so the API token and base URL live in one place."""
        url = QUrl(f"{self._base_url}{path}")
        req = QNetworkRequest(url)
        req.setTransferTimeout(15000)
        if self._api_token:
            req.setRawHeader(b"X-Api-Key", self._api_token.encode())
        body = b""
        if payload is not None:
            req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, JSON)
            body = json.dumps(payload).encode()
        method = method.upper()
        if method == "GET":
            reply = self._manager.get(req)
        elif method == "POST":
            reply = self._manager.post(req, body)
        elif method == "DELETE":
            reply = self._manager.deleteResource(req)
        elif method == "PATCH":
            reply = self._manager.sendCustomRequest(req, b"PATCH", body)
        else:
            raise ValueError(method)
        if on_done is not None:
            reply.finished.connect(lambda: self._finish(reply, on_done))
        else:
            reply.finished.connect(reply.deleteLater)
        return reply

    @staticmethod
    def _finish(reply: QNetworkReply, on_done: Callback) -> None:
        reply.deleteLater()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        raw = bytes(reply.readAll().data())
        if status is None:
            on_done(-1, reply.errorString())
            return
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw.decode(errors="replace")
        on_done(int(status), parsed)

    @staticmethod
    def error_message(status: int, body) -> str:
        if status == -1:
            return str(body)
        if isinstance(body, dict) and body.get("detail"):
            detail = body["detail"]
            return detail if isinstance(detail, str) else json.dumps(detail)
        return f"HTTP {status}"

    def _set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.busyChanged.emit()

    # ---- certificate pinning (M40) -----------------------------------------------------

    def _on_ssl_errors(self, reply: QNetworkReply, errors: list) -> None:
        """A certificate the system doesn't trust (the server's self-signed one) is accepted only when
        its key matches the pin stored for this address, or the pin of the trusted server that
        announced this address, and its only problems are ones a pinned self-signed certificate
        has. A key this app hasn't seen waits for the person to trust it."""
        authority = authority_of(reply.url())
        try:
            pin = pin_for_der(bytes(reply.sslConfiguration().peerCertificate().toDer()))
        except Exception:
            self._set_pin_problem(f"{authority} sent a certificate this app couldn't read.")
            return
        unusable = sorted({e.errorString() for e in errors if e.error() not in PINNABLE_SSL_ERRORS})
        if unusable:
            self._set_pin_problem(f"{authority}'s certificate can't be used: {'; '.join(unusable)}.")
            return
        stored = self._pins.for_address(authority)
        if stored:
            if stored == pin:
                reply.ignoreSslErrors(errors)
            else:
                self._set_pin_problem(
                    f"The certificate key at {authority} isn't the one you trusted, so the connection was refused. "
                    "If the server's key really changed, forget the old key and connect again."
                )
            return
        announced = self._pins.known_pin_for_authority(authority)
        if announced:
            if announced == pin:
                self._pins.trust_address(authority, pin)
                reply.ignoreSslErrors(errors)
            else:
                self._set_pin_problem(
                    f"The certificate key at {authority} isn't the key of the server that announced this address, "
                    "so the connection was refused."
                )
            return
        if not self._pending:
            self._pending = {"pin": pin, "authority": authority, "url": f"https://{authority}"}
            self.pinPromptChanged.emit()

    def _on_encrypted(self, reply: QNetworkReply) -> None:
        """After every TLS handshake: once a pin is stored for an address, only that key is accepted,
        even when the system itself trusts the certificate."""
        authority = authority_of(reply.url())
        stored = self._pins.for_address(authority)
        if not stored:
            return
        try:
            pin = pin_for_der(bytes(reply.sslConfiguration().peerCertificate().toDer()))
        except Exception:
            pin = ""
        if pin != stored:
            reply.abort()
            self._set_pin_problem(f"The certificate key at {authority} isn't the one you trusted, so the connection was refused.")

    def _set_pin_problem(self, message: str) -> None:
        if message != self._pin_problem:
            self._pin_problem = message
            self.pinPromptChanged.emit()

    def _server_pin_problem(self, body: dict) -> str:
        """After /health answered over HTTPS: the key this connection used must be the key the server
        reports, and a server id seen before must still use the same key. Returns why not, or ""."""
        authority = authority_of(QUrl(self._base_url))
        used = self._pins.for_address(authority)
        if not used:
            return ""  # a certificate the system trusts; nothing is pinned for this address
        reported = str(body.get("tls_pin") or "")
        if reported and reported != used:
            return (f"{authority} reports a different certificate key than the one this connection used, so something "
                    "may be intercepting the connection. Refusing to connect.")
        server_id = str(body.get("server_id") or "")
        known = self._pins.for_server(server_id)
        if known and known != used:
            self._conflict_server_id = server_id
            name = body.get("server_name") or server_id
            return f"{name} used a different certificate key before. Refusing to connect; forget the old key if the server really changed."
        if server_id and not known:
            self._pins.remember_server(server_id, used)
        return ""

    def _remember_server(self, body: dict) -> None:
        """After a pinned HTTPS connect: remember this address and the public address the server
        announces, so a failed connection can try the other one."""
        base = QUrl(self._base_url)
        server_id = str(body.get("server_id") or "")
        if base.scheme() != "https" or not self._pins.for_server(server_id):
            return
        port = base.port(443)
        public_host = str(body.get("public_host") or "").strip().lower().rstrip(".")
        if public_host:
            public_url = f"https://[{public_host}]:{port}" if ":" in public_host else f"https://{public_host}:{port}"
        else:
            public_url = ""
        on_public = bool(public_host) and base.host().lower() == public_host
        self._pins.remember_addresses(server_id, str(body.get("server_name") or ""),
                                      lan_url="" if on_public else self._base_url, public_url=public_url)

    def _other_remembered_url(self) -> str:
        """The other address remembered for the server behind the current address, or ""."""
        authority = authority_of(QUrl(self._base_url))
        for server_id in self._pins.server_ids():
            remembered = self._pins.addresses(server_id)
            lan, public = remembered["lanUrl"], remembered["publicUrl"]
            if lan and public and authority_of(QUrl(lan)) == authority:
                return public
            if lan and public and authority_of(QUrl(public)) == authority:
                return lan
        return ""

    @Slot()
    def trustPendingPin(self) -> None:
        """The person compared the pin with Settings > Remote access on the server and trusts it."""
        pending = self._pending
        if not pending:
            return
        self._pins.trust_address(pending["authority"], pending["pin"])
        self._pending = {}
        self.pinPromptChanged.emit()
        base = QUrl(self._base_url)
        if base.scheme() != "https" or authority_of(base) != pending["authority"]:
            self._set_base_url(pending["url"])
        self.checkHealth()

    @Slot()
    def rejectPendingPin(self) -> None:
        if not self._pending:
            return
        self._pending = {}
        self.pinPromptChanged.emit()
        self._status_text = "Not connected: the server's certificate wasn't trusted."
        self.statusTextChanged.emit()

    @Slot()
    def forgetPin(self) -> None:
        """Forget the trusted key for the current server address (and a server id that was refused for
        a key change), so the next connection asks again."""
        self._pins.forget(authority_of(QUrl(self._base_url)))
        if self._conflict_server_id:
            self._pins.forget_server(self._conflict_server_id)
            self._conflict_server_id = ""
        self._set_pin_problem("")

    # ---- connect / session -------------------------------------------------------------

    @Slot()
    def checkHealth(self) -> None:
        """Reach the server, then find out who we are. Kept under its old name so the
        original M0 flow (and its tests) still work."""
        self._status_text = "Checking..."
        self.statusTextChanged.emit()
        self._request_seq += 1
        seq = self._request_seq
        self._set_busy(True)
        if self._pending or self._pin_problem:
            self._pending = {}
            self._pin_problem = ""
            self.pinPromptChanged.emit()

        def on_health(status: int, body) -> None:
            if seq != self._request_seq:
                return  # superseded by a newer attempt
            if status == 200 and isinstance(body, dict) and body.get("status") == "ok" and body.get("setup_complete", True) is False:
                self._server = {}
                self._connected = False
                self._me = {}
                self._status_text = "This server hasn't been set up yet. Finish setup in its web UI, then connect again."
                self._set_busy(False)
                self.connectedChanged.emit()
                self.statusTextChanged.emit()
                self.sessionChanged.emit()
            elif status == 200 and isinstance(body, dict) and body.get("status") == "ok":
                problem = self._server_pin_problem(body) if QUrl(self._base_url).scheme() == "https" else ""
                if problem:
                    self._set_pin_problem(problem)
                    self._health_failed(-1, problem)
                    return
                self._remember_server(body)
                self._server = body
                self._connected = True
                self._status_text = "Connected"
                self.connectedChanged.emit()
                self.statusTextChanged.emit()
                self.refreshSession()
            elif status == -1 and (self._pending or self._pin_problem):
                self._certificate_stop(status, body)
            else:
                alternatives = self._fallback_urls() if status == -1 else []
                if alternatives:
                    self._probe_alternatives(alternatives, seq, status, body)
                else:
                    self._health_failed(status, body)

        self.request("GET", "/health", on_done=on_health)

    def _certificate_stop(self, status: int, body) -> None:
        """A certificate stopped the connection: ask the person to trust a new key, or say why it was refused."""
        if not self._pending:
            self._health_failed(-1, self._pin_problem or self.error_message(status, body))
            return
        self._server = {}
        self._connected = False
        self._me = {}
        self._status_text = (f"{self._pending['authority']} has a certificate this app hasn't seen before. "
                             "Compare its pin with Settings > Remote access on the server, then trust it.")
        self._set_busy(False)
        self.connectedChanged.emit()
        self.statusTextChanged.emit()
        self.sessionChanged.emit()

    def _health_failed(self, status: int, body) -> None:
        self._server = {}
        self._connected = False
        self._me = {}
        self._status_text = "Connection failed: " + (self.error_message(status, body) if status != 200 else f"unexpected response: {body}")
        self._set_busy(False)
        self.connectedChanged.emit()
        self.statusTextChanged.emit()
        self.sessionChanged.emit()

    def _moved_url(self) -> str:
        """M34 moved the server's default port from 8686 to 40204. For a saved address still on
        8686, return the same host on 40204; otherwise "". Only tried after a network failure,
        and the probe sends no token."""
        url = QUrl(self._base_url)
        if url.port() == 8686 and url.host():
            url.setPort(40204)
            return url.toString().rstrip("/")
        return ""

    @staticmethod
    def _https_of(base: str) -> str:
        """The same address over HTTPS, for an http address that isn't this machine; otherwise ""."""
        url = QUrl(base)
        if url.scheme() != "http" or not url.host() or is_loopback_host(url.host()):
            return ""
        if url.port() == -1:
            url.setPort(80)  # keep the port that was typed, even the default one
        url.setScheme("https")
        return url.toString().rstrip("/")

    def _fallback_urls(self) -> list[str]:
        """Addresses to try after a network failure, in order: the same address over HTTPS (a server
        listening on the LAN serves HTTPS only since 0.8.1c), the other address remembered for this
        server (LAN or public), the port moved from 8686, and that moved address over HTTPS."""
        moved = self._moved_url()
        candidates = (self._https_of(self._base_url), self._other_remembered_url(), moved,
                      self._https_of(moved) if moved else "")
        out: list[str] = []
        for candidate in candidates:
            if candidate and candidate != self._base_url and candidate not in out:
                out.append(candidate)
        return out

    def _probe_alternatives(self, urls: list[str], seq: int, status: int, body) -> None:
        """The saved address failed. Probe each alternative's /health (without the token) and switch
        for good to the first that answers. A certificate this app hasn't seen stops the search and
        asks the person to trust it; if nothing answers, report the original failure."""
        candidate, rest = urls[0], urls[1:]
        req = QNetworkRequest(QUrl(f"{candidate}/health"))
        req.setTransferTimeout(15000)
        reply = self._manager.get(req)

        def on_probe(probe_status: int, probe_body) -> None:
            if seq != self._request_seq:
                return  # superseded by a newer attempt
            if probe_status == 200 and isinstance(probe_body, dict) and probe_body.get("status") == "ok":
                self._set_base_url(candidate)
                self.checkHealth()
            elif probe_status == -1 and (self._pending or self._pin_problem):
                self._certificate_stop(status, body)
            elif rest:
                self._probe_alternatives(rest, seq, status, body)
            else:
                self._health_failed(status, body)

        reply.finished.connect(lambda: self._finish(reply, on_probe))

    @Slot()
    def refreshSession(self) -> None:
        def on_me(status: int, body) -> None:
            self._set_busy(False)
            if status == 200 and isinstance(body, dict):
                self._me = body
            else:
                self._me = {}
                if status == 401 and self._api_token:
                    # The stored token is no longer valid (regenerated on the web, user deleted).
                    self._api_token = ""
                    if self._settings:
                        self._settings.setValue("server/apiToken", "")
            self.sessionChanged.emit()

        self.request("GET", "/api/auth/me", on_done=on_me)

    @Slot(str, str)
    def login(self, username: str, password: str) -> None:
        """Local account: session cookie first, then swap it for a personal API token."""
        self._set_busy(True)

        def on_login(status: int, body) -> None:
            if status != 200:
                self._set_busy(False)
                self.loginFailed.emit(self.error_message(status, body) if status != 401 else "That username and password don't match.")
                return
            self._fetch_token()

        self.request("POST", "/api/auth/login", {"username": username, "password": password}, on_login)

    def _fetch_token(self) -> None:
        def on_token(status: int, body) -> None:
            if status == 200 and isinstance(body, dict) and body.get("api_token"):
                self._set_api_token(body["api_token"])
                self.refreshSession()
            else:
                self._set_busy(False)
                self.loginFailed.emit("Signed in, but couldn't get an API token: " + self.error_message(status, body))

        # Each sign-in is its own device on the server (M37), named after this computer.
        self.request("POST", "/api/auth/token", {"name": socket.gethostname() or "KDE desktop", "platform": "kde"}, on_done=on_token)

    @Slot()
    def startPlexLogin(self) -> None:
        self._set_busy(True)

        def on_pin(status: int, body) -> None:
            if status != 200 or not isinstance(body, dict):
                self._set_busy(False)
                self.loginFailed.emit("Couldn't start Plex sign-in: " + self.error_message(status, body))
                return
            self._plex_pin = body
            self.plexPinChanged.emit()
            QDesktopServices.openUrl(QUrl(body["auth_url"]))
            self._plex_timer.start()
            self.plexPinChanged.emit()
            self._set_busy(False)

        self.request("POST", "/api/auth/plex/pin", on_done=on_pin)

    @Slot()
    def openPlexAuth(self) -> None:
        if self._plex_pin.get("auth_url"):
            QDesktopServices.openUrl(QUrl(self._plex_pin["auth_url"]))

    @Slot()
    def cancelPlexLogin(self) -> None:
        self._plex_timer.stop()
        self._plex_pin = {}
        self.plexPinChanged.emit()

    def _poll_plex(self) -> None:
        pin = self._plex_pin
        if not pin:
            self._plex_timer.stop()
            return

        def on_poll(status: int, body) -> None:
            if not self._plex_timer.isActive():
                return
            if status == 202:
                return  # not claimed yet; keep polling
            self._plex_timer.stop()
            self._plex_pin = {}
            self.plexPinChanged.emit()
            if status == 200:
                self._fetch_token()
            else:
                self.loginFailed.emit("Plex sign-in refused: " + self.error_message(status, body))

        self.request("POST", "/api/auth/plex", {"pin_id": pin["pin_id"], "code": pin["code"]}, on_poll)

    @Slot()
    def logout(self) -> None:
        self.cancelPlexLogin()
        self.request("POST", "/api/auth/logout")
        self._set_api_token("")
        self._me = {}
        self.sessionChanged.emit()
