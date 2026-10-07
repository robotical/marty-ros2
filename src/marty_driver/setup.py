from setuptools import find_packages, setup

setup(
    name='marty_driver',
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/marty_driver']),
        ('share/marty_driver', ['package.xml']),
    ],
    install_requires=['setuptools', 'martypy==3.7.2'],
    zip_safe=True,
    maintainer='Robotical',
    maintainer_email='hello@robotical.io',
    description='Marty V2 ROS 2 driver',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={'console_scripts': ['marty_driver_node = marty_driver.node:main']},
)
