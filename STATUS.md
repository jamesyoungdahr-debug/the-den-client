# Status

## Last completed
**0.4.4 (2026-09-12, uncommitted):** the Indexers page adds from the server's preset
catalog (`IndexerListModel.presets` / `loadPresets()` / `addIndexer(preset, name, url,
apiKey)`; the dialog shows only the fields a preset needs and flags Cloudflare ones), and
Settings gained the external FlareSolverr/Byparr URL. The app icon is set from the hicolor
theme so installed builds show it (a checkout falls back to `src/assets/logo.svg`). Model test
re-verified against the dev backend; the QML awaits the real-desktop pass.

**0.4.3 (2026-09-12):** Movies and TV read the merged library from the-den's
`/api/library/movies|series` (needs the-den 0.4.3), so titles that are only on Plex show
up with their Plex poster (the thumb proxy URL gets `?api_key=` because QML `Image` can't
send headers), a *Plex* badge, an *On Plex* filter, and no Releases/Remove actions. The
sidebar scrolls when the window is shorter than the nav.

**U4 -- the HoltOS Glass redesign of the whole client (2026-09-12).** Everything was
rebuilt on the backend's current API:

- **Sign-in.** Login page with *Sign in with Plex* (backend PIN flow, plex.tv opens in
  the system browser, the client polls) and a local username/password form; either way
  the client swaps the session for a personal API token (`POST /api/auth/token`), keeps
  only that in QSettings, and sends it as `X-Api-Key`. `GET /api/auth/me` decides what
  the shell shows (admin group, request buttons, quota).
- **Shell.** Glass sidebar with Browse / Library / Admin groups (Admin only for admins,
  pending-requests badge), rail mode when collapsed or under 900px, top bar with global
  search and the page's single primary action, page stack, toasts.
- **Pages.** Discover (hero + Recommended for you + rails), Search (poster grid with type
  chips), Detail (backdrop hero, facts, genres, cast, seasons with per-season
  availability, availability panel, request/add with a season picker, recommendations),
  Requests (filters, approve / decline with a note / withdraw / remove), Movies and TV as
  poster grids with add dialogs, Episodes with progress and per-season sections,
  Releases with quality chips and best-match, Calendar as an agenda (missing / upcoming /
  movies wanted), Downloads on `/torrents` (engine header, grouped rows with drawn
  progress bars, pause / resume / remove, add by hand, polling while visible), Indexers
  with test/delete and an add dialog, Settings as cards bound to `/api/settings` (fixed:
  it had been broken since the torrent client replaced qBittorrent).
- **Code.** `JsonListModel`/`JsonRecord` base (fields declared, roles generated, the
  reply-sequence guard everywhere, `loading`/`count`), so the near-identical model pairs
  and the copy-pasted error banner block flagged by the last review are gone. `theme.py`
  reads the shared `design/exports/holt_tokens.py`. A `holt/` QML component library.
- **Verified headlessly** against the dev backend: 10 model checks, the page compile
  harness (13 pages, zero QML warnings) and a full-app screenshot walk (10 PNGs, zero
  warnings) via `tests/run_all.sh`. Two PySide pitfalls found on the way and documented
  in the code: a `Property` notify must be a signal declared on the same class (a base
  signal, or re-declaring the base's name, segfaults), and integer `font.pixelSize`.

## Currently working on
**Session handoff note (2026-09-13):** Tier 2 (the-den's docs/feature-research.md, E1-E10) is
finished. This client got every E-item whose surfaces column includes it; E4/E7/E8/E9/E10 skipped
it on purpose. The E6 gap is closed in 0.4.16. See the-den's CONTEXT.txt "PICK UP HERE" section for
what's next; the real-desktop pass on HoltOS is still open.

**0.5.0 (M33, 2026-09-13):** needs the-den 0.8.0. Sign-in is always required: "Continue without
signing in" and the anonymous account row are gone, `ApiClient` drops `canBrowse` and
`authRequired`, and a server whose web setup isn't finished is reported on the login page ("This
server hasn't been set up yet. Finish setup in its web UI, then connect again.") instead of
connecting. Settings drops the Accounts section. `tests/run_all.sh` green against an M33 server.

**0.4.16 (E6, 2026-09-13):** Settings gains a Subtitles section (OpenSubtitles API key + languages).
The key joins `SECRETS` in the settings controller, so a blank field keeps the stored value, and the
field clears after a save like the other secrets. QML harness: SettingsPage.qml clean;
`check_settings_controller.py` passes.

**0.4.15 (E2, 2026-09-13):** Root Folders section on Settings: named library folders per
media type (Movies vs Kids Movies, 4K vs 1080p, etc.) with a default per type, a
RootFoldersModel (JsonListModel over `/api/root-folders`, mirrors ImportListsModel) and
an add/edit dialog. No per-title picker yet (matches the same gap quality profiles
already have on every surface). QML harness: 15 pages clean.

**0.4.14 (E1, 2026-09-13):** Import Lists section on Settings: auto-add movies/series
from a TMDB list or a Plex watchlist on a schedule, an ImportListsModel (mirrors
NotificationAgentsModel) and an add/edit dialog for picking a TMDB list ID or a Plex
watchlist. QML harness: 15 pages clean including SettingsPage.qml.

**0.4.13 (E5, 2026-09-13):** Detail page gains a History panel (`page.item.history`, read
straight through from the server's JSON detail payload -- no model change needed since
`JsonRecord` already passes the raw JSON through as a `QVariantMap`), showing every
grab/upgrade/import/failure/removal for the title with a tone-mapped badge per event
(needs the-den's E5 history_events work). QML harness: DetailPage.qml verified clean.

**0.4.12 (M23, 2026-09-13):** Manual import for unmatched downloads: a new
ManualImportPage lists any download with leftover files (a movie/episode grab that found
no video, a season pack with unmatched episodes, or a torrent added by hand with no title
link), with per-file Assign (movie/episode, season picker for season packs) and
Import-as-is actions against the server's `/downloads/unmatched` API.

**0.4.11 (M22, 2026-09-13):** Discover splits into a Movies group and a Series group
(All / Movies / Series chips at the top), with four new rails (trending and top rated for
each) and a "View more" button on every rail that opens RailPage: the same list as a
poster grid, Load more appending the next TMDB page through the rail model's
loadMore() (needs the-den 0.6.7 for ?page=). QML harness: 14 pages including RailPage.

## Next steps
- **See it on a real screen.** The screenshot walk uses the Basic QQC2 style offscreen;
  `org.kde.desktop` on the HoltOS desktop may size controls differently. Run
  `makepkg -si` from this repo root there and click through.
- Live blur behind the sidebar/top bar (`MultiEffect`) once seen on real hardware; the
  ground-layer glass is deliberate for now.
- Users page (per-person quotas, roles) is web-only; the client points there.
- Window state (size, sidebar collapsed) is not yet remembered between runs.
