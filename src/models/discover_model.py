"""Discover (U4): TMDB rails and search from /api/discover/*, and the detail record for
one movie or series with its availability (library + Plex) and request state."""

from __future__ import annotations

from PySide6.QtCore import Property, QModelIndex, QUrl, Signal, Slot

from models.base import JsonListModel, JsonRecord

CARD_FIELDS = [
    ("mediaType", "media_type"),
    ("tmdbId", "tmdb_id"),
    ("title", "title"),
    ("year", "year"),
    ("overview", "overview", ""),
    ("posterPath", "poster_path", ""),
    ("backdropPath", "backdrop_path", ""),
    ("rating", "rating", 0.0),
    ("status", "status", ""),
    ("onPlex", "on_plex", False),
    ("libraryHref", "library_href", ""),
]


class RailModel(JsonListModel):
    """One Discover rail -- GET /api/discover/{rail}?page=N (20 cards a page): trending,
    trending-movies, popular-movies, upcoming-movies, top-rated-movies, trending-tv,
    popular-tv, on-the-air, top-rated-tv, recommended. refresh() loads page 1;
    loadMore() appends the next page (the "View more" grid shares this model)."""

    FIELDS = CARD_FIELDS
    PAGE_SIZE = 20
    pageChanged = Signal()

    def __init__(self, api, rail: str, parent=None):
        super().__init__(api, parent)
        self._rail = rail
        self._page = 0
        self._has_more = False

    rail = Property(str, lambda self: self._rail, constant=True)
    page = Property(int, lambda self: self._page, notify=pageChanged)
    hasMore = Property(bool, lambda self: self._has_more, notify=pageChanged)

    def _set_items(self, items: list[dict]) -> None:
        super()._set_items(items)
        self._page = 1
        self._has_more = len(items) >= self.PAGE_SIZE
        self.pageChanged.emit()

    @Slot()
    def refresh(self) -> None:
        self._fetch(f"/api/discover/{self._rail}")

    @Slot()
    def loadMore(self) -> None:
        if self._loading or not self._has_more:
            return
        nxt = self._page + 1
        self._seq += 1
        seq = self._seq
        self._set_loading(True)

        def on_done(status: int, body) -> None:
            if seq != self._seq:
                return
            self._set_loading(False)
            if status != 200 or not isinstance(body, list):
                self.errorOccurred.emit(self.api.error_message(status, body))
                return
            seen = {(i.get("media_type"), i.get("tmdb_id")) for i in self._items}
            fresh = [i for i in body if (i.get("media_type"), i.get("tmdb_id")) not in seen]
            if fresh:
                first = len(self._items)
                self.beginInsertRows(QModelIndex(), first, first + len(fresh) - 1)
                self._items.extend(fresh)
                self.endInsertRows()
                self.countChanged.emit()
            self._page = nxt
            self._has_more = len(body) >= self.PAGE_SIZE
            self.pageChanged.emit()

        self.api.request("GET", f"/api/discover/{self._rail}?page={nxt}", on_done=on_done)


class DiscoverSearchModel(JsonListModel):
    """GET /api/discover/search?q= -- movies and series together, each card stamped
    with the library's / Plex's status."""

    FIELDS = CARD_FIELDS
    queryChanged = Signal()

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        self._query = ""

    query = Property(str, lambda self: self._query, notify=queryChanged)

    @Slot(str)
    def search(self, query: str) -> None:
        self._query = query.strip()
        self.queryChanged.emit()
        if not self._query:
            self._set_items([])
            return
        self._fetch(f"/api/discover/search?q={QUrl.toPercentEncoding(self._query).data().decode()}")


class DetailController(JsonRecord):
    """GET /api/discover/movie|tv/{id}: everything the detail page shows, and the
    actions on it. Requesting goes through POST /api/requests -- for admins the backend
    approves instantly and that is how "Add to library" works from here too."""

    requestFinished = Signal(bool, str)
    kindChanged = Signal()

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        self._kind = ""
        self._tmdb_id = 0

    kind = Property(str, lambda self: self._kind, notify=kindChanged)
    tmdbId = Property(int, lambda self: self._tmdb_id, notify=kindChanged)

    @Slot(str, int)
    def load(self, kind: str, tmdbId: int) -> None:
        self._kind, self._tmdb_id = kind, tmdbId
        self.kindChanged.emit()
        self._set_data({})
        self._fetch(f"/api/discover/{kind}/{tmdbId}")

    @Slot()
    def reload(self) -> None:
        if self._kind:
            self._fetch(f"/api/discover/{self._kind}/{self._tmdb_id}")

    @Slot(list)
    def request(self, seasons: list) -> None:
        payload: dict = {"media_type": self._kind, "tmdb_id": self._tmdb_id}
        if self._kind == "tv" and seasons:
            payload["seasons"] = [int(s) for s in seasons]

        def on_done(status: int, body) -> None:
            if status == 201 and isinstance(body, dict):
                approved = body.get("status") == "approved"
                self.requestFinished.emit(True, "Added to the library" if approved else "Request sent for approval")
                self.reload()
            else:
                self.requestFinished.emit(False, self.api.error_message(status, body))

        self.api.request("POST", "/api/requests", payload, on_done)
