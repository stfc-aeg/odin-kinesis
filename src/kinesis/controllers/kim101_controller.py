import typing
import logging

from kinesis.controllers.baseMotorController import BaseMotorController
from kinesis.motor_stages.piezoStages import PiezoStage
import kinesis.messages as MSG
from kinesis.responses import mID_to_func

class KimController(BaseMotorController):

    def __init__(self, port: str, device_type: str, bay_system: bool, stages: dict):
        super().__init__(port, device_type, bay_system, stages)

    # -------- PZMOT Implementations --------

    def move(self, steps: int, motor: PiezoStage):
        """Move to a given absolute position.
        :param bytearray params: command parameters, 4 bytes for target pos in encoder counts
        """
        if not self.port_is_open():
            return
        # The KIM101 controller doesn't reply with pzmot_move_completed messages
        # The instant queue exists so this should be okay
        motor.instant_queue.put(
            (next(motor._queue_counter), (MSG.pzmot_move_absolute, {'pos': steps}))
        )

    def move_home(self, motor: PiezoStage):
        """For the KIM devices, this is 'zeroing'. See pages 15/20 of the KIM001/101 manual:
        https://www.thorlabs.com/drawings/2527d5f06e52745-AF3E603D-F192-6020-FF13C3853C610B19/KIM001-KinesisManual.pdf"""
        if not self.port_is_open():
            return
        motor.instant_queue.put(
          (next(motor._queue_counter),
          (MSG.pzmot_set_poscounts, {'pos': 0}))
        )

    def set_jogparams(self, motor: PiezoStage):
        """Set the jog parameters for a given stage."""
        jogparams = {
            'jog_mode': motor.jog_mode,
            'jog_step_size_fwd': motor.jog_step_size_fwd,
            'jog_step_size_rev': motor.jog_step_size_rev,
            'jog_step_rate': motor.jog_step_rate,
            'jog_step_accn': motor.jog_step_accn
        }
        motor.instant_queue.put(
            (next(motor._queue_counter), (MSG.pzmot_set_kcubejogparams, jogparams))
        )

    def get_jogparams(self, motor: PiezoStage):
        """Get the jog parameters for a given stage."""
        motor.instant_queue.put(
            (next(motor._queue_counter),
             (MSG.pzmot_get_kcubejogparams, None))
            )

    def move_jog(self, direction: bool, motor: PiezoStage):
        """Start a jog movement.
        :param bool direction: given from motor, True is forward
        """
        if not self.port_is_open():
            return
        if direction:
            motor.instant_queue.put(
                (next(motor._queue_counter),
                (MSG.pzmot_move_jog, {'jog_dir': 0x01}))
            )
        else:
            motor.instant_queue.put(
                (next(motor._queue_counter),
                (MSG.pzmot_move_jog, {'jog_dir': 0x02}))
            )

    def move_stop(self, motor: PiezoStage):
        """Stop the current move."""
        if not self.port_is_open():
            return

        # This is an await command, but we want stop to occur immediately - priority 0
        motor.instant_queue.put(
            (0, (MSG.mot_move_stop, None))
        )
        # Remove all other await tasks from the queue to avoid continued movement
        while not motor.await_queue.empty():
            var = motor.await_queue.get()

    # ------------ Positional functions ------------

    def get_encoder_position(self, motor: PiezoStage):
        """Get the position counter value of the stage."""
        if not self.port_is_open():
            return
        motor.instant_queue.put(
            (next(motor._queue_counter), (MSG.pzmot_req_poscounts, None))
        )

    # ------------ Decode replies ------------

    def _decode_reply(self, reply: bytearray):
        """Handle the expected responses for the KIM001 or KIM101 devices.
        Converts bytearray to usable information.
        :param bytearray reply: bytes to be decoded
        """
        if not reply:
            return None, None
        motor: PiezoStage = None

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
            case "pzmot_move_completed":
                motor.moving = False
                motor.current_position = response["position"]
            case "pzmot_get_params":
                match response["submessage_id"]:
                    case 5:
                        motor.current_position = response["position"]
                    case 0x2D:
                        motor.jog_mode = response["jog_mode"]
                        motor.jog_step_size_fwd = response["jog_step_size_fwd"]
                        motor.jog_step_size_rev = response["jog_step_size_rev"]
                        motor.jog_step_rate = response["jog_step_rate"]
                        motor.jog_step_accn = response["jog_step_accn"]
        return motor, response["msg"]