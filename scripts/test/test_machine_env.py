"""Portable console setup loads the correct workspace, SDK and robot settings."""

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_setup(tmp_path, config, root=ROOT):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('ROS_', 'MARTY_', 'AMENT_', 'COLCON_'))}
    env['MARTY_MACHINE_CONFIG'] = str(config)
    return subprocess.run([
        'bash', '-uc', 'source "$1" || exit; '
        'printf "%s\\n" "$ROS_WORKSPACE" "$ROS_DOMAIN_ID" "$MARTY_ROS_ROBOTS_FILE" '
        '"${UNDERLAY_READY:-}" "${VENV_READY:-}" "${OVERLAY_READY:-}" "$-"',
        'setup-test', str(root / 'scripts/setup_env.sh'),
    ], cwd=tmp_path, env=env, text=True, capture_output=True)


def test_paths_with_spaces_and_nounset(tmp_path):
    workspace = tmp_path / 'workspace with spaces'
    (workspace / 'install').mkdir(parents=True)
    (workspace / 'install/setup.bash').write_text('export OVERLAY_READY=yes\n')
    underlay = tmp_path / 'ROS setup.bash'
    underlay.write_text('export UNDERLAY_READY=yes\n: "${UNSET_ROS_VARIABLE}"\n')
    venv = tmp_path / 'python environment'
    (venv / 'bin').mkdir(parents=True)
    (venv / 'bin/activate').write_text('export VENV_READY=yes\n')
    robots = tmp_path / 'robot settings.yaml'
    robots.write_text('martys: {}\n')
    config = tmp_path / 'machine.env'
    config.write_text(
        f'ROS_WORKSPACE="{workspace}"\nROS_SETUP_FILE="{underlay}"\n'
        f'MARTY_PYTHON_VENV="{venv}"\nMARTY_ROS_ROBOTS_FILE="{robots}"\nROS_DOMAIN_ID=57\n'
    )
    result = run_setup(tmp_path, config)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[:6] == [str(workspace), '57', str(robots), 'yes', 'yes', 'yes']
    assert 'u' in lines[6]


def test_relative_paths_use_checkout_not_current_directory(tmp_path):
    root = tmp_path / 'checkout with spaces'
    (root / 'scripts').mkdir(parents=True)
    (root / 'config').mkdir()
    (root / '.venv/bin').mkdir(parents=True)
    shutil.copy(ROOT / 'scripts/setup_env.sh', root / 'scripts/setup_env.sh')
    (root / 'config/robots.yaml.example').write_text('martys: {}\n')
    (root / '.venv/bin/activate').write_text('export VENV_READY=yes\n')
    config = tmp_path / 'machine.env'
    config.write_text('ROS_SETUP_FILE=/dev/null\nROS_WORKSPACE=.\n'
                      'MARTY_ROS_ROBOTS_FILE=config/robots.yaml.example\n'
                      'MARTY_PYTHON_VENV=.venv\n')
    result = run_setup(tmp_path, config, root=root)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert Path(lines[0]).resolve() == root
    assert Path(lines[2]).resolve() == root / 'config/robots.yaml.example'


def test_missing_explicit_configuration_is_an_error(tmp_path):
    result = run_setup(tmp_path, tmp_path / 'missing.env')
    assert result.returncode != 0
    assert 'Machine configuration not found' in result.stderr


def test_missing_robot_or_python_environment_is_an_error(tmp_path):
    config = tmp_path / 'machine.env'
    config.write_text('ROS_SETUP_FILE=/dev/null\nMARTY_ROS_ROBOTS_FILE=missing.yaml\n')
    result = run_setup(tmp_path, config)
    assert result.returncode != 0
    assert 'Robot configuration not found' in result.stderr
    config.write_text('ROS_SETUP_FILE=/dev/null\nMARTY_PYTHON_VENV=missing-venv\n')
    result = run_setup(tmp_path, config)
    assert result.returncode != 0
    assert 'Python environment not found' in result.stderr
