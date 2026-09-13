import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import "holt"

// Manual import (M23): downloads The Den couldn't fully place on its own -- a movie or
// episode grab that found no video, a season pack with files left over, or a torrent
// added by hand with no target -- each leftover file gets an Assign action (the
// record's own target for a movie or episode, an episode picker for a season pack)
// and an Import-as-is action (pick the movies or tv root).
HoltPage {
    id: page
    objectName: "manualImportPage"
    title: "Manual import"
    padding: Theme.space4

    Component.onCompleted: manualImportModel.refresh()

    Connections {
        target: manualImportModel
        function onErrorOccurred(message) { banner.showError(message) }
        function onAssigned(ok, message) { Controls.ApplicationWindow.window.toast(message, ok ? "positive" : "error") }
        function onImported(ok, message) { Controls.ApplicationWindow.window.toast(message, ok ? "positive" : "error") }
    }

    ColumnLayout {
        width: page.width - 2 * page.padding
        spacing: Theme.space4

        PageHeader { title: "Manual import"; meta: manualImportModel.count + " to review" }
        StatusBanner { id: banner }

        Repeater {
            model: manualImportModel
            delegate: GlassPanel {
                id: entryPanel
                required property var model
                Layout.fillWidth: true
                ColumnLayout {
                    width: entryPanel.width - 2 * entryPanel.padding
                    spacing: Theme.space2

                    Eyebrow { text: entryPanel.model.releaseTitle }
                    Meta {
                        text: entryPanel.model.kind === "movie" ? "grabbed for " + entryPanel.model.label + " -- no video file found"
                            : entryPanel.model.kind === "episode" ? "grabbed for " + entryPanel.model.label + " -- no video file found"
                            : entryPanel.model.kind === "season" ? "season pack for " + entryPanel.model.label + " -- some files matched no episode"
                            : "added by hand -- never tied to a title"
                    }

                    Repeater {
                        model: entryPanel.model.files
                        delegate: ColumnLayout {
                            id: fileRow
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.topMargin: Theme.space2
                            spacing: 6

                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: fileRow.modelData.name; font.family: Theme.fontCore; font.pixelSize: 13; font.weight: Font.Bold; color: Theme.ink; elide: Text.ElideMiddle; Layout.fillWidth: true }
                                Meta { text: (fileRow.modelData.size / 1048576).toFixed(1) + " MB" }
                            }

                            RowLayout {
                                spacing: Theme.space2

                                HoltButton {
                                    visible: entryPanel.model.kind === "movie" || entryPanel.model.kind === "episode"
                                    kind: "primary"; small: true
                                    text: "Assign to " + entryPanel.model.label
                                    onClicked: manualImportModel.assign(entryPanel.model.downloadId, fileRow.modelData.name, entryPanel.model.kind, entryPanel.model.kind === "movie" ? entryPanel.model.movieId : entryPanel.model.episodeId)
                                }

                                Controls.ComboBox {
                                    id: episodePicker
                                    visible: entryPanel.model.kind === "season"
                                    textRole: "label"
                                    valueRole: "id"
                                    model: entryPanel.model.seasonEpisodes
                                    font.family: Theme.fontCore
                                    Layout.preferredWidth: 220
                                }
                                HoltButton {
                                    visible: entryPanel.model.kind === "season"
                                    kind: "primary"; small: true; text: "Assign"
                                    onClicked: manualImportModel.assign(entryPanel.model.downloadId, fileRow.modelData.name, "episode", episodePicker.currentValue)
                                }

                                Controls.ComboBox {
                                    id: rootPicker
                                    textRole: "text"
                                    valueRole: "value"
                                    model: [{ text: "Movies folder", value: "movies" }, { text: "TV folder", value: "tv" }]
                                    font.family: Theme.fontCore
                                    Layout.preferredWidth: 150
                                }
                                HoltButton {
                                    kind: "quiet"; small: true; text: "Import as-is"
                                    onClicked: manualImportModel.importAsIs(entryPanel.model.downloadId, fileRow.modelData.name, rootPicker.currentValue)
                                }
                            }
                        }
                    }
                }
            }
        }

        EmptyState {
            visible: !manualImportModel.loading && manualImportModel.count === 0
            title: "Nothing to review"
            body: "Every finished download has been imported or is still in the library queue."
        }
    }
}
