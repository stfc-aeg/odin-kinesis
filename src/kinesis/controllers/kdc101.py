"""KDC101 motor controller for Thorlabs devices.

Manages serial communications and motor control for KDC101 devices.
Stage encoder conversions are pulled from stage_specs.
Stage configuration drives behavior; encoder conversion factors come from stage_specs.
"""
import logging
import itertools
from queue import Queue, PriorityQueue

from kinesis.controllers.serial_controller import SerialController
from kinesis.responses import mID_to_func
from kinesis.stage_specs import val_to_enc, enc_to_val
import kinesis.messages as MSG

class KDC101(SerialController):
    """Motor controller for KDC101 Thorlabs devices.
    
    Manages serial communications, command queuing, and motor control.
    Stage configuration drives behavior; encoder conversion factors come from stage_specs.
    """

    def __init__(self, name, port, device_type, stage_details, step_forward_label, step_backward_label):
        """Initialize KDC101 controller.
        
        :param name: Controller name/identifier
        :param port: Serial port (e.g., '/dev/ttyUSB0')
        :param device_type: Device type string (e.g., 'KDC101')
        :param stage_details: Stage config dict {stage_type, upper_limit, lower_limit}
        """
        # Initialize base class
        super().__init__(name, port, device_type, step_forward_label, step_backward_label)
        
        # KDC101-specific attributes for base class
        self.chan_ident = 1
        self.destination = 0x50
        
        self.tree = {}
        
        # Store single stage configuration and runtime state
        self.stage = {
            # Configuration
            'chan_ident': self.chan_ident,
            'stage_type': stage_details.get('stage_type', 'MTS50-Z8'),
            'upper_limit': stage_details.get('upper_limit', 25.0),
            'lower_limit': stage_details.get('lower_limit', 0.0),
            'destination': self.destination,
            
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
        
        # Set base class queue references
        self.await_queue = self.stage['await_queue']
        self.instant_queue = self.stage['instant_queue']

    def initialize(self):
        """Post-init setup - get parameters and build parameter tree."""
        # Query initial jog parameters
        self.get_jogparams()
        
        # Build parameter tree
        self.tree = {
            'type': (lambda: self.device_type, None),
            'motor': {
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
            'connected': (lambda: self.connected, self.reconnect),
            'forward_label': (lambda: self.step_forward_label, None),
            'backward_label': (lambda: self.step_backward_label, None)
        }

    # -------- Unit Conversion --------

    def val_to_enc(self, val, val_type):
        """Convert physical value to encoder counts."""
        return val_to_enc(self.stage['stage_type'], val, val_type)

    def enc_to_val(self, enc, val_type):
        """Convert encoder counts to physical value."""
        return enc_to_val(self.stage['stage_type'], enc, val_type)

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
