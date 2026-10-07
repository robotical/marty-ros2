"""Expose the Mac USB byte relay as a real serial PTY in the Linux container."""

import os
import pty
import select
import socket
import threading
import tty


class USBPTY:
    def __init__(self, host='host.docker.internal', port=8785):
        self.master, self.slave = pty.openpty()
        tty.setraw(self.slave)
        self.path = os.ttyname(self.slave)
        self.socket = socket.create_connection((host, port), timeout=3)
        self.socket.settimeout(1)
        self.closed = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _pump(self):
        try:
            while not self.closed.is_set():
                ready = select.select([self.socket, self.master], [], [], 0.05)[0]
                if self.socket in ready:
                    content = self.socket.recv(4096)
                    if not content:
                        raise ConnectionError('USB relay disconnected')
                    os.write(self.master, content)
                if self.master in ready:
                    self.socket.sendall(os.read(self.master, 4096))
        except (OSError, ConnectionError) as exc:
            self.error = exc

    def close(self):
        self.closed.set()
        self.thread.join(2)
        self.socket.close()
        os.close(self.master)
        os.close(self.slave)
