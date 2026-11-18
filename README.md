# Telepathy

**Telepathy** is AGi's shared ROS 2 package for the Web Teleops Console and the transport between the browser interface and an AGi system.

It provides the `telepathic_management` ROS 2 package and the `telepathic_console` executable. The console serves the shared WebUI, connects to rosbridge, and publishes typed `TelepathicSignal` messages to `/telepathic/stimulus`. Each assistant's Telepathic Input Core (TIC) decodes the signal locally and passes the text into its own cognitive system.

The `telepathic_console` executable is a standalone web server packaged in a
ROS 2 package so it can be installed and launched with `ros2 run`. It is not a
ROS node: it communicates with ROS through the rosbridge WebSocket API and does
not create an `rclpy` node.

## Repository contents

This repository is a ROS 2 workspace package at its root. It includes the console backend, frontend, Canvas Studio host UI, and package-level checks.

## Requirements

- ROS 2 Jazzy
- `cryptic_signal_core` from [AGi-Robot/cypher](https://github.com/AGi-robot/cypher)
- rosbridge running at `ws://127.0.0.1:9090` by default
- Python dependencies declared in `package.xml` and `setup.py`

## Install in an assistant workspace

Clone Telepathy and Cypher beside the assistant repository, then link both packages into that workspace's `src` directory. From the workspace root:

```sh
git clone https://github.com/AGi-robot/telepathy.git ../telepathy
git clone https://github.com/AGi-robot/cypher.git ../cypher
ln -s ../../cypher src/cryptic_signal_core
ln -s ../../telepathy src/telepathic_management
```

The repository provides the shared input and UI transport. Assistant-specific chat, memory, and TIC behavior remain in each assistant repository. Build it with the assistant's ROS packages:

```sh
source /opt/ros/jazzy/setup.bash
colcon build --packages-up-to telepathic_management
source install/setup.bash
ros2 run telepathic_management telepathic_console
```

Set `AGI_ROSBRIDGE_URL` to use a different rosbridge WebSocket URL. Set `AGI_WEB_TELEOPS_CONSOLE_INTERFACE_DIR` to override the bundled interface directory. Canvas drawing language and SVG rendering are provided by [Grace Canvas](https://github.com/AGi-robot/canvas).

## License

Telepathy is licensed under **AGPL-3.0-only**. See [LICENSE](LICENSE). The Grace avatar assets have separate terms documented in [`telepathic_management/telepathic_console/backend/static/assets/README.md`](telepathic_management/telepathic_console/backend/static/assets/README.md).
