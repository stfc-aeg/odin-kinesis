"""Base motor controller class to handle serial communications for Thorlabs controllers.
Specific implementations of movement and positional commands (relating to the parameters needed)
will be handled by child classes.
"""
import serial
import logging
import time
import struct
from typing import Callable

from kinesis.commands import CMD, DEVICE_COMMANDS
from kinesis.responses import mID_to_func
from kinesis.motor_stages.baseMotorStage import BaseMotorStage
from kinesis.motor_stages.encoderStages import EncoderStage

class BaseMotorController:
    """Base controller class manages serial communications."""

    def __init__(self, port: str, device_type: str, bay_system: bool, stages: dict):
        self.device_type = device_type
        self.stages = stages

        self.serial = None
        self._in_buffer = bytearray()

        self._open_serial(port)

        self.tree = {}

        self.tree = {}
        chan_ident = 1

        # Create motor children
        for name, details in stages.items():
            stage_type = details['stage_type']
            if stage_type in ['MTS25-Z8', 'MTS50-Z8']:
                self.stages[name] = EncoderStage(name, chan_ident, stage_type, self)

            chan_ident += 1

    def initialize(self):
        """Post-init function to populate further motor parameters."""
        logging.debug(f"controller init")
        for motor in self.stages.values():
            motor.initialize()
        logging.debug(f"made it through motor init")
        for name, stage in self.stages.items():
            self.tree[name] = self.stages[name].tree
        self.tree = {
            'motors': self.tree
        }
        logging.debug(f"tree created")

    def _open_serial(self, port: str):
        """Open the serial connection."""
        self.ser = serial.Serial(port, baudrate=115200, bytesize=8, parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE, xonxoff=0, rtscts=True, timeout=1)

    def port_is_open(self):
        """Check if the serial port is open.
        :returns: False if closed, True if open
        """
        try:
            if not self.ser.is_open:
                logging.debug("Serial port is not open.")
                return False
        except AttributeError:
            logging.warning(f"No serial port is connected.")
            return False
        return True

    def close_serial(self):
        """Close the serial connection."""
        if not self.port_is_open():
            return
        self.ser.close()
        logging.debug("Serial connection closed.")

    def send_cmd(self, command_fn: Callable, command_args, motor: BaseMotorStage):
        if not self.port_is_open() or not motor:
            return
        
        data = command_fn(
            cID=motor.channel_identity,
            dest=motor.destination,
            source=0x01,  # Page 35: this shouldn't change
            **(command_args or {})
        )
        # command functions return bytes and exp_rsp
        self.ser.write(data['bytes'])

        # Return any expected response info
        return data.get('exp_rsp', None)


    # def send_cmd(self, command: str, command_params: bytearray=None, motor: BaseMotorStage=None):
    #     """Send a command through the serial port.
    #     :param str command: name of the command to send
    #     :param bytearray command_params: additional parameter bytes required by command
    #     :param Motor: motor to send the command to
    #     :param bool await_response: does the response require waiting (e.g.: movement taking time)
    #     """
    #     if not self.port_is_open() or not motor:
    #         return

    #     # Command header structure:
    #     # bytes | detail
    #     # 0, 1  | message id
    #     # 2, 3  | param1/2, or data packet length if command has data
    #     # 4     | destination: 0x50 but different for bay/card systems
    #     # 5     | source: 0x01 as host is always communicating

    #     # cmd = CMD.get_command(command)
    #     cmd = DEVICE_COMMANDS[command][self.device_type]
    #     data = cmd.build_command(
    #         chan_ident=motor.channel_identity,
    #         data=command_params,
    #         destination=motor.destination
    #     )

    #     self.ser.write(data)

    def _recv_reply(self):
        """Receive any available replies."""
        if not self.port_is_open():
            return []
        time.sleep(0.04)  # Necessary delay for data arrival
        # Fill buffer from serial
        while self.ser.in_waiting > 0:
            self._in_buffer.extend(self.ser.read())
        replies = []
        # While there is more data than at least one header
        while len(self._in_buffer) >= 6:
            # Check bytes for known message ID
            mID, length = struct.unpack_from("<HH", self._in_buffer)
            if not mID in mID_to_func:
                logging.debug(f"Message ID not recognised.")
                self._in_buffer = self._in_buffer[1:]  # Remove first byte and check again
                continue

            # Now identified as a potential message, check other locations
            long = self._in_buffer[4] & 0x80  # MSB of byte 4 is 'post-header data' flag
            dest = self._in_buffer[4] & ~0x80  # Dest is rest of byte
            source = self._in_buffer[5]  # 5th byte is source
            # Check locations
            if dest not in (0x00, 0x01) or source not in (
                0x00, 0x11, 0x21, 0x22, 0x23, 0x24,
                0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x50):
                logging.debug(f"Invalid source or destination for msg {mID}, src: {source}, dest: {dest}")
                self._in_buffer = self._in_buffer[1:]  # Remove first byte and check again
                continue

            # Post-header data message handling
            if long:
                # Messages are limited in docs to 255 bytes
                if length > 255:
                    logging.debug(f"Invalid length {length} for mID {mID}.")
                    self._in_buffer = self._in_buffer[1:]  # Remove first byte and check again
                    continue
            else:
                length = 0
            msg_length = 6+length

            # Check if entire message is available
            if len(self._in_buffer) < msg_length:
                # Wait for more data next time, retaining buffer
                break
            # If it is, get the message
            msg = bytes(self._in_buffer[:msg_length])
            replies.append(msg)
            # Remove message from the buffer
            self._in_buffer = self._in_buffer[msg_length:]

        return replies

    # def _recv_reply(self):
    #     """Receive and parse a reply."""
    #     if not self.port_is_open():
    #         return []

    #     time.sleep(0.04)  # necessary delay

    #     # Get every byte - this could be multiple messages
    #     while self.ser.in_waiting > 0:
    #         self._in_buffer.extend(self.ser.read())

    #     # Process raw into replies
    #     replies = []
    #     i = 0
    #     while i < (len(self._in_buffer)-1):  # mID needs 2 bytes
    #         mID = self._in_buffer[i:i+2]
    #         mID = int.from_bytes(mID, 'little')
    #         rsp, length = CMD.get_response_info(mID)
    #         if rsp == "Unknown":  # If this is not a response ID, move on
    #             i += 1
    #             continue
    #         msg_length = 6 + length  # Header is 6 bytes
    #         if i + msg_length > len(self._in_buffer):
    #             # Not enough data yet, break
    #             break
        
    #         msg = self._in_buffer[i:i+msg_length]
    #         replies.append(msg)
    #         i += msg_length

    #     # Any unprocessed bytes 
    #     self._in_buffer = self._in_buffer[i:]

    #     return replies

    def _get_motor_from_channel(self, cID: int, source: int):
        """Return a motor object based on the channel identity and source values passed."""
        # Generally, if cID isn't 1, the 'source' of the response (or 'destination' of the motor)
        # will be 0x50 (generic USB device). If cID is 1, source may be 0x50, but in a 'card/bay'
        # system, this will be 0x21->0x2A for bay 0->9. Checking both should cover most all cases
        # See pages 35 and 36 of the APT protocol for more information.
        for name, motor in self.stages.items():
            if cID == motor.channel_identity and source == motor.destination:
                return motor
        return None

    def _decode_reply(self, reply: bytearray):
        raise NotImplementedError("Reply decoding must be implemented by the controller subclass.")

    def _check_reply_queues(self):
        """Check the instant queue to send any commands from it.
        Then check for replies, seeing if a response is expected by any motor.
        If it is, send the next command from that motor's await_queue.
        """
        # Send one instant command from the queue, if there is one
        for name, motor in self.stages.items():
            if not motor.instant_queue.empty():
                priority, (cmd_fn, cmd_args) = motor.instant_queue.get()
                self.send_cmd(cmd_fn, cmd_args, motor)
            # With no active command and one in queue, send one
            if (motor.current_command is None) and (not motor.await_queue.empty()):
                cmd_fn, cmd_args = motor.await_queue.get()
                exp_rsp = self.send_cmd(cmd_fn, cmd_args, motor)

                motor.current_command = cmd_fn.__name__
                motor.expected_response = exp_rsp['name']

        # Then process replies
        replies = self._recv_reply()

        for reply in replies:
            # rsp, cID, params = self.decode_reply(reply)
            motor, response = self._decode_reply(reply)

            # Bad data
            if not motor:
                continue

            # If this is an expected response, clear/move through await_queue
            if response == motor.expected_response:
                logging.debug(f"Response for motor {motor.name}, moving through queue.")

                motor.current_command = None
                motor.expected_response = None

                if motor.await_queue.empty():
                    logging.debug(f"Motor {motor.name} queue cleared.")
                else:
                    cmd_fn, cmd_args = motor.await_queue.get()
                    exp_rsp = self.send_cmd(cmd_fn, cmd_args, motor)

                    motor.current_command = cmd_fn.__name__
                    motor.expected_response = exp_rsp['name']

