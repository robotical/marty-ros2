"""ROS unit conversions without assuming torque, gyro or robot-model calibration."""

import json
import math

JOINT_NAMES = ('left_hip', 'left_twist', 'left_knee', 'right_hip', 'right_twist',
               'right_knee', 'left_arm', 'right_arm', 'eyes')


def joint_mapping(encoded='{}'):
    overrides = json.loads(encoded)
    if not isinstance(overrides, dict):
        raise ValueError('joint_map must be a JSON object keyed by servo ID')
    mapping = {i: {'name': name, 'sign': 1.0, 'offset_rad': 0.0}
               for i, name in enumerate(JOINT_NAMES)}
    for key, config in overrides.items():
        i = int(key)
        if i not in mapping or not isinstance(config, dict):
            raise ValueError('joint_map IDs must be 0..8 with object values')
        if set(config) - {'name', 'sign', 'offset_rad'}:
            raise ValueError('Unknown joint_map field')
        mapping[i].update(config)
    names = []
    for item in mapping.values():
        if not isinstance(item['name'], str) or not item['name']:
            raise ValueError('Joint names must be nonempty strings')
        if item['sign'] not in (-1, 1) or not math.isfinite(float(item['offset_rad'])):
            raise ValueError('Joint signs must be -1/1 and offsets finite radians')
        names.append(item['name'])
    if len(set(names)) != len(names):
        raise ValueError('Joint names must be unique')
    return mapping


def servo_values(data, mapping):
    result = []
    for raw_id, servo in sorted(data.items(), key=lambda pair: int(pair[0])):
        i = int(raw_id)
        if i not in mapping:
            continue
        config = mapping[i]
        ok = bool(servo.get('commsOK', False))
        angle, current = servo.get('pos', -32768), servo.get('current', -32768)
        result.append({
            'id': i, 'name': config['name'], 'flags': int(servo.get('flags', 0)),
            'enabled': bool(servo.get('enabled', False)), 'comms_ok': ok,
            'position_radians': config['sign'] * math.radians(angle) + config['offset_rad']
            if ok and angle != -32768 else float('nan'),
            'current_amperes': current / 1000.0 if ok and current != -32768 else float('nan'),
        })
    return result


def battery_values(data):
    if not data.get('battInfoValid', False):
        return None
    nan = float('nan')
    percent = float(data.get('battRemainCapacityPercent', nan)) / 100.0
    return {
        'voltage': nan, 'design_capacity': nan,
        'temperature': float(data.get('battTempDegC', nan)),
        'current': float(data.get('battCurrentMA', nan)) / 1000.0,
        'charge': float(data.get('battRemainCapacityMAH', nan)) / 1000.0,
        'capacity': float(data.get('battFullCapacityMAH', nan)) / 1000.0,
        'percentage': percent if 0 <= percent <= 1 else nan,
        'present': True,
    }


def json_values(data):
    def clean(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {str(k): clean(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [clean(v) for v in value]
        return value
    return json.dumps(clean(data), allow_nan=False, sort_keys=True)
