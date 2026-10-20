FROM ros:jazzy-ros-base
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    python3-venv ros-jazzy-diagnostic-msgs ros-jazzy-rosidl-default-generators && \
    rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /opt/marty-env && \
    /opt/marty-env/bin/pip install --no-cache-dir martypy==3.7.2
ENV PATH=/opt/marty-env/bin:$PATH
WORKDIR /ws
COPY src/marty_interfaces src/marty_interfaces
COPY src/marty_driver src/marty_driver
COPY src/marty_bringup src/marty_bringup
RUN . /opt/ros/jazzy/setup.sh && \
    MAKEFLAGS=-j1 CMAKE_BUILD_PARALLEL_LEVEL=1 \
    python /usr/bin/colcon build --base-paths src --executor sequential \
    --cmake-args -DBUILD_TESTING=OFF && rm -rf build log
COPY examples/onboard-pi/ros-entrypoint.sh /marty-entrypoint.sh
ENTRYPOINT ["bash", "/marty-entrypoint.sh"]
CMD ["ros2", "launch", "marty_bringup", "bringup.launch.py", "robots_file:=/config/robots.yaml"]
