from setuptools import setup

setup(
    name='marty_bringup', version='0.1.0', packages=['marty_bringup'],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/marty_bringup']),
        ('share/marty_bringup', ['package.xml']),
        ('share/marty_bringup/launch', ['launch/bringup.launch.py']),
        ('share/marty_bringup/config', ['config/marty.yaml']),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Robotical', maintainer_email='hello@robotical.io',
    description='Marty V2 ROS 2 bringup', license='Apache-2.0',
)
