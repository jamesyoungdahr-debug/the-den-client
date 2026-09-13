from PySide6.QtCore import Slot

from models.base import JsonListModel


class ImportListsModel(JsonListModel):
    """Import lists (E1) -- /api/import-lists: auto-add movies/series from a TMDB list
    or a Plex watchlist on a schedule."""

    PATH = "/api/import-lists"
    FIELDS = [
        ("listId", "id"),
        ("name", "name"),
        ("kind", "kind"),
        ("config", "config", {}),
        ("listEnabled", "enabled", True),
        ("lastSyncedAt", "last_synced_at", None),
        ("lastResult", "last_result", None),
    ]

    @Slot(str, str, "QVariantMap", bool)
    def addList(self, name: str, kind: str, config: "QVariantMap", enabled: bool) -> None:
        payload = {"name": name.strip(), "kind": kind, "config": dict(config), "enabled": enabled}
        self._write("POST", self.PATH, payload=payload)

    @Slot(int, str, str, "QVariantMap", bool)
    def updateList(self, listId: int, name: str, kind: str, config: "QVariantMap", enabled: bool) -> None:
        payload = {"name": name.strip(), "kind": kind, "config": dict(config), "enabled": enabled}
        self._write("PUT", f"{self.PATH}/{listId}", payload=payload)

    @Slot(int)
    def deleteList(self, listId: int) -> None:
        self._write("DELETE", f"{self.PATH}/{listId}")

    @Slot(int)
    def syncList(self, listId: int) -> None:
        self._write("POST", f"{self.PATH}/{listId}/sync")