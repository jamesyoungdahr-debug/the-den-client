from PySide6.QtCore import Property, QUrl, Signal, Slot

from models.base import JsonListModel
from models.movie_model import plex_poster


class SeriesListModel(JsonListModel):
    """The TV library as people see it: The Den's series merged with what the Plex scan
    found -- GET /api/library/series. Plex-only entries have seriesId 0 (no episode list
    in The Den); plexSeasons is the number of seasons Plex has."""

    PATH = "/api/library/series"
    FIELDS = [
        ("seriesId", "id", 0),
        ("tvmazeId", "tvmaze_id", 0),
        ("tmdbId", "tmdb_id", 0),
        ("title", "title"),
        ("year", "year"),
        ("posterPath", "poster_path", ""),
        ("have", "have", 0),
        ("total", "total", 0),
        ("onPlex", "on_plex", False),
        ("plexSeasons", "plex_season_count", 0),
        ("source", "source", "den"),
        ("available", "available", False),
    ]

    statsChanged = Signal()
    plexCount = Property(int, lambda self: sum(1 for s in self._items if s.get("on_plex")), notify=statsChanged)

    def _set_items(self, items: list[dict]) -> None:
        super()._set_items(items)
        self.statsChanged.emit()

    @Slot()
    def refresh(self) -> None:
        self._fetch(self.PATH, transform=lambda items: [
            plex_poster(self.api, {**i, "plex_season_count": len(i.get("plex_seasons") or {})}) for i in items
        ])

    @Slot(int, str, str, str, str)
    def addSeries(self, tvmazeId: int, title: str, year: str, overview: str, posterPath: str) -> None:
        payload: dict = {"tvmaze_id": tvmazeId, "title": title}
        if year:
            payload["year"] = int(year)
        if overview:
            payload["overview"] = overview
        if posterPath:
            payload["poster_path"] = posterPath
        self._write("POST", "/series", payload)

    @Slot(int)
    def deleteSeries(self, seriesId: int) -> None:
        self._write("DELETE", f"/series/{seriesId}")


class SeriesSearchResultsModel(JsonListModel):
    """Ephemeral TVmaze search results (GET /series/search-tvmaze) for the add flow."""

    FIELDS = [
        ("tvmazeId", "tvmaze_id"),
        ("title", "title"),
        ("year", "year"),
        ("overview", "overview", ""),
        ("posterPath", "poster_path", ""),
    ]

    @Slot(str)
    def search(self, query: str) -> None:
        if not query.strip():
            self._set_items([])
            return
        self._fetch(f"/series/search-tvmaze?q={QUrl.toPercentEncoding(query).data().decode()}")

    @Slot()
    def clear(self) -> None:
        self._set_items([])
