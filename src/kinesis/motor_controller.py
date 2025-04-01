"""Class to manage the state of some number of motors and process serial commands on their behalf."""

from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError

# Motor imports
from concurrent import futures
from tornado.concurrent import run_on_executor

import serial
import time
import logging

from kinesis.motor import Motor
from kinesis.commands import CMD

class MotorController():
    """Class to represent an arbitrary motor controller."""

    def __init__(self, port: str, device_type: str, bay_system: bool, stages: dict):
        """Initialise the motor controller.
        :param str port: serial port to use
        :param str device_type: type of motor controller e.g. KDC101
        :param dict stages: dictionary of stages with name and details (devices.json)
        """
        self.device_type = device_type  # Used for command compatibility
        self.stages = stages  # Used to instantiate motor stages this controls

        # self.cmd = CMD_RSP("test/config/commands.json")
        self.cmd = CMD()

        # Create serial connection
        self.open_serial(port)

        self.stages = {}
        self.tree = {}
        chan_ident = 1
        # Create motor children
        for name, details in stages.items():
            stage_type = details['stage_type']
            self.stages[name] = Motor(name, chan_ident, stage_type, self)

            chan_ident += 1

            self.tree[name] = self.stages[name].tree

        self.tree = {
            'motors': self.tree
        }


    # ------------ Serial functions ------------

    def open_serial(self, port: str):
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

    def send_cmd(self, command: str, command_params: bytearray=None, motor:Motor=None, await_response: bool=False):
        """Send a command through the serial port.
        :param str command: name of the command to send
        :param bytearray command_params: additional parameter bytes required by command
        :param Motor: motor to send the command to
        :param bool await_response: does the response require waiting (e.g.: movement taking time)
        """
        if not self.port_is_open() or not motor:
            return

        if await_response:
            if motor.current_command:
                logging.debug(f"Adding {command} to {motor.name} queue.")
                # Add command and any parameters to the queue
                motor.command_queue.append(
                    (command, command_params)
                )
                return
            motor.current_command = command

            # Expected response info - only need name, not length from tuple
            motor.expected_response = self.cmd.get_expected_response(command)[0]

        # Command header structure:
        # bytes | detail
        # 0, 1  | message id
        # 2, 3  | param1/2, or data packet length if command has data
        # 4     | destination: 0x50 but different for bay/card systems
        # 5     | source: 0x01 as host is always communicating

        cmd = CMD.get_command(command)
        data = cmd.build_command(
            chan_ident=motor.channel_identity,
            data=command_params,
            destination=motor.destination
        )

        logging.debug(f"data: {data}")

        self.ser.write(data)

    def recv_reply(self):
        """Receive and parse a reply."""
        if not self.port_is_open():
            return

        time.sleep(0.04)  # necessary delay

        reply = bytearray()
        while self.ser.in_waiting > 0:
            # Read every byte
            reply.extend(self.ser.read())

        return reply

    def decode_reply(self, reply: bytearray):
        """Convert reply to readable information.
        :return tuple: response name, channel identity, response body
        """
        if not reply:
            return '','', ''  # response, params


        mID = reply[:2]
        rsp, length = self.cmd.get_response_info(mID)

        # If there is non-header info in reply, channel_identity is first, and define params
        if length > 0:
            cID = int.from_bytes(reply[6:8], byteorder='little')
            rsp_params = reply[8:]
        # If reply is header-only, cID is third byte
        else:
            cID = reply[2]  # cID goes here if there's no non-header data
            rsp_params = b''

        return rsp, cID, rsp_params

    def _check_reply_queues(self):
        """Check the queue for any replies, and see if that response is expected by any given motor.
        If it is, send the next command in that motor's queue.
        """
        reply = self.recv_reply()
        rsp, cID, params = self.decode_reply(reply)

        for name, motor in self.stages.items():
            if cID == motor.channel_identity:
                logging.debug(f"cid: {cID}, motor cID: {motor.channel_identity}")
                logging.debug(f"motor exp_rsp: {motor.expected_response}")
                if rsp == motor.expected_response:
                    logging.debug(f"Response for motor {motor.name}, moving through queue.")

                    motor.current_command = None
                    if not motor.command_queue:
                        logging.debug(f"motor {motor.name} queue empty.")
                    else:
                        cmd = motor.command_queue.pop()
                        logging.debug(f"New command {cmd} for motor {motor.name}")
                        # Commands saved to queue are a command and parameters
                        self.send_cmd(
                            command=cmd[0],
                            command_params=cmd[1],
                            motor=motor,
                            await_response=True
                        )

    # ------------ Controller functions ------------

    def identify(self):
        """Run the identify command, flashing to identify the controller."""
        if not self.port_is_open():
            return
        self.send_cmd('identify')

    # def get_hardware_info(self):
    #     """Get the controller's serial number."""
    #     if not self.port_is_open():
    #         return
    #     self.send_cmd('req_info')

    #     reply = self.recv_reply()
    #     msg, hwinfo = self.decode_reply(reply)

    #     # As according to page 52 of manual
    #     hardware_info = {
    #         "serial_number": int.from_bytes(hwinfo[0:4], byteorder='little'),
    #         "model_number":  hwinfo[4:12].decode('ascii').strip(),
    #         "hardware_type": int.from_bytes(hwinfo[12:14], byteorder='little'),
    #         "firmware_version": {
    #             "major":   hwinfo[16],
    #             "interim": hwinfo[15],
    #             "minor":   hwinfo[14],
    #         },
    #         "hardware_version":   int.from_bytes(hwinfo[78:80], byteorder='little'),
    #         "modification_state": int.from_bytes(hwinfo[80:82], byteorder='little'),
    #         "number_of_channels": int.from_bytes(hwinfo[82:84], byteorder='little')
    #     }

    #     return hardware_info

    # def get_mmi_params(self):
    #     """Get controller-cube top panel/wheel settings.
    #     For specific parameter information, see pages 137-138 of the protocol.
    #     :returns dict: mmi parameters
    #     """
    #     if not self.port_is_open():
    #         return
    #     self.send_cmd('req_mmiparams')
    #     reply = self.recv_reply()
    #     msg, mmiinfo = self.decode_reply(reply)

    #     mmi_params = {
    #         'channel_identity': mmiinfo[0:2],
    #         'joystick_mode': mmiinfo[2:4],
    #         'joystick_max_velocity': mmiinfo[4:8],
    #         'joystick_acceleration': mmiinfo[8:12],
    #         'direction_sense': mmiinfo[12:14],
    #         'preset_position_1': mmiinfo[14:18],
    #         'preset_position_2': mmiinfo[18:22],
    #         'display_brightness': mmiinfo[22:24],
    #         'display_timeout': mmiinfo[24:26],
    #         'display_dim_level': mmiinfo[26:28]
    #     }
    #     # preset_position_3 (28:32) and w_joystick_sensitivity (32:34) are for BBD30x only

    #     return mmi_params

    # ------------ Movement functions ------------
    # These functions await a reply that the motor has reached its position.

    def move(self, params, motor: Motor):
        self.send_cmd(
            'move_absolute_arg',
            command_params=params,
            motor=motor,
            await_response=True
        )

    def move_home(self, motor: Motor):
        """Home the device."""
        if not self.port_is_open():
            return
        # No parameters but requires waiting
        self.send_cmd(
            command='move_home',
            motor=motor,
            await_response=True
        )

    def move_stop(self, motor: Motor):
        """Stop the current move."""
        if not self.port_is_open():
            return
        # No parameters but requires waiting (stops are not instant)
        self.send_cmd(
            commmand='move_stop',
            motor=motor,
            await_response=True
        )

    # # ------------ Positional functions ------------

    def get_encoder_position(self, motor: Motor):
        """Get motor position (enccnt). This is then converted to a readable value.
        :return float: position converted to unit
        """
        if not self.port_is_open():
            return
        self.send_cmd(
            command='req_enccounter',
            motor=Motor,
            await_response=False
        )

        reply = self.recv_reply()
        try:
            if self.DEBUG:
                logging.debug(f"Encoder position reply: {reply}")
            rsp, cID, params = self.decode_reply(reply)
            # Pages 64-65, GET structure
            pos = params[2:]
            motor.current_position = motor.convert_enccnt(pos)
        except ValueError:
            position=None
        motor.current_position = position

