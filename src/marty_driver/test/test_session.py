"""Movement lifecycle and failure cases using a threaded SDK boundary fixture."""

import threading
import time

import pytest
from marty_driver.motion import Motion
from marty_driver.session import Session
from marty_driver.telemetry import battery_values, joint_mapping, servo_values


def wait_for(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate(), 'Condition did not become true'


class FakeSDK:
    def __init__(self):
        self.callback = None
        self.ready = True
        self.silent = False
        self.status_silent = False
        self.stop_ok = True
        self.accept = True
        self.until = 0.0
        self.calls = []
        self.closed = threading.Event()
        self.ack_gate = None
        self.thread = threading.Thread(target=self._emit, daemon=True)
        self.thread.start()

    def register_publish_callback(self, callback):
        self.callback = callback

    def _emit(self):
        while not self.closed.wait(0.03):
            if self.callback and not self.silent:
                self.callback(121)
                if not self.status_silent:
                    self.callback(124)

    def get_accelerometer(self):
        return [0.0, 0.0, 1.0]

    def get_robot_status(self):
        moving = time.monotonic() < self.until
        return {'isMoving': moving, 'isPaused': False, 'workQCount': int(moving)}

    def get_joints(self):
        return {}

    def get_power_status(self):
        return {}

    def is_conn_ready(self):
        return self.ready

    def move_joint(self, *args, **kwargs):
        self.calls.append(('move', args, kwargs))
        self.until = time.monotonic() + kwargs['move_time'] / 1000
        if self.ack_gate:
            self.ack_gate.wait(2)
        return self.accept

    def stop(self, mode):
        self.calls.append(('stop', mode))
        if self.stop_ok:
            self.until = 0.0
        return self.stop_ok

    def close(self):
        self.closed.set()
        self.thread.join(1)


@pytest.fixture
def fixture():
    instances = []

    def factory(*args):
        sdk = FakeSDK()
        instances.append(sdk)
        return sdk

    session = Session(locator='fixture', factory=factory, stale_after=0.2,
                      reconnect_interval=0.1, completion_margin=0.5)
    assert session.connect().result(2)
    wait_for(lambda: session.status()['motion_status_valid'])
    yield session, instances
    session.close()


def test_acknowledgement_is_not_completion_and_busy_goals_are_rejected(fixture):
    session, instances = fixture
    ticket = session.reserve(Motion(4, move_time_ms=400))
    session.start(ticket)
    wait_for(lambda: ticket.acknowledged_at is not None)
    assert not ticket.result.done()
    with pytest.raises(RuntimeError, match='already'):
        session.reserve(Motion(4))
    assert ticket.result.result(3)[0]
    assert instances[0].calls[0][2]['blocking'] is False


def test_cancel_clears_movement_and_requires_idle_status(fixture):
    session, instances = fixture
    ticket = session.reserve(Motion(4, move_time_ms=2000))
    session.start(ticket)
    wait_for(lambda: ticket.acknowledged_at is not None)
    assert session.stop(ticket, 'canceled').result(1)
    success, outcome, message = ticket.result.result(1)
    assert not success and outcome == 'canceled'
    assert 'idle status confirmed' in message
    assert instances[0].calls[-1] == ('stop', 'clear and stop')


def test_stop_before_dispatch_never_sends_the_movement(fixture):
    session, instances = fixture
    ticket = session.reserve(Motion(4))
    assert session.stop(ticket, 'canceled').result(1)
    session.start(ticket)
    assert ticket.result.result(1)[1] == 'canceled'
    assert all(c[0] != 'move' for c in instances[0].calls)


def test_slow_ack_leaves_telemetry_and_status_responsive(fixture):
    session, instances = fixture
    gate = threading.Event()
    instances[0].ack_gate = gate
    ticket = session.reserve(Motion(4, move_time_ms=1000))
    session.start(ticket)
    wait_for(lambda: instances[0].calls)
    before = session.status()['telemetry_age_seconds']
    time.sleep(0.1)
    assert session.status()['telemetry_age_seconds'] < 0.1
    assert before < 0.1
    stop = session.stop(ticket)
    gate.set()
    assert stop.result(1)
    assert ticket.result.result(1)[1] == 'stopped'


def test_stale_robot_status_aborts_even_when_accel_remains_live(fixture):
    session, instances = fixture
    ticket = session.reserve(Motion(4, move_time_ms=2000))
    session.start(ticket)
    wait_for(lambda: ticket.acknowledged_at is not None)
    instances[0].status_silent = True
    assert ticket.result.result(2)[1] == 'failed'
    assert session.status()['connected']
    with pytest.raises(RuntimeError):
        session.reserve(Motion(4))


def test_disconnect_loss_reconnect_and_old_callbacks_are_ignored(fixture):
    session, instances = fixture
    old = instances[0]
    generation = session.generation
    ticket = session.reserve(Motion(4, move_time_ms=2000))
    session.start(ticket)
    wait_for(lambda: ticket.acknowledged_at is not None)
    old.silent = True
    assert not ticket.result.result(2)[0]
    wait_for(lambda: len(instances) == 2 and session.status()['motion_status_valid'])
    assert session.generation > generation
    assert session.active is None
    assert not any(c[0] == 'move' for c in instances[1].calls)
    old.callback(121)
    assert all(s.generation == session.generation for s in session.drain())
    assert session.disconnect().result(1)
    time.sleep(0.3)
    assert len(instances) == 2
    assert not session.status()['connected']


def test_rejected_or_lost_ack_stops_possible_motion(fixture):
    session, instances = fixture
    instances[0].accept = False
    ticket = session.reserve(Motion(4))
    session.start(ticket)
    assert ticket.result.result(2)[1] == 'failed'
    assert instances[0].calls[-1][0] == 'stop'


def test_stop_rejection_aborts_and_latches_motion_fault(fixture):
    session, instances = fixture
    ticket = session.reserve(Motion(4, move_time_ms=1000))
    session.start(ticket)
    wait_for(lambda: ticket.acknowledged_at is not None)
    instances[0].stop_ok = False
    assert not session.stop(ticket, 'canceled').result(1)
    assert ticket.result.result(1)[1] == 'failed'
    with pytest.raises(RuntimeError):
        session.reserve(Motion(4))
    instances[0].stop_ok = True


def test_movement_timeout_stops_the_robot(fixture):
    session, instances = fixture
    ticket = session.reserve(Motion(4, move_time_ms=100))
    session.start(ticket)
    wait_for(lambda: ticket.acknowledged_at is not None)
    instances[0].until = time.monotonic() + 20
    assert ticket.result.result(2)[1] == 'timeout'


@pytest.mark.parametrize('motion', [Motion(99), Motion(0, num_steps=0),
    Motion(0, num_steps=2, side='left'), Motion(0, turn_degrees=101),
    Motion(0, step_length_mm=100), Motion(1, side='auto'),
    Motion(4, joint_id=9), Motion(4, position_degrees=91), Motion(4, move_time_ms=0)])
def test_invalid_requests(motion):
    with pytest.raises(ValueError):
        motion.validate()


def test_units_validity_and_calibrated_joint_mapping():
    mapping = joint_mapping('{"0":{"name":"hip","sign":-1,"offset_rad":0.1}}')
    values = servo_values({0: {'pos': 30, 'current': 120, 'commsOK': True, 'flags': 129},
                           1: {'pos': -32768, 'current': -32768, 'commsOK': True}}, mapping)
    assert values[0]['position_radians'] == pytest.approx(-0.5235987756 + 0.1)
    assert values[0]['current_amperes'] == pytest.approx(0.12)
    assert str(values[1]['position_radians']) == 'nan'
    assert battery_values({'battInfoValid': False}) is None
    battery = battery_values({'battInfoValid': True, 'battRemainCapacityPercent': 75,
                              'battCurrentMA': -200, 'battRemainCapacityMAH': 600})
    assert battery['percentage'] == 0.75
    assert battery['current'] == pytest.approx(-0.2)
    assert battery['charge'] == pytest.approx(0.6)


def test_bad_mapping_is_rejected():
    with pytest.raises(ValueError):
        joint_mapping('{"0":{"name":"eyes"}}')
    with pytest.raises(ValueError):
        joint_mapping('{"0":{"sign":0}}')
