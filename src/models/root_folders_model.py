from PySide6.QtCore import Slot

from models.base import JsonListModel


class RootFoldersModel(JsonListModel):
    """Root folders (E2) -- /api/root-folders: named library folders per media type."""

    PATH = "/api/root-folders"
    FIELDS = [
        ("folderId", "id"),
        ("name", "name"),
        ("mediaType", "media_type"),
        ("path", "path"),
        ("isDefault", "is_default", False),
    ]

    @Slot(str, str, str, bool)
    def addFolder(self, name: str, mediaType: str, path: str, isDefault: bool) -> None:
        payload = {"name": name.strip(), "media_type": mediaType, "path": path.strip(), "is_default": isDefault}
        self._write("POST", self.PATH, payload=payload)

    @Slot(int, str, str, str, bool)
    def updateFolder(self, folderId: int, name: str, mediaType: str, path: str, isDefault: bool) -> None:
        payload = {"name": name.strip(), "media_type": mediaType, "path": path.strip(), "is_default": isDefault}
        self._write("PUT", f"{self.PATH}/{folderId}", payload=payload)

    @Slot(int)
    def deleteFolder(self, folderId: int) -> None:
        self._write("DELETE", f"{self.PATH}/{folderId}")