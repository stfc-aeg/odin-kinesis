"""Class to handle the state of a given motor.
It tracks the encoder/scale-factor values for the stage type, the command queue for that motor
and handles conversions for that motor.
"""
import logging
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

        self.tree = {
            'position': {
                'home': (lambda: None, self.home),
                'set_target_pos': (lambda: self.target_position, self.set_target_position),
                'current_pos': (lambda: self.get_current_position(), None),
                'stop': (lambda: None, self.stop)
            },
            'command': {
                'current_command': (lambda: self.current_command, None),
                'expected_response': (lambda: self.expected_response, None),
                'command_queue': (lambda: self.command_queue, None)
            }
        }

    # ------------ Positional functions ------------

    def get_current_position(self):
        """Get the current position of this motor."""
        self.controller.get_encoder_position(self)
        return self.current_position

    def set_target_position(self, pos):
        """Set the target position of the motor."""
        pos = float(pos)
        self.target_position = pos

        if self.target_position != self.current_position:
            params = self.convert_position(self.target_position)
            self.controller.move(params, self)

    def home(self, value):
        """Home the motor."""
        self.homing = True
        self.controller.move_home(self)

    def stop(self, value):
        """Stop the motor."""
        self.homing = False
        self.moving = False
        self.controller.move_stop(self)
