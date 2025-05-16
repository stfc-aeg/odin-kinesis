import typing
import logging

from kinesis.controllers.baseMotorController import BaseMotorController
from kinesis.motor_stages.piezoStages import PiezoStage
from kinesis.commands import CMD

class PzController(BaseMotorController):

    def __init__(self, port: str, device_type: str, bay_system: bool, stages: dict):
        super().__init__(port, device_type, bay_system, stages)

    # -------- PZMOT Implementations --------

    def move(self, params: bytearray, motor: PiezoStage):
        """Move to a given absolute position.
        :param bytearray params: command parameters, 4 bytes for target pos in encoder counts
        """
        if not self.port_is_open():
            return
        motor.await_queue.put(
            ('move', params)
        )

    def move_home(self, motor: PiezoStage):
        """Home the device."""
        if not self.port_is_open():
            return
        motor.await_queue.put(
            ('home', None)
        )

    def set_jogparams(self, motor: PiezoStage):
        """Set the jog parameters for a given stage."""
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

    def get_jogparams(self, motor: PiezoStage):
        """Get the jog parameters for a given stage."""
        motor.instant_queue.put((1, ('get_jog_params', None)))

    def move_jog(self, direction: bool, motor: PiezoStage):
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

    def move_stop(self, motor: PiezoStage):
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

    def get_encoder_position(self, motor: PiezoStage):
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
        """Handle expected responses for devices using the PZMOT command implementations.
        Converts the bytearray to usable information.
        :param bytearray reply: bytes to be decoded
        """
        if not reply:
            return '', ''  # motor, response name
        motor: PiezoStage = None

        mID = int.from_bytes(reply[:2], 'little')  # Message ID
        rsp, length = CMD.get_response_info(mID)

        # Channel identity is (usually) third byte if header-only, or first two bytes of non-header data
        # For submessage-IDs, the cID will be the third and fourth bytes of non-header data
        if length == 0:
            cID = reply[2]
        elif mID==0x08C2:  # Submessage get_ code
            subMId = int.from_bytes(reply[6:8], byteorder='little')
            cID = int.from_bytes(reply[8:10], byteorder='little')
        else:  # not submessage, has data
            cID = int.from_bytes(reply[6:8], byteorder='little')

        source = reply[5]

        match rsp, length:
            case ("Unknown", 0):
                return "Unknown", None
            case ("move_completed", 14):
                motor = self._get_motor_from_channel(cID, source)
                motor.moving = False
            case ("pzmot_getparams", r_len):
                # Variable length on this reply
                pass