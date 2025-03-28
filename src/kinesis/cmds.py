"""File to manage commands and responses."""

from dataclasses import dataclass
from typing import Optional, Dict, List
import json
import re  # for the device compatibility
import logging

@dataclass
class Command:
    name: str
    command: bytes
    response_name: Optional[str]
    response_code: Optional[bytes]
    response_length: Optional[int]
    compatible_devices: Optional[List[str]]

class CMD_RSP:
    def __init__(self, config_path: str):
        self.MAPPING: Dict[str, Command] = self._load_config(config_path)

    def _load_config(self, path:str) -> Dict[str, Command]:
        with open(path, "r") as file:
            data = json.load(file)

        # There may or may not be a response code, but fromhex() expects something, so add checks
        return {
            name: Command(
                name=name,
                command=bytes.fromhex(field["command"]),
                response_code=bytes.fromhex(field["response_code"]) if field["response_code"] else None,
                response_name=field["response_name"],
                response_length=field["response_length"],
                compatible_devices=field.get("compatible_devices", [])
            )
            for name, field in data.items()
        }

    def get_command(self, name: str) -> Optional[bytes]:
        """Get command bytes by name.
        :param str name: name of command
        :return bytes: command bytearray if it exists, else None
        """
        return self.MAPPING.get(name).command if name in self.MAPPING else None

    def get_response_info(self, code: bytes) -> tuple[str, int]:
        """Get response name and length from the code.
        :param bytes code: 2-byte response header
        :return tuple: name and length of response if it exists, else placeholder
        """
        for item in self.MAPPING.values():
            if item.response_code == code:
                return item.response_name, item.response_length
        return "Unknown", 0

    def get_expected_response(self, name: str) -> tuple[Optional[str], int]:
        """Get the expected response for a given command, if it exists.
        :param str name: name of command
        :returns tuple: response and length if it exists, else None/0
        """
        if name in self.MAPPING:
            cmd = self.MAPPING[name]
            return cmd.response_name, cmd.response_length
        return None, 0

    def check_compatibility(self, name: str, device: str) -> bool:
        """Check if a command is compatible with the given device.
        :param str name: name of command
        :param str device: name of device
        :return bool: True if yes, False if no
        """
        cmd = self.MAPPING.get(name)
        if not cmd:
            logging.debug("No such command.")
            return False  # exit if no such command

        compatible_devices = cmd.get('compatible_devices', None)
        if compatible_devices is None:
            return True  # None means compatible with all devices

        for pattern in compatible_devices:
            # e.g.: 'BBD30*' becomes '^BBD30.*', 'starts with BBD30, ends with anything'
            regex = "^" + re.escape(pattern).replace("\\*",".*") + "$"
            if re.match(regex, device):
                return True  # compatible

        return False


# class CMD:

#     # (p.52) get hardware info
#     req_info = b'\x05\x00\x00\x00\x50\x01'
#     # (p.63) get enccounter count
#     req_enccounter = b'\x0A\x04\x01\x00\x50\x01'
#     # (p.64) get position count
#     req_poscounter = b'\x11\x04\x01\x00\x50\x01'
#     # (p.66) get the velocity parameters
#     req_velparams = b'\x14\x04\x01\x00\x50\x01'
#     # (p.68) get jog parameters
#     req_jogparams = b'\x17\x04\x01\x00\x50\x01'
#     # (p.137) get settings for top panel wheel
#     req_mmiparams = b'\x21\x05\x01\x00\x50\x01'
#     # (p.46) flash screen
#     identify = b'\x23\x02\x00\x00\x50\x01'
#     # (p.73) get backlash settings
#     req_genmoveparams = b'\x3B\x04\x01\x00\x50\x01'
#     # (p.76) get home parameters
#     req_homeparams = b'\x41\x04\x01\x00\x50\x01'
#     # (p.80) move home
#     move_home = b'\x43\x04\x01\x00\x50\x01'

#     # (p.74) set relative movement parameter (append +4 bytes: movement value in encoder counts)
#     set_moverelparams = b'\x45\x04\x06\x00\xD0\x01\x01\x00'
#     # (p.74) get rel movement parameters
#     req_moverelparams = b'\x46\x04\x01\x00\x50\x01'
#     # (p.80) move predefined relative (set by set_moverelparams)
#     move_relative_param = b'\x48\x04\x01\x00\x50\x01'
#     # (p.80) move relative by given amount (append +4 bytes: movement value in encoder counts)
#     move_relative_arg = b'\x48\x04\x06\x00\xD0\x01\x01\x00'

#     # (p.75) set absolute movement parameter (append +4 bytes: movement value in encoder counts)
#     set_moveabsparams = b'\x50\x04\x06\x00\xD0\x01\x01\x00'
#     # (p.75) get absolute movement parameters
#     req_moveabsparams = b'\x51\x04\x01\x00\x50\x01'
#     # (p.80) move predefined absolute
#     move_absolute_param = b'\x53\x04\x01\x00\x50\x01'
#     # (p.80) move predefined absolute (append +4 bytes: movement value in encoder counts)
#     move_abs_arg = b'\x53\x04\x06\x00\xD0\x01\x01\x00'

#     # (p.87) move at fixed speed forward
#     move_velocity_forward = b'\x57\x04\x01\x02\x50\x01'
#     # (p.87) move at fixed speed backward
#     move_velocity_backward = b'\x57\x04\x01\x01\x50\x01'
#     # (p.88) stop movement
#     move_stop = b'\x65\x04\x01\x00\x50\x01'
#     # (p.86) jog forward
#     move_jog_forward = b'\x6A\x04\x01\x02\x50\x01'
#     # (p.86) jog backward
#     move_jog_backward = b'\x6A\x04\x01\x01\x50\x01'


#     def __init__(self):
#         pass


# class RSP:
#     """Manage and retrieve responses."""

#     # code: (response name, length of response)
#     RESPONSES = {
#         b'\x06\x00': ('get_info', 84),
#         b'\x0b\x04': ('get_enccounter', 6),
#         b'\x12\x04': ('get_poscounter', 6),
#         b'\x15\x04': ('get_velparams', 14),
#         b'\x18\x04': ('get_jogparams', 22),
#         b'\x22\x05': ('get_kcubemmiparams', 36),  # KDC101 specific
#         b'\x3c\x04': ('get_genmoveparams', 6),
#         b'\x42\x04': ('get_homeparams', 14),
#         b'\x44\x04': ('move_homed', 0),
#         b'\x47\x04': ('get_moverelparams', 6),
#         b'\x52\x04': ('get_moveabsparams', 6),
#         b'\x64\x04': ('move_completed', 14),
#         b'\x66\x04': ('move_stopped', 14),
#     }

#     @classmethod
#     def get_response(cls, code: bytes):
#         code=bytes(code)
#         return cls.RESPONSES.get(code, ('Unknown', 0))