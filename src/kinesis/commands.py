import struct
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple, ClassVar
import re
import logging

@dataclass
class Command:
    name: str  # Identifier
    msg_id: int  # First two bytes
    param1: Optional[int]=0x00  # byte 2
    param2: Optional[int]=0x00  # byte 3

    response_name: Optional[str] = None
    response_length: Optional[int] = None
    response_code: Optional[int] = None
    response_format: Optional[str] = None

    compatible_devices: Optional[List[str]] = None

    # build_command
    header_packing: ClassVar[struct.Struct] = struct.Struct('<HBBBB')
    packer: Optional[struct.Struct] = None

    def build_command(self,
                      chan_ident: Optional[int] = 0x01,
                      data: Optional[Tuple[int, ...]] = None,
                      destination: int = 0x50,
                      source: int = 0x01) -> bytes:
        """Build a command on known parameters and optional arguments.
        :param int chan_ident: channel identity of destination
        :param ints data: optional post-header data
        :param destination: byte 4, destination of data (usually 0x50, generic USB unit)
        :param source: byte 5, source of data (always 0x01, host)
        :return bytes: packed command
        """
        payload = b''

        # If data provided, param1 and param2 represent post-header data length
        if data:
            packer = self.get_packer(len(data))
            payload = packer.pack(chan_ident, *data)
            # Page 35 - MSB is set via OR if there is a post-header packet
            destination |= 0x80
            param1, param2 = self.param1, self.param2
        # If chan_ident and no data, param1 and 2 are set to that
        elif chan_ident is not None:
            param1, param2 = chan_ident, self.param2
        # If somehow no data or chan_ident, use defaults
        else:
            param1, param2 = self.param1, self.param2

        header = self.header_packing.pack(
            self.msg_id,
            param1, param2,
            destination, source
        )
        return header + payload

    def get_packer(self, data_length: int) -> struct.Struct:
        """Return a packer object based on the length of the data."""
        if self.packer:
            return self.packer
        # Size is based on header info, if there is any
        if self.param1 and self.param1 > 2:
            # -2, as H covers first two bytes: channel identity
            self.packer = struct.Struct(f'<H{self.param1 -2}B')
        # There shouldn't be non-header data without param1, but if there is, pack it correctly
        else:
            self.packer = struct.Struct(f'<H{data_length}B')

        return self.packer

    def unpack_response(self, payload: bytes) -> Tuple:
        """Unpack a response based on its given response format."""
        if not self.response_format:
            raise ValueError(f"No response_format defined for {self.name}.")
        return struct.unpack(self.response_format, payload)


class CMD:
    _commands: List[Command] = []
    _name_to_command: Dict[str, Command] = {}
    _code_to_response: Dict[int, Tuple[str, int]] = {}

    @classmethod
    def register(cls, command: Command):
        """Add a command to the CMD class."""
        cls._commands.append(command)
        cls._name_to_command[command.name] = command
        setattr(cls, command.name, command)

        if command.response_code is not None:
            cls._code_to_response[command.response_code] = (
                command.response_name or command.name, command.response_length or 0
            )

    @classmethod
    def get_command(cls, name: str) -> Optional[Command]:
        return cls._name_to_command.get(name)

    @classmethod
    def get_response_info(cls, code: int) -> Tuple[str, int]:
        return cls._code_to_response.get(code, ("Unknown", 0))

    @classmethod
    def get_expected_response(cls, name: str) -> Tuple[Optional[str], int]:
        command = cls.get_command(name)
        if command:
            return command.response_name, command.response_length
        return None, 0

# Helper functions
def move_command(name, msg_id, param1=0x00, param2=0x00, **kwargs):
    return Command(name, msg_id,
                   param1=param1, param2=param2,
                   response_name='move_completed',
                   response_code=0x0464,
                   response_length=14,
                   **kwargs)

def request_command(name, msg_id, response_code, length, format=None, **kwargs):
    return Command(name, msg_id,
                   response_name=f'get_{name[4:]}' if name.startswith("req_") else f'response_{name}',
                   response_code=response_code,
                   response_length=length,
                   response_format=format)

# -------- Register commands --------

# Page 46: Flash screen
CMD.register(Command('identify', 0x0223))

# Page 52: Get hardware info
CMD.register(request_command('req_info', 0x0005, 0x0006, 84))
# Page 63: Get encoder count
CMD.register(request_command('req_enccounter', 0x040A, 0x040B, 6))
# Page 64: Get position count
CMD.register(request_command('req_poscounter', 0x0411, 0x412, 6))
# Page 68: Get jog parameters
CMD.register(request_command('req_jogparams', 0x0417, 0x0418, 22))
# Page 137: Get kcube settings
CMD.register(request_command('get_kcubemmiparams', 0x0521, 0x0522, 36,
                             compatible_devices=['KST101', 'KDC101', 'KDB101', 'BBD30*']))
# Page 76: Home parameters
CMD.register(request_command('req_homeparams', 0x0441, 0x0442, 14))

# Page 80: Move to home
CMD.register(Command('move_home', 0x0443, response_name='move_homed', response_code=0x0444, response_length=0))

# Page 75: Set/req absolute movement parameter (data +4 bytes: movement value in encoder counts)
CMD.register(Command('set_moveabsparams', 0x0450, param1=0x06))
CMD.register(request_command('req_moveabsparams', 0x0451, 0x0452, 6))
# Page 80: Move predefined absolute (data +4 bytes: location value in encoder counts)
CMD.register(move_command('move_absolute_arg', 0x0453, param1=0x06))

# Page 68: Set/req jog parameters (data +20 bytes: 2 jog mode, 4 jog step size, 4 min, 4 acceleration, 4 max velocity, 2 stop mode)
CMD.register(Command('set_jogparams', 0x0416, param1=0x16))
CMD.register(request_command('req_jogparams', 0x0417, 0x0418, 22))
# Page 86: Jog forward (param2=0x01) or backward (param2=0x02)
CMD.register(move_command('move_jog_forward', 0x046A, param2=0x01))
CMD.register(move_command('move_jog_backward', 0x046A, param2=0x02))

# Page 88: Stop movement (abrupt: param2 0x01, profiled: 0x02)
CMD.register(move_command('move_stop', 0x0465, param2=0x01))

# -------- Device-Specific Command Map --------

DEVICE_COMMANDS: Dict[str, Dict[str, Command]] = {
    'move': {
        'KDC101': CMD.get_command('move_absolute_arg')
    },
    'home': {
        'KDC101': CMD.get_command('move_home')
    },
    'stop': {
        'KDC101': CMD.get_command('move_stop')
    },
    'jog_forward': {
        'KDC101': CMD.get_command('move_jog_forward')
    },
    'jog_backward': {
        'KDC101': CMD.get_command('move_jog_backward')
    },
    'get_jog_params': {
        'KDC101': CMD.get_command('req_jogparams')
    },
    'set_jog_params': {
        'KDC101': CMD.get_command('set_jogparams')
    },
    'get_position': {
        'KDC101': CMD.get_command('req_enccounter')
    }
}