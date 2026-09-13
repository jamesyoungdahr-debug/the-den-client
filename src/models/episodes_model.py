from PySide6.QtCore import Property, Signal, Slot

from models.base import JsonListModel


class EpisodesModel(JsonListModel):
    """Episodes for one series -- GET /series/{id}/episodes. load(seriesId) remembers the
    series so refresh() after a grab reloads the same list."""

    FIELDS = [
        ("episodeId", "id"),
        ("seriesId", "series_id"),
        ("seasonNumber", "season_number"),
        ("episodeNumber", "episode_number"),
        ("title", "title", ""),
        ("airDate", "air_date", ""),
        ("hasFile", "has_file", False),
        ("monitored", "monitored", True),
        ("fileQuality", "file_quality", ""),
        ("fileScore", "file_score", 0),
        ("upgradable", "upgradable", False),
    ]

    seriesChanged = Signal()
    seasonActionDone = Signal(int, bool, str)  # season number, ok, message
    # A Property's notify must be a signal declared on the same class (a base-class
    # signal, or re-declaring the base's name, crashes PySide's property cache), so
    # derived stats get their own signal, emitted after every reset.
    statsChanged = Signal()

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        self._series_id: int | None = None

    def _set_items(self, items: list[dict]) -> None:
        super()._set_items(items)
        self.statsChanged.emit()

    currentSeriesId = Property(int, lambda self: self._series_id or 0, notify=seriesChanged)
    haveCount = Property(int, lambda self: sum(1 for e in self._items if e.get("has_file")), notify=statsChanged)

    @Slot(int)
    def load(self, seriesId: int) -> None:
        self._series_id = seriesId
        self.seriesChanged.emit()
        self._fetch(f"/series/{seriesId}/episodes")

    @Slot()
    def refresh(self) -> None:
        if self._series_id is not None:
            self._fetch(f"/series/{self._series_id}/episodes")

    def _season_post(self, seriesId: int, seasonNumber: int, action: str, payload: dict | None, done_message: str) -> None:
        def on_done(status: int, body) -> None:
            if status == 200:
                extra = ""
                if isinstance(body, dict) and "grabbed" in body:
                    extra = " · grabbed a release" if body["grabbed"] else " · nothing new found"
                self.seasonActionDone.emit(seasonNumber, True, done_message + extra)
            else:
                self.seasonActionDone.emit(seasonNumber, False, self.api.error_message(status, body))
            self.refresh()

        self.api.request("POST", f"/series/{seriesId}/seasons/{seasonNumber}/{action}", payload, on_done)

    @Slot(int, int, bool)
    def monitorSeason(self, seriesId: int, seasonNumber: int, monitored: bool) -> None:
        self._season_post(seriesId, seasonNumber, "monitor", {"monitored": monitored}, "Season monitored" if monitored else "Season unmonitored")

    @Slot(int, int)
    def markSeasonHave(self, seriesId: int, seasonNumber: int) -> None:
        self._season_post(seriesId, seasonNumber, "mark-have", None, "Season marked as have")

    @Slot(int, int)
    def searchSeason(self, seriesId: int, seasonNumber: int) -> None:
        self._season_post(seriesId, seasonNumber, "search", None, "Season searched")

    @Slot(int, result=bool)
    def seasonMonitored(self, seasonNumber: int) -> bool:
        """True when any episode of the season is monitored."""
        return any(e.get("monitored", True) for e in self._items if e.get("season_number") == seasonNumber)

    @Slot(int, result=bool)
    def seasonComplete(self, seasonNumber: int) -> bool:
        """True when every episode of the season has a file."""
        eps = [e for e in self._items if e.get("season_number") == seasonNumber]
        return bool(eps) and all(e.get("has_file") for e in eps)
