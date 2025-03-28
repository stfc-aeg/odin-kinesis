"""Class to manage the state of some number of motors and process serial commands on their behalf."""

from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError

# Motor imports
from concurrent import futures
from tornado.concurrent import run_on_executor

import serial
import time
import logging

from kinesis.cmds import CMD_RSP
from kinesis.controller import KinesisError

class MotorController():
    """Class to represent an arbitrary motor controller."""

    def __init__(self, port: str, device_type: str, stages: int):
        self.device_type = device_type  # Used for command compatibility
        self.stages = stages  # Used to instantiate motor stages this controls

        self.cmd = CMD_RSP("test/config/commands.json")

        # Create serial connection
        self.open_serial('/dev/ttyUSB0')

        # Create motor children
        # 
        # provided via argument as this does not need access to the options
        # that should be handled at adapter-level
        # may need a 'motor_details' dict or something. or at least a list of types in order

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

    def send_cmd(self, command: str, command_params: bytearray=None, await_response: bool=False):
        """Send a command through the serial port.
        :param str command: name of the command to send
        :param bytearray command_params: additional parameter bytes required by command
        :param bool await_response: does the response require waiting (e.g.: movement taking time)
        """
        if not self.port_is_open():
            return

        # Set current command and response for await_reply
        # Not needed for instant activities
        if await_response:
            if self.current_command:
                logging.debug(f"Command in progress, adding {command} to queue.")
                # Append the command and any parameters
                self.command_queue.append(
                    (command,
                    command_params)
                )
                return
            self.current_command = command
            # Only need first part of expected response info (name, not length)
            self.expected_response = self.cmd.get_expected_response(command)[0]

        # Get command bytes and add params if provided
        cmd = self.cmd.get_command(command)
        if command_params:
            cmd += command_params
        # Send the command
        self.ser.write(cmd)

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
        """Convert reply to readable information."""
        if not reply:
            return '',''  # response, params

        mID = reply[:2]
        rsp, length = self.cmd.get_response_info(mID)
        logging.debug(f"Reply: {rsp}")

        rsp_params = reply[6:6+length] if length >0 else b''

        return rsp, rsp_params
    # ------------ Controller functions ------------

    def identify(self):
        """Run the identify command, flashing to identify the controller."""
        if not self.port_is_open():
            return
        self.send_cmd('identify')

    def get_hardware_info(self):
        """Get the controller's serial number."""
        if not self.port_is_open():
            return
        self.send_cmd('req_info')

        reply = self.recv_reply()
        msg, hwinfo = self.decode_reply(reply)

        # As according to page 52 of manual
        hardware_info = {
            "serial_number": int.from_bytes(hwinfo[0:4], byteorder='little'),
            "model_number":  hwinfo[4:12].decode('ascii').strip(),
            "hardware_type": int.from_bytes(hwinfo[12:14], byteorder='little'),
            "firmware_version": {
                "major":   hwinfo[16],
                "interim": hwinfo[15],
                "minor":   hwinfo[14],
            },
            "hardware_version":   int.from_bytes(hwinfo[78:80], byteorder='little'),
            "modification_state": int.from_bytes(hwinfo[80:82], byteorder='little'),
            "number_of_channels": int.from_bytes(hwinfo[82:84], byteorder='little')
        }

        return hardware_info

    def get_mmi_params(self):
        """Get controller-cube top panel/wheel settings.
        For specific parameter information, see pages 137-138 of the protocol.
        :returns dict: mmi parameters
        """
        if not self.port_is_open():
            return
        self.send_cmd('req_mmiparams')
        reply = self.recv_reply()
        msg, mmiinfo = self.decode_reply(reply)

        mmi_params = {
            'channel_identity': mmiinfo[0:2],
            'joystick_mode': mmiinfo[2:4],
            'joystick_max_velocity': mmiinfo[4:8],
            'joystick_acceleration': mmiinfo[8:12],
            'direction_sense': mmiinfo[12:14],
            'preset_position_1': mmiinfo[14:18],
            'preset_position_2': mmiinfo[18:22],
            'display_brightness': mmiinfo[22:24],
            'display_timeout': mmiinfo[24:26],
            'display_dim_level': mmiinfo[26:28]
        }
        # preset_position_3 (28:32) and w_joystick_sensitivity (32:34) are for BBD30x only

        return mmi_params

    # ------------ Movement functions ------------
    # These functions await a reply that the motor has reached its position.

    def move_absolute(self, distance: float):
        """Move to the specified position.
        :param float distance: desired motor position
        """
        logging.debug(f"arg distance: {distance}")
        if not self.port_is_open():
            return

        # Command params - 4 bytes of distance
        params = self.convert_distance(distance)

        self.send_cmd(
            'move_absolute_arg',
            command_params=params,
            await_response=True
        )

    def move_relative(self, distance: float):
        """Move by the specified amount.
        :param float distance: desired amount to move
        """
        if not self.port_is_open():
            return
        # Command params - 4 bytes of distance
        params = self.convert_distance(distance)
        self.send_cmd(
            command='move_relative_arg',
            command_params=params,
            await_response=True
        )

    def move_home(self, value):
        """Home the device."""
        if not self.port_is_open():
            return
        # No parameters but requires waiting
        self.send_cmd(
            command='move_home',
            await_response=True
        )

    def move_stop(self):
        """Stop the current move."""
        if not self.port_is_open():
            return
        # No parameters but requires waiting (stops are not instant)
        self.send_cmd(
            commmand='move_stop',
            await_response=True
        )

        rsp = ''
        while not rsp=='move_stopped':
            time.sleep(0.5)
            reply = self.recv_reply()
            rsp, params = self.decode_reply(reply)
            # Debug about position?
        logging.debug("Movement stopped.")

    # ------------ Positional functions ------------

    def get_position(self):
        """Get motor position (poscnt). This is then converted to a readable value.
        :return float: position converted to unit
        """
        if not self.port_is_open():
            return

        # This command can fail, so it is attempted multiple times.
        for i in range(3):
            self.send_cmd('req_poscounter')

            reply = self.recv_reply()
            try:
                if self.DEBUG:
                    logging.debug(f"get_position reply: {reply}")
                rsp, params = self.decode_reply(reply)
                # Page 63, GET structure
                pos = params[2:]
                position = self.convert_enccnt(pos)
                # If the value is wildly unrealistic (for degrees OR mm), try again
                if position > 1000:
                    continue
                break
            except ValueError:
                position=None
        return position

    def get_encoder_position(self):
        """Get motor position (enccnt). This is then converted to a readable value.
        :return float: position converted to unit
        """
        if not self.port_is_open():
            return
        self.send_cmd('req_enccounter')

        reply = self.recv_reply()
        try:
            if self.DEBUG:
                logging.debug(f"Encoder position reply: {reply}")
            rsp, params = self.decode_reply(reply)
            # Pages 64-65, GET structure
            pos = params[2:]
            position = self.convert_enccnt(pos)
        except ValueError:
            position=None
        return position
