"""KDC101 motor controller for Thorlabs devices.

Manages serial communications and motor control for KDC101 devices.
Stage configuration drives behavior; encoder conversion factors come from stage_specs.
"""
import struct
import serial
import logging
import itertools
from queue import Queue, PriorityQueue

from kinesis.responses import mID_to_func
from kinesis.stage_specs import val_to_enc, enc_to_val
import kinesis.messages as MSG


class KDC101:
    """Motor controller for KDC101 Thorlabs devices.
    
    Manages serial communications, command queuing, and motor control.
    Stage configuration drives behavior; encoder conversion factors come from stage_specs.
    """

    def __init__(self, name, port, device_type, bay_system, stage_details):
        """Initialize KDC101 controller.
        
        :param name: Controller name/identifier
        :param port: Serial port (e.g., '/dev/ttyUSB0')
        :param device_type: Device type string (e.g., 'KDC101')
        :param bay_system: Whether this is a bay/card system
        :param stage_details: Stage config dict {stage_type, upper_limit, lower_limit}
        """
        self.name = name
        self.device_type = device_type
        self.port = port
        self.bay_system = bay_system
        
        self.serial = None
        self._in_buffer = bytearray()
        self.connected = False
        self.tree = {}
        
        # Store single stage configuration and runtime state
        self.stage = {
            # Configuration
            'chan_ident': 1,
            'stage_type': stage_details.get('stage_type', 'MTS50-Z8'),
            'upper_limit': stage_details.get('upper_limit', 25.0),
            'lower_limit': stage_details.get('lower_limit', 0.0),
            'destination': 0x50,
            
            # Runtime state
            'current_position': 0.0,
            'target_position': 0.0,
            'moving': False,
            'homing': False,
            'reverse_jog': False,
            'current_command': None,
            'expected_response': None,
            
            # Jog parameters
            'jog_mode': 0x02,        # 0x01=continuous, 0x02=step
            'jog_step_size': 1.0,    # mm
            'jog_min_vel': 0.0,      # mm/s
            'jog_accel': 0.5,        # mm/s^2
            'jog_max_vel': 1.0,      # mm/s
            'jog_stop_mode': 0x02,   # 0x01=instant, 0x02=profiled
            
            # Command queues
            'await_queue': Queue(maxsize=0),
            'instant_queue': PriorityQueue(maxsize=0),
            '_queue_counter': itertools.count()
        }
        
        # Open serial connection
        self._open_serial(self.port)

    def initialize(self):
        """Post-init setup - query device parameters and build parameter tree."""
        # Query initial jog parameters
        self.get_jogparams()
        
        # Build parameter tree
        self.tree = {
            'type': (lambda: self.device_type, None),
            'motors': {
                'position': {
                    'home': (lambda: None, self.move_home),
                    'set_target_pos': (lambda: self.stage['target_position'], self.set_target_position),
                    'current_pos': (lambda: self.stage['current_position'], None),
                    'stop': (lambda: None, self.stop)
                },
                'jog': {
                    'mode': (lambda: self.stage['jog_mode'], self.set_jog_mode),
                    'step_size': (lambda: self.stage['jog_step_size'], self.set_jog_step_size),
                    'min_vel': (lambda: self.stage['jog_min_vel'], self.set_jog_min_vel),
                    'accel': (lambda: self.stage['jog_accel'], self.set_jog_accel),
                    'max_vel': (lambda: self.stage['jog_max_vel'], self.set_jog_max_vel),
                    'stop_mode': (lambda: self.stage['jog_stop_mode'], self.set_jog_stop_mode),
                    'step': (lambda: None, self.jog), 
                    'reverse': (lambda: self.stage['reverse_jog'], self.set_reverse_jog)
                },
                'limits': {
                    'upper_limit': (lambda: self.stage['upper_limit'], self.set_upper_limit),
                    'lower_limit': (lambda: self.stage['lower_limit'], self.set_lower_limit)
                }
            },
            'connected': (lambda: self.connected, self.reconnect)
        }

    # -------- Serial Communication --------

    def _open_serial(self, port):
        """Open serial connection to device."""
        try:
            self.serial = serial.Serial(
                port, 
                baudrate=115200, 
                bytesize=8, 
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE, 
                xonxoff=0, 
                rtscts=True, 
                timeout=1
            )
            self.connected = True
            logging.debug(f"Opened serial connection on {port}")
        except Exception as e:
            logging.error(f"Could not open serial connection to {port}: {e}")
            self.connected = False

    def port_is_open(self):
        """Check if serial port is open and connected."""
        if not self.serial:
            self.connected = False
            return False
        
        try:
            if not self.serial.is_open:
                logging.debug("Serial port is not open.")
                self.connected = False
                return False
        except (AttributeError, Exception):
            logging.warning(f"Serial connection issue for {self.name}")
            self.connected = False
            return False
        
        self.connected = True
        return True

    def close_serial(self):
        """Close serial connection."""
        if not self.port_is_open():
            return
        self.serial.close()
        logging.debug("Serial connection closed.")

    def reconnect(self, val):
        """Attempt to reconnect to device."""
        self._open_serial(self.port)

    def send_cmd(self, command_fn, command_args):
        """Send a command to the device.
        
        :param command_fn: Message building function
        :param command_args: Arguments for the message function
        :return: Expected response info dict
        """
        if not self.port_is_open():
            return None

        data = command_fn(
            cID=self.stage['chan_ident'],
            dest=self.stage['destination'],
            source=0x01,
            **(command_args or {})
        )
        
        self.serial.write(data['bytes'])
        return data.get('exp_rsp', None)

    def _recv_reply(self):
        """Receive and parse replies from device."""
        if not self.port_is_open():
            return []
        
        # Fill buffer from serial
        while self.serial.in_waiting > 0:
            self._in_buffer.extend(self.serial.read())
        
        replies = []
        
        # Process complete messages from buffer
        while len(self._in_buffer) >= 6:
            # Check message header
            mID, length = struct.unpack_from("<HH", self._in_buffer)
            
            if mID not in mID_to_func:
                logging.debug(f"Unknown message ID {hex(mID)}")
                self._in_buffer = self._in_buffer[1:]
                continue

            # Check address fields
            long = self._in_buffer[4] & 0x80
            dest = self._in_buffer[4] & ~0x80
            source = self._in_buffer[5]
            
            if dest not in (0x00, 0x01) or source not in (
                0x00, 0x11, 0x21, 0x22, 0x23, 0x24,
                0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x50):
                logging.debug(f"Invalid src/dest for {hex(mID)}: src={source}, dest={dest}")
                self._in_buffer = self._in_buffer[1:]
                continue

            # Check message length
            if long and length > 255:
                logging.debug(f"Invalid length {length}")
                self._in_buffer = self._in_buffer[1:]
                continue
            
            msg_length = 6 + (length if long else 0)

            # Wait for complete message
            if len(self._in_buffer) < msg_length:
                break
            
            msg = bytes(self._in_buffer[:msg_length])
            replies.append(msg)
            self._in_buffer = self._in_buffer[msg_length:]

        return replies

    # -------- Unit Conversion --------

    def val_to_enc(self, val, val_type):
        """Convert physical value to encoder counts."""
        return val_to_enc(self.stage['stage_type'], val, val_type)

    def enc_to_val(self, enc, val_type):
        """Convert encoder counts to physical value."""
        return enc_to_val(self.stage['stage_type'], enc, val_type)

    # -------- Command and Reply Queue Processing --------

    def _check_command_queues(self):
        """Process instant and await command queues."""
        # Process instant queue
        if not self.stage['instant_queue'].empty():
            priority, (cmd_fn, cmd_args) = self.stage['instant_queue'].get()
            exp_rsp = self.send_cmd(cmd_fn, cmd_args)
            if exp_rsp:
                self.stage['current_command'] = cmd_fn.__name__
                self.stage['expected_response'] = exp_rsp['name']
        
        # Process await queue if no active command
        if (self.stage['current_command'] is None) and (not self.stage['await_queue'].empty()):
            cmd_fn, cmd_args = self.stage['await_queue'].get()
            exp_rsp = self.send_cmd(cmd_fn, cmd_args)
            if exp_rsp:
                self.stage['current_command'] = cmd_fn.__name__
                self.stage['expected_response'] = exp_rsp['name']

    def _check_reply_queues(self):
        """Process device replies and advance command queues."""
        replies = self._recv_reply()

        for reply in replies:
            response = self._decode_reply(reply)

            if not response:
                continue

            # If expected response received, advance to next command
            if response == self.stage['expected_response']:
                logging.debug(f"Response: {response}")

                self.stage['current_command'] = None
                self.stage['expected_response'] = None

                if not self.stage['await_queue'].empty():
                    cmd_fn, cmd_args = self.stage['await_queue'].get()
                    exp_rsp = self.send_cmd(cmd_fn, cmd_args)
                    if exp_rsp:
                        self.stage['current_command'] = cmd_fn.__name__
                        self.stage['expected_response'] = exp_rsp['name']

    def _decode_reply(self, reply):
        """Decode device reply and update stage state.
        
        :return: response_type string or None
        """
        if not reply:
            return None

        mID = int.from_bytes(reply[:2], 'little')
        parser_func = mID_to_func.get(mID)
        
        if not parser_func:
            logging.debug(f"No parser for message ID {hex(mID)}")
            return None

        response = parser_func(reply)
        chan_id = response.get("cID")
        source = response.get("source")
        
        # Verify this is for our stage
        if chan_id != self.stage['chan_ident'] or source != self.stage['destination']:
            return None

        msg_type = response.get("msg")
        
        # Update stage state based on response type
        if msg_type == "mot_move_completed":
            self.stage['moving'] = False
        elif msg_type == "mot_move_homed":
            self.stage['homing'] = False
        elif msg_type == "mot_get_enccounter":
            pos = self.enc_to_val(response["enc_count"], 'POS')
            self.stage['current_position'] = pos
        elif msg_type == "mot_get_jogparams":
            # Update jog parameters from response
            self.stage['jog_mode'] = response["jog_mode"]
            self.stage['jog_step_size'] = self.enc_to_val(response["step_size"], 'POS')
            self.stage['jog_min_vel'] = self.enc_to_val(response["min_velocity"], 'VEL')
            self.stage['jog_accel'] = self.enc_to_val(response["acceleration"], 'ACC')
            self.stage['jog_max_vel'] = self.enc_to_val(response["max_velocity"], 'VEL')
            self.stage['jog_stop_mode'] = response["stop_mode"]

        return msg_type

    # -------- Motor Control Methods --------

    def move_home(self, val):
        """Send home command."""
        self.stage['homing'] = True
        if not self.port_is_open():
            return
        self.stage['await_queue'].put((MSG.mot_move_home, {}))

    def move_stop(self, val):
        """Send stop command."""
        self.stage['homing'] = False
        self.stage['moving'] = False
        if not self.port_is_open():
            return
        
        # Stop is immediate priority - use priority 0 and clear await queue
        self.stage['instant_queue'].put((0, (MSG.mot_move_stop, {'stop_mode': 0x01})))
        # Remove all other await tasks from the queue to avoid continued movement
        while not self.stage['await_queue'].empty():
            self.stage['await_queue'].get()

    def move(self, position):
        """Move stage to target position."""
        if not self.port_is_open():
            return
        
        # Convert position to encoder counts
        enc_pos = self.val_to_enc(position, 'POS')
        self.stage['moving'] = True
        self.stage['await_queue'].put((MSG.mot_move_absolute, {'pos': enc_pos}))

    def move_jog(self, direction):
        """Execute jog movement."""
        if not self.port_is_open():
            return
        
        direction_code = 0x01 if direction else 0x02  # 0x01=forward, 0x02=backward
        self.stage['await_queue'].put((MSG.mot_move_jog, {'direction': direction_code}))

    def get_current_position(self):
        """Query current position from device."""
        if not self.port_is_open():
            return
        
        self.stage['instant_queue'].put((next(self.stage['_queue_counter']), (MSG.mot_req_enccounter, {})))

    def get_jogparams(self):
        """Query jog parameters from device."""
        if not self.port_is_open():
            return
        
        self.stage['instant_queue'].put((next(self.stage['_queue_counter']), (MSG.mot_req_jogparams, {})))

    def set_jogparams(self):
        """Send jog parameters to device."""
        if not self.port_is_open():
            return
        
        # Convert physical values to encoder counts
        jogparams = {
            'jog_mode': self.stage['jog_mode'],
            'step_size': self.val_to_enc(self.stage['jog_step_size'], 'POS'),
            'min_vel': self.val_to_enc(self.stage['jog_min_vel'], 'VEL'),
            'accel': self.val_to_enc(self.stage['jog_accel'], 'ACC'),
            'max_vel': self.val_to_enc(self.stage['jog_max_vel'], 'VEL'),
            'stop_mode': self.stage['jog_stop_mode']
        }
        self.stage['instant_queue'].put((next(self.stage['_queue_counter']), (MSG.mot_set_jogparams, jogparams)))

    # -------- Stage Control --------

    def set_target_position(self, pos):
        """Set target position and move if within limits."""
        pos = float(pos)
        self.stage['target_position'] = pos
        
        # Check bounds and move if needed
        if (self.stage['target_position'] != self.stage['current_position'] and
            self.stage['lower_limit'] <= self.stage['target_position'] <= self.stage['upper_limit']):
            self.move(pos)

    def stop(self):
        """Stop the stage."""
        self.move_stop()

    def jog(self, direction):
        """Execute a jog movement."""
        direction = bool(direction)
        
        # Apply reverse setting
        if self.stage['reverse_jog']:
            direction = not direction
        
        # Check if jog would exceed limits
        sign = 1 if direction else -1
        predicted_pos = self.stage['current_position'] + self.stage['jog_step_size'] * sign
        
        if self.stage['lower_limit'] <= predicted_pos <= self.stage['upper_limit']:
            self.move_jog(direction)

    def set_reverse_jog(self, rev):
        """Reverse (True) or unreverse (False) the jog direction."""
        self.stage['reverse_jog'] = bool(rev)

    # -------- Jog Parameter Setters --------

    def set_jog_mode(self, value):
        """Set jog mode (continuous or step)."""
        if value not in (0x01, 0x02):
            value = 0x02
        self.stage['jog_mode'] = value
        self.set_jogparams()

    def set_jog_step_size(self, value):
        """Set step size for jogging in mm."""
        self.stage['jog_step_size'] = float(value)
        self.set_jogparams()

    def set_jog_min_vel(self, value):
        """Set minimum velocity for jogging in mm/s."""
        self.stage['jog_min_vel'] = float(value)
        self.set_jogparams()

    def set_jog_accel(self, value):
        """Set acceleration for jogging in mm/s^2."""
        self.stage['jog_accel'] = float(value)
        self.set_jogparams()

    def set_jog_max_vel(self, value):
        """Set maximum velocity for jogging in mm/s."""
        self.stage['jog_max_vel'] = float(value)
        self.set_jogparams()

    def set_jog_stop_mode(self, value):
        """Set jog stop mode."""
        if value not in (0x01, 0x02):
            value = 0x02
        self.stage['jog_stop_mode'] = value
        self.set_jogparams()

    # -------- Limit Setters --------

    def set_upper_limit(self, lim):
        """Set upper travel limit in mm."""
        self.stage['upper_limit'] = float(lim)

    def set_lower_limit(self, lim):
        """Set lower travel limit in mm."""
        self.stage['lower_limit'] = float(lim)
