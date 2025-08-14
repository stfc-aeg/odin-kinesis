"""Class to implement basic functionality for motors that use the 'MGMSG_MOT' style.
See the communications protocol docs for examples, such as the KDC101.
Functions implemented are movement, homing, stopping, position-getting, jogging and set jog params.
"""
import typing
import logging

from kinesis.controllers.baseMotorController import BaseMotorController
from kinesis.motor_stages.encoderStages import EncoderStage, ValueType  # Assumption for this is encoder stage
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
            'step_size': motor.val_to_enc(motor.jog_step_size, ValueType.POS),
            'min_vel': motor.val_to_enc(motor.jog_min_vel, ValueType.VEL),
            'accel': motor.val_to_enc(motor.jog_accel, ValueType.ACC),
            'max_vel': motor.val_to_enc(motor.jog_max_vel, ValueType.VEL),
            'stop_mode': motor.jog_stop_mode
        }
        motor.instant_queue.put(
            (next(motor._queue_counter), (MSG.mot_set_jogparams, jogparams))
        )

    def get_jogparams(self, motor: EncoderStage):
        """Get the jog parameters for a given stage."""
        motor.instant_queue.put(
            (next(motor._queue_counter),
            (MSG.mot_req_jogparams, None))
            )

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
        else:
            motor.await_queue.put(
                (MSG.mot_move_jog, {'direction': 0x02})
            )

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

        match response["msg"]:
            case "mot_move_completed":
                motor.moving = False
            case "mot_move_homed":
                motor.homing = False
            case "mot_get_enccounter":
                pos = motor.enc_to_val(response["enc_count"], ValueType.POS)
                motor.current_position = pos
            case "mot_get_jogparams":
                # This needs a value conversion
                motor.jog_mode = response["jog_mode"]
                motor.jog_step_size = motor.enc_to_val(response["step_size"], ValueType.POS)
                motor.jog_min_vel = motor.enc_to_val(response["min_velocity"], ValueType.VEL)
                motor.jog_accel = motor.enc_to_val(response["acceleration"], ValueType.ACC)
                motor.jog_max_vel = motor.enc_to_val(response["max_velocity"], ValueType.VEL)
                motor.jog_stop_mode = response["stop_mode"]

        return motor, response["msg"]
