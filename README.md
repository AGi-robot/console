# Console

External interfaces for AGi systems. Telepathy Console is the first console.
It is outside Grace's entity; the entity receptor is in
[Telepathy](https://github.com/AGi-robot/telepathy).

The ROS package currently retains the deployment name `telepathic_management`
and executable `telepathic_console`. It serves the WebUI on port 8853.

## Signal flow

The browser submits text or structured requests to `/api/telepathic/send`.
The console backend encodes UTF-8 using Cypher's `ternary_utf8_v1` and publishes
`TelepathicSignal` on `/telepathic/stimulus` through local rosbridge. The receptor
in Grace decodes it. This is encoding, not encryption; browser-to-console HTTP
carries the original text. Canvas WebSocket requests use the same signal codec.
Responses stream on `/telepathic/response`.

Console imports only the shared Cypher codec. It does not import HRM, TMS, SCS,
or Grace's entity modules. The retired AuRoRA settings editor is disabled;
runtime configuration belongs to Shell. Unsupported image/reward topics are
not advertised by the chat page.

## Install

Clone beside Shell at `AIVA/console`, link `shell/src/telepathic_management` to
`../../console`, and build with colcon. Start with
`ros2 run telepathic_management telepathic_console`.

The source history is retained through a merge of the former Telepathy repository.
