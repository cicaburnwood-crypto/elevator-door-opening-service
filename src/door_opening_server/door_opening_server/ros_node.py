"""Drop-in Humble service: one fresh frame -> 0.0 or 100.0."""
from pathlib import Path
import json
import math
import threading
import time
from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rcl_interfaces.msg import ParameterDescriptor
from rosidl_runtime_py.utilities import get_service
from sensor_msgs.msg import Image
from std_msgs.msg import String
from .backend import OnnxDoorClassifier, image_to_rgb
from .policy import SingleFrameCapture, opening_percent

SERVICE_NAME = '/inspection/detection_door_opening'
SERVICE_TYPE = 'scan_planner_msgs/srv/DetectDoorOpening'

class DoorOpeningServer(Node):
    def __init__(self, *, predictor=None, **kwargs):
        super().__init__('door_opening_server', **kwargs)
        share = Path(get_package_share_directory('door_opening_server'))
        defaults = dict(image_topic='/camera/color/image_raw',
                        model_path=str(share/'models/elevator_epoch5.onnx'),
                        provider='auto', intra_op_threads=4, max_frame_age_sec=.25,
                        image_reliability='best_effort', threshold=.47, frame_timeout_sec=1.0)
        for name, value in defaults.items():
            self.declare_parameter(name, value, ParameterDescriptor(read_only=True))
        cfg = {name: self.get_parameter(name).value for name in defaults}
        self.threshold = float(cfg['threshold'])
        self.timeout = float(cfg['frame_timeout_sec'])
        max_age = float(cfg['max_frame_age_sec'])
        if not math.isfinite(self.threshold) or not 0 < self.threshold < 1:
            raise ValueError('threshold must be in (0,1)')
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 30:
            raise ValueError('frame_timeout_sec must be in (0,30]')
        if not math.isfinite(max_age) or not 0 < max_age <= 1:
            raise ValueError('max_frame_age_sec must be in (0,1]')
        if not cfg['image_topic'] or cfg['image_reliability'] not in ('best_effort','reliable'):
            raise ValueError('Invalid image_topic/image_reliability')
        if cfg['provider'] not in ('auto','cpu','cuda') or cfg['intra_op_threads'] < 1:
            raise ValueError('Invalid provider/intra_op_threads')
        self.max_age_ns = round(max_age*1e9)
        service_class = get_service(SERVICE_TYPE)
        if service_class.Request().get_fields_and_field_types():
            raise ValueError('DetectDoorOpening request must be empty')
        fields = service_class.Response().get_fields_and_field_types()
        if set(fields) != {'opening_percent'} or fields['opening_percent'] not in ('float','float32'):
            raise ValueError('DetectDoorOpening response must be float32 opening_percent')
        self.predictor = predictor if predictor is not None else OnnxDoorClassifier(
            cfg['model_path'], cfg['provider'], int(cfg['intra_op_threads']))
        self._request_lock = threading.Lock()
        self._capture_lock = threading.Lock()
        self._capture = None
        self._frame_ready = threading.Event()
        self._stopping = threading.Event()
        self._service_group = ReentrantCallbackGroup()
        self._image_group = MutuallyExclusiveCallbackGroup()
        qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                         reliability=ReliabilityPolicy.RELIABLE if cfg['image_reliability']=='reliable' else ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
        self.subscription = self.create_subscription(Image, cfg['image_topic'], self.on_image, qos, callback_group=self._image_group)
        self.details_publisher = self.create_publisher(String, SERVICE_NAME+'/details', 10)
        self.service = self.create_service(service_class, SERVICE_NAME, self.on_request, callback_group=self._service_group)
        self.get_logger().info(f'Ready: {SERVICE_NAME} [{SERVICE_TYPE}]; RGB={cfg["image_topic"]}; one fresh frame; '
                               f'p > {self.threshold} -> 100; wait timeout={self.timeout}s; provider={getattr(self.predictor,"provider","test")}')

    def on_image(self, message):
        received = time.monotonic()
        stamp = message.header.stamp.sec*1_000_000_000 + message.header.stamp.nanosec
        with self._capture_lock:
            if self._capture is not None and self._capture.offer(message, stamp, received, self.get_clock().now().nanoseconds):
                self._frame_ready.set()

    def on_request(self, request, response):
        del request
        response.opening_percent = 0.0
        if not self._request_lock.acquire(blocking=False):
            self.get_logger().warning('Concurrent inspection rejected; returning 0.0')
            return response
        started = time.monotonic()
        details = dict(started_ns=self.get_clock().now().nanoseconds, probabilities=[], threshold=self.threshold,
                       sample_count=0, mean_probability=None, rule='single_frame_gt_threshold', reason='')
        try:
            with self._capture_lock:
                self._frame_ready.clear()
                capture = SingleFrameCapture(time.monotonic(), self.get_clock().now().nanoseconds, self.max_age_ns, self.timeout)
                self._capture = capture
            self._frame_ready.wait(max(0., capture.start_monotonic+self.timeout-time.monotonic()))
            with self._capture_lock:
                self._capture = None
                sample = capture.sample
            if self._stopping.is_set() or sample is None:
                details['reason'] = 'shutdown' if self._stopping.is_set() else 'no_fresh_frame_before_timeout'
                return response
            probability = float(self.predictor.score(image_to_rgb(sample.image)))
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError('Invalid model probability')
            details.update(probabilities=[probability], sample_count=1, mean_probability=probability,
                           stamp_ns=[sample.stamp_ns])
            response.opening_percent = opening_percent(probability, self.threshold)
            return response
        except Exception as error:
            details['reason'] = 'inference_error: '+str(error)
            self.get_logger().error(details['reason'])
            return response
        finally:
            details.update(opening_percent=float(response.opening_percent), duration_s=time.monotonic()-started)
            message = String(); message.data = json.dumps(details, allow_nan=False)
            self.details_publisher.publish(message)
            self.get_logger().info(f'opening_percent={response.opening_percent}; samples={details["sample_count"]}; '
                                   f'p={details["probabilities"]}; reason={details["reason"]}')
            with self._capture_lock:
                self._capture = None
            self._request_lock.release()

    def stop(self):
        self._stopping.set()
        self._frame_ready.set()

def main(args=None):
    rclpy.init(args=args); node=None; executor=MultiThreadedExecutor(num_threads=3)
    try:
        node=DoorOpeningServer(); executor.add_node(node); executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None: node.stop()
        executor.shutdown()
        if node is not None: node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()

if __name__=='__main__': main()
