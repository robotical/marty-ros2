"""Import source in host-only tests as well as the installed ROS workspace."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
