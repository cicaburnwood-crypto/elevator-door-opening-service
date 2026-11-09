"""Installed launch forwards typed overrides and serves the expected interface."""
import subprocess,os,signal,time

def test_installed_launch():
    process=subprocess.Popen(['ros2','launch','door_opening_server','door_opening.launch.py','provider:=cpu','threshold:=0.5','frame_timeout_sec:=0.2'],stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        deadline=time.monotonic()+20
        while True:
            assert process.poll() is None,'Launch exited'
            query=subprocess.run(['ros2','param','get','/door_opening_server','threshold'],capture_output=True,text=True,timeout=5)
            if query.returncode==0 and '0.5' in query.stdout:break
            assert time.monotonic()<deadline,'Launch readiness timeout'
            time.sleep(.1)
        call=subprocess.run(['ros2','service','call','/inspection/detection_door_opening','scan_planner_msgs/srv/DetectDoorOpening','{}'],capture_output=True,text=True,timeout=10)
        assert call.returncode==0 and 'opening_percent=0.0' in call.stdout
    finally:
        os.killpg(process.pid,signal.SIGINT)
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
