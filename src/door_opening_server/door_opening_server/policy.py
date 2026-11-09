"""Latch exactly one fresh RGB acquisition per request."""
from dataclasses import dataclass
import math
from typing import Any

@dataclass(frozen=True)
class Sample:
    stamp_ns: int
    image: Any

class SingleFrameCapture:
    def __init__(self, start_monotonic, start_ros_ns, max_age_ns, timeout_sec):
        self.start_monotonic = start_monotonic
        self.start_ros_ns = start_ros_ns
        self.max_age_ns = max_age_ns
        self.timeout_sec = timeout_sec
        self.sample = None

    def offer(self, image, stamp_ns, received_monotonic, now_ros_ns):
        if self.sample is not None:
            return False
        if not 0 <= received_monotonic - self.start_monotonic < self.timeout_sec:
            return False
        if stamp_ns <= 0 or stamp_ns < self.start_ros_ns:
            return False
        if not 0 <= now_ros_ns - stamp_ns <= self.max_age_ns:
            return False
        self.sample = Sample(stamp_ns, image)
        return True

def opening_percent(probability, threshold):
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        return 0.0
    if not math.isfinite(threshold) or not 0 < threshold < 1:
        return 0.0
    return 100.0 if probability > threshold else 0.0
