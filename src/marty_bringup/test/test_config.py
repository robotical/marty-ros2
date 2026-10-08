"""Reject ambiguous or malformed physical robot configuration before launch."""

import pytest
import yaml

from marty_bringup.config import load_robots


def write_config(tmp_path, entries):
    path = tmp_path / 'robots.yaml'
    path.write_text(yaml.safe_dump({'martys': entries}))
    return path


def test_multiple_namespaces_and_numeric_rate(tmp_path):
    path = write_config(tmp_path, {
        '/marty/': {'method': 'usb', 'locator': '/dev/serial/by-id/robot',
                    'subscribe_rate_hz': 20, 'auto_connect': False},
        'fleet/marty2': {'method': 'wifi', 'locator': 'marty2.local'},
    })
    result = load_robots(path)
    assert set(result) == {'/marty', '/fleet/marty2'}
    assert type(result['/marty']['subscribe_rate_hz']) is float


@pytest.mark.parametrize('parameters,message', [
    ({'locator': '/dev/test', 'auto_connect': 'false'}, 'auto_connect must be bool'),
    ({'locator': '/dev/test', 'serial_baud': True}, 'serial_baud must be int'),
    ({'locator': '/dev/test', 'subscribe_rate_hz': float('nan')}, 'must be finite'),
    ({'locator': '/dev/test', 'unknown': 1}, 'unknown driver parameter'),
    ({'method': 'wifi', 'locator': 'ws://marty.local/ws'}, 'not a URL'),
    ({'method': 'usb'}, 'nonempty locator'),
])
def test_invalid_parameters(tmp_path, parameters, message):
    with pytest.raises(ValueError, match=message):
        load_robots(write_config(tmp_path, {'marty': parameters}))


def test_duplicate_namespaces_and_connections(tmp_path):
    connection = {'method': 'usb', 'locator': '/dev/test'}
    with pytest.raises(ValueError, match='Duplicate namespace'):
        load_robots(write_config(tmp_path, {'marty': connection, '/marty': connection}))
    with pytest.raises(ValueError, match='same connection'):
        load_robots(write_config(tmp_path, {'marty': connection, 'marty2': connection}))


def test_wrong_file_structure_and_namespace(tmp_path):
    path = tmp_path / 'robots.yaml'
    path.write_text('martys: []')
    with pytest.raises(ValueError, match='at least one robot'):
        load_robots(path)
    with pytest.raises(ValueError, match='Invalid ROS namespace'):
        load_robots(write_config(tmp_path, {'marty-2': {'locator': '/dev/test'}}))
