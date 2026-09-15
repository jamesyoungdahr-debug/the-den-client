import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "holt"

// Server URL + sign-in: "Sign in with Plex" (PIN flow in the system browser) first,
// local account second. Shown until the backend reports we may browse.
HoltPage {
    id: page
    objectName: "loginPage"
    title: "Sign in"
    padding: 0

    Component.onCompleted: discoveredServers.start()
    Component.onDestruction: discoveredServers.stop()

    Connections {
        target: apiClient
        function onLoginFailed(message) { banner.showError(message) }
    }

    Item {
        implicitHeight: Math.max(card.implicitHeight + 2 * Theme.space6, page.height)

        GlassPanel {
            id: card
            strong: true
            width: Math.min(440, page.width - 2 * Theme.space4)
            anchors.centerIn: parent
            padding: Theme.space5

            ColumnLayout {
                width: parent.width
                spacing: Theme.space3

                RowLayout {
                    spacing: 12
                    OtterMark { markSize: 44 }
                    ColumnLayout {
                        spacing: 0
                        Text { text: "The Den"; font.family: Theme.fontCore; font.weight: Font.Black; font.pixelSize: 26; font.letterSpacing: -1; color: Theme.ink }
                        Eyebrow { text: "part of HoltOS" }
                    }
                }

                StatusBanner { id: banner }

                // ---- servers on this network ----
                ColumnLayout {
                    visible: discoveredServers.count > 0 || !discoveredServers.available
                    Layout.fillWidth: true
                    spacing: Theme.space2

                    Eyebrow { text: "Servers on this network"; accent: false }

                    Loader {
                        active: discoveredServers.available && discoveredServers.count > 0
                        Layout.fillWidth: true
                        sourceComponent: ColumnLayout {
                            width: parent.width
                            spacing: 4
                            Repeater {
                                model: discoveredServers
                                HoltButton {
                                    kind: "secondary"
                                    text: model.name + "  ·  " + model.url
                                    onClicked: { urlField.text = model.url; apiClient.baseUrl = model.url; apiClient.checkHealth() }
                                }
                            }
                        }
                    }

                    Meta {
                        visible: !discoveredServers.available
                        text: "LAN discovery isn't available on this computer (python-zeroconf is missing)."
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                    }
                }

                Field {
                    label: "Server"
                    HoltTextField {
                        id: urlField
                        text: apiClient.baseUrl
                        placeholderText: "http://den.local:40204"
                        onAccepted: { apiClient.baseUrl = text; apiClient.checkHealth() }
                    }
                }
                RowLayout {
                    spacing: 8
                    HoltButton { text: apiClient.connected ? "Reconnect" : "Connect"; kind: apiClient.connected ? "secondary" : "primary"; enabled: !apiClient.busy; onClicked: { apiClient.baseUrl = urlField.text; apiClient.checkHealth() } }
                    Badge {
                        tone: apiClient.connected ? "available" : (apiClient.busy ? "processing" : "missing")
                        label: apiClient.connected ? "connected" : (apiClient.busy ? "checking" : "offline")
                    }
                    Item { Layout.fillWidth: true }
                }
                Meta { visible: !apiClient.connected && apiClient.statusText !== "Not connected"; text: apiClient.statusText; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone }

                // ---- trust panel (new server certificate) ----
                ColumnLayout {
                    visible: apiClient.pendingPin !== ""
                    Layout.fillWidth: true
                    spacing: Theme.space2

                    Eyebrow { text: "New server certificate"; accent: false }

                    Meta {
                        text: "Compare this pin with Settings > Remote access on " + apiClient.pendingServer + ". Trust it only if they match."
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                    }

                    TextEdit {
                        text: apiClient.pendingPin
                        font.family: "JetBrains Mono"
                        wrapMode: Text.WrapAnywhere
                        readOnly: true
                        selectByMouse: true
                        Layout.fillWidth: true
                        color: Theme.ink
                    }

                    RowLayout {
                        spacing: 8
                        HoltButton { kind: "primary"; text: "Trust this server"; onClicked: apiClient.trustPendingPin() }
                        HoltButton { kind: "secondary"; text: "Cancel"; onClicked: apiClient.rejectPendingPin() }
                    }
                }

                // ---- refusal panel (pin problem) ----
                ColumnLayout {
                    visible: apiClient.pinProblem !== ""
                    Layout.fillWidth: true
                    spacing: Theme.space2

                    Meta {
                        text: apiClient.pinProblem
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                    }

                    HoltButton { kind: "secondary"; text: "Forget the saved key"; onClicked: apiClient.forgetPin() }
                }

                // ---- sign-in, once connected ----
                ColumnLayout {
                    visible: apiClient.connected
                    Layout.fillWidth: true
                    spacing: Theme.space3

                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder }

                    ColumnLayout {
                        visible: !apiClient.plexWaiting
                        spacing: 8
                        Layout.fillWidth: true
                        HoltButton {
                            Layout.fillWidth: true
                            kind: "primary"
                            text: "Sign in with Plex"
                            enabled: !apiClient.busy
                            onClicked: apiClient.startPlexLogin()
                        }
                        Meta { text: "Opens plex.tv in your browser; come back here once you've approved it."; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone }
                    }
                    GlassPanel {
                        visible: apiClient.plexWaiting
                        Layout.fillWidth: true
                        ColumnLayout {
                            width: parent.width
                            spacing: 8
                            Eyebrow { text: "Waiting for plex.tv" }
                            Text { text: "Approve the link in your browser. Your code is " + apiClient.plexCode + "."; font.family: Theme.fontCore; font.pixelSize: 13; color: Theme.ink70; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            RowLayout {
                                HoltButton { small: true; text: "Open plex.tv again"; onClicked: apiClient.openPlexAuth() }
                                HoltButton { small: true; kind: "quiet"; text: "Cancel"; onClicked: apiClient.cancelPlexLogin() }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder }
                        Eyebrow { text: "or a local account"; accent: false }
                        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder }
                    }

                    Field { label: "Username"; HoltTextField { id: userField; onAccepted: passField.forceActiveFocus() } }
                    Field { label: "Password"; HoltTextField { id: passField; echoMode: TextInput.Password; onAccepted: apiClient.login(userField.text, passField.text) } }
                    HoltButton { text: "Sign in"; enabled: !apiClient.busy && userField.text.length > 0 && passField.text.length > 0; onClicked: apiClient.login(userField.text, passField.text) }
                }
            }
        }
    }
}
