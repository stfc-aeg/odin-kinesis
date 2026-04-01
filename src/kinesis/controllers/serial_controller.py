from abc import ABC, abstractmethod
import struct
import serial
import logging

from kinesis.responses import mID_to_func

class SerialController(ABC):
    """Base class for Thorlabs motor controllers.

    Handles common serial communication, command queues, and reply processing.
    Subclasses (i.e. controller classes) must implement device-specific reply decoding and
    handling of stages.
    If a subclass has multiple stages, it may need unique handling of reply queues to determine
    response destinations.
    """
    def __init__(self, name, port, device_type, step_forward_label, step_backward_label):
        """Initialize Thorlabs controller.

        :param name: Controller name/identifier
        :param port: Serial port (e.g., '/dev/ttyUSB0')
        :param device_type: Device type string
        """
        self.name = name
        self.device_type = device_type
        self.port = port

        self.step_forward_label = step_forward_label
        self.step_backward_label = step_backward_label

        self.serial = None
        self._in_buffer = bytearray()
        self.connected = False

        # Command queues - subclasses will set these up
        self.await_queue = None
        self.instant_queue = None
        self.current_command = None
        self.expected_response = None

        # Open serial connection
        self._open_serial(self.port)

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
            cID=self.chan_ident,
            dest=self.destination,
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

    # -------- Command and Reply Queue Processing --------

    def _check_command_queues(self):
        """Process instant and await command queues."""
        # Process instant queue
        if not self.instant_queue.empty():
            priority, (cmd_fn, cmd_args) = self.instant_queue.get()
            exp_rsp = self.send_cmd(cmd_fn, cmd_args)
            if exp_rsp:
                self.current_command = cmd_fn.__name__
                self.expected_response = exp_rsp['name']

        # Process await queue if no active command
        if (self.current_command is None) and (not self.await_queue.empty()):
            cmd_fn, cmd_args = self.await_queue.get()
            exp_rsp = self.send_cmd(cmd_fn, cmd_args)
            if exp_rsp:
                self.current_command = cmd_fn.__name__
                self.expected_response = exp_rsp['name']

    def _check_reply_queues(self):
        """Process device replies and advance command queues."""
        replies = self._recv_reply()

        for reply in replies:
            response = self._decode_reply(reply)

            if not response:
                continue

            # If expected response received, advance to next command
            if response == self.expected_response:
                logging.debug(f"Response: {response}")

                self.current_command = None
                self.expected_response = None

                if not self.await_queue.empty():
                    cmd_fn, cmd_args = self.await_queue.get()
                    exp_rsp = self.send_cmd(cmd_fn, cmd_args)
                    if exp_rsp:
                        self.current_command = cmd_fn.__name__
                        self.expected_response = exp_rsp['name']

    @abstractmethod
    def _decode_reply(self, reply):
        """Decode device reply and update controller state.

        Must be implemented by subclasses.

        :param reply: Raw reply bytes
        :return: response_type string or None
        """
        pass

    # -------- Unit Conversion --------

    def val_to_enc(self, val, val_type):
        """Convert physical value to encoder counts.

        Default implementation - subclasses can override for device-specific conversion.
        """
        # This is a placeholder - subclasses should implement their own conversion
        # based on their stage specifications
        raise NotImplementedError("Subclasses must implement val_to_enc")

    def enc_to_val(self, enc, val_type):
        """Convert encoder counts to physical value.

        Default implementation - subclasses can override for device-specific conversion.
        """
        # This is a placeholder - subclasses should implement their own conversion
        # based on their stage specifications
        raise NotImplementedError("Subclasses must implement enc_to_val")

