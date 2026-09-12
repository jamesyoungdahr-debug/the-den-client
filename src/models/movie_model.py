from PySide6.QtCore import Property, QUrl, Signal, Slot

from models.base import JsonListModel


def plex_poster(api, item: dict) -> dict:
    """Plex-only entries carry a poster path on The Den's own thumb proxy. QML's Image can't
    send the API token as a header, so make it an absolute URL with the token as a query
    parameter (the proxy accepts that form for exactly this reason)."""
    path = item.get("poster_path") or ""
    if path.startswith("/api/plex/thumb/"):
        token = api.apiToken
        item = {**item, "poster_path": f"{api.baseUrl}{path}" + (f"?api_key={token}" if token else "")}
    return item


class MovieListModel(JsonListModel):
    """The movie library as people see it: The Den's rows merged with what the Plex scan
    found -- GET /api/library/movies. `source` is den | plex | both; Plex-only entries
    have movieId 0 and can't be searched or removed here."""

    PATH = "/api/library/movies"
    FIELDS = [
        ("movieId", "id", 0),
        ("tmdbId", "tmdb_id", 0),
        ("title", "title"),
        ("year", "year"),
        ("posterPath", "poster_path", ""),
        ("hasFile", "has_file", False),
        ("downloading", "downloading", False),
        ("onPlex", "on_plex", False),
        ("source", "source", "den"),
        ("available", "available", False),
    ]

    statsChanged = Signal()
    plexCount = Property(int, lambda self: sum(1 for m in self._items if m.get("on_plex")), notify=statsChanged)
    denCount = Property(int, lambda self: sum(1 for m in self._items if m.get("id")), notify=statsChanged)
    availableCount = Property(int, lambda self: sum(1 for m in self._items if m.get("available")), notify=statsChanged)
    trackedCount = Property(int, lambda self: sum(1 for m in self._items if m.get("id")), notify=statsChanged)

    def _set_items(self, items: list[dict]) -> None:
        super()._set_items(items)
        self.statsChanged.emit()

    @Slot()
    def refresh(self) -> None:
        self._fetch(self.PATH, transform=lambda items: [plex_poster(self.api, i) for i in items])

    @Slot(int, str, str, str, str)
    def addMovie(self, tmdbId: int, title: str, year: str, overview: str, posterPath: str) -> None:
        payload: dict = {"tmdb_id": tmdbId, "title": title}
        if year:
            payload["year"] = int(year)
        if overview:
            payload["overview"] = overview
        if posterPath and "/api/plex/thumb/" not in posterPath:
            payload["poster_path"] = posterPath
        self._write("POST", "/movies", payload)

    @Slot(int)
    def deleteMovie(self, movieId: int) -> None:
        self._write("DELETE", f"/movies/{movieId}")


class MovieSearchResultsModel(JsonListModel):
    """Ephemeral TMDB search results (GET /movies/search-tmdb) for the add flow."""

    FIELDS = [
        ("tmdbId", "tmdb_id"),
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
        self._fetch(f"/movies/search-tmdb?q={QUrl.toPercentEncoding(query).data().decode()}")

    @Slot()
    def clear(self) -> None:
        self._set_items([])
