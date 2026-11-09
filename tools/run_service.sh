#!/usr/bin/env bash
set -euo pipefail
source /opt/ros/humble/setup.bash
source "${DOOR_WS:-$HOME/door_ws}/install/setup.bash"
exec ros2 launch door_opening_server door_opening.launch.py "$@"
