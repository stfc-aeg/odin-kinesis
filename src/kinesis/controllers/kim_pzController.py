import typing
import logging

from kinesis.controllers.baseMotorController import BaseMotorController
from kinesis.motor_stages.motor import Motor

class PzController(BaseMotorController):

    def __init__(self, port: str, device_type: str, bay_system: bool, stages: dict):
        super().__init__(port, device_type, bay_system, stages)

    # -------- PZMOT Implementations --------

    def move(self, params: bytearray, motor: Motor):
        """Move to a given absolute position.
        :param bytearray params: command parameters, 4 bytes for target pos in encoder counts
        """
        if not self.port_is_open():
            return
        motor.await_queue.put(
            ('move', params)
        )

    def move_home(self, motor: Motor):
        """For the KIM devices, this is 'zeroing'. See pages 15/20 of the KIM001/101 manual:
        https://www.thorlabs.com/drawings/2527d5f06e52745-AF3E603D-F192-6020-FF13C3853C610B19/KIM001-KinesisManual.pdf"""
        if not self.port_is_open():
            return
        motor.await_queue.put(
            ('home', None)
        )

    def set_jogparams(self, motor: Motor):
        """Set the jog parameters for a given stage."""
        jogparams = [
            motor.jog_mode.to_bytes(2, byteorder='little')
        ]

        jogparams = [
            motor.jog_mode.to_bytes(2, byteorder='little'),  # 2 bytes
            motor.convert_position(motor.jog_step_size),  # 4 bytes
            motor.convert_velocity(motor.jog_min_vel),  # 4 bytes
            motor.convert_accel(motor.jog_accel),  # 4 bytes
            motor.convert_velocity(motor.jog_max_vel),  # 4 bytes
            motor.jog_stop_mode.to_bytes(2, byteorder='little') # 2 bytes
        ]
        params = b''.join(jogparams)

        motor.instant_queue.put(
            (1, ('set_jog_params', params))
        )

    def get_jogparams(self, motor: Motor):
        """Get the jog parameters for a given stage."""
        motor.instant_queue.put((1, ('get_jog_params', None)))

    def move_jog(self, direction: bool, motor: Motor):
        """Start a jog movement.
        :param bool direction: given from motor, True is forward
        """
        if not self.port_is_open():
            return
        if direction:
            motor.await_queue.put(
                ('jog_forward', None)
            )
            logging.debug(f"added forward jog to queue")
        else:
            motor.await_queue.put(
                ('jog_backward', None)
            )
            logging.debug(f"added backward jog to queue")

    def move_stop(self, motor: Motor):
        """Stop the current move."""
        if not self.port_is_open():
            return
        
        # This is an await command, but we want stop to occur immediately - priority 0
        motor.instant_queue.put(
            (0, ('stop', None))
        )
        # Remove all other await tasks from the queue to avoid continued movement
        while not motor.await_queue.empty():
            var = motor.await_queue.get()

    # ------------ Positional functions ------------

    def get_encoder_position(self, motor: Motor):
        """Get motor position (enccnt). This is then converted to a readable value.
        :return float: position converted to unit
        """
        if not self.port_is_open():
            return
        
        motor.instant_queue.put(
            (1, ('get_position', None))
        )

    # ------------ Decode replies ------------

    def _decode_reply(self, reply: bytearray):
        """Handle the expected responses for the KIM001 or KIM101 devices.
        Converts bytearray to usable information.
        :param bytearray reply: bytes to be decoded
        """