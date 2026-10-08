from glob import glob
from setuptools import setup

setup(
    name='marty_simulation', version='0.1.0', packages=['marty_simulation'],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/marty_simulation']),
        ('share/marty_simulation', ['package.xml']),
        ('share/marty_simulation/launch', glob('launch/*.launch.py')),
        ('share/marty_simulation/config', glob('config/*')),
        ('share/marty_simulation/physics', glob('physics/*')),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Robotical', maintainer_email='hello@robotical.io',
    description='Marty MuJoCo simulation with RViz', license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={'console_scripts': ['marty_simulation_node = marty_simulation.node:main']},
)
