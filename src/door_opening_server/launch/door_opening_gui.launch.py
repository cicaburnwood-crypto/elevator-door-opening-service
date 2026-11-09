from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    share=Path(get_package_share_directory('door_opening_server'))
    return LaunchDescription([
        DeclareLaunchArgument('image_topic',default_value='/camera/color/image_raw'),
        DeclareLaunchArgument('provider',default_value='auto'),
        DeclareLaunchArgument('threshold',default_value='0.47'),
        DeclareLaunchArgument('frame_timeout_sec',default_value='1.0'),
        DeclareLaunchArgument('model_path',default_value=str(share/'models/elevator_epoch5.onnx')),
        DeclareLaunchArgument('max_frame_age_sec',default_value='0.25'),
        DeclareLaunchArgument('intra_op_threads',default_value='4'),
        DeclareLaunchArgument('image_reliability',default_value='best_effort'),
        DeclareLaunchArgument('gui_host',default_value='127.0.0.1'),
        DeclareLaunchArgument('gui_port',default_value='8878'),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(share/'launch/door_opening.launch.py')),
             launch_arguments={'image_topic':LaunchConfiguration('image_topic'),
                               'provider':LaunchConfiguration('provider'),
                               **{n:LaunchConfiguration(n) for n in ('threshold','frame_timeout_sec','model_path','max_frame_age_sec','intra_op_threads','image_reliability')}}.items()),
        Node(package='door_opening_server',executable='door_opening_gui',name='door_opening_gui',
             output='screen',parameters=[{'image_topic':LaunchConfiguration('image_topic'),
                                         'gui_host':LaunchConfiguration('gui_host'),
                                         'gui_port':ParameterValue(LaunchConfiguration('gui_port'),value_type=int)}])])
