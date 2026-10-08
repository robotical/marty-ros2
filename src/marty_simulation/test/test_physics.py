"""Exercise the actual native physics model and its RViz joint/mesh contract."""

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from marty_simulation.physics import MartyPhysics

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'physics/marty2_full.xml'


def test_model_assets_and_mimics_match_physics():
    description = ROOT.parent / 'marty2_description'
    urdf = ET.parse(description / 'urdf/marty2.urdf').getroot()
    physics = MartyPhysics(MODEL)
    independent = {j.attrib['name'] for j in urdf.findall('joint')
                   if j.attrib['type'] == 'revolute' and j.find('mimic') is None}
    assert set(physics.joints) == independent
    for mesh in urdf.findall('.//mesh'):
        path = mesh.attrib['filename'].removeprefix('package://marty2_description/')
        assert (description / path).is_file()
    assert len(urdf.findall('joint/mimic')) == 11


def test_stable_pose_actual_motion_and_mimic_after_ten_seconds():
    physics = MartyPhysics(MODEL)
    physics.set_targets(['eye_left_joint', 'arm_servo_gear_left_joint'], [-0.5, 0.5])
    for _ in range(500):
        physics.step()
    names, positions, velocities = physics.joint_state()
    feedback = dict(zip(names, positions))
    assert physics.data.time == pytest.approx(10)
    assert feedback['eye_left_joint'] == pytest.approx(-0.5, abs=0.005)
    assert feedback['arm_servo_gear_left_joint'] == pytest.approx(0.5, abs=0.01)
    assert physics.data.qpos[2] == pytest.approx(physics.base_height, abs=0.002)
    assert physics.data.qpos[physics.model.joint('eye_right_joint').qposadr[0]] == pytest.approx(
        0.5, abs=0.005)
    assert max(abs(v) for v in velocities) < 0.01


@pytest.mark.parametrize('names,positions', [
    (['eye_left_joint'], [float('nan')]),
    (['eye_left_joint'], [float('inf')]),
    (['eye_left_joint'], [3.0]),
    (['unknown_joint'], [0.0]),
    (['eye_left_joint', 'eye_left_joint'], [0.0, 0.0]),
    (['eye_left_joint'], []),
    (['eye_left_joint', 'unknown_joint'], [-0.4, 0.0]),
])
def test_invalid_commands_leave_all_targets_unchanged(names, positions):
    physics = MartyPhysics(MODEL)
    before = physics.data.ctrl.copy()
    with pytest.raises(ValueError):
        physics.set_targets(names, positions)
    assert list(physics.data.ctrl) == list(before)


def test_gui_mimics_are_not_treated_as_independent_actuators():
    physics = MartyPhysics(MODEL)
    physics.set_targets(['eye_left_joint', 'eye_right_joint'], [-0.5, 0.5])
    assert physics.data.ctrl[physics.joints['eye_left_joint'][0]] == -0.5


def test_free_mode_has_no_assistance_forces_or_damping():
    physics = MartyPhysics(MODEL, mode='free')
    physics.step()
    assert not any(physics.data.qfrc_applied)
    assert not any(physics.model.dof_damping)
