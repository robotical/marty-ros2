"""Decode the Pi's H.264 stream on the workstation; publish each fresh frame once."""

from queue import Empty, Full, Queue
from threading import Event, Thread

import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


class CameraReceiver(Node):
    def __init__(self):
        super().__init__('camera_receiver')
        self.source = self.declare_parameter('source', '').value
        self.frame_id = self.declare_parameter('frame_id', 'marty_camera_optical_frame').value
        rate = float(self.declare_parameter('publish_rate_hz', 10.0).value)
        if not self.source or not 1.0 <= rate <= 60.0:
            raise ValueError('Set source to the stream URL and publish_rate_hz between 1 and 60')
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)
        self.publisher = self.create_publisher(Image, 'image_raw', qos)
        self.frames = Queue(maxsize=1)
        self.stopping = Event()
        self.timer = self.create_timer(1.0 / rate, self.publish_frame)
        self.worker = Thread(target=self.capture, daemon=True)
        self.worker.start()

    def capture(self):
        while not self.stopping.is_set():
            capture = cv2.VideoCapture()
            try:
                opened = capture.open(self.source, cv2.CAP_FFMPEG, [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000,
                ])
                if not opened:
                    raise RuntimeError('Cannot open camera stream')
                self.get_logger().info(f'Camera stream connected: {self.source}')
                while not self.stopping.is_set():
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        raise RuntimeError('Camera stream interrupted')
                    item = (self.get_clock().now().to_msg(), frame)
                    try:
                        self.frames.get_nowait()
                    except Empty:
                        pass
                    try:
                        self.frames.put_nowait(item)
                    except Full:
                        pass
            except (cv2.error, RuntimeError) as error:
                if not self.stopping.is_set():
                    self.get_logger().warning(f'{error}; reconnecting in 2 seconds')
            finally:
                capture.release()
                # A disconnected camera must not leave a cached image to republish.
                try:
                    self.frames.get_nowait()
                except Empty:
                    pass
            self.stopping.wait(2.0)

    def publish_frame(self):
        try:
            stamp, frame = self.frames.get_nowait()
        except Empty:
            return
        message = Image()
        message.header.stamp = stamp  # Receipt time on this workstation, not sensor exposure time.
        message.header.frame_id = self.frame_id
        message.height, message.width = frame.shape[:2]
        message.encoding = 'bgr8'
        message.is_bigendian = False
        message.step = message.width * 3
        message.data = frame.tobytes()
        self.publisher.publish(message)

    def destroy_node(self):
        self.stopping.set()
        self.worker.join(timeout=9.0)
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = CameraReceiver()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
