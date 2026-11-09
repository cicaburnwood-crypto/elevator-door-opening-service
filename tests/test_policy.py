from types import SimpleNamespace
import numpy as np
import pytest
from door_opening_server.policy import SingleFrameCapture, opening_percent
from door_opening_server.backend import image_to_rgb

@pytest.mark.parametrize('p,expected',[(.8,100.),(.2,0.),(.47,0.),(float('nan'),0.),(float('inf'),0.),(-1.,0.),(1.1,0.)])
def test_threshold(p,expected):
    assert opening_percent(p,.47)==expected

def test_first_fresh_frame_only():
    c=SingleFrameCapture(10.,1_000_000_000,250_000_000,1.)
    assert not c.offer('old',999_999_999,10.1,1_100_000_000)
    assert not c.offer('zero',0,10.1,1_100_000_000)
    assert not c.offer('future',1_200_000_000,10.1,1_100_000_000)
    assert not c.offer('late',1_000_000_001,10.4,1_400_000_000)
    assert c.offer('first',1_500_000_000,10.5,1_500_000_000)
    assert not c.offer('second',1_600_000_000,10.6,1_600_000_000)
    assert c.sample.image=='first'

def test_deadline():
    c=SingleFrameCapture(10.,1,250_000_000,.1)
    assert not c.offer('late',100_000_001,10.11,100_000_001)

def test_bgr_padding():
    msg=SimpleNamespace(encoding='bgr8',width=1,height=2,step=4,data=bytes([1,2,3,0,4,5,6,0]))
    assert image_to_rgb(msg).tolist()==[[[3,2,1]],[[6,5,4]]]
