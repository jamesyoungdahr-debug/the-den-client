import QtQuick
import QtQuick.Layouts

// Centred empty state: the sleepy otter, title, body, optional action.
GlassPanel {
    id: empty
    property string title: ""
    property string body: ""
    property string actionText: ""
    signal action()

    padding: Theme.space5
    Layout.fillWidth: true

    ColumnLayout {
        width: parent.width
        spacing: Theme.space2
        Image {
            source: Qt.resolvedUrl("../../assets/otter-idle.png")
            Layout.preferredWidth: 72
            Layout.preferredHeight: 72
            Layout.alignment: Qt.AlignHCenter
            sourceSize.width: 144
            sourceSize.height: 144
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
            opacity: 0.9
        }
        Text { text: empty.title; font.family: Theme.fontCore; font.pixelSize: Theme.sizeSectionTitle; font.weight: Font.ExtraBold; color: Theme.ink; Layout.alignment: Qt.AlignHCenter }
        Text { text: empty.body; font.family: Theme.fontCore; font.pixelSize: Theme.sizeBodySmall; color: Theme.ink55; Layout.alignment: Qt.AlignHCenter; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; Layout.maximumWidth: 420 }
        HoltButton { visible: empty.actionText !== ""; text: empty.actionText; small: true; Layout.alignment: Qt.AlignHCenter; Layout.topMargin: Theme.space2; onClicked: empty.action() }
    }
}
