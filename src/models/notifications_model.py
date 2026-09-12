from PySide6.QtCore import Property, Signal, Slot

from models.base import JsonListModel


class NotificationAgentsModel(JsonListModel):
    """Notification agents (M15) -- /api/notifications/agents plus the kinds and events catalogues."""

    PATH = "/api/notifications/agents"
    FIELDS = [
        ("agentId", "id"),
        ("name", "name"),
        ("kind", "kind"),
        ("events", "events", []),
        ("agentEnabled", "enabled", True),
        ("config", "config", {}),
        ("hasToken", "has_token", False),
        ("hasWebhookUrl", "has_webhook_url", False),
        ("hasBotToken", "has_bot_token", False),
        ("hasAppToken", "has_app_token", False),
        ("hasUserKey", "has_user_key", False),
    ]

    catalogueChanged = Signal()
    testResult = Signal(int, bool, str)  # agent id or 0 for a pre-save test, ok, message

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        self._kinds: list[dict] = []
        self._events: list[dict] = []

    kinds = Property("QVariantList", lambda self: self._kinds, notify=catalogueChanged)
    events = Property("QVariantList", lambda self: self._events, notify=catalogueChanged)

    @Slot()
    def loadCatalogue(self) -> None:
        def on_kinds_done(status: int, body) -> None:
            if status == 200:
                self._kinds = body if isinstance(body, list) else []
                self.catalogueChanged.emit()
            else:
                self.errorOccurred.emit(self.api.error_message(status, body))

        def on_events_done(status: int, body) -> None:
            if status == 200:
                self._events = body if isinstance(body, list) else []
                self.catalogueChanged.emit()
            else:
                self.errorOccurred.emit(self.api.error_message(status, body))

        self.api.request("GET", "/api/notifications/kinds", on_done=on_kinds_done)
        self.api.request("GET", "/api/notifications/events", on_done=on_events_done)

    @Slot(str, str, "QVariantMap", "QVariantList", bool)
    def addAgent(self, name: str, kind: str, config: "QVariantMap", events: "QVariantList", enabled: bool) -> None:
        payload = {"name": name.strip(), "kind": kind, "config": dict(config), "events": list(events), "enabled": enabled}
        self._write("POST", self.PATH, payload=payload)

    @Slot(int, str, str, "QVariantMap", "QVariantList", bool)
    def updateAgent(self, agentId: int, name: str, kind: str, config: "QVariantMap", events: "QVariantList", enabled: bool) -> None:
        payload = {"name": name.strip(), "kind": kind, "config": dict(config), "events": list(events), "enabled": enabled}
        self._write("PUT", f"{self.PATH}/{agentId}", payload=payload)

    @Slot(int)
    def deleteAgent(self, agentId: int) -> None:
        self._write("DELETE", f"{self.PATH}/{agentId}")

    @Slot(int)
    def testAgent(self, agentId: int) -> None:
        def on_done(status: int, body) -> None:
            message = "sent" if status == 200 else self.api.error_message(status, body)
            self.testResult.emit(agentId, status == 200, message)

        self.api.request("POST", f"{self.PATH}/{agentId}/test", on_done=on_done)

    @Slot(str, "QVariantMap")
    def testConfig(self, kind: str, config: "QVariantMap") -> None:
        payload = {"kind": kind, "config": dict(config)}

        def on_done(status: int, body) -> None:
            message = "sent" if status == 200 else self.api.error_message(status, body)
            self.testResult.emit(0, status == 200, message)

        self.api.request("POST", "/api/notifications/test", payload=payload, on_done=on_done)
