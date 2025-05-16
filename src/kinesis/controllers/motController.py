"""Class to implement basic functionality for motors that use the 'MGMSG_MOT' style.
See the communications protocol docs for examples, such as the KDC101.
Functions implemented are movement, homing, stopping, position-getting, jogging and set jog params.
"""
import typing
import logging

from kinesis.controllers.baseMotorController import BaseMotorController
from kinesis.motor_stages.encoderStages import EncoderStage  # Assumption for this is encoder stage
from kinesis.commands import CMD
import kinesis.messages as MSG
from kinesis.responses import mID_to_func

class MotController(BaseMotorController):

    def __init__(self, port: str, device_type: str, bay_system: bool, stages: dict):
        super().__init__(port, device_type, bay_system, stages)

    # -------- MGMSG_MOT Implementations --------

    def move(self, position: float, motor: EncoderStage):
        """Move to a given absolute position.
        :param float position: the position to move the motor to.
        """
        if not self.port_is_open():
            return
        motor.await_queue.put(
            (MSG.mot_move_absolute, {'pos': position})
        )

    def move_home(self, motor: EncoderStage):
        """Home the device."""
        if not self.port_is_open():
            return
        motor.await_queue.put(
            (MSG.mot_move_home, {})
        )

    def set_jogparams(self, motor: EncoderStage):
        """Set the jog parameters for a given stage."""
        jogparams = {
            'jog_mode': motor.jog_mode,
            'step_size': motor.jog_step_size,
            'min_vel': motor.jog_min_vel,
            'accel': motor.jog_accel,
            'max_vel': motor.jog_max_vel,
            'stop_mode': motor.jog_stop_mode
        }
        motor.instant_queue.put(
            (next(motor._queue_counter), (MSG.mot_set_jogparams, jogparams))
        )

    def get_jogparams(self, motor: EncoderStage):
        """Get the jog parameters for a given stage."""
        motor.instant_queue.put((1, (MSG.mot_req_jogparams, None)))

    def move_jog(self, direction: bool, motor: EncoderStage):
        """Start a jog movement.
        :param bool direction: given from motor, True is forward
        """
        if not self.port_is_open():
            return
        if direction:
            motor.await_queue.put(
                (MSG.mot_move_jog, {'direction': 0x01})
            )
            logging.debug(f"added forward jog to queue")
        else:
            motor.await_queue.put(
                (MSG.mot_move_jog, {'direction': 0x00})
            )
            logging.debug(f"added backward jog to queue")

    def move_stop(self, motor: EncoderStage):
        """Stop the current move."""
        if not self.port_is_open():
            return
        
        # This is an await command, but we want stop to occur immediately - priority 0
        motor.instant_queue.put(
            (0, ('mot_move_stop', {}))
        )
        # Remove all other await tasks from the queue to avoid continued movement
        while not motor.await_queue.empty():
            var = motor.await_queue.get()

    # ------------ Positional functions ------------

    def get_encoder_position(self, motor: EncoderStage):
        """Get motor position (enccnt). This is then converted to a readable value.
        :return float: position converted to unit
        """
        if not self.port_is_open():
            return

        motor.instant_queue.put(
            (next(motor._queue_counter), (MSG.mot_req_enccounter, {}))
        )

    # ------------ Decode replies ------------

    def _decode_reply(self, reply: bytearray):
        """Use the registered response parsers to handle a response."""
        if not reply:
            return None, None
        motor: EncoderStage = None

        mID = int.from_bytes(reply[:2], 'little')
        parser_func = mID_to_func.get(mID)
        if not parser_func:
            logging.debug(f"Unexpected response: {hex(mID)}")
            return None, None

        response = parser_func(reply)
        cID = response.get("cID")
        source = response.get("source")
        motor = self._get_motor_from_channel(cID, source)

        logging.debug(f"response: {response}")

        match response["msg"]:
            case "mot_move_completed":
                motor.moving = False
            case "mot_move_homed":
                motor.homing = False
            case "mot_get_enccounter":
                pos = motor.read_position(response["enc_count"])
                motor.current_position = pos
            case "mot_get_jogparams":
                # This needs a value conversion
                motor.jog_mode = response["jog_mode"]
                motor.jog_step_size = response["step_size"]
                motor.jog_min_vel = response["min_velocity"]
                motor.jog_accel = response["acceleration"]
                motor.jog_max_vel = response["max_velocity"]
                motor.jog_stop_mode = response["stop_mode"]

        return motor, response["msg"]

    # def _decode_reply(self, reply: bytearray):
    #     """Handle the expected responses for devices using the MGMSG_MOT command implementations.
    #     Converts bytearray to usable information.
    #     :param bytearray reply: bytes to be decoded
    #     """
    #     if not reply:
    #         return '','',  # motor, response name
    #     motor: EncoderStage = None

    #     mID = int.from_bytes(reply[:2], 'little')  # Message ID
    #     rsp, length = CMD.get_response_info(mID)

    #     # Channel identity is (usually) third byte if header-only, or first two bytes of non-header data
    #     if length == 0:
    #         cID = reply[2]
    #     else:
    #         cID = int.from_bytes(reply[6:8], byteorder='little')

    #     source = reply[5]  # Source is the final header byte

    #     # Process the reply in its own statement
    #     # motor is identified there in case cID is handled uniquely
    #     match rsp, length:
    #         case ("Unknown", 0):
    #             return "Unknown", None
    #         case ("move_homed", 0):
    #             motor = self._get_motor_from_channel(cID, source)
    #             motor.homing = False
    #         case ("move_completed", 14):
    #             motor = self._get_motor_from_channel(cID, source)
    #             motor.moving = False
    #         case ("get_enccounter", 6):
    #             motor = self._get_motor_from_channel(cID, source)
    #             params = reply[8:]
    #             position = motor.read_position(params)
    #             motor.current_position = position
    #         case ("get_info", 84):
    #             hwinfo = reply[6:]
    #             # As according to page 52 of manual
    #             self.hardware_info = {
    #                 "serial_number": int.from_bytes(hwinfo[0:4], byteorder='little'),
    #                 "model_number":  hwinfo[4:12].decode('ascii').strip(),
    #                 "hardware_type": int.from_bytes(hwinfo[12:14], byteorder='little'),
    #                 "firmware_version": {
    #                     "major":   hwinfo[16],
    #                     "interim": hwinfo[15],
    #                     "minor":   hwinfo[14],
    #                 },
    #                 "hardware_version":   int.from_bytes(hwinfo[78:80], byteorder='little'),
    #                 "modification_state": int.from_bytes(hwinfo[80:82], byteorder='little'),
    #                 "number_of_channels": int.from_bytes(hwinfo[82:84], byteorder='little')
    #             }
    #         case ("get_jogparams", 22):
    #             motor = self._get_motor_from_channel(cID, source)
    #             jogparams = reply[8:]
    #             motor.jog_mode = int.from_bytes(jogparams[0:2], byteorder='little')
    #             motor.jog_step_size = motor.read_position(jogparams[2:6])
    #             motor.jog_min_vel = motor.read_velocity(jogparams[6:10])
    #             motor.jog_accel = motor.read_accel(jogparams[10:14])
    #             motor.jog_max_vel = motor.read_velocity(jogparams[14:18])
    #             motor.jog_stop_mode = int.from_bytes(jogparams[18:20], byteorder='little')

    #     # Called by _check_reply_queues, return the motor and what the expected response is
    #     # If the response needs handling, this has been done already
    #     # If the response is in the queue, that gets sorted now
    #     return motor, rsp
