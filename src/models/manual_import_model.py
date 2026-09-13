"""Manual import (M23): the queue of finished downloads The Den couldn't fully place --
GET /downloads/unmatched -- each with its leftover files and, for a season pack, that
season's episodes to assign one to."""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot

from models.base import JsonListModel


class ManualImportModel(JsonListModel):
    PATH = "/downloads/unmatched"
    FIELDS = [
        ("downloadId", "id"),
        ("releaseTitle", "release_title"),
        ("kind", "kind", ""),
        ("label", "label", ""),
        ("movieId", "movie_id", 0),
        ("episodeId", "episode_id", 0),
        ("files", "files", []),
        ("seasonEpisodes", "season_episodes", []),
    ]

    assigned = Signal(bool, str)
    imported = Signal(bool, str)

    @Slot(int, str, str, int)
    def assign(self, downloadId: int, file: str, kind: str, targetId: int) -> None:
        """Link one leftover file to a movie or episode by hand, with the normal Plex naming."""
        def on_done(status: int, body) -> None:
            if status == 200:
                self.assigned.emit(True, "Assigned")
            else:
                self.assigned.emit(False, self.api.error_message(status, body))
            self.refresh()

        self.api.request("POST", f"/downloads/{downloadId}/assign", {"file": file, "kind": kind, "id": targetId}, on_done)

    @Slot(int, str, str)
    def importAsIs(self, downloadId: int, file: str, root: str) -> None:
        """Link one leftover file into the library root under its own name, no title match."""
        def on_done(status: int, body) -> None:
            if status == 200:
                self.imported.emit(True, "Imported")
            else:
                self.imported.emit(False, self.api.error_message(status, body))
            self.refresh()

        self.api.request("POST", f"/downloads/{downloadId}/import-as-is", {"file": file, "root": root}, on_done)
