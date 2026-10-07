"""Typed, bounded firmware movement requests, independent of ROS."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Motion:
    command: int
    num_steps: int = 1
    side: str = 'auto'
    turn_degrees: int = 0
    step_length_mm: int = 25
    move_time_ms: int = 1000
    joint_id: int = 8
    position_degrees: int = 0

    def validate(self):
        if self.command not in range(5):
            raise ValueError('Unknown movement command')
        if not 100 <= self.move_time_ms <= 10000:
            raise ValueError('move_time_ms must be 100..10000')
        if self.command == 0:
            if not 1 <= self.num_steps <= 10:
                raise ValueError('num_steps must be 1..10')
            if self.side not in ('auto', 'left', 'right'):
                raise ValueError('WALK side must be auto, left or right')
            if self.side != 'auto' and self.num_steps != 1:
                raise ValueError('An explicit starting foot requires num_steps=1')
            if not -100 <= self.turn_degrees <= 100 or not -50 <= self.step_length_mm <= 50:
                raise ValueError('turn_degrees must be -100..100; step_length_mm -50..50')
        if self.command in (1, 2) and self.side not in ('left', 'right'):
            raise ValueError('DANCE/KICK side must be left or right')
        if self.command == 4:
            if self.joint_id not in range(9) or not -90 <= self.position_degrees <= 90:
                raise ValueError('joint_id must be 0..8; position_degrees -90..90')

    @property
    def duration_seconds(self):
        return self.move_time_ms * (self.num_steps if self.command == 0 else 1) / 1000.0

    def send(self, sdk):
        self.validate()
        common = {'move_time': self.move_time_ms, 'blocking': False}
        if self.command == 0:
            return sdk.walk(
                num_steps=self.num_steps, start_foot=self.side, turn=self.turn_degrees,
                step_length=self.step_length_mm, **common,
            )
        if self.command == 1:
            return sdk.dance(side=self.side, **common)
        if self.command == 2:
            return sdk.kick(side=self.side, **common)
        if self.command == 3:
            return sdk.stand_straight(**common)
        return sdk.move_joint(self.joint_id, self.position_degrees, **common)
