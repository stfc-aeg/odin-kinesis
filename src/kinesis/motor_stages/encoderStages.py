"""Class to handle the state of a given motor.
It tracks the encoder/scale-factor values for the stage type, the command queue for that motor
and handles conversions for that motor.
"""
import logging
from kinesis.motor_stages.baseMotorStage import BaseMotorStage

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

    def __init__(self, name, chan_ident: int=1, stage_type: str=None, controller=None, destination=0x50):
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
            'step': (lambda: None, self.jog)
        }
        self.controller.get_jogparams(self)

    # ------------ Conversion functions ------------

    def convert_position(self, movement):
        """Convert a movement to an encoder count in the controller format (4 bytes).
        :param movement: movement change - e.g. 5mm, 20 degrees
        :return bytes: movement translated to encoder units
        """
        mv_enccnt = int(movement * self.enc_cnt)
        return mv_enccnt.to_bytes(4, byteorder='little', signed=True)

    def read_position(self, enccnt_bytes):
        """Convert position bytes back to a readable figure (depends on stage: mm, deg, etc.).
        :return float: rounded converted encoder value
        """
        enccnt = int.from_bytes(enccnt_bytes, byteorder='little', signed=True)
        return round((enccnt/self.enc_cnt), 4)

    def convert_velocity(self, vel):
        """Convert velocity to the controller format (4 bytes).
        :return bytes: scaled velocity in bytes
        """
        vel_apt = int(vel * self.sf_vel)
        return vel_apt.to_bytes(4, byteorder='little', signed=True)

    def read_velocity(self, vel_bytes):
        """Convert 4-byte controller velocity back to readable value.
        :return velocity: rounded to 4 figures
        """
        vel_apt = int.from_bytes(vel_bytes, byteorder='little', signed=True)
        return round((vel_apt/self.sf_vel), 4)

    def convert_accel(self, accel):
        """Convert acceleration to controller format (4 bytes).
        :return bytes: scaled acceleration in bytes
        """
        acc_apt = int(accel * self.sf_acc)
        return acc_apt.to_bytes(4, byteorder='little', signed=True)

    def read_accel(self, acc_bytes):
        """Convert 4-byte controller acceleration value back to mm/s^2."""
        acc_apt = int.from_bytes(acc_bytes, byteorder='little', signed=True)
        return round((acc_apt/self.sf_acc), 4)

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
