#!/usr/bin/env bash
# Source this file in Bash. Preparing a terminal never starts a ROS node.
_marty_setup_env() {
  local repo config auto_export nounset result
  repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd) || return
  export MARTY_ROS_ROOT="$repo"
  config=${MARTY_MACHINE_CONFIG:-$repo/config/machine.env}
  if [[ -f "$config" ]]; then
    auto_export=$-
    set -a
    source "$config"
    result=$?
    [[ $auto_export == *a* ]] || set +a
    [[ $result == 0 ]] || return "$result"
  elif [[ -n ${MARTY_MACHINE_CONFIG:-} ]]; then
    printf 'Machine configuration not found: %s\n' "$config" >&2
    return 1
  fi
  export ROS_WORKSPACE=${ROS_WORKSPACE:-$repo}
  [[ $ROS_WORKSPACE == /* ]] || ROS_WORKSPACE="$repo/$ROS_WORKSPACE"
  if [[ ! -d "$ROS_WORKSPACE" ]]; then
    printf 'ROS workspace not found: %s\n' "$ROS_WORKSPACE" >&2
    return 1
  fi
  export ROS_SETUP_FILE=${ROS_SETUP_FILE:-/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash}
  if [[ ! -r "$ROS_SETUP_FILE" ]]; then
    printf 'ROS setup not found: %s. Set ROS_SETUP_FILE in %s.\n' "$ROS_SETUP_FILE" "$config" >&2
    return 1
  fi
  export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}
  if [[ -z ${MARTY_ROS_ROBOTS_FILE:-} && -f "$repo/config/robots.yaml" ]]; then
    export MARTY_ROS_ROBOTS_FILE="$repo/config/robots.yaml"
  fi
  if [[ -n ${MARTY_ROS_ROBOTS_FILE:-} ]]; then
    [[ $MARTY_ROS_ROBOTS_FILE == /* ]] || MARTY_ROS_ROBOTS_FILE="$repo/$MARTY_ROS_ROBOTS_FILE"
    export MARTY_ROS_ROBOTS_FILE
    if [[ ! -r "$MARTY_ROS_ROBOTS_FILE" ]]; then
      printf 'Robot configuration not found: %s\n' "$MARTY_ROS_ROBOTS_FILE" >&2
      return 1
    fi
  fi
  if [[ -z ${MARTY_PYTHON_VENV:-} && -f "$repo/.venv/bin/activate" ]]; then
    export MARTY_PYTHON_VENV="$repo/.venv"
  fi
  if [[ -n ${MARTY_PYTHON_VENV:-} ]]; then
    [[ $MARTY_PYTHON_VENV == /* ]] || MARTY_PYTHON_VENV="$repo/$MARTY_PYTHON_VENV"
    export MARTY_PYTHON_VENV
    if [[ ! -r "$MARTY_PYTHON_VENV/bin/activate" ]]; then
      printf 'Python environment not found: %s\n' "$MARTY_PYTHON_VENV" >&2
      return 1
    fi
  fi
  # ROS-generated setup scripts and virtualenv activation can reference unset variables.
  nounset=$-
  set +u
  source "$ROS_SETUP_FILE"
  result=$?
  if [[ $result == 0 && -n ${MARTY_PYTHON_VENV:-} ]]; then
    source "$MARTY_PYTHON_VENV/bin/activate"
    result=$?
  fi
  if [[ $result == 0 && -f "$ROS_WORKSPACE/install/setup.bash" ]]; then
    source "$ROS_WORKSPACE/install/setup.bash"
    result=$?
  fi
  [[ $nounset != *u* ]] || set -u
  return "$result"
}
_marty_setup_env
