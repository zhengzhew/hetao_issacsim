"""Read-only STS3215 acquisition: 1 Mbps, little-endian position registers.

Verified on the six STS3215 servos of the yellow leader arm. This module
only constructs READ instructions; it never changes torque, offsets or IDs.
"""
import json
import time


def read_packet(sid, address=56, length=2):
    if type(sid) is not int or not 1 <= sid <= 6 or (address, length) not in ((3, 2), (56, 2)):
        raise ValueError('Only model/position reads for servo IDs 1..6 are supported')
    body = bytes((sid, 4, 2, address, length))
    return b'\xff\xff' + body + bytes((~sum(body) & 255,))


def take_reply(buffer, sid, request=None):
    while len(buffer) >= 2:
        if buffer[:2] != b'\xff\xff':
            del buffer[0]
            continue
        if len(buffer) < 4:
            return None
        # Two-byte reads have length 4; an error can return a shorter status.
        if not 2 <= buffer[3] <= 4:
            del buffer[0]
            continue
        size = buffer[3] + 4
        if len(buffer) < size:
            return None
        frame = bytes(buffer[:size])
        if sum(frame[2:]) & 255 != 255:
            del buffer[0]
            continue
        del buffer[:size]
        if request is not None and frame == request:
            continue
        if frame[2] != sid:
            continue
        if frame[4]:
            raise ValueError(f'飞特舵机 ID {sid} 返回错误状态 0x{frame[4]:02x}')
        if frame[3] != 4:
            raise ValueError(f'飞特舵机 ID {sid} 返回的位置数据长度不正确')
        return int.from_bytes(frame[5:7], 'little')
    return None


class FeetechReader:
    def __init__(self, port):
        import serial
        self.port = serial.Serial(port=None, baudrate=1_000_000, timeout=.002, write_timeout=.3)
        self.port.dtr = False
        self.port.rts = False
        self.port.port = port
        self.models = []

    def open(self):
        self.port.open()
        try:
            self.models = [self.read(sid, 3, 2) for sid in range(1, 7)]
            if self.models != [777] * 6:
                raise ValueError('当前飞特版本仅支持已验证的 STS3215（型号 777），读到：' + str(self.models))
        except Exception:
            self.close()
            raise

    def close(self):
        self.port.close()

    def read(self, sid, address=56, length=2):
        packet = read_packet(sid, address, length)
        for attempt in range(3):
            try:
                return self._read_once(sid, address, packet)
            except TimeoutError:
                if attempt == 2:
                    raise
                print(json.dumps({'event':'serial-read-retry','id':sid,'attempt':attempt + 2}), flush=True)

    def _read_once(self, sid, address, packet):
        self.port.reset_input_buffer()
        self.port.write(packet)
        self.port.flush()
        buffer = bytearray()
        end = time.perf_counter() + .12
        while time.perf_counter() < end:
            buffer.extend(self.port.read(self.port.in_waiting or 1))
            value = take_reply(buffer, sid, packet)
            if value is not None:
                if address == 56 and not 0 <= value < 4096:
                    raise ValueError(f'飞特舵机 ID {sid} 位置超出范围：{value}')
                return value
        register = '型号' if address == 3 else '位置'
        raise TimeoutError(f'飞特舵机 ID {sid} 无有效{register}响应；请检查主臂供电、USB 和舵机连接（1000000 波特率）')

    def positions(self):
        return [self.read(sid) for sid in range(1, 7)]
