from setuptools import setup

setup(
    name='marty_camera', version='0.1.0', packages=['marty_camera'],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/marty_camera']),
        ('share/marty_camera', ['package.xml']),
        ('share/marty_camera/launch', ['launch/view.launch.py']),
        ('share/marty_camera/config', ['config/camera.rviz']),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Robotical', maintainer_email='hello@robotical.io',
    description='Network camera receiver for Marty', license='Apache-2.0',
    entry_points={'console_scripts': ['camera_receiver = marty_camera.receiver:main']},
)
