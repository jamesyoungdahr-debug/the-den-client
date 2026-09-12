import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "holt"

// The TV library as a poster grid; click through to episodes; add via TVmaze search.
HoltPage {
    id: page
    objectName: "seriesPage"
    title: "TV"
    padding: Theme.space4
    property string filter: "all"

    Component.onCompleted: {
        seriesModel.refresh()
        if (apiClient.isAdmin) Controls.ApplicationWindow.window.pageAction = { text: "Add series", trigger: function () { addDialog.open() } }
    }
    Controls.StackView.onDeactivated: Controls.ApplicationWindow.window.pageAction = null
    Controls.StackView.onActivated: if (apiClient.isAdmin) Controls.ApplicationWindow.window.pageAction = { text: "Add series", trigger: function () { addDialog.open() } }

    Connections {
        target: seriesModel
        function onErrorOccurred(message) { banner.showError(message) }
    }
    Connections {
        target: seriesSearchModel
        function onErrorOccurred(message) { banner.showError("Search error: " + message) }
    }

    ColumnLayout {
        width: page.width - 2 * page.padding
        spacing: Theme.space3


        PageHeader {
            title: "TV"
            meta: (seriesModel.count - seriesModel.plexCount) + " series in The Den" + (seriesModel.plexCount ? " · " + seriesModel.plexCount + " on Plex" : "")
            Chip { text: "All"; on: page.filter === "all"; onClicked: page.filter = "all" }
            Chip { text: "Incomplete"; on: page.filter === "missing"; onClicked: page.filter = "missing" }
            Chip { visible: seriesModel.plexCount > 0; text: "On Plex"; on: page.filter === "plex"; onClicked: page.filter = "plex" }
        }
        StatusBanner { id: banner }

        Flow {
            Layout.fillWidth: true
            spacing: Theme.space3
            Repeater {
                model: seriesModel
                delegate: PosterCard {
                    visible: page.filter === "all" || (page.filter === "plex" && model.onPlex) || (page.filter === "missing" && !model.available)
                    posterWidth: Theme.posterLg
                    title: model.title
                    year: model.year
                    posterPath: model.posterPath
                    status: model.seriesId === 0 ? "available" : (model.total && model.have === model.total ? "available" : (model.have ? "partial" : (model.onPlex ? "available" : "wanted")))
                    showRating: false
                    onClicked: {
                        if (model.seriesId > 0) Controls.ApplicationWindow.window.push("EpisodesPage.qml", { seriesId: model.seriesId, seriesTitle: model.title, posterPath: model.posterPath })
                        else if (model.tmdbId) Controls.ApplicationWindow.window.openDetail("tv", model.tmdbId)
                    }
                    Badge { visible: model.onPlex; anchors { left: parent.left; leftMargin: 8 } y: Math.round(parent.posterWidth * 1.5) - height - 8; solid: true; tone: "available"; label: model.seriesId === 0 ? "Plex · " + model.plexSeasons + (model.plexSeasons === 1 ? " season" : " seasons") : "Plex" }
                    HoltButton { visible: apiClient.isAdmin && model.seriesId > 0; anchors { right: parent.right; rightMargin: 6 } y: Math.round(parent.posterWidth * 1.5) - height - 6; small: true; kind: "quiet"; text: "✕"; onClicked: seriesModel.deleteSeries(model.seriesId) }
                }
            }
        }

        EmptyState {
            visible: !seriesModel.loading && seriesModel.count === 0
            title: "No series yet"
            body: apiClient.isAdmin ? "Add one here or from Discover; episode lists come from TVmaze." : "Request a series on Discover and it'll show up here once approved."
            actionText: "Discover"
            onAction: Controls.ApplicationWindow.window.navigate("discover")
        }
    }

    HoltDialog {
        id: addDialog
        title: "Add a series"
        onClosed: { seriesSearchModel.clear(); searchField.text = "" }
        RowLayout {
            Layout.fillWidth: true
            HoltTextField { id: searchField; Layout.fillWidth: true; placeholderText: "Search TVmaze…"; onAccepted: seriesSearchModel.search(text) }
            HoltButton { text: "Search"; onClicked: seriesSearchModel.search(searchField.text) }
        }
        Repeater {
            model: seriesSearchModel
            delegate: HoltRow {
                required property var model
                Text { text: model.title; font.family: Theme.fontCore; font.pixelSize: 13; font.weight: Font.Bold; color: Theme.ink; elide: Text.ElideRight; Layout.fillWidth: true }
                Meta { text: model.year ? String(model.year) : "" }
                actions: HoltButton { kind: "primary"; small: true; text: "Add"; onClicked: { seriesModel.addSeries(model.tvmazeId, model.title, model.year ? String(model.year) : "", model.overview, model.posterPath); addDialog.close() } }
            }
        }
        footer: HoltButton { kind: "quiet"; text: "Close"; onClicked: addDialog.close() }
    }
}
