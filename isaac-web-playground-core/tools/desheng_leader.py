"""Read-only Desheng SE leader to Isaac Sim. No servo writes or torque changes.

Uses the FF FF / FF F5 compatibility read verified on the connected arm.
ID 1..6 map to Rotation, Pitch, Elbow, Wrist_Pitch, Wrist_Roll, Jaw.
With --calibration, measured ranges map to simulation limits independently of the connection pose.
Without it, relative mode preserves the virtual pose at connection.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import signal
import time
from urllib.request import urlopen
from so101_leader import Playground, SO101_JOINTS
from desheng_calibration import RangeCalibration


def read_packet(sid, address, length):
    if sid not in range(1, 7) or (address, length) not in ((0x38, 2), (0x28, 1)):
        raise ValueError('Only six-axis position and torque-state reads are allowed')
    body = bytes((sid, 4, 2, address, length))
    return b'\xff\xff' + body + bytes((~sum(body) & 255,))


def take_reply(buffer, sid, length):
    while len(buffer) >= 2:
        start = buffer.find(b'\xff\xf5')
        if start < 0:
            buffer[:] = b'\xff' if buffer[-1] == 255 else b''
            return None
        del buffer[:start]
        if len(buffer) < 4:
            return None
        size = buffer[3] + 4
        if size < 6 or size > 32:
            del buffer[0]
            continue
        if len(buffer) < size:
            return None
        frame = bytes(buffer[:size])
        if sum(frame[2:]) & 255 != 255:
            del buffer[0]
            continue
        del buffer[:size]
        if frame[2] != sid:
            continue
        # This hardware returns 02 as the leading read-response byte.
        # Preserve the observed contract, do not reinterpret it as Feetech status.
        if frame[4] != 2 or len(frame[5:-1]) != length:
            raise ValueError('Unexpected read response: ' + frame.hex(' '))
        return int.from_bytes(frame[5:-1], 'big')
    return None


def delta_ticks(current, previous):
    if not 0 <= current < 4096 or not 0 <= previous < 4096:
        raise ValueError('Position is outside the verified 12-bit range')
    return (current - previous + 2048) % 4096 - 2048


class DeshengReader:
    def __init__(self, port, baud=115200):
        import serial
        self.port = serial.Serial(port=None, baudrate=baud, timeout=.002, write_timeout=.3)
        self.port.dtr = False
        self.port.rts = False
        self.port.port = port

    def open(self):
        self.port.open()

    def close(self):
        self.port.close()

    def read(self, sid, address=0x38, length=2):
        for attempt in range(3):
            try:
                return self._read_once(sid, address, length)
            except TimeoutError:
                if attempt == 2:
                    raise
                print(json.dumps({'event':'serial-read-retry','id':sid,'attempt':attempt + 2}), flush=True)

    def _read_once(self, sid, address=0x38, length=2):
        self.port.reset_input_buffer()
        self.port.write(read_packet(sid, address, length))
        self.port.flush()
        buffer = bytearray()
        end = time.perf_counter() + .12
        while time.perf_counter() < end:
            buffer.extend(self.port.read(self.port.in_waiting or 1))
            value = take_reply(buffer, sid, length)
            if value is not None:
                if address == 0x38 and not 0 <= value < 4096:
                    raise ValueError(f'ID {sid} invalid position {value}')
                return value
        raise TimeoutError(f'ID {sid}: no valid position response')

    def positions(self):
        return [self.read(i) for i in range(1, 7)]


def recovery_decision(session, teleop, launch_id, source):
    """Resume only our session, or a new SO-101 scene without another leader."""
    if session.get('robotId') != 'so101':
        return 'stop'
    if session.get('status') != 'ready':
        return 'wait'
    if teleop.get('engaged') and teleop.get('source') != source:
        return 'stop'
    if session.get('launchId') != launch_id:
        return 'reanchor'
    return 'retry' if teleop.get('engaged') else 'stop'


def get_json(server, path):
    with urlopen(server + path, timeout=3) as response:
        return json.load(response)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', required=True)
    ap.add_argument('--server', default='http://127.0.0.1:8080')
    ap.add_argument('--rate', type=float, default=20)
    ap.add_argument('--seconds', type=float, default=0, help='0 keeps running')
    ap.add_argument('--calibration', help='Desheng v401 leader range calibration JSON')
    ap.add_argument('--invert', default='', help='Comma-separated virtual joint names')
    ap.add_argument('--stop-file', help='Exit and release COM port when this file exists')
    args = ap.parse_args()
    if not 1 <= args.rate <= 30 or args.seconds < 0:
        ap.error('rate must be 1..30; seconds must be nonnegative')
    inverted = set(filter(None, args.invert.split(',')))
    if not inverted <= set(SO101_JOINTS):
        ap.error('Unknown joint in --invert')
    calibration = RangeCalibration.load(args.calibration) if args.calibration else None
    stop = Path(args.stop_file) if args.stop_file else None
    if stop and stop.exists():
        raise RuntimeError('Stop file already exists; remove it before starting')
    with urlopen(args.server + '/api/status', timeout=8) as r:
        status = json.load(r)
    session = status.get('bridge', {}).get('result', {}).get('session', {})
    if session.get('status') != 'ready' or session.get('robotId') != 'so101':
        raise RuntimeError('Load the SO-101 virtual arm first')
    limits = session.get('robot', {}).get('joint_limits', {})
    if calibration:
        calibration.validate_limits(limits)
    with urlopen(args.server + '/api/teleop/status', timeout=5) as r:
        existing = json.load(r)
    if existing.get('teleop', {}).get('engaged'):
        raise RuntimeError('Another leader is active; disconnect it first')
    reader = DeshengReader(args.port)
    client = Playground(args.server)
    token = None
    running = True
    def finish(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, finish)
    signal.signal(signal.SIGTERM, finish)
    count = 0
    launch_id = session.get('launchId')
    source = 'desheng-se:' + args.port
    failure_since = None
    try:
        reader.open()
        previous = reader.positions()
        zero = list(previous)
        torque = [reader.read(i, 0x28, 1) for i in range(1, 7)]
        print(json.dumps({'event':'serial-ready','port':args.port,'raw':zero,'torque_readback':torque,'servo_writes':False,'mapping':'calibrated-range' if calibration else 'relative','calibration':args.calibration}), flush=True)
        code, reply = client.post('/api/teleop/engage', {'source':'desheng-se:' + args.port})
        if code != 200 or not reply.get('ok'):
            raise RuntimeError(str(reply))
        teleop = reply['teleop']
        token = teleop['token']
        if set(teleop['follower_joints']) != set(SO101_JOINTS):
            raise RuntimeError('Virtual joint map differs from SO-101')
        anchor = teleop['last_positions']
        if not all(name in anchor and math.isfinite(anchor[name]) for name in SO101_JOINTS):
            raise RuntimeError('Missing initial virtual joint positions')
        displacement = [0] * 6
        started = report = next_tick = time.perf_counter()
        while running and not (stop and stop.exists()):
            now = time.perf_counter()
            if args.seconds and now - started >= args.seconds:
                break
            raw = reader.positions()
            for j in range(6):
                delta = delta_ticks(raw[j], previous[j])
                # Calibrated absolute reads do not depend on sample displacement.
                # A timeout/retry or fast hand motion can legitimately exceed 512 ticks.
                # RangeCalibration bounds targets; the bridge slews the virtual joints.
                if not calibration and abs(delta) > 512:
                    raise ValueError(f'ID {j+1}: implausible single-sample change {delta}')
                displacement[j] += delta
            previous = raw
            targets = calibration.targets(raw, limits, inverted) if calibration else {name:anchor[name] + displacement[j] * math.tau / 4096 * (-1 if name in inverted else 1)
                       for j, name in enumerate(SO101_JOINTS)}
            count += 1
            try:
                code, result = client.post('/api/teleop', {'token':token,'seq':count,'positions':targets})
            except (ConnectionError, OSError) as exc:
                code, result = 503, {'error': str(exc)}
            if code != 200 or not result.get('applied'):
                if code not in (200, 429, 502, 503, 504):
                    raise RuntimeError('Teleop rejected: ' + str(result))
                failure_since = failure_since or time.perf_counter()
                if time.perf_counter() - failure_since > 30:
                    raise RuntimeError('Teleop unavailable for 30 seconds: ' + str(result))
                try:
                    health = get_json(args.server, '/api/status')
                    new_session = health.get('bridge', {}).get('result', {}).get('session', {})
                    # Busy/not-yet-readable bridges can occur during scene composition.
                    if not new_session:
                        raise ConnectionError('Scene is loading')
                    remote = get_json(args.server, '/api/teleop/status')['teleop']
                except (OSError, ConnectionError, KeyError) as exc:
                    print(json.dumps({'event':'waiting-for-scene','reason':str(exc)}), flush=True)
                    time.sleep(.3)
                    continue
                decision = recovery_decision(new_session, remote, launch_id, source)
                if decision == 'stop':
                    print(json.dumps({'event':'stopped-by-page-or-robot-change'}), flush=True)
                    break
                if decision == 'reanchor':
                    # Relative mode reanchors; calibrated mode keeps the same fixed mapping.
                    if calibration:
                        limits = new_session.get('robot', {}).get('joint_limits', {})
                        calibration.validate_limits(limits)
                    previous = reader.positions()
                    code, reply = client.post('/api/teleop/engage', {'source':source})
                    if code != 200 or not reply.get('ok'):
                        time.sleep(.3)
                        continue
                    teleop = reply['teleop']
                    token = teleop['token']
                    if set(teleop['follower_joints']) != set(SO101_JOINTS):
                        raise RuntimeError('Virtual joint map changed')
                    anchor = teleop['last_positions']
                    if not all(name in anchor and math.isfinite(anchor[name]) for name in SO101_JOINTS):
                        raise RuntimeError('Missing virtual pose after reload')
                    displacement = [0] * 6
                    launch_id = new_session['launchId']
                    print(json.dumps({'event':'scene-reconnected','launchId':launch_id,'raw_zero':previous}), flush=True)
                    failure_since = None
                else:
                    print(json.dumps({'event':'temporary-interruption','reason':result,'action':decision}), flush=True)
                time.sleep(.2)
                next_tick = time.perf_counter()
                continue
            failure_since = None
            if now >= report:
                print(json.dumps({'event':'following','samples':count,'raw':raw,'delta_ticks':displacement,'requested_targets':targets,'targets':result.get('targets'),'mapping':'calibrated-range' if calibration else 'relative','rate_hz':result.get('rate_hz')}), flush=True)
                report = now + 2
            next_tick += 1 / args.rate
            delay = next_tick - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.perf_counter()
    finally:
        reader.close()
        if token:
            try:
                client.post('/api/teleop/disengage', {'token':token})
            except Exception as exc:
                print('Disengage failed: ' + str(exc), flush=True)
        client.close()
        print(json.dumps({'event':'closed','port':args.port,'samples':count}), flush=True)


if __name__ == '__main__':
    main()