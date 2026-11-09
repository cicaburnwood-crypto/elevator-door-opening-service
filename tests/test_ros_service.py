"""Real DDS requests: one new frame, no fixed one-second wait, failure -> 0."""
import threading,time,json
from pathlib import Path
import numpy as np
import pytest
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.executors import MultiThreadedExecutor
from sensor_msgs.msg import Image
from std_msgs.msg import String
from scan_planner_msgs.srv import DetectDoorOpening
from ament_index_python.packages import get_package_share_directory
from door_opening_server.ros_node import DoorOpeningServer,SERVICE_NAME
from door_opening_server.backend import OnnxDoorClassifier

def wait(predicate,timeout=5):
    deadline=time.monotonic()+timeout
    while not predicate():
        assert time.monotonic()<deadline,'Timed out'
        time.sleep(.002)

class Predictor:
    def __init__(self,p=.8):self.p=p;self.calls=0
    def score(self,rgb):self.calls+=1;return self.p

class Harness:
    def __init__(self,predictor=None,timeout=1.):
        rclpy.init();self.predictor=predictor or Predictor()
        self.server=DoorOpeningServer(predictor=self.predictor,parameter_overrides=[Parameter('image_reliability',value='reliable'),Parameter('frame_timeout_sec',value=timeout)])
        self.client_node=Node('elevator_test_client');self.pub=self.client_node.create_publisher(Image,'/camera/color/image_raw',10)
        self.details=[];self.sub=self.client_node.create_subscription(String,SERVICE_NAME+'/details',lambda msg:self.details.append(json.loads(msg.data)),10)
        self.client=self.client_node.create_client(DetectDoorOpening,SERVICE_NAME)
        self.executor=MultiThreadedExecutor(num_threads=4);self.executor.add_node(self.server);self.executor.add_node(self.client_node)
        self.thread=threading.Thread(target=self.executor.spin,daemon=True);self.thread.start()
        assert self.client.wait_for_service(timeout_sec=5);wait(lambda:self.pub.get_subscription_count()>0)
    def request(self):
        f=self.client.call_async(DetectDoorOpening.Request());wait(lambda:self.server._capture is not None);return f
    def image(self,old=False,encoding='rgb8'):
        msg=Image();msg.height=2;msg.width=2;msg.step=6;msg.encoding=encoding;msg.data=bytes(12)
        msg.header.stamp=self.client_node.get_clock().now().to_msg()
        if old:msg.header.stamp.sec-=5
        self.pub.publish(msg)
    def close(self):
        self.server.stop();self.executor.shutdown();self.thread.join(3)
        self.server.destroy_node();self.client_node.destroy_node();rclpy.shutdown()

@pytest.fixture
def h():
    obj=Harness()
    try:yield obj
    finally:obj.close()

def test_exactly_one_frame_returns_immediately_and_no_reuse(h):
    f=h.request();start=time.monotonic();h.image();wait(f.done)
    assert f.result().opening_percent==100. and time.monotonic()-start<.75
    assert h.predictor.calls==1
    wait(lambda:len(h.details)==1);assert h.details[0]['sample_count']==1
    f=h.request();time.sleep(.05);assert not f.done()
    h.predictor.p=.1;h.image();wait(f.done);assert f.result().opening_percent==0. and h.predictor.calls==2

def test_stale_then_fresh(h):
    f=h.request();h.image(old=True);time.sleep(.05);assert not f.done() and h.predictor.calls==0
    h.image();wait(f.done);assert f.result().opening_percent==100.

def test_no_frame_timeout():
    h=Harness(timeout=.15)
    try:
        f=h.request();wait(f.done);assert f.result().opening_percent==0. and h.predictor.calls==0
        wait(lambda:bool(h.details));assert h.details[-1]['reason']=='no_fresh_frame_before_timeout'
    finally:h.close()

def test_concurrent_rejected(h):
    first=h.request();second=h.client.call_async(DetectDoorOpening.Request());wait(second.done)
    assert second.result().opening_percent==0. and not first.done()
    h.image();wait(first.done);assert first.result().opening_percent==100.

@pytest.mark.parametrize('mode',['invalid_encoding','nan','exception'])
def test_errors_return_zero(h,mode):
    if mode=='nan':h.predictor.p=float('nan')
    if mode=='exception':
        def fail(rgb):raise RuntimeError('test failure')
        h.predictor.score=fail
    f=h.request();h.image(encoding='mono8' if mode=='invalid_encoding' else 'rgb8');wait(f.done)
    assert f.result().opening_percent==0.
    wait(lambda:bool(h.details));assert h.details[-1]['reason'].startswith('inference_error:')

def test_installed_real_onnx():
    path=Path(get_package_share_directory('door_opening_server'))/'models/elevator_epoch5.onnx'
    model=OnnxDoorClassifier(path,'cpu',2)
    assert model.metadata['epoch']==5 and model.metadata['door_id']=='elevator_20261104'
    assert 0<=model.score(np.zeros((360,640,3),dtype=np.uint8))<=1
