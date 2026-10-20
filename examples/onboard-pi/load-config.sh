# Source machine settings without requiring ROS to be installed on the Pi host.
export MARTY_ROS_ROOT
MARTY_ROS_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
machine_config=${MARTY_MACHINE_CONFIG:-$MARTY_ROS_ROOT/config/machine.env}
if [[ -f "$machine_config" ]]; then
    set -a
    source "$machine_config"
    set +a
elif [[ -n ${MARTY_MACHINE_CONFIG:-} ]]; then
    echo "Machine configuration missing: $machine_config" >&2
    return 1
fi
