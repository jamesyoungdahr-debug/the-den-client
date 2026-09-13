import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "holt"

// Settings as cards, bound to the backend's /api/settings record. Secrets show
// "set / not set" and are only sent when typed. Save lives in the top bar.
HoltPage {
    id: page
    objectName: "settingsPage"
    title: "Settings"
    padding: Theme.space4

    readonly property var s: settingsController.data

    Component.onCompleted: {
        settingsController.load()
        notificationsModel.loadCatalogue()
        notificationsModel.refresh()
        Controls.ApplicationWindow.window.pageAction = { text: "Save", trigger: function () { page.save() } }
    }
    Controls.StackView.onDeactivated: Controls.ApplicationWindow.window.pageAction = null
    Controls.StackView.onActivated: Controls.ApplicationWindow.window.pageAction = { text: "Save", trigger: function () { page.save() } }

    function num(text, fallback) { var n = Number(text); return isNaN(n) || text === "" ? fallback : n }
    function save() {
        settingsController.save({
            tmdb_api_key: tmdbField.text,
            movies_root: moviesRootField.text,
            tv_root: tvRootField.text,
            automation_interval_seconds: num(intervalField.text, 900),
            discord_webhook_url: discordField.text,
            downloads_root: downloadsRootField.text,
            torrent_port: num(portField.text, 6881),
            download_rate_limit_kib: num(downField.text, 0),
            upload_rate_limit_kib: num(upField.text, 0),
            seed_ratio_limit: num(ratioField.text, 0),
            seed_time_limit_minutes: num(seedTimeField.text, 0),
            plex_scan_interval_minutes: num(plexIntervalField.text, 30),
            request_movie_limit: num(movieLimitField.text, 10),
            request_series_limit: num(seriesLimitField.text, 5),
            request_limit_days: num(limitDaysField.text, 7),
            flaresolverr_url: solverField.text,
        })
    }

    Connections {
        target: settingsController
        function onErrorOccurred(message) { banner.showError(message) }
        function onSaved() { banner.show("Saved. Torrent and automation changes are live already.", "positive"); tmdbField.text = ""; discordField.text = ""; Controls.ApplicationWindow.window.toast("Settings saved", "positive") }
    }

    component Section: GlassPanel {
        property string name: ""
        property string note: ""
        default property alias body: bodyCol.data
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Layout.preferredWidth: 400
        Layout.alignment: Qt.AlignTop
        ColumnLayout {
            width: parent.width
            spacing: Theme.space3
            RowLayout { Eyebrow { text: name } Item { Layout.fillWidth: true } Meta { text: note; visible: note !== "" } }
            ColumnLayout { id: bodyCol; spacing: Theme.space3; Layout.fillWidth: true }
        }
    }

    ColumnLayout {
        width: page.width - 2 * page.padding
        spacing: Theme.space3

        PageHeader { title: "Settings"; meta: "Blank fields fall back to the server's environment defaults. Secrets never show their value." }
        StatusBanner { id: banner }

        GridLayout {
            Layout.fillWidth: true
            columns: page.width > 1000 ? 2 : 1
            columnSpacing: Theme.space3
            rowSpacing: Theme.space3

            Section {
                name: "Library"
                Field { label: "TMDB API key · " + (page.s.has_tmdb_api_key ? "set" : "using the built-in key"); HoltTextField { id: tmdbField; echoMode: TextInput.Password; placeholderText: "leave blank to keep the current key" } }
                RowLayout {
                    spacing: Theme.space3
                    Field { label: "Movies folder"; HoltTextField { id: moviesRootField; text: page.s.movies_root || "" } }
                    Field { label: "TV folder"; HoltTextField { id: tvRootField; text: page.s.tv_root || "" } }
                }
            }

            Section {
                name: "Torrent client"; note: "built in"
                Field { label: "Downloads folder"; hint: "Finished files are hard-linked into the library so torrents keep seeding."; HoltTextField { id: downloadsRootField; text: page.s.downloads_root || "" } }
                RowLayout {
                    spacing: Theme.space3
                    Field { label: "Listen port"; HoltTextField { id: portField; text: page.s.torrent_port !== undefined ? String(page.s.torrent_port) : ""; validator: IntValidator { bottom: 1024; top: 65535 } } }
                    Field { label: "Down KiB/s (0 = none)"; HoltTextField { id: downField; text: page.s.download_rate_limit_kib !== undefined ? String(page.s.download_rate_limit_kib) : ""; validator: IntValidator { bottom: 0 } } }
                    Field { label: "Up KiB/s (0 = none)"; HoltTextField { id: upField; text: page.s.upload_rate_limit_kib !== undefined ? String(page.s.upload_rate_limit_kib) : ""; validator: IntValidator { bottom: 0 } } }
                }
                RowLayout {
                    spacing: Theme.space3
                    Field { label: "Seed ratio (0 = forever)"; HoltTextField { id: ratioField; text: page.s.seed_ratio_limit !== undefined ? String(page.s.seed_ratio_limit) : "" } }
                    Field { label: "Seed minutes (0 = none)"; HoltTextField { id: seedTimeField; text: page.s.seed_time_limit_minutes !== undefined ? String(page.s.seed_time_limit_minutes) : ""; validator: IntValidator { bottom: 0 } } }
                }
            }

            Section {
                name: "Automation"
                Field { label: "Check interval (seconds)"; hint: "How often The Den advances downloads, imports finished ones, and searches for what's missing."; HoltTextField { id: intervalField; text: page.s.automation_interval_seconds !== undefined ? String(page.s.automation_interval_seconds) : ""; validator: IntValidator { bottom: 60 } } }
            }

            Section {
                name: "Requests"; note: "quotas for non-admins"
                RowLayout {
                    spacing: Theme.space3
                    Field { label: "Movies (0 = unlimited)"; HoltTextField { id: movieLimitField; text: page.s.request_movie_limit !== undefined ? String(page.s.request_movie_limit) : ""; validator: IntValidator { bottom: 0 } } }
                    Field { label: "Series"; HoltTextField { id: seriesLimitField; text: page.s.request_series_limit !== undefined ? String(page.s.request_series_limit) : ""; validator: IntValidator { bottom: 0 } } }
                    Field { label: "Window (days)"; HoltTextField { id: limitDaysField; text: page.s.request_limit_days !== undefined ? String(page.s.request_limit_days) : ""; validator: IntValidator { bottom: 1 } } }
                }
                Meta { text: "Per-person limits are set on the web Users page. Admins have no quota."; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone }
            }

            Section {
                name: "Indexers"; note: "Cloudflare"
                Field { label: "External FlareSolverr / Byparr URL"; hint: "Optional. Leave blank to use the built-in solver (needs Chromium on the server)."; HoltTextField { id: solverField; text: page.s.flaresolverr_url || ""; placeholderText: "http://127.0.0.1:8191" } }
            }
            Section {
                name: "Notifications"; note: "Discord, ntfy, webhook, Telegram, Pushover"
                Repeater {
                    model: notificationsModel
                    delegate: HoltRow {
                        required property var model
                        thumbWidth: 0
                        Text { text: model.name; font.family: Theme.fontCore; font.pixelSize: 14; font.weight: Font.Bold; color: Theme.ink; elide: Text.ElideRight; Layout.fillWidth: true }
                        Meta { text: model.kind + " · " + (model.events.length ? model.events.length + " events" : "all events"); Layout.fillWidth: true }
                        actions: [
                            Badge { tone: model.agentEnabled ? "available" : "missing"; label: model.agentEnabled ? "enabled" : "disabled" },
                            HoltButton { small: true; text: "Test"; onClicked: notificationsModel.testAgent(model.agentId) },
                            HoltButton { small: true; text: "Edit"; onClicked: agentDialog.openFor(model) },
                            HoltButton { kind: "quiet"; small: true; text: "Delete"; onClicked: notificationsModel.deleteAgent(model.agentId) }
                        ]
                    }
                }
                EmptyState { visible: !notificationsModel.loading && notificationsModel.count === 0; title: "No agents yet"; body: "Add Discord, ntfy, a webhook, Telegram or Pushover."; actionText: "Add agent"; onAction: agentDialog.openFor(null) }
                HoltButton { kind: "secondary"; small: true; text: "Add agent"; visible: notificationsModel.count > 0; onClicked: agentDialog.openFor(null) }
                Field { label: "Legacy Discord webhook · " + (page.s.has_discord_webhook ? "set" : "not set"); hint: "Still fires for every event; add it as an agent above to pick events."; HoltTextField { id: discordField; echoMode: TextInput.Password; placeholderText: "leave blank to keep the current value" } }
            }

            Section {
                name: "Import Lists"; note: "TMDB list, Plex watchlist"
                Repeater {
                    model: importListsModel
                    delegate: HoltRow {
                        required property var model
                        thumbWidth: 0
                        Text { text: model.name; font.family: Theme.fontCore; font.pixelSize: 14; font.weight: Font.Bold; color: Theme.ink; elide: Text.ElideRight; Layout.fillWidth: true }
                        Meta { text: (model.kind === "tmdb_list" ? "TMDB list " + (model.config.list_id || "") : "Plex watchlist") + " · " + (model.lastResult || "never synced"); Layout.fillWidth: true }
                        actions: [
                            Badge { tone: model.listEnabled ? "available" : "missing"; label: model.listEnabled ? "enabled" : "disabled" },
                            HoltButton { small: true; text: "Sync now"; onClicked: importListsModel.syncList(model.listId) },
                            HoltButton { small: true; text: "Edit"; onClicked: importListDialog.openFor(model) },
                            HoltButton { kind: "quiet"; small: true; text: "Delete"; onClicked: importListsModel.deleteList(model.listId) }
                        ]
                    }
                }
                EmptyState { visible: !importListsModel.loading && importListsModel.count === 0; title: "No import lists yet"; body: "Auto-add from a TMDB list or your Plex watchlist."; actionText: "Add list"; onAction: importListDialog.openFor(null) }
                HoltButton { kind: "secondary"; small: true; text: "Add list"; visible: importListsModel.count > 0; onClicked: importListDialog.openFor(null) }
            }

            Section {
                name: "Root Folders"; note: "extra movie/TV libraries beyond the default folders above"
                Repeater {
                    model: rootFoldersModel
                    delegate: HoltRow {
                        required property var model
                        thumbWidth: 0
                        Text { text: model.name; font.family: Theme.fontCore; font.pixelSize: 14; font.weight: Font.Bold; color: Theme.ink; elide: Text.ElideRight; Layout.fillWidth: true }
                        Meta { text: model.mediaType + " · " + model.path; Layout.fillWidth: true }
                        actions: [
                            Badge { visible: model.isDefault; tone: "available"; label: "default for " + model.mediaType },
                            HoltButton { small: true; text: "Edit"; onClicked: rootFolderDialog.openFor(model) },
                            HoltButton { kind: "quiet"; small: true; text: "Delete"; onClicked: rootFoldersModel.deleteFolder(model.folderId) }
                        ]
                    }
                }
                EmptyState { visible: !rootFoldersModel.loading && rootFoldersModel.count === 0; title: "No extra root folders yet"; body: "Everything uses the Movies/TV library folders above."; actionText: "Add folder"; onAction: rootFolderDialog.openFor(null) }
                HoltButton { kind: "secondary"; small: true; text: "Add folder"; visible: rootFoldersModel.count > 0; onClicked: rootFolderDialog.openFor(null) }
            }

            Section {
                name: "Plex"
                note: page.s.has_plex_token ? "connected as " + (page.s.plex_owner_username || "owner") : "not connected"
                Meta { text: page.s.has_plex_token ? ("Server: " + (page.s.plex_server_name || "not chosen") + " · last scan " + (page.s.plex_last_scan_result || "never")) : "Connect the owner account from the web Settings page; the client can then scan on the interval below."; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone }
                RowLayout {
                    spacing: Theme.space3
                    Field { label: "Library scan every (minutes)"; Layout.maximumWidth: 240; HoltTextField { id: plexIntervalField; text: page.s.plex_scan_interval_minutes !== undefined ? String(page.s.plex_scan_interval_minutes) : ""; validator: IntValidator { bottom: 5 } } }
                    HoltButton { text: "Scan now"; enabled: page.s.has_plex_token === true; Layout.alignment: Qt.AlignBottom; onClicked: settingsController.scanPlex() }
                }
            }

            Section {
                name: "Accounts"
                note: page.s.auth_required ? "sign-in required" : "sign-in optional"
                Meta { text: page.s.auth_required ? "Every page and API call needs a signed-in account; this client uses the API token from your profile." : "Anyone not signed in is an admin. Turn sign-in on from the web Settings page once everyone has an account."; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone }
            }
        }
    }

    // Notification agent add/edit (M15). Nested children reach the dialog's state as agentDialog.<prop>.
    HoltDialog {
        id: agentDialog
        title: "Notification agent"
        property int agentId: 0
        property var current: null
        property var values: ({})
        property var selectedEvents: []
        readonly property var secretKeys: ["token", "webhook_url", "bot_token", "app_token", "user_key"]
        readonly property var kindDef: notificationsModel.kinds[kindField.currentIndex] || null

        function kindIndex(k) { for (var i = 0; i < notificationsModel.kinds.length; i++) if (notificationsModel.kinds[i].kind === k) return i; return 0 }
        function openFor(m) {
            agentId = m ? m.agentId : 0
            current = m
            nameField.text = m ? m.name : ""
            kindField.currentIndex = m ? kindIndex(m.kind) : 0
            enabledBox.checked = m ? m.agentEnabled : true
            values = m ? Object.assign({}, m.config) : {}
            selectedEvents = m ? m.events.slice() : []
            open()
        }

        Field { label: "Name"; HoltTextField { id: nameField; placeholderText: "e.g. Phone" } }
        Field { label: "Kind"; Controls.ComboBox { id: kindField; model: notificationsModel.kinds; textRole: "kind"; font.family: Theme.fontCore } }
        Repeater {
            model: agentDialog.kindDef ? agentDialog.kindDef.fields : []
            delegate: Field {
                required property string modelData
                readonly property bool secret: agentDialog.secretKeys.indexOf(modelData) !== -1
                label: modelData.replace(/_/g, " ") + (modelData === "token" ? " (optional)" : "")
                HoltTextField {
                    text: parent.parent.secret ? "" : (agentDialog.values[parent.parent.modelData] || "")
                    echoMode: parent.parent.secret ? TextInput.Password : TextInput.Normal
                    placeholderText: agentDialog.current && parent.parent.secret && agentDialog.current["has" + parent.parent.modelData.split("_").map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1) }).join("")]
                        ? "leave blank to keep the current value"
                        : (parent.parent.modelData === "url" && agentDialog.kindDef && agentDialog.kindDef.kind === "ntfy" ? "https://ntfy.sh" : "")
                    onTextChanged: { var v = agentDialog.values; v[parent.parent.modelData] = text; agentDialog.values = v }
                }
            }
        }
        Field {
            label: "Events"
            hint: "Leave all unselected to receive every event."
            Flow {
                spacing: 6
                Repeater {
                    model: notificationsModel.events
                    delegate: Chip {
                        required property var modelData
                        text: modelData.label
                        on: agentDialog.selectedEvents.indexOf(modelData.key) !== -1
                        onClicked: { var e = agentDialog.selectedEvents.slice(); var i = e.indexOf(modelData.key); if (i === -1) e.push(modelData.key); else e.splice(i, 1); agentDialog.selectedEvents = e }
                    }
                }
            }
        }
        Controls.CheckBox { id: enabledBox; text: "Enabled"; font.family: Theme.fontCore }
        footer: [
            HoltButton { kind: "quiet"; text: "Cancel"; onClicked: agentDialog.close() },
            HoltButton { kind: "secondary"; text: "Send test"; enabled: !!agentDialog.kindDef; onClicked: agentDialog.agentId ? notificationsModel.testAgent(agentDialog.agentId) : notificationsModel.testConfig(agentDialog.kindDef.kind, agentDialog.values) },
            HoltButton {
                kind: "primary"; text: "Save"
                enabled: nameField.text.length > 0 && !!agentDialog.kindDef
                onClicked: {
                    if (agentDialog.agentId) notificationsModel.updateAgent(agentDialog.agentId, nameField.text, agentDialog.kindDef.kind, agentDialog.values, agentDialog.selectedEvents, enabledBox.checked)
                    else notificationsModel.addAgent(nameField.text, agentDialog.kindDef.kind, agentDialog.values, agentDialog.selectedEvents, enabledBox.checked)
                    agentDialog.close()
                }
            }
        ]
    }

    // Import list add/edit (E1).
    HoltDialog {
        id: importListDialog
        title: "Import list"
        property int listId: 0
        property var current: null

        function openFor(m) {
            listId = m ? m.listId : 0
            current = m
            ilNameField.text = m ? m.name : ""
            ilKindField.currentIndex = m && m.kind === "plex_watchlist" ? 1 : 0
            ilListIdField.text = m && m.config ? (m.config.list_id || "") : ""
            ilEnabledBox.checked = m ? m.listEnabled : true
            open()
        }

        Field { label: "Name"; HoltTextField { id: ilNameField; placeholderText: "e.g. Watchlist movies" } }
        Field {
            label: "Kind"
            Controls.ComboBox { id: ilKindField; model: ["TMDB list", "Plex watchlist"]; font.family: Theme.fontCore }
        }
        Field {
            label: "TMDB list ID"
            hint: "The numeric ID from the list's TMDB URL (themoviedb.org/list/<id>). Public lists only, movies only."
            visible: ilKindField.currentIndex === 0
            HoltTextField { id: ilListIdField }
        }
        Meta {
            visible: ilKindField.currentIndex === 1
            text: "Reads the connected Plex account's Discover watchlist (Settings → Plex must be connected first). Movies and series with a TMDB match are added."
            Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone
        }
        Controls.CheckBox { id: ilEnabledBox; text: "Enabled"; font.family: Theme.fontCore }
        footer: [
            HoltButton { kind: "quiet"; text: "Cancel"; onClicked: importListDialog.close() },
            HoltButton {
                kind: "primary"; text: "Save"
                enabled: ilNameField.text.length > 0
                onClicked: {
                    var kind = ilKindField.currentIndex === 1 ? "plex_watchlist" : "tmdb_list"
                    var config = kind === "tmdb_list" ? {"list_id": ilListIdField.text.trim()} : {}
                    if (importListDialog.listId) importListsModel.updateList(importListDialog.listId, ilNameField.text, kind, config, ilEnabledBox.checked)
                    else importListsModel.addList(ilNameField.text, kind, config, ilEnabledBox.checked)
                    importListDialog.close()
                }
            }
        ]
    }

    // Root folder add/edit (E2).
    HoltDialog {
        id: rootFolderDialog
        title: "Root folder"
        property int folderId: 0

        function openFor(m) {
            folderId = m ? m.folderId : 0
            rfNameField.text = m ? m.name : ""
            rfMediaTypeField.currentIndex = m && m.mediaType === "tv" ? 1 : 0
            rfPathField.text = m ? m.path : ""
            rfDefaultBox.checked = m ? m.isDefault : false
            open()
        }

        Field { label: "Name"; HoltTextField { id: rfNameField; placeholderText: "e.g. Kids Movies" } }
        Field {
            label: "Media type"
            Controls.ComboBox { id: rfMediaTypeField; model: ["Movie", "TV"]; font.family: Theme.fontCore }
        }
        Field { label: "Path"; HoltTextField { id: rfPathField; placeholderText: "/path/to/library" } }
        Controls.CheckBox { id: rfDefaultBox; text: "Default for this media type"; font.family: Theme.fontCore }
        footer: [
            HoltButton { kind: "quiet"; text: "Cancel"; onClicked: rootFolderDialog.close() },
            HoltButton {
                kind: "primary"; text: "Save"
                enabled: rfNameField.text.length > 0 && rfPathField.text.length > 0
                onClicked: {
                    var mediaType = rfMediaTypeField.currentIndex === 1 ? "tv" : "movie"
                    if (rootFolderDialog.folderId) rootFoldersModel.updateFolder(rootFolderDialog.folderId, rfNameField.text, mediaType, rfPathField.text, rfDefaultBox.checked)
                    else rootFoldersModel.addFolder(rfNameField.text, mediaType, rfPathField.text, rfDefaultBox.checked)
                    rootFolderDialog.close()
                }
            }
        ]
    }
}
