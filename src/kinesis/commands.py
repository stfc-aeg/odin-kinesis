import struct
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
import re
import logging

@dataclass
class Command:
    name: str  # Identifier
    msg_id: int  # First two bytes, e.g.: 0x0223 (identify, p46)
    # msg_id: Tuple[int, int]  # First 2 bytes
    param1: Optional[int]=None  # byte 2
    param2: Optional[int]=None  # byte 3

    response_name: Optional[str] = None
    response_length: Optional[int] = None
    response_code: Optional[int] = None
    response_format: Optional[str] = None

    compatible_devices: Optional[List[str]] = None

    def build_command(self, 
            chan_ident: Optional[int]=0x01,
            param1: Optional[int]=None,
            param2: Optional[int]=None,
            data: Optional[Tuple[int,...]]=None,
            destination: int=0x50,
            source: int=0x01) -> bytes:
        """Build a command based on known parameters and optional arguments.
        :param int chan_ident: channel identity of destination
        :param int param1: overrides default param1 (byte 2)
        :param int param2: overrides dfault param2 (byte 3)
        :param ints data: optional post-header data
        :param destination: byte 4, destination of data (usually 0x50, generic USB unit)
        :param source: byte 5, source of data (always 0x01, host)
        :return bytes: packed command
        """
        payload = b''

        # If data is provided, assume param1 and param2 are known: length of post-header data
        if data:
            payload = struct.pack(f'<H{len(data)}B', chan_ident, *data)
            # See page 35 of docs - MSB is set via OR if there is a post-header packet
            destination |= 0x80
            # Assume they're known
            param1 = self.param1
            param2 = self.param2
        # If data is not provided and there is a channel identity, set params 1 and 2 to that
        elif chan_ident is not None:
            param1, param2 = chan_ident, self.param2 if self.param2 is not None else 0x00
        # If there's somehow no data and no chan_ident, use the defaults
        else:
            param1, param2 = self.param1, self.param2

        header = struct.pack('<HBBBB',
                             self.msg_id,
                             param1, param2,
                             destination, source)
        return header+payload


