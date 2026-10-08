"""Startup parameter defaults shared by the driver and launch configuration."""

DEFAULT_PARAMETERS = {
    'method': 'usb', 'locator': '', 'serial_baud': 115200, 'wifi_port': 80,
    'subscribe_rate_hz': 10.0, 'auto_connect': False, 'auto_reconnect': True,
    'stale_after_seconds': 2.0, 'reconnect_interval_seconds': 2.0,
    'completion_margin_seconds': 5.0, 'joint_map': '{}',
    'acceleration_scale': 9.80665, 'imu_frame': 'marty_accelerometer',
    'battery_frame': 'marty_battery',
}
