# Marty ROS graph

The diagram shows one standalone Marty driver and its public ROS interfaces.
An arrow shows a data or control path; service and action exchanges are bidirectional.
The retained status topic uses reliable/transient-local QoS; diagnostics uses reliable QoS.

Regenerate after editing the Graphviz source:

```bash
dot -Tpng docs/ros-graphs/marty-overview.dot -o docs/ros-graphs/marty-overview.png
dot -Tsvg docs/ros-graphs/marty-overview.dot -o docs/ros-graphs/marty-overview.svg
```
