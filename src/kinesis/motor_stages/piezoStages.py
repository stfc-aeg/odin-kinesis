"""Class to handle the state of a given motor.
It tracks the encoder/scale-factor values for the stage type, the command queue for that motor
and handles conversions for that motor.
"""
import logging
from kinesis.motor_stages.baseMotorStage import BaseMotorStage

class PiezoStage(BaseMotorStage):
    """Class to represent the state of a motor stage.
    The stages targeted here are those such as the PD1V/M with piezo inertia drives.
    They should be controllable with the KIM001/101 or TIM001/101 controllers so that control schemes match.
    """

    def __init__(self, name, chan_ident: int=1, stage_type: str=None, controller=None, destination=0x50):
        # Initialise properties and tree of base motor stage
        super().__init__(name, chan_ident, stage_type, controller, destination)
        logging.debug(f"motor initialising")
        # Details on pages 396-397
        self.jog_mode = 0x02  # Step
        self.jog_step_size_fwd = 250  # 1-2000 Steps
        self.jog_step_size_rev = 260
        self.jog_step_rate     = 200  # 1-2000 Steps/s
        self.jog_step_accn     = 100  # 1-100K steps/sec^2

    def initialize(self):
        """Post-init adapter function to get required parameters."""
        logging.debug(f"Initialize: updating tree for Piezo Stage {self.name}.")
        self.tree['jog'] = {
            'mode': (lambda: self.jog_mode, self.set_jog_mode),
            'step_size_fwd': (lambda: self.jog_step_size_fwd, self.set_jog_step_size_fwd),
            'step_size_rev': (lambda: self.jog_step_size_rev, self.set_jog_step_size_rev),
            'step_rate': (lambda: self.jog_step_rate, self.set_jog_step_rate),
            'accel': (lambda: self.jog_step_accn, self.set_jog_step_accn),
            'step': (lambda: None, self.jog)
        }
        self.controller.get_jogparams(self)

    # ------------ Movement functions ------------

    def set_target_position(self, pos):
        """Set the target position of the stage in steps and signal the controller to move."""
        pos = int(pos)  # Step count is integer
        self.target_position = pos

        if self.target_position != self.current_position:
            self.controller.move(pos, self)

    # ------------ Jog functions ------------

    def jog(self, direction):
        """Start jogging in a given direction
        :param bool direction: True (forward), False (back).
        """
        direction = bool(direction)
        self.controller.move_jog(direction, self)

    def set_jog_mode(self, value):
        """Set the jog mode then update the params through the controller.
        :param int value: 0x01 (continuous), 0x02 (step)
        """
        if value not in (0x01, 0x02):
            value = 0x02  # Step if not in range
        self.jog_mode = value
        self.controller.set_jogparams(self)

    def set_jog_step_size_fwd(self, value):
        """Set jog step size then update params through controller."""
        self.jog_step_size_fwd = value
        self.controller.set_jogparams(self)

    def set_jog_step_size_rev(self, value):
        """Set jog step size then update params through controller."""
        self.jog_step_size_rev = value
        self.controller.set_jogparams(self)

    def set_jog_step_rate(self, value):
        """Set jog minimum velocity then update params through controller."""
        self.jog_step_rate = value
        self.controller.set_jogparams(self)

    def set_jog_step_accn(self, value):
        """Set jog acceleration then update params through controller."""
        self.jog_step_accn = value
        self.controller.set_jogparams(self)
