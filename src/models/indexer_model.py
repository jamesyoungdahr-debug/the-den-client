from PySide6.QtCore import Property, Signal, Slot

from models.base import JsonListModel


class IndexerListModel(JsonListModel):
    """Indexers -- GET/POST/DELETE /indexers and GET /indexers/{id}/test and GET /indexers/presets."""

    PATH = "/indexers"
    FIELDS = [
        ("indexerId", "id"),
        ("name", "name"),
        ("url", "url"),
        ("protocol", "protocol", "torznab"),
        ("implementation", "implementation", ""),
        ("preset", "preset", ""),
        ("indexerEnabled", "enabled", True),
    ]

    testResult = Signal(int, bool, str)  # indexer id, ok, message
    presetsChanged = Signal()

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        self._presets: list[dict] = []
        self._stats: dict = {}

    presets = Property("QVariantList", lambda self: self._presets, notify=presetsChanged)

    @Slot()
    def loadPresets(self) -> None:
        def on_done(status: int, body) -> None:
            if status == 200:
                self._presets = body if isinstance(body, list) else []
                self.presetsChanged.emit()
            else:
                self.errorOccurred.emit(self.api.error_message(status, body))

        self.api.request("GET", "/indexers/presets", on_done=on_done)

    statsChanged = Signal()
    stats = Property("QVariantMap", lambda self: self._stats, notify=statsChanged)

    @Slot()
    def loadStats(self) -> None:
        def on_done(status: int, body) -> None:
            if status == 200 and isinstance(body, list):
                self._stats = {str(row["indexer_id"]): row for row in body}
                self.statsChanged.emit()
            else:
                self.errorOccurred.emit(self.api.error_message(status, body))

        self.api.request("GET", "/indexers/stats", on_done=on_done)

    @Slot(int, bool)
    def setEnabled(self, indexerId: int, enabled: bool) -> None:
        payload = {"enabled": enabled}
        self._write("PATCH", f"/indexers/{indexerId}", payload)

    @Slot(str, str, str, str)
    def addIndexer(self, preset: str, name: str, url: str, apiKey: str) -> None:
        chosen = next((p for p in self._presets if p.get("slug") == preset), None)
        payload = {"name": name.strip(), "url": url.strip(), "enabled": True}
        if chosen:
            payload["preset"] = preset
            payload["implementation"] = chosen.get("implementation") or "torznab"
        else:
            payload["implementation"] = "torznab"
        payload["protocol"] = payload["implementation"] if payload["implementation"] in ("torznab", "newznab") else "native"
        if apiKey:
            payload["api_key"] = apiKey
        self._write("POST", "/indexers", payload)

    @Slot(int)
    def deleteIndexer(self, indexerId: int) -> None:
        self._write("DELETE", f"/indexers/{indexerId}")

    @Slot(int)
    def testIndexer(self, indexerId: int) -> None:
        def on_done(status: int, body) -> None:
            if status == 200:
                ok = bool(body.get("ok", True)) if isinstance(body, dict) else True
                message = body.get("message") or body.get("detail") or "reachable" if isinstance(body, dict) else "reachable"
                self.testResult.emit(indexerId, ok, str(message))
            else:
                self.testResult.emit(indexerId, False, self.api.error_message(status, body))

        self.api.request("GET", f"/indexers/{indexerId}/test", on_done=on_done)
