"""Run the normal ROS driver through the Docker Desktop USB PTY."""

import os

from marty_driver.node import main
from usb_pty import USBPTY

if __name__ == '__main__':
    link = USBPTY()
    try:
        main(args=['--ros-args', '-r', '__ns:=/marty', '-p', 'method:=usb',
                   '-p', f'locator:={link.path}', '-p', 'auto_connect:=true',
                   '-p', 'serial_baud:=' + os.environ.get('MARTY_SERIAL_BAUD', '115200')])
    finally:
        link.close()
