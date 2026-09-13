import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import "holt"

// "View more" on a Discover rail: the same TMDB list as a paged poster grid. Shares the
// rail's model, so Load more appends page after page (20 cards each).
HoltPage {
    id: page
    objectName: "railPage"
    property var railModel: null
    property string railTitle: ""
    property string subtitle: ""
    title: railTitle
    padding: Theme.space4

    Component.onCompleted: { if (page.railModel && page.railModel.count === 0) page.railModel.refresh() }

    Connections {
        target: page.railModel
        function onErrorOccurred(message) { banner.showError(message) }
    }

    ColumnLayout {
        width: page.width - 2 * page.padding
        spacing: Theme.space3

        PageHeader {
            title: page.railTitle
            meta: (page.subtitle !== "" ? page.subtitle + " · " : "") + (page.railModel ? page.railModel.count + " titles" + (page.railModel.loading ? " · loading…" : "") : "")
        }

        StatusBanner { id: banner }

        Flow {
            Layout.fillWidth: true
            spacing: Theme.space3
            Repeater {
                model: page.railModel
                delegate: PosterCard {
                    posterWidth: Theme.posterLg
                    title: model.title
                    year: model.year
                    posterPath: model.posterPath
                    status: model.status
                    rating: model.rating
                    onClicked: Controls.ApplicationWindow.window.openDetail(model.mediaType, model.tmdbId)
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            HoltButton {
                kind: "primary"
                text: page.railModel && page.railModel.loading ? "Loading…" : "Load more"
                visible: page.railModel ? page.railModel.hasMore : false
                enabled: page.railModel ? !page.railModel.loading : false
                onClicked: page.railModel.loadMore()
            }
            Item { Layout.fillWidth: true }
        }

        EmptyState {
            visible: page.railModel ? (!page.railModel.loading && page.railModel.count === 0) : true
            title: "Nothing here"
            body: "TMDB returned no titles for this list."
        }
    }
}
