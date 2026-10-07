"""Single-client, loopback-only raw USB relay for ROS in Docker Desktop."""

import argparse
import select
import socket

import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('serial_port')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--port', type=int, default=8785)
    args = parser.parse_args()
    device = serial.Serial(port=None, baudrate=args.baud, timeout=0, write_timeout=1)
    device.port = args.serial_port
    device.rts = device.dtr = False
    device.open()
    try:
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1', args.port))
            server.listen(1)
            print(
                f'USB relay ready: {args.serial_port} at {args.baud}, TCP {args.port}', flush=True
            )
            while True:
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(1)
                    try:
                        while True:
                            if select.select([connection], [], [], 0.01)[0]:
                                content = connection.recv(4096)
                                if not content:
                                    break
                                device.write(content)
                            content = device.read(min(device.in_waiting, 4096))
                            if content:
                                connection.sendall(content)
                    except (ConnectionError, TimeoutError):
                        pass
    finally:
        device.close()


if __name__ == '__main__':
    main()
