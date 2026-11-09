from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

FIELDS = {'image_topic':str, 'provider':str, 'model_path':str, 'intra_op_threads':int,
          'max_frame_age_sec':float, 'image_reliability':str, 'threshold':float, 'frame_timeout_sec':float}

def create_node(context):
    overrides = {}
    for name, kind in FIELDS.items():
        value = LaunchConfiguration(name).perform(context)
        if value != '': overrides[name] = kind(value)
    return [Node(package='door_opening_server', executable='detection_door_opening_server',
                 name='door_opening_server', output='screen',
                 parameters=[LaunchConfiguration('params_file').perform(context), overrides])]

def generate_launch_description():
    share = Path(get_package_share_directory('door_opening_server'))
    return LaunchDescription([
        DeclareLaunchArgument('params_file', default_value=str(share/'config/door_opening.yaml')),
        *[DeclareLaunchArgument(name,default_value='',description='Override YAML/node default') for name in FIELDS],
        OpaqueFunction(function=create_node)])