class CMD:
    # Page 46: Flash screen
    identify = Command('identify', 0x0223, param1=0x00, param2=0x00)
    # Page 52: Get hardware info
    req_info = Command('req_info', 0x0005, param1=0x00, param2=0x00,
                       response_name='get_info',
                       response_code=0x0006,
                       response_length=84)
    # Page 63: Get enccounter count
    req_enccounter = Command('req_enccounter', 0x040A,
                       response_name='get_enccounter',
                       response_code=0x040B,
                       response_length=6)
    # Page 64: Get position count
    req_poscounter = Command('req_poscounter', 0x0411,
                             response_name='get_poscounter',
                             response_code=0x0412,
                             response_length=6)
    # Page 68: Get jog parameters
    req_jogparams = Command('req_jogparams', 0x0417,
                            response_name='get_jogparams',
                            response_code=0x0418,
                            response_length=22)
    # Page 137: Get settings
    req_kcubemmiparams = Command('req_kcubemmiparams', 0x0521,
                                 response_name='get_kcubemmiparams',
                                 response_code=0x0522,
                                 response_length=36,
                                 compatible_devices=['KST101', 'KDC101', 'KDB101', 'BBD30*'])
    # Page 73: Get general move parameters / backlash settings
    req_genmoveparams = Command('req_genmoveparams', 0x043B,
                                response_name='get_genmoveparams',
                                response_code=0x043C,
                                response_length=6)
    # Page 76: Get home parameters
    req_homeparams = Command('req_homeparams', 0x0441,
                            response_name='get_homeparams',
                            response_code=0x0442,
                            response_length=14)
    # Page 80: Move home
    move_home = Command('move_home', 0x0443,
                        response_name='move_homed',
                        response_code=0x0444,
                        response_length=0)

    # Page 74: set relative movement parameter (data +4 bytes: movement value in encoder counts)
    set_moverelparams = Command('set_moverelparams', 0x0445,
                                param1=0x06, param2=0x00)
    # Page 74: request relative movement parameters
    req_moverelparams = Command('set_moverelparams', 0x0446,
                                response_name='get_moverelparams',
                                response_code=0x0447,
                                response_length=6)
    # Page 80: Move predefined relative (set by set_moverelparams)
    move_relative_param = Command('move_relative_param', 0x0448,
                                response_name='move_completed',
                                response_code=0x0464,
                                response_length=14)
    # Page 80: Move relative by given amount (data +4 bytes: movement value in encoder counts)
    move_relative_arg = Command('move_relative_arg', 0x0448,
                                param1=0x06, param2=0x00,
                                response_name='move_completed',
                                response_code=0x0464,
                                response_length=14)
    # Page 75: Set absolute movement parameter (data +4 bytes: movement value in encoder counts)
    set_moveabsparams = Command('set_moveabsparams', 0x0450,
                                param1=0x06, param2=0x00)
    # Page 75: Request absolute movement parameters
    req_moveabsparams = Command('req_moveabsparams', 0x0451,
                                response_name='get_moveabsparams',
                                response_code=0x0452,
                                response_length=6)
    # Page 80: Move predefined absolute
    move_absolute_param = Command('move_absolute_param', 0x0453,
                                response_name='move_completed',
                                response_code=0x0464,
                                response_length=14)
    # Page 80: Move to absolute position (data +4 bytes: location value in encoder counts)
    move_absolute_arg = Command('move_absolute_arg', 0x0453,
                                param1=0x06, param2=0x00,
                                response_name='move_completed',
                                response_code=0x0464,
                                response_length=14)

    # Page 66: Set velocity parameters (data +12 bytes: 4 minimum, 4 acceleration, 4 maximum velocity)
    set_velparams = Command('set_velparams', 0x0413,
                            param1=0x0E, param2=0x00)
    # Page 66: Get velocity parameters
    req_velparams = Command('req_velparams', 0x0414,
                             response_name='get_velparams',
                             response_code=0x0415,
                             response_length=14)
    # Page 87: Move at fixed speed forward (param2 0x01)
    move_velocity_forward = Command('move_velocity_forward', 0x0457,
                                    param2=0x01,
                                    response_name='move_completed',
                                    response_code=0x0464,
                                    response_length=14)
    # Page 87: Move at fixed speed backward (param 0x02)
    move_velocity_backward = Command('move_velocity_backward', 0x0457,
                                     param2=0x02,
                                     response_name='move_completed',
                                     response_code=0x0464,
                                     response_length=14)

    # Page 68: Set jog parameters (data +20 bytes: 2 jog mode, 4 jog step size, 4 min, 4 acceleration, 4 max velocity, 2 stop mode)
    set_jogparams = Command('set_jogparams', 0x0416,
                            param1=0x16, param2=0x00)
    # Page 68: Get jog parameters
    req_jogparams = Command('req_jogparams', 0x0417,
                            response_name='get_jogpaarams',
                            response_code=0x0418,
                            response_length=22)
    # Page 86: Jog forward
    move_jog_forward = Command('move_jog_forward', 0x046A,
                               param2=0x01,
                               response_name='move_completed',
                               response_code=0x0464,
                               response_length=14)
    # Page 86: Jog backward
    move_jog_backward = Command('move_jog_backward', 0x046A,
                                param2=0x02,
                                response_name='move_completed',
                                response_code=0x0464,
                                response_length=14)
    # Page 88: Stop movement (abrupt: param2 0x01, profiled: 0x02)
    move_stop = Command('move_stop', 0x0465,
                        param2=0x01,
                        response_name='move_completed',
                        response_code=0x0464,
                        response_length=14)


    @classmethod
    def get_command(cls, name: str) -> Optional[Command]:
        """Retrieve a Command by name."""
        return getattr(cls, name, None)

    @classmethod
    def get_response_info(cls, code: int) -> Tuple[str, int]:
        """Get response name and length from the message ID."""
        code = int.from_bytes(code, byteorder='little')
        for command in cls.__dict__.values():
            if isinstance(command, Command) and command.response_code == code:
                return command.response_name, command.response_length
        return "Unknown", 0

    @classmethod
    def get_expected_response(cls, name: str) -> Tuple[Optional[str], int]:
        """Get the expected response for a given Command."""
        command = cls.get_command(name)
        if command:
            return command.response_name, command.response_length
        return None, 0

    @classmethod
    def check_compatibility(cls, name: str, device: str) -> bool:
        """Check if a command is compatible with the given device."""
        command = cls.get_command(name)
        if not command:
            logging.debug("No such command.")
            return False

        if command.compatible_devices is None:
            return True

        for pattern in command.compatible_devices:
            regex = "^" + re.escape(pattern).replace("\\*", ".*") + "$"
            if re.match(regex, device):
                return True

        return False