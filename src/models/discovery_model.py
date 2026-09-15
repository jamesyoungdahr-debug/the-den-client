"""DiscoveredServersModel (M40): A Qt list model of The Den servers found on the LAN
through mDNS/DNS-SD (service type "_theden._tcp.local."). TXT properties advertised by
each server are name, id (32 lowercase hex characters), api, https ("1" or "0") and, when
https is "1", pin (a string like "sha256/..."). The model is only a list for the login
page to pick from: it never trusts pins; the pin is kept only so the page can show it for
comparison."""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    Signal,
    Slot,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public pure helper – tests can call this without zeroconf on the classpath.
# ---------------------------------------------------------------------------

def parse_service(
    properties: dict,
    addresses: list[str],
    port: int,
    service_name: str,
) -> dict | None:
    """Parse raw mDNS TXT/record data into a server row dict, or return *None*.

    Parameters
    ----------
    properties : dict
        May have bytes or str keys and values (values may be ``None``).  Bytes are
        decoded as UTF-8 with ``errors="replace"``.
    addresses : list[str]
        IP addresses advertised by the service.
    port : int
        TCP port from the DNS record.
    service_name : str
        The full mDNS name (e.g. "My Server._theden._tcp.local.").

    Returns
    -------
    dict | None
        A row dict with keys ``name``, ``serverId``, ``host``, ``port``, ``https``,
        ``pin``, ``url``, ``serviceName`` – or *None* when the record is invalid.
    """

    # ---- decode bytes --------------------------------------------------------
    decoded: dict[str, str | None] = {}
    for key, value in properties.items():
        k = key.decode("utf-8", errors="replace") if isinstance(key, bytes) else key
        v = (value.decode("utf-8", errors="replace")
             if isinstance(value, bytes) and value is not None else value)
        decoded[k] = v

    # ---- server id -----------------------------------------------------------
    server_id: str | None = decoded.get("id")
    if server_id is None or not re.fullmatch(r"[0-9a-f]{32}", server_id):
        return None

    # ---- host (first valid non-link-local, non-loopback IPv4) ----------------
    host: str | None = None
    for addr in addresses:
        try:
            ip = ipaddress.IPv4Address(addr)
        except (ipaddress.AddressValueError, ValueError):
            continue
        if ip.is_loopback or ip.is_link_local:
            continue
        host = str(ip)
        break
    if host is None:
        return None

    # ---- port ----------------------------------------------------------------
    if not (1 <= port <= 65535):
        return None

    # ---- https / pin ---------------------------------------------------------
    https: bool = decoded.get("https") == "1"
    pin: str = (decoded.get("pin") or "") if https else ""

    # ---- name ----------------------------------------------------------------
    name = ""
    raw_name: str | None = decoded.get("name")
    if raw_name is not None and isinstance(raw_name, str):
        name = raw_name.strip()
    suffix = "._theden._tcp.local."
    if not name:
        name = (service_name[:-len(suffix)] if service_name.endswith(suffix)
                else service_name) or "The Den"

    # ---- url -----------------------------------------------------------------
    scheme = "https" if https else "http"
    url = f"{scheme}://{host}:{port}"

    return {
        "name": name,
        "serverId": server_id,
        "host": host,
        "port": port,
        "https": https,
        "pin": pin,
        "url": url,
        "serviceName": service_name,
    }


# ---------------------------------------------------------------------------
# QAbstractListModel
# ---------------------------------------------------------------------------

class DiscoveredServersModel(QAbstractListModel):
    """List model of The Den servers discovered via mDNS/DNS-SD.

    TXT pins are shown for comparison only and **never trusted** by this model;
    the login page is responsible for any pin verification it chooses to perform.
    """

    # ---- role constants ------------------------------------------------------
    NameRole = Qt.ItemDataRole.UserRole + 1
    ServerIdRole = Qt.ItemDataRole.UserRole + 2
    HostRole = Qt.ItemDataRole.UserRole + 3
    PortRole = Qt.ItemDataRole.UserRole + 4
    HttpsRole = Qt.ItemDataRole.UserRole + 5
    PinRole = Qt.ItemDataRole.UserRole + 6
    UrlRole = Qt.ItemDataRole.UserRole + 7

    # ---- QML signals ---------------------------------------------------------
    countChanged = Signal()
    availableChanged = Signal()
    browsingChanged = Signal()

    # Internal signals – zeroconf callbacks run on its own thread, so we
    # cross-thread into the Qt event loop with QueuedConnection.
    _serviceFound = Signal(dict)
    _serviceLost = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        self._rows: list[dict] = []  # sorted by name (case-insensitive)
        self._available = True
        self._browsing = False

        self._serviceFound.connect(self._on_found, type=Qt.ConnectionType.QueuedConnection)
        self._serviceLost.connect(self._on_lost, type=Qt.ConnectionType.QueuedConnection)

    # ---- roleNames -----------------------------------------------------------
    def roleNames(self) -> dict[int, bytes]:
        return {
            self.NameRole: b"name",
            self.ServerIdRole: b"serverId",
            self.HostRole: b"host",
            self.PortRole: b"port",
            self.HttpsRole: b"https",
            self.PinRole: b"pin",
            self.UrlRole: b"url",
        }

    # ---- rowCount / data -----------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self._rows)
        return 0

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        row_dict = self._rows[index.row()]
        role_map = {
            self.NameRole: "name",
            self.ServerIdRole: "serverId",
            self.HostRole: "host",
            self.PortRole: "port",
            self.HttpsRole: "https",
            self.PinRole: "pin",
            self.UrlRole: "url",
        }
        key = role_map.get(role)
        if key is not None:
            return row_dict.get(key)
        return None

    # ---- QML properties ------------------------------------------------------
    count = Property(int, lambda self: len(self._rows), notify=countChanged)
    available = Property(bool, lambda self: self._available, notify=availableChanged)
    browsing = Property(bool, lambda self: self._browsing, notify=browsingChanged)

    # ---- start / stop --------------------------------------------------------
    @Slot()
    def start(self) -> None:
        """Begin mDNS browsing for The Den servers."""
        if self._browsing:
            return

        try:
            from zeroconf import IPVersion, ServiceBrowser, Zeroconf  # noqa: F401

            self._zc = Zeroconf(ip_version=IPVersion.V4Only)
            self._browser = ServiceBrowser(
                self._zc, "_theden._tcp.local.", handlers=[self._on_state_change]
            )
            self._browsing = True
            self.browsingChanged.emit()
        except Exception as exc:  # noqa: BLE001 – zeroconf may be missing entirely
            logger.warning("Failed to start mDNS browsing: %s", exc)
            self._available = False
            self.availableChanged.emit()
            self._browsing = False
            self.browsingChanged.emit()

    @Slot()
    def stop(self) -> None:
        """Stop browsing and clear all discovered servers."""
        if hasattr(self, "_browser"):
            try:
                self._browser.cancel()
            except Exception:  # noqa: BLE001
                pass
        if hasattr(self, "_zc"):
            try:
                self._zc.close()
            except Exception:  # noqa: BLE001
                pass

        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()
        self.countChanged.emit()

        self._browsing = False
        self.browsingChanged.emit()

    # ---- zeroconf callback (runs on the zeroconf thread) ---------------------
    def _on_state_change(
        self,
        zeroconf: Any,
        service_type: str,
        name: str,
        state_change: Any,
    ) -> None:
        """Called by zeroconf on its own thread – only emit signals here."""
        try:
            from zeroconf import ServiceStateChange
        except ImportError:
            return

        if state_change in (ServiceStateChange.Added, ServiceStateChange.Updated):
            info = zeroconf.get_service_info(service_type, name, timeout=3000)
            if info is None:
                return
            row = parse_service(
                properties=info.properties or {},
                addresses=info.parsed_addresses(),
                port=info.port or 0,
                service_name=name,
            )
            if row is not None:
                self._serviceFound.emit(row)

        elif state_change == ServiceStateChange.Removed:
            self._serviceLost.emit(name)

    # ---- slots (run on the Qt thread via QueuedConnection) -------------------
    @Slot(dict)
    def _on_found(self, row: dict) -> None:
        """Insert or replace a discovered server row."""
        # Check for existing entry with same serverId
        existing_idx = -1
        for i, r in enumerate(self._rows):
            if r["serverId"] == row["serverId"]:
                existing_idx = i
                break

        count_before = len(self._rows)

        if existing_idx >= 0:
            # Replace in place – keep sort order (name may have changed, so re-sort)
            self.layoutAboutToBeChanged.emit()
            self._rows[existing_idx] = row
            self._sort_rows()
            self.layoutChanged.emit()
        else:
            # Insert keeping rows sorted by name (case-insensitive)
            import bisect
            key = row["name"].lower()
            keys_lower = [r["name"].lower() for r in self._rows]
            insert_pos = bisect.bisect_left(keys_lower, key)
            self.beginInsertRows(QModelIndex(), insert_pos, insert_pos)
            self._rows.insert(insert_pos, row)
            self.endInsertRows()

        if len(self._rows) != count_before:
            self.countChanged.emit()

    @Slot(str)
    def _on_lost(self, service_name: str) -> None:
        """Remove every row whose serviceName matches the lost service."""
        indices_to_remove = [
            i for i, r in enumerate(self._rows) if r["serviceName"] == service_name
        ]
        if not indices_to_remove:
            return

        count_before = len(self._rows)

        # Remove from highest index to lowest so positions stay valid
        for idx in sorted(indices_to_remove, reverse=True):
            self.beginRemoveRows(QModelIndex(), idx, idx)
            self._rows.pop(idx)
            self.endRemoveRows()

        if len(self._rows) != count_before:
            self.countChanged.emit()

    # ---- helpers -------------------------------------------------------------
    def _sort_rows(self) -> None:
        """Re-sort the internal list by name (case-insensitive)."""
        self._rows.sort(key=lambda r: r["name"].lower())

    @Slot(int, result="QVariantMap")
    def get(self, row: int) -> dict:
        """Return the full row dict (without serviceName) for QML access."""
        if 0 <= row < len(self._rows):
            d = dict(self._rows[row])
            d.pop("serviceName", None)
            return d
        return {}
