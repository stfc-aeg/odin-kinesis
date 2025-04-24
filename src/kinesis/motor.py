"""Class to handle the state of a given motor.
It tracks the encoder/scale-factor values for the stage type, the command queue for that motor
and handles conversions for that motor.
"""
import logging
from queue import Queue, PriorityQueue

class Motor():
    """Class to represent the state of a motor stage."""

    # POS = EncCnt x Pos
    # VEL = EncCnt x T x 65536 x Vel
    # ACC = EncCnt x T^2 x 65536 x Acc
    # where T = 2048/6e6 (KDC101)
    # ==> VEL (PRM1-Z8) = 6.2942e4 x Vel
    # ==> ACC (PRM1-Z8) = 14.6574 x Acc

    def __init__(self, name, chan_ident: int=1, stage_type: str=None, controller=None, destination=0x50):
        self.name = name
        self.channel_identity = chan_ident  # For commands
        self.command_queue = []
        self.current_command = None
        self.expected_response = None

        self.await_queue = Queue(maxsize=0)
        self.instant_queue = PriorityQueue(maxsize=0)

        self.controller = controller
        self.destination = destination

        self.moving = False
        self.homing = False
        self.current_position = 0
        self.target_position = None

        self.DEBUG = False

        # Device parameters should be provided by motor controller
        self.stage_type = getattr(STAGETYPES, stage_type, STAGETYPES.MTS50_Z8)

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

        self.tree = {
            'position': {
                'home': (lambda: None, self.home),
                'set_target_pos': (lambda: self.target_position, self.set_target_position),
                'current_pos': (lambda: self.get_current_position(), None)
            },
            'command': {
                'current_command': (lambda: self.current_command, None),
                'expected_response': (lambda: self.expected_response, None),
                'command_queue': (lambda: self.command_queue, None)
            },
            'jog': {
                'mode': (lambda: self.jog_mode, self.set_jog_mode),
                'step_size': (lambda: self.jog_step_size, self.set_jog_step_size),
                'min_vel': (lambda: self.jog_min_vel, self.set_jog_min_vel),
                'accel': (lambda: self.jog_accel, self.set_jog_accel),
                'max_vel': (lambda: self.jog_max_vel, self.set_jog_max_vel),
                'stop_mode': (lambda: self.jog_stop_mode, self.set_jog_stop_mode),
                'step': (lambda: None, self.jog)
            }
        }

    def initialize(self):
        """Post-init adapter function to populate further parameters."""
        logging.debug("Adding current pos to tree for motors")
        self.tree['position']['current_position'] = (lambda: self.get_current_position(), None)

    # ------------ Conversion functions ------------

    def convert_distance(self, movement):
        """Convert a movement to an encoder increment in the required binary format.
        The movement may be linear or rotational, depending on the device.
        :param movement: movement change - e.g.: 5mm, 20 degrees
        :return bytes: movement translated to encoder units
        """
        # Movement to encoder counts
        mv_enccnt = int(movement * self.enc_cnt)
        # To bytes
        mv_enccnt_bytes = mv_enccnt.to_bytes(4, byteorder='little',signed=True)

        if self.DEBUG:
            logging.debug(f"enccnt: {mv_enccnt}, mv_enccnt_bytes, {mv_enccnt_bytes.hex()}")
        return mv_enccnt_bytes

    def convert_enccnt(self, enccnt):
        """Convert an encoder count back to a readable figure.
        The unit depends on the stage: mm, degrees, etc.
        :param enccnt: reported encoder count
        :return int: rounded converted encoder value
        """
        # Integer from bytes
        enccnt_int = int.from_bytes(enccnt, byteorder='little',signed=True)
        # Convert to unit from encoder count
        fig = round(enccnt_int/self.enc_cnt, 1)
        if self.DEBUG:
            logging.debug(f"enccnt: {enccnt}, result figure: {fig}")
        return fig
    
    def convert_velocity(self, vel):
        """Convert velocity to the controller format (4 bytes)."""
        vel_apt = int(vel * self.sf_vel)
        return vel_apt.to_bytes(4, byteorder='little', signed=True)

    def convert_accel(self, accel):
        """Convert acceleration to controller format (4 bytes)."""
        acc_apt = int(accel * self.sf_acc)
        return acc_apt.to_bytes(4, byteorder='little', signed=True)

    # ------------ Positional functions ------------

    def get_current_position(self):
        """Get the current position of this motor."""
        self.controller.get_encoder_position(self)
        return self.current_position

    def set_target_position(self, pos):
        """Set the target position of the motor."""
        self.target_position = pos

        if self.target_position != self.current_position:
            params = self.convert_distance(self.target_position)
            self.controller.move(params, self)

    def home(self, value):
        """Home the motor."""
        self.homing = True
        self.controller.move_home(self)

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
