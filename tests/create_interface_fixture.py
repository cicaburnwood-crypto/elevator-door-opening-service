"""Create a test-only interface package; never install this over the robot's planner messages."""
from pathlib import Path
import sys


def create(root):
    root = Path(root); (root / 'srv').mkdir(parents=True, exist_ok=True)
    (root / 'srv/DetectDoorOpening.srv').write_text('---\nfloat32 opening_percent\n')
    (root / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.8)
project(scan_planner_msgs)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME} "srv/DetectDoorOpening.srv")
ament_export_dependencies(rosidl_default_runtime)
ament_package()
''')
    (root / 'package.xml').write_text('''<?xml version="1.0"?>
<package format="3"><name>scan_planner_msgs</name><version>0.0.0</version>
<description>Isolated transport test fixture only</description>
<maintainer email="test@example.com">Test fixture</maintainer><license>Proprietary</license>
<buildtool_depend>ament_cmake</buildtool_depend>
<build_depend>rosidl_default_generators</build_depend>
<exec_depend>rosidl_default_runtime</exec_depend>
<member_of_group>rosidl_interface_packages</member_of_group>
<export><build_type>ament_cmake</build_type></export></package>
''')


if __name__ == '__main__':
    create(sys.argv[1])
