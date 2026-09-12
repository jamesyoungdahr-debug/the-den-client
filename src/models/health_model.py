from PySide6.QtCore import Property, Signal, Slot

from models.base import JsonRecord


class HealthModel(JsonRecord):
    """Server health (M16) -- GET /health; `checks` is the list of open issues."""

    checksChanged = Signal()

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        self.dataChanged.connect(self.checksChanged)

    @Property("QVariantList", notify=checksChanged)
    def checks(self):
        return list(self._data.get("checks") or [])

    @Property(int, notify=checksChanged)
    def count(self):
        return len(self.checks)

    @Property(bool, notify=checksChanged)
    def hasErrors(self):
        return any(check.get("level") == "error" for check in self.checks)

    @Slot()
    def refresh(self):
        self._fetch("/health")
