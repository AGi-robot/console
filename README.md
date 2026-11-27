# Console

External interfaces for AGi systems. Telepathy Console is the first console.
It is outside AIVA's entity; the entity receptor is in
[Telepathy](https://github.com/Project-AGi/telepathy).

The ROS package currently retains the deployment name `telepathic_management`
and executable `telepathic_console`. It serves the WebUI on port 8853.

## Signal flow

The browser submits text or structured requests to `/api/telepathic/send`.
The console backend encodes UTF-8 using Cypher's `ternary_utf8_v1` and publishes
`TelepathicSignal` on `/telepathic/stimulus` through local rosbridge. The receptor
in AIVA decodes it. Response events use `std_msgs/String` on
`/telepathic/response`; AIVA encodes each event's text content with the same
Cypher scheme. Console decodes that content after rosbridge, before relaying
the event to the WebUI. This is encoding, not encryption; browser-to-console
HTTP carries the original text. Canvas WebSocket requests use the same signal
codec.

Console imports only the shared Cypher codec. It does not import HRM, TMS, SCS,
or AIVA's entity modules. The retired AuRoRA settings editor is disabled;
runtime configuration belongs to Shell. Unsupported image/reward topics are
not advertised by the chat page.

## Signal Garden preview

Open **Flow** from the companion header, or visit `/flow`, to explore a
browser-local simulation of the current AIVA conversation and Canvas paths.
AIVA's existing anime artwork anchors an interactive module map. Play, pause,
step, reset, and speed controls animate ROS topics, HTTP/WebSocket connections,
and in-process Python calls. Select a module for its role and interfaces.

This is an illustrative preview: entered prompts stay in the browser and do
not call AIVA or a model. It does not observe live processes or infer module
health. Canvas demonstrates vector tools with an illustrative vision review;
optional MOSS imaging and passive logging are shown as separate branches.
AuRoRA's SCS/HRM/TMS runtime is separate from this AIVA map. No additional
frontend dependencies are needed. Rebuild the Console ROS package and restart
Console to update an installed WebUI.

## Install

Clone beside Shell at `AIVA/console`, link `shell/src/telepathic_management` to
`../../console`, and build with colcon. Start with
`ros2 run telepathic_management telepathic_console`.

The source history is retained through a merge of the former Telepathy repository.

## Automatic activity lighting

Console uses OpenRGB only for automatic online/activity lighting. AIVA's model has no lighting controls in this server. Expressive lighting, its editable catalogue, and model tools belong to [Toolbox](https://github.com/Project-AGi/toolbox/blob/dev/LIGHTING.md), used by Agentic and Interactive.

On the same Linux host, both renderers use `AGI_OPENRGB_LOCK_PATH` (default `~/.agi/openrgb-device.lock`). Console yields while an expressive effect holds the device and resumes the latest automatic state after release, including when resting. Run both processes as the same user with the same lock path. Console does not import Toolbox.
