"""Socket RIC peer: real MartyPy framing, handshake, status and command exchange."""

import asyncio
import json
import struct
import threading
import time
from urllib.parse import parse_qs, urlsplit

from martypy.LikeHDLC import LikeHDLC


async def send_binary(writer, payload):
    size = len(payload)
    header = bytes([0x82, size]) if size < 126 else bytes([0x82, 126]) + struct.pack('>H', size)
    writer.write(header + payload)
    await writer.drain()


async def read_binary(reader):
    header = await reader.readexactly(2)
    opcode, size = header[0] & 15, header[1] & 127
    if size == 126:
        size = struct.unpack('>H', await reader.readexactly(2))[0]
    elif size == 127:
        size = struct.unpack('>Q', await reader.readexactly(8))[0]
    mask = await reader.readexactly(4) if header[1] & 128 else None
    payload = await reader.readexactly(size)
    if mask:
        payload = bytes(v ^ mask[i % 4] for i, v in enumerate(payload))
    return payload if opcode == 2 else b''


def ros_packet(topic, payload):
    size = len(payload)
    low, high = size & 255, size >> 8
    topic_low, topic_high = topic & 255, topic >> 8
    return bytes([255, 254, low, high, 255 - ((low + high) & 255), topic_low, topic_high]) + (
        payload + bytes([255 - ((topic_low + topic_high + sum(payload)) & 255)])
    )


class FirmwarePeer:
    def __init__(self):
        self.ready = threading.Event()
        self.connections = set()
        self.commands = []
        self.until = 0.0
        self.silent = False
        self.status_silent = False
        self.reject_motion = False
        self.reject_stop = False
        self.ack_delay = 0.0
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        assert self.ready.wait(3)

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.server = self.loop.run_until_complete(
            asyncio.start_server(self._client, '127.0.0.1', 0)
        )
        self.port = self.server.sockets[0].getsockname()[1]
        self.ready.set()
        self.loop.run_forever()
        self.loop.close()

    async def _client(self, reader, writer):
        # RIC accepts MartyPy's historical upgrade request without Sec-WebSocket-Key.
        # A standards-strict WebSocket server would reject that actual SDK client.
        await reader.readuntil(b'\r\n\r\n')
        writer.write(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n'
                     b'Connection: Upgrade\r\nSec-WebSocket-Accept: fixture\r\n\r\n')
        await writer.drain()
        self.connections.add(writer)
        decoded = asyncio.Queue()
        decoder = LikeHDLC(decoded.put_nowait, lambda: None)
        subscribed = False

        async def publication():
            while True:
                await asyncio.sleep(0.05)
                if not subscribed or self.silent:
                    continue
                moving = time.monotonic() < self.until
                servos = b''.join(struct.pack('>BhhB', i, 30 if i == 0 else 0, 120, 129)
                                  for i in range(9))
                content = ros_packet(120, servos)
                content += ros_packet(121, struct.pack('>fffBB', 0, 0, 1024, 19, 0))
                content += ros_packet(122, struct.pack('>BBHHhHHB', 75, 25, 600, 800,
                                                       -200, 100, 2, 20))
                if not self.status_silent:
                    content += ros_packet(124, bytes([int(moving), int(moving)]))
                await send_binary(writer, LikeHDLC.encode(bytes([0, 0]) + content))

        async def requests():
            nonlocal subscribed
            while True:
                frame = await decoded.get()
                if len(frame) < 4 or frame[1] & 63 != 2:
                    continue
                request = frame[3:].rstrip(b'\0').decode()
                self.commands.append(request)
                response = {'rslt': 'ok', 'req': request}
                if request == 'v':
                    response.update(SystemName='RIC', SystemVersion='1.3.21')
                elif request == 'hwstatus':
                    response['hw'] = [
                        {'IDNo': i, 'name': name, 'type': 'SmartServo'}
                        for i, name in enumerate(('LeftHip', 'LeftTwist', 'LeftKnee',
                            'RightHip', 'RightTwist', 'RightKnee', 'LeftArm', 'RightArm', 'Eyes'))
                    ] + [{'IDNo': 19, 'name': 'IMU0', 'type': 'IMU'}]
                elif 'subscription' in request:
                    # MartyPy 3.7.2 sends permissive firmware JSON, so don't require
                    # a strict JSON parser to accept the SDK's subscription request.
                    subscribed = '"rateHz":0}' not in request
                elif request.startswith('traj/'):
                    if self.reject_motion:
                        response['rslt'] = 'fail'
                    else:
                        parsed = urlsplit(request)
                        params = parse_qs(parsed.query)
                        duration = int(params.get('moveTime', ['1000'])[0]) / 1000
                        if parsed.path.startswith('traj/step/'):
                            duration *= int(parsed.path.rsplit('/', 1)[1])
                        self.until = time.monotonic() + duration
                    await asyncio.sleep(self.ack_delay)
                elif request == 'robot/stop':
                    if self.reject_stop:
                        response['rslt'] = 'fail'
                    else:
                        self.until = 0.0
                await send_binary(writer, LikeHDLC.encode(
                    bytes([frame[0], 0x42, 1]) + json.dumps(response).encode() + b'\0'
                ))

        tasks = [asyncio.create_task(publication()), asyncio.create_task(requests())]
        try:
            while True:
                data = await read_binary(reader)
                for byte in data:
                    decoder.decodeData(byte)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self.connections.discard(writer)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            writer.close()
            await asyncio.gather(writer.wait_closed(), return_exceptions=True)

    def drop_connections(self):
        async def close_clients():
            writers = list(self.connections)
            for writer in writers:
                writer.close()
            await asyncio.gather(*(writer.wait_closed() for writer in writers),
                                 return_exceptions=True)
        asyncio.run_coroutine_threadsafe(close_clients(), self.loop).result(3)

    def close(self):
        async def shutdown():
            for writer in list(self.connections):
                writer.close()
            await asyncio.gather(*(writer.wait_closed() for writer in list(self.connections)),
                                 return_exceptions=True)
            self.server.close()
            await self.server.wait_closed()
        asyncio.run_coroutine_threadsafe(shutdown(), self.loop).result(3)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(3)
