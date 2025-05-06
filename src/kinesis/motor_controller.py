"""Class to manage the state of some number of motors and process serial commands on their behalf."""

import serial
import time
import logging

from kinesis.motor import Motor
from kinesis.commands import CMD, DEVICE_COMMANDS

class MotorController():
    """Class to represent an arbitrary motor controller."""

    DEBUG = False

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

        self.hardware_info = {}  # For storing info about device

        # Create serial connection
        self.open_serial(port)
        self._in_buffer = bytearray()  # For potential leftover data between reads

        time.sleep(1)

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

    def initialize(self):
        """Post-init function to populate further motor parameters."""
        for motor in self.stages.values():
            motor.initialize()

        for name, stage in self.stages.items():
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

    def send_cmd(self, command: str, command_params: bytearray=None, motor:Motor=None):
        """Send a command through the serial port.
        :param str command: name of the command to send
        :param bytearray command_params: additional parameter bytes required by command
        :param Motor: motor to send the command to
        :param bool await_response: does the response require waiting (e.g.: movement taking time)
        """
        if not self.port_is_open() or not motor:
            return

        # Command header structure:
        # bytes | detail
        # 0, 1  | message id
        # 2, 3  | param1/2, or data packet length if command has data
        # 4     | destination: 0x50 but different for bay/card systems
        # 5     | source: 0x01 as host is always communicating

        # cmd = CMD.get_command(command)
        cmd = DEVICE_COMMANDS[command][self.device_type]
        data = cmd.build_command(
            chan_ident=motor.channel_identity,
            data=command_params,
            destination=motor.destination
        )

        self.ser.write(data)

    def _recv_reply(self):
        """Receive and parse a reply."""
        if not self.port_is_open():
            return []

        time.sleep(0.04)  # necessary delay

        # Get every byte - this could be multiple messages
        while self.ser.in_waiting > 0:
            self._in_buffer.extend(self.ser.read())

        # Process raw into replies
        replies = []
        i = 0
        while i < (len(self._in_buffer)-1):  # mID needs 2 bytes
            mID = self._in_buffer[i:i+2]
            mID = int.from_bytes(mID, 'little')
            rsp, length = self.cmd.get_response_info(mID)
            if rsp == "Unknown":  # If this is not a response ID, move on
                i += 1
                continue
            msg_length = 6 + length  # Header is 6 bytes
            if i + msg_length > len(self._in_buffer):
                # Not enough data yet, break
                break
        
            msg = self._in_buffer[i:i+msg_length]
            replies.append(msg)
            i += msg_length

        # Any unprocessed bytes 
        self._in_buffer = self._in_buffer[i:]

        return replies

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
        """Convert reply to usable information.
        :param bytearray reply: the bytes to be decoded
        """
        if not reply:
            return '','',  # motor, response name
        motor: Motor = None

        mID = int.from_bytes(reply[:2], 'little')  # Message ID
        rsp, length = self.cmd.get_response_info(mID)

        # Channel identity is (usually) third byte if header-only, or first two bytes of non-header data
        if length == 0:
            cID = reply[2]
        else:
            cID = int.from_bytes(reply[6:8], byteorder='little')
        # cID = reply[2] if length==0 else reply[6:8]
        # cID = int.from_bytes(cID, byteorder='little')
        source = reply[5]  # Source is the final header byte

        # Process the reply in its own statement
        # motor is identified there in case cID is handled uniquely
        match rsp, length:
            case ("Unknown", 0):
                return "Unknown", None
            case ("move_homed", 0):
                motor = self._get_motor_from_channel(cID, source)
                motor.homing = False
            case ("move_completed", 14):
                motor = self._get_motor_from_channel(cID, source)
                motor.moving = False
            case ("get_enccounter", 6):
                motor = self._get_motor_from_channel(cID, source)
                params = reply[8:]
                position = motor.read_position(params)
                motor.current_position = position
            case ("get_info", 84):
                hwinfo = reply[6:]
                # As according to page 52 of manual
                self.hardware_info = {
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
            case ("get_jogparams", 22):
                motor = self._get_motor_from_channel(cID, source)
                jogparams = reply[8:]
                motor.jog_mode = int.from_bytes(jogparams[0:2], byteorder='little')
                motor.jog_step_size = motor.read_position(jogparams[2:6])
                motor.jog_min_vel = motor.read_velocity(jogparams[6:10])
                motor.jog_accel = motor.read_accel(jogparams[10:14])
                motor.jog_max_vel = motor.read_velocity(jogparams[14:18])
                motor.jog_stop_mode = int.from_bytes(jogparams[18:20], byteorder='little')

        # Called by _check_reply_queues, return the motor and what the expected response is
        # If the response needs handling, this has been done already
        # If the response is in the queue, that gets sorted now
        return motor, rsp

    def _check_reply_queues(self):
        """Check the instant queue to send any commands from it.
        Then check for replies, seeing if a response is expected by any motor.
        If it is, send the next command from that motor's await_queue.
        """
        # Send one instant command from the queue, if there is one
        for name, motor in self.stages.items():
            if not motor.instant_queue.empty():
                priority, cmd = motor.instant_queue.get()
                self.send_cmd(
                    command=cmd[0],
                    command_params=cmd[1],
                    motor=motor
                )
            # With no active command and one in queue, send one
            if (motor.current_command is None) and (not motor.await_queue.empty()):
                cmd = motor.await_queue.get()
                self.send_cmd(
                    command=cmd[0],
                    command_params=cmd[1],
                    motor=motor
                )
                motor.current_command = DEVICE_COMMANDS[cmd[0]][self.device_type].name
                # Expected response info - only need name, not length from tuple
                motor.expected_response, exp_rsp_length = CMD.get_expected_response(motor.current_command)

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
                    cmd = motor.await_queue.get()
                    logging.debug(f"Command {cmd} retrived from motor {motor.name} queue.")
                    # Commands are saved in queue as (command, parameters)
                    self.send_cmd(
                        command=cmd[0],
                        command_params=cmd[1],
                        motor=motor
                    )
                    motor.current_command = DEVICE_COMMANDS[cmd[0]][self.device_type].name
                    # Expected response info - only need name, not length from tuple
                    motor.expected_response, exp_rsp_length = CMD.get_expected_response(motor.current_command)

    # ------------ Controller functions ------------

    def identify(self):
        """Run the identify command, flashing to identify the controller."""
        if not self.port_is_open():
            return
        self.send_cmd('identify')

    def get_hardware_info(self, value):
        """Get hardware info for the controller."""
        if not self.port_is_open():
            return
        self.send_cmd('req_info')

    # ------------ Movement functions ------------
    # These functions await a reply that the motor has reached its position.

    def move(self, params: bytearray, motor: Motor):
        """Move to a given absolute position.
        :param bytearray params: command parameters, 4 bytes for target pos in encoder counts
        """
        if not self.port_is_open():
            return
        logging.debug("move added to queue")
        motor.await_queue.put(
            ('move', params)
        )

    def move_home(self, motor: Motor):
        """Home the device."""
        if not self.port_is_open():
            return
        motor.await_queue.put(
            ('home', None)
        )

    def set_jogparams(self, motor: Motor):
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

        # motor.instant_queue.put(
        #     (1, ('req_enccounter', None))
        # )
