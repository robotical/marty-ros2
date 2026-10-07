"""One SDK connection and command lane; fresh telemetry drives motion completion."""

import itertools
import math
import queue
import threading
import time
from collections import deque
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass, field
from functools import partial

from .sdk import open_marty

TOPICS = {120: 'servos', 121: 'accel', 122: 'power', 124: 'robot'}


@dataclass(frozen=True)
class Sample:
    topic: int
    data: object
    generation: int
    received: float
    stamp_ns: int


@dataclass
class Ticket:
    motion: object
    generation: int
    result: Future = field(default_factory=Future)
    sent_at: float | None = None
    acknowledged_at: float | None = None
    seen_moving: bool = False
    idle_since: float | None = None
    stop_reason: str = ''
    stop_acknowledged_at: float | None = None
    stopping: bool = False


class Session:
    """Serialize SDK calls while its receive thread only captures decoded samples."""

    def __init__(self, *, method='usb', locator='', rate_hz=10.0, baud=115200, port=80,
                 stale_after=2.0, reconnect_interval=2.0, auto_reconnect=True,
                 completion_margin=5.0, factory=open_marty, stamp=time.time_ns):
        if method not in ('usb', 'wifi', 'exp') or not locator:
            raise ValueError('Provide usb/wifi/exp and an explicit locator')
        if not 1 <= rate_hz <= 50 or baud <= 0 or not 1 <= port <= 65535:
            raise ValueError('Invalid connection parameters')
        if any(not math.isfinite(v) or v <= 0
               for v in (stale_after, reconnect_interval, completion_margin)):
            raise ValueError('Timeouts must be positive')
        self.config = (method, locator, rate_hz, baud, port)
        self.stale_after = stale_after
        self.reconnect_interval = reconnect_interval
        self.auto_reconnect = auto_reconnect
        self.completion_margin = completion_margin
        self.factory, self.stamp = factory, stamp
        self.lock = threading.RLock()
        self.state = 'disconnected'
        self.error = ''
        self.generation = 0
        self.sdk = None
        self.active = None
        self.enabled = False
        self.latest = {}
        self.samples = deque(maxlen=256)
        self.dropped_samples = 0
        self._stop_pending = 0
        self._motion_fault = False
        self._connected_at = 0.0
        self._next_connect = 0.0
        self._tasks = queue.PriorityQueue(maxsize=16)
        self._counter = itertools.count()
        self._quit = threading.Event()
        self.worker = threading.Thread(target=self._run, name='marty-command-worker', daemon=True)
        self.worker.start()

    def _submit(self, callback, priority=5):
        future = Future()
        try:
            self._tasks.put_nowait((priority, next(self._counter), callback, future))
        except queue.Full:
            future.set_exception(RuntimeError('Driver command queue is full'))
        return future

    def connect(self):
        with self.lock:
            if self.state in ('connecting', 'disconnecting'):
                f = Future()
                f.set_exception(RuntimeError('A connection transition is in progress'))
                return f
            self.enabled = True
            if self.sdk is not None:
                f = Future()
                f.set_result(self.status()['connected'])
                return f
            self.state = 'connecting'
            return self._submit(self._connect)

    def disconnect(self):
        with self.lock:
            self.enabled = False
            self.state = 'disconnecting'
            if self.active:
                self.active.stop_reason = 'disconnected'
            return self._submit(lambda: self._disconnect('Disconnected by request'), priority=0)

    def stop(self, ticket=None, reason='stopped'):
        with self.lock:
            if ticket is not None and ticket is not self.active:
                f = Future()
                f.set_result(False)
                return f
            target = self.active
            if target:
                target.stop_reason = reason
            self._stop_pending += 1
            future = self._submit(lambda: self._requested_stop(target), priority=0)
            if future.done():
                self._stop_pending -= 1
                if target:
                    self._motion_fault = True
                    self._finish(target, False, 'failed', 'Stop command queue is full')
            return future

    def _requested_stop(self, target):
        try:
            return self._stop(target)
        finally:
            with self.lock:
                self._stop_pending -= 1

    def reserve(self, motion):
        motion.validate()
        with self.lock:
            status = self.status()
            robot = self.latest.get(124)
            if not status['connected'] or not status['motion_status_valid']:
                raise RuntimeError('Connection and fresh robot status are required')
            if self.active or self._stop_pending or self._motion_fault:
                raise RuntimeError('A movement or stop is already in progress')
            if status['moving'] or status['paused'] or status['queued_movements'] != 0:
                raise RuntimeError('Marty must have an idle, unpaused, empty movement queue')
            if robot.data.get('isFwUpdating', False):
                raise RuntimeError('Marty is updating firmware')
            self.active = Ticket(motion, self.generation)
            return self.active

    def start(self, ticket):
        future = self._submit(lambda: self._send_motion(ticket))
        if future.done() and future.exception():
            with self.lock:
                self._finish(ticket, False, 'failed', str(future.exception()))

    def drain(self):
        with self.lock:
            result = list(self.samples)
            self.samples.clear()
            return result

    def status(self):
        with self.lock:
            now = time.monotonic()
            age = now - max((s.received for s in self.latest.values()), default=now)
            robot = self.latest.get(124)
            robot_age = now - robot.received if robot else float('inf')
            fresh = bool(self.latest) and age <= self.stale_after
            valid = robot is not None and robot_age <= self.stale_after
            connected = self.state == 'ready' and fresh
            return {
                'generation': self.generation, 'connection_state': self.state,
                'connected': connected, 'telemetry_fresh': fresh,
                'motion_status_valid': valid,
                'moving': bool(robot.data.get('isMoving')) if valid else False,
                'paused': bool(robot.data.get('isPaused')) if valid else False,
                'queued_movements': int(robot.data.get('workQCount', -1)) if valid else -1,
                'telemetry_age_seconds': age if self.latest else float('inf'),
                'motion_status_age_seconds': robot_age,
                'dropped_samples': self.dropped_samples, 'last_error': self.error,
            }

    def close(self):
        if self._quit.is_set():
            return
        self.disconnect().result(timeout=30)
        self._quit.set()
        self.worker.join(timeout=2)
        if self.worker.is_alive():
            raise RuntimeError('Marty command worker did not stop')

    def _connect(self):
        with self.lock:
            if not self.enabled:
                self.state = 'disconnected'
                return False
            self.state = 'connecting'
            self.generation += 1
            generation = self.generation
            self.latest.clear()
            self.samples.clear()
        sdk = None
        try:
            sdk = self.factory(*self.config)
            with self.lock:
                abandoned = not self.enabled
                if abandoned:
                    self.state = 'disconnected'
                else:
                    self.sdk = sdk
                    self.state = 'ready'
                    self.error = ''
                    self._motion_fault = False
                    self._connected_at = time.monotonic()
            if abandoned:
                sdk.close()
                return False
            sdk.register_publish_callback(lambda topic: self._capture(sdk, generation, topic))
            return True
        except Exception as exc:
            if sdk:
                sdk.close()
            with self.lock:
                self.sdk = None
                self.state, self.error = 'disconnected', str(exc)
                self._next_connect = time.monotonic() + self.reconnect_interval
            return False

    def _capture(self, sdk, generation, topic):
        if topic not in TOPICS:
            return
        getters = {120: sdk.get_joints, 121: sdk.get_accelerometer,
                   122: sdk.get_power_status, 124: sdk.get_robot_status}
        try:
            data = deepcopy(getters[topic]())
            if topic in (120, 122, 124) and not data:
                return
            sample = Sample(topic, data, generation, time.monotonic(), self.stamp())
            with self.lock:
                if sdk is not self.sdk or generation != self.generation:
                    return
                self.latest[topic] = sample
                if len(self.samples) == self.samples.maxlen:
                    self.dropped_samples += 1
                self.samples.append(sample)
                ticket = self.active
                if topic == 124 and ticket and ticket.sent_at is not None:
                    if sample.received >= ticket.sent_at and data.get('isMoving'):
                        ticket.seen_moving = True
        except Exception as exc:
            with self.lock:
                self.error = f'Telemetry capture failed: {exc}'

    def _send_motion(self, ticket):
        with self.lock:
            if ticket is not self.active or ticket.result.done():
                return
            if ticket.stop_reason:
                return
            status = self.status()
            if ticket.generation != self.generation or not status['connected']:
                self._finish(ticket, False, 'failed', 'Connection changed before command dispatch')
                return
            if not status['motion_status_valid'] or status['moving'] or status['paused'] or (
                status['queued_movements'] != 0
            ):
                self._finish(ticket, False, 'failed', 'Marty became unavailable or busy')
                return
            sdk = self.sdk
            ticket.sent_at = time.monotonic()
        try:
            accepted = ticket.motion.send(sdk)
        except Exception as exc:
            accepted = False
            with self.lock:
                self.error = str(exc)
        with self.lock:
            if accepted:
                ticket.acknowledged_at = time.monotonic()
            else:
                # A lost acknowledgement is ambiguous: clear possible firmware work.
                ticket.stop_reason = 'failed'
        if not accepted:
            self._stop(ticket)

    def _stop(self, target):
        try:
            with self.lock:
                sdk = self.sdk
                if target and target.result.done():
                    target = None
                if target:
                    target.stopping = True
            accepted = bool(sdk and sdk.stop('clear and stop'))
            with self.lock:
                if target:
                    if accepted:
                        target.stop_acknowledged_at = time.monotonic()
                    else:
                        self._motion_fault = True
                        self._finish(target, False, 'failed', 'Stop was not acknowledged')
                if not accepted:
                    self.error = 'Stop was not acknowledged; motion may still be running'
            return accepted
        except Exception as exc:
            with self.lock:
                self.error = f'Stop failed: {exc}'
                self._motion_fault = True
                if target:
                    self._finish(target, False, 'failed', self.error)
            return False

    def _finish(self, ticket, success, outcome, message):
        if not ticket.result.done():
            ticket.result.set_result((success, outcome, message))
        if self.active is ticket:
            self.active = None

    def _disconnect(self, reason):
        with self.lock:
            sdk, self.sdk = self.sdk, None
            self.state = 'disconnecting'
            target = self.active
            self.generation += 1
            self.latest.clear()
            self.samples.clear()
            if target:
                self._finish(target, False, 'failed', reason)
        stopped = True
        try:
            if sdk:
                stopped = bool(sdk.stop('clear and stop'))
        except Exception:
            stopped = False
        finally:
            if sdk:
                try:
                    sdk.close()
                except Exception as exc:
                    with self.lock:
                        self.error = str(exc)
            with self.lock:
                self.state = 'disconnected'
                self._next_connect = time.monotonic() + self.reconnect_interval
        return stopped

    def _tick(self):
        operation = None
        with self.lock:
            now = time.monotonic()
            sdk, ticket = self.sdk, self.active
            status = self.status()
            if sdk and now - self._connected_at > self.stale_after and (
                not status['telemetry_fresh'] or not sdk.is_conn_ready()
            ):
                self.error = 'Connection lost or telemetry stopped'
                operation = partial(self._disconnect, 'Connection lost or telemetry stopped')
            elif not sdk and self.enabled and self.auto_reconnect and now >= self._next_connect:
                operation = self._connect
        # SDK requests need the receive thread; never hold our lock while waiting.
        if operation:
            operation()
            return
        with self.lock:
            if not ticket or ticket.result.done() or ticket.sent_at is None:
                # A cancellation may arrive before dispatch; stop still needs confirmation.
                if not ticket or ticket.stop_acknowledged_at is None:
                    return
            robot = self.latest.get(124)
            if ticket.stop_acknowledged_at is not None:
                after = ticket.stop_acknowledged_at
                if robot and robot.received > after and status['motion_status_valid'] and (
                    not status['moving'] and status['queued_movements'] == 0
                ):
                    reason = ticket.stop_reason
                    self._finish(ticket, False, reason, f'Movement {reason}; idle status confirmed')
                elif now - after > self.stale_after:
                    self._motion_fault = True
                    self._finish(
                        ticket, False, 'failed', 'Stop accepted but idle status not confirmed'
                    )
                return
            if ticket.stop_reason:
                return
            if not status['motion_status_valid']:
                ticket.stop_reason = 'failed'
                self.error = 'Robot status became stale during movement'
                operation = partial(self._stop, ticket)
            elif now - ticket.sent_at > ticket.motion.duration_seconds + self.completion_margin:
                ticket.stop_reason = 'timeout'
                operation = partial(self._stop, ticket)
        if operation:
            operation()
            return
        with self.lock:
            if ticket.acknowledged_at is None or ticket.stop_reason:
                return
            idle = not status['moving'] and not status['paused'] and (
                status['queued_movements'] == 0 and robot.received > ticket.acknowledged_at
            )
            if not idle:
                ticket.idle_since = None
                return
            if ticket.idle_since is None:
                ticket.idle_since = robot.received
            elapsed = now - ticket.sent_at
            if robot.received - ticket.idle_since >= 0.15 and (
                ticket.seen_moving or elapsed >= ticket.motion.duration_seconds
            ):
                self._finish(ticket, True, 'succeeded', 'Firmware movement queue is idle')

    def _run(self):
        while not self._quit.is_set():
            try:
                _, _, callback, future = self._tasks.get(timeout=0.02)
            except queue.Empty:
                pass
            else:
                try:
                    future.set_result(callback())
                except Exception as exc:
                    future.set_exception(exc)
                    with self.lock:
                        self.error = str(exc)
            try:
                self._tick()
            except Exception as exc:
                with self.lock:
                    self.error = f'Worker failed: {exc}'
                self._disconnect(f'Worker failed: {exc}')
