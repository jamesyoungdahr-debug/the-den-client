import QtQuick

// The HoltOS otter head mark, from the ComfyUI render (use at 38 px and up;
// smaller marks use RingMark).
Image {
    property int markSize: 44
    width: markSize
    height: markSize
    sourceSize.width: markSize * 2
    sourceSize.height: markSize * 2
    fillMode: Image.PreserveAspectFit
    smooth: true
    mipmap: true
    source: Qt.resolvedUrl("../../assets/otter-mark.png")
}
