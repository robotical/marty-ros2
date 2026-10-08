"""Read local robot connections without depending on the working directory."""

import math
import re

import yaml
from marty_driver.config import DEFAULT_PARAMETERS


def load_robots(path):
    with open(path, encoding='utf-8') as stream:
        document = yaml.safe_load(stream)
    if not isinstance(document, dict) or set(document) != {'martys'}:
        raise ValueError('Robot configuration must contain a martys mapping')
    entries = document['martys']
    if not isinstance(entries, dict) or not entries:
        raise ValueError('martys must contain at least one robot')
    robots = {}
    endpoints = set()
    for name, parameters in entries.items():
        if not isinstance(name, str) or not re.fullmatch(
                r'/?[A-Za-z_][A-Za-z0-9_]*(/[A-Za-z_][A-Za-z0-9_]*)*/?', name):
            raise ValueError(f'Invalid ROS namespace: {name!r}')
        namespace = '/' + name.strip('/')
        if namespace in robots:
            raise ValueError(f'Duplicate namespace: {namespace}')
        if not isinstance(parameters, dict):
            raise ValueError(f'{namespace} parameters must be a mapping')
        result = {}
        for key, value in parameters.items():
            if key not in DEFAULT_PARAMETERS:
                raise ValueError(f'{namespace}: unknown driver parameter {key}')
            kind = type(DEFAULT_PARAMETERS[key])
            # Accept a YAML integer for a floating-point ROS parameter, but not a bool.
            if kind is float and type(value) in (int, float) and math.isfinite(value):
                value = float(value)
            elif type(value) is not kind:
                raise ValueError(f'{namespace}: {key} must be {kind.__name__}')
            if kind is float and not math.isfinite(value):
                raise ValueError(f'{namespace}: {key} must be finite')
            result[key] = value
        method = result.get('method', DEFAULT_PARAMETERS['method'])
        locator = result.get('locator', '')
        if method not in ('usb', 'wifi', 'exp') or not locator.strip():
            raise ValueError(f'{namespace}: set method (usb/wifi/exp) and a nonempty locator')
        if method == 'wifi' and '://' in locator:
            raise ValueError(f'{namespace}: Wi-Fi locator must be an IP or hostname, not a URL')
        endpoint = (method, locator, result.get('wifi_port', 80) if method == 'wifi' else None)
        if endpoint in endpoints:
            raise ValueError(f'{namespace}: another robot uses the same connection')
        endpoints.add(endpoint)
        robots[namespace] = result
    return robots
