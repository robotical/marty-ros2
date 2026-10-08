"""Native MuJoCo binding for the browser simulator's unchanged MJCF model."""

import math

import mujoco


class MartyPhysics:
    def __init__(self, model_path, mode='stabilized'):
        if mode not in ('stabilized', 'free'):
            raise ValueError('mode must be stabilized or free')
        self.mode = mode
        self.model = mujoco.MjModel.from_xml_path(str(model_path))
        # The source's 2 ms step is unstable for the very small eye inertias.
        # 0.5 ms resolves that joint without changing geometry or actuator limits.
        self.model.opt.timestep = 0.0005
        if mode == 'stabilized':
            # Passive damping includes the mimic joints, which otherwise oscillate
            # against their equality constraints. This is an explicit simulation
            # estimate (critical damping for a unit spring), not a servo measurement.
            for dof in range(6, self.model.nv):
                self.model.dof_damping[dof] = 2 * math.sqrt(self.model.dof_M0[dof])
        self.data = mujoco.MjData(self.model)
        self.joints = {}
        for actuator_id in range(self.model.nu):
            joint_id = int(self.model.actuator_trnid[actuator_id, 0])
            joint = self.model.joint(joint_id)
            self.joints[joint.name] = (
                actuator_id, int(joint.qposadr[0]), int(joint.dofadr[0]),
            )
        self.known_joints = {self.model.joint(i).name for i in range(self.model.njnt)}
        mujoco.mj_resetDataKeyframe(self.model, self.data, self.model.key('neutral').id)
        self.base_height = float(self.data.qpos[2])
        mujoco.mj_forward(self.model, self.data)

    def set_targets(self, names, positions):
        """Validate the whole command before updating any actuator; units are radians."""
        if not names or len(names) != len(positions) or len(set(names)) != len(names):
            raise ValueError('Supply unique joint names and one position per name')
        targets = []
        for name, position in zip(names, positions):
            if name not in self.known_joints or not math.isfinite(position):
                raise ValueError(f'Unknown joint or non-finite position: {name}')
            # joint_state_publisher_gui also emits mimic joints; MuJoCo computes these.
            if name not in self.joints:
                continue
            actuator_id, _, _ = self.joints[name]
            lower, upper = self.model.actuator_ctrlrange[actuator_id]
            if not lower <= position <= upper:
                raise ValueError(f'{name} must be between {lower:g} and {upper:g} radians')
            targets.append((actuator_id, position))
        if not targets:
            raise ValueError('Command contains no independently controlled joints')
        for actuator_id, position in targets:
            self.data.ctrl[actuator_id] = position

    def step(self, count=40):
        for _ in range(count):
            self.data.qfrc_applied[:] = 0
            if self.mode == 'stabilized':
                self._balance()
            mujoco.mj_step(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        if not all(math.isfinite(float(value)) for value in self.data.qpos):
            raise RuntimeError('MuJoCo produced non-finite joint positions')

    def _balance(self):
        # Ported from src/mujocoMartyPhysics.ts, writeBalanceForces. These are
        # visualization assistance forces, not calibrated physical controllers.
        w, x, y, z = self.data.qpos[3:7]
        roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x*x + y*y))
        pitch = math.asin(max(-1, min(1, 2 * (w * y - z * x))))
        self.data.qfrc_applied[2] = max(-3, min(
            12, (self.base_height - self.data.qpos[2]) * 62 - self.data.qvel[2] * 4.2))
        self.data.qfrc_applied[3] = max(-0.6, min(
            0.6, -roll * 0.55 - self.data.qvel[3] * 0.06))
        self.data.qfrc_applied[4] = max(-0.6, min(
            0.6, -pitch * 0.55 - self.data.qvel[4] * 0.06))

    def joint_state(self):
        return (
            list(self.joints),
            [float(self.data.qpos[qpos]) for _, qpos, _ in self.joints.values()],
            [float(self.data.qvel[dof]) for _, _, dof in self.joints.values()],
        )
