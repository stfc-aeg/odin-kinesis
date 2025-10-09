"""Class to handle the state of a given motor.
It tracks the encoder/scale-factor values for the stage type, the command queue for that motor
and handles conversions for that motor.
"""
import logging
from enum import Enum, auto
from kinesis.motor_stages.baseMotorStage import BaseMotorStage

class ValueType(Enum):
    """Enum for scale factor conversion types. Position, velocity or acceleration."""
    POS = auto()
    VEL = auto()
    ACC = auto()

class EncoderStage(BaseMotorStage):
    """Class to represent the state of a motor stage.
    The stages targeted here are those such as the MTS50-Z8 which use an encoder to calculate their
    position. This is for the conversion functions, which should work similarly across stages.
    These stages also have the same jog parameters, generically using the MGMSG_SET_JOGPARAMS msg.
    """
    # POS = EncCnt x Pos
    # VEL = EncCnt x T x 65536 x Vel
    # ACC = EncCnt x T^2 x 65536 x Acc
    # where T = 2048/6e6 (KDC101)
    # ==> VEL (PRM1-Z8) = 6.2942e4 x Vel
    # ==> ACC (PRM1-Z8) = 14.6574 x Acc

    def __init__(self, name, upper_limit, lower_limit, chan_ident: int=1, stage_type: str=None, controller=None, destination=0x50):
        # Initialise properties and tree of base motor stage
        super().__init__(name, chan_ident, stage_type, controller, destination)

        # Device parameters should be provided by motor controller
        self.stage_type = getattr(STAGETYPES, stage_type, STAGETYPES.MTS50_Z8)

        # Defined as floats, rounded to ints, page 39
        self.enc_cnt = int(self.stage_type['enc_cnt'])
        self.sf_vel  = int(self.stage_type['sf_vel'])
        self.sf_acc  = int(self.stage_type['sf_acc'])

        # Details on page 68
        self.jog_mode = 0x02  # Step. 0x01 is continuous
        self.jog_step_size = 1  # mm
        self.jog_min_vel = 0  # mm/s
        self.jog_accel = 0.5  # mm/s^2
        self.jog_max_vel = 1  # mm/s
        self.jog_stop_mode = 0x02  # Profiled, 0x01 is abrupt

        self.upper_limit = upper_limit
        self.lower_limit = lower_limit

    def initialize(self):
        """Post-init adapter function to get required parameters."""
        logging.debug(f"Initialize: updating tree for Encoder Stage {self.name}.")
        self.tree['jog'] = {
            'mode': (lambda: self.jog_mode, self.set_jog_mode),
            'step_size': (lambda: self.jog_step_size, self.set_jog_step_size),
            'min_vel': (lambda: self.jog_min_vel, self.set_jog_min_vel),
            'accel': (lambda: self.jog_accel, self.set_jog_accel),
            'max_vel': (lambda: self.jog_max_vel, self.set_jog_max_vel),
            'stop_mode': (lambda: self.jog_stop_mode, self.set_jog_stop_mode),
            'step': (lambda: None, self.jog),
            'reverse': (lambda: self.reverse_jog, self.reverse_jog_direction)
        }
        self.tree['limits'] = {
            'upper_limit': (lambda: self.upper_limit, self.set_upper_limit),
            'lower_limit': (lambda: self.lower_limit, self.set_lower_limit)
        }
        self.controller.get_jogparams(self)

    # ------------ Conversion functions ------------

    def val_to_enc(self, val: float, val_type: ValueType) -> int:
        """Convert a value (position, velocity, acceleration) to an encoder count.
        :param float val: value to be converted
        :param str type: type of value: pos, vel, or acc
        """
        match val_type:
            case ValueType.POS:
                return int(val*self.enc_cnt)
            case ValueType.VEL:
                return int(val*self.sf_vel)
            case ValueType.ACC:
                return int(val*self.sf_acc)

    def enc_to_val(self, enc: float, val_type: ValueType) -> float:
        """Convert decoded bytes back to a useful value."""
        match val_type:
            case ValueType.POS:
                return round((enc/self.enc_cnt), 4)
            case ValueType.VEL:
                return round((enc/self.sf_vel), 4)
            case ValueType.ACC:
                return round((enc/self.sf_acc), 4)

    # ------------ Positional functions ------------

    def set_target_position(self, pos):
        """Set target position. If this differs to current position, move to target position."""
        pos = float(pos)
        self.target_position = pos

        if (self.target_position != self.current_position) and (
            self.lower_limit <= self.target_position and self.target_position <= self.upper_limit):
            pos = self.val_to_enc(pos, ValueType.POS)
            self.controller.move(pos, self)

    def set_upper_limit(self, lim):
        """Set the upper limit position of the stage in mm."""
        self.upper_limit = lim

    def set_lower_limit(self, lim):
        """Set the upper limit position of the stage in mm."""
        self.lower_limit = lim

    # ------------ Jog functions ------------

    def jog(self, direction):
        """Start jogging in a given direction
        :param bool direction: True (forward), False (back).
        """
        direction = bool(direction)

        if self.reverse_jog:
            direction = not direction

        # Check if step moves beyond limit
        sign = 1 if direction else -1
        predicted_pos = self.current_position + self.jog_step_size*sign
        if (self.lower_limit <= predicted_pos) and (predicted_pos <= self.upper_limit):
            self.controller.move_jog(direction, self)

    def set_jog_mode(self, value):
        """Set the jog mode then update the params through the controller.
        :param int value: 0x01 (continuous), 0x02 (step)
        """
        if value not in (0x01, 0x02):
            value = 0x02  # Step if not in range
        self.jog_mode = value
        self.controller.set_jogparams(self)

    def set_jog_step_size(self, value):
        """Set jog step size then update params through controller."""
        self.jog_step_size = value
        self.controller.set_jogparams(self)

    def set_jog_min_vel(self, value):
        """Set jog minimum velocity then update params through controller."""
        self.jog_min_vel = value
        self.controller.set_jogparams(self)

    def set_jog_accel(self, value):
        """Set jog acceleration then update params through controller."""
        self.jog_accel = value
        self.controller.set_jogparams(self)

    def set_jog_max_vel(self, value):
        """Set jog maximum velocity then update params through controller."""
        self.jog_max_vel = value
        self.controller.set_jogparams(self)

    def set_jog_stop_mode(self, value):
        """Set jog stop mode then update params through controller.
        :param int value: 0x01 (instant stop) or 0x02 (profiled stop)
        """
        if value not in (0x01, 0x02):
            value = 0x02  # Profiled stop if not in range
        self.jog_stop_mode = value
        self.controller.set_jogparams(self)

class STAGETYPES():

    MTS50_Z8 = {
        'enc_cnt': 34554.96,
        'sf_vel': 772981.3692,
        'sf_acc': 263.8443072
    }
