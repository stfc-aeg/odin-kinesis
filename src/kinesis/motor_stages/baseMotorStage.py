"""Class to handle the state of a given motor.
It tracks the encoder/scale-factor values for the stage type, the command queue for that motor
and handles conversions for that motor.
"""
import logging
import itertools
from queue import Queue, PriorityQueue

class BaseMotorStage():
    """Class to represent the state of a motor stage."""
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

        self.reverse_jog = False

        # Cannot compare functions as a queue priority tool, as all but stop are '1'. This iterator
        # will increment each so that simple function-in-queue structure can stay
        self._queue_counter = itertools.count()

        self.tree = {
            'position': {
                'home': (lambda: None, self.home),
                'set_target_pos': (lambda: self.target_position, self.set_target_position),
                'current_pos': (lambda: self.current_position, None),
                'stop': (lambda: None, self.stop)
            },
            'command': {
                'current_command': (lambda: self.current_command, None),
                'expected_response': (lambda: self.expected_response, None),
                'command_queue': (lambda: self.command_queue, None)
            }
        }

    # ------------ Positional functions ------------

    def reverse_jog_direction(self, rev):
        """Reverse (True) or unreverse (False) the direction of the jog."""
        self.reverse_jog = bool(rev)

    def get_current_position(self):
        """Get the current position of this motor."""
        self.controller.get_encoder_position(self)
        return self.current_position

    def set_target_position(self, pos):
        """Set the target position of the motor."""
        raise NotImplementedError(f"Target position handling should be done on a case-by-case basis.")

    def home(self, value):
        """Home the motor."""
        self.homing = True
        self.controller.move_home(self)

    def stop(self, value):
        """Stop the motor."""
        self.homing = False
        self.moving = False
        self.controller.move_stop(self)
