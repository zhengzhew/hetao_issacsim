"""Desheng range calibration to simulation limits; never writes servo settings."""
import json
import math
from pathlib import Path
from so101_leader import SO101_JOINTS


NAMED_JOINTS = ('shoulder_pan', 'shoulder_lift', 'elbow_flex',
                'wrist_flex', 'wrist_roll', 'gripper')


class RangeCalibration:
    def __init__(self, document):
        if not isinstance(document, dict):
            raise ValueError('校准 JSON 顶层必须是对象')
        wrapped = document.get('format') == 'lerobot_style_desheng_v401'
        named = not wrapped and all(name in document for name in NAMED_JOINTS)
        if wrapped:
            if (document.get('version') != 1 or document.get('resolution') != 4096
                    or document.get('role') != 'leader'
                    or document.get('normalization') != 'range_m100_100'
                    or not isinstance(document.get('motors'), dict)):
                raise ValueError('Unsupported Desheng leader calibration format')
        elif not named or 'format' in document or document.get('role', 'leader') != 'leader':
            raise ValueError('请选择主臂校准 JSON，或配置包的 .robot.json 入口文件')
        self.motors = []
        for sid, name in enumerate(NAMED_JOINTS, 1):
            m = document['motors'].get(str(sid), {}) if wrapped else document[name]
            if not isinstance(m, dict):
                raise ValueError(f'关节 {name} 缺少校准数据')
            low, high, offset = m.get('range_min'), m.get('range_max'), m.get('homing_offset')
            # Named-joint files from SO101-Calibrate record offsets already written by
            # bus.write_calibration before export. Do not apply these a second time.
            offset_ok = type(offset) is int and (-2047 <= offset <= 2047 if named else offset == 0)
            if (type(m.get('id')) is not int or m['id'] != sid
                    or type(low) is not int or type(high) is not int
                    or not 0 <= low < high < 4096 or type(m.get('drive_mode')) is not int
                    or m['drive_mode'] not in (0, 1) or not offset_ok):
                raise ValueError(f'ID {sid} ({name}): invalid range/direction or unsupported offset')
            self.motors.append(dict(m))

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding='utf-8-sig')))

    @staticmethod
    def validate_limits(limits):
        for name in SO101_JOINTS:
            pair = limits.get(name)
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in pair)
                    or pair[0] >= pair[1]):
                raise ValueError(f'{name}: missing or invalid simulation joint limits')

    def targets(self, raw, limits, inverted=()):
        self.validate_limits(limits)
        if len(raw) != 6 or any(not math.isfinite(v) or not 0 <= v < 4096 for v in raw):
            raise ValueError('Expected six finite 12-bit encoder positions')
        result = {}
        for name, value, m in zip(SO101_JOINTS, raw, self.motors):
            # Same range_m100_100 rule as the calibration producer, expressed as 0..1.
            # Hardware middle offsets were already written to the servo: do not add again.
            fraction = min(1., max(0., (value - m['range_min']) / (m['range_max'] - m['range_min'])))
            if bool(m['drive_mode']) != (name in inverted):
                fraction = 1. - fraction
            low, high = limits[name]
            result[name] = low + fraction * (high - low)
        return result
