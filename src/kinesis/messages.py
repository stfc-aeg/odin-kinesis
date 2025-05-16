"""File to manage Thorlabs APT communications protocol messages."""
from typing import Optional, Dict, TypedDict
import struct

class ExpRsp(TypedDict):
    mID: int
    name: str

class MessageDict(TypedDict):
    bytes: bytes
    exp_rsp: Optional[ExpRsp]

def _pack_message(
        mID: int,
        dest: int,
        source: int,
        *,  # Denotes that following functions must be passed positionally
        param1: int = 0,
        param2: int = 0,
        data: Optional[bytes] = None
    ):
    """Pack the message header and any provided data.
    This assumes that whatever function is calling it has already packed the data.
    """
    if data is not None:
        assert param1 == param2 == 0  # These should not be set in this case
        return struct.pack("<HHBB", mID, len(data), dest|0x80, source) + data
    else:  # We do not have data
        return struct.pack("<H2b2B", mID, param1, param2, dest, source)

# [0x0223] Page 46: Flash screen
def mod_identify(cID: int, dest: int, source: int) -> MessageDict:
    return {'bytes': _pack_message(0x0223, dest, source, param1=cID)}

# [0x040A] Page 63: Get encoder count, includes expected response
def mot_req_enccounter(cID: int, dest: int, source: int) -> MessageDict:
    return {
        'bytes': _pack_message(0x040A, dest, source, param1=cID),
        'exp_rsp': {'mID': 0x040B, 'name': 'mot_get_enccounter'}
        }

# [0x0416] Page 68: Set jog parameters
def mot_set_jogparams(cID: int, dest: int, source: int,
                      jog_mode: int, step_size: float,
                      min_vel: float, accel: float, max_vel: float,
                      stop_mode: int) -> MessageDict:
    data = struct.pack("<HH4lH", cID, jog_mode, step_size, min_vel, accel, max_vel, stop_mode)
    return {
        'bytes': _pack_message(0x0416, dest, source, data=data)
    }

# [0x0417] Page 68: Get jog parameters, includes expected response
def mot_req_jogparams(cID: int, dest: int, source: int) -> MessageDict:
    return {
        'bytes': _pack_message(0x0417, dest, source, param1=cID),
        'exp_rsp': {'mID': 0x0418, 'name': 'mot_get_jogparams'}
    }

# [0x046A] Page 86: Jog forward (param2=0x01) or backward (0x02), includes response info
def mot_move_jog(cID: int, dest: int, source: int, direction: int) -> MessageDict:
    return {
        'bytes': _pack_message(0x046A, dest, source, param1=cID, param2=direction),
        'exp_rsp': {'mID': 0x0464, 'name': 'mot_move_completed'}
    }

# [0x0443] Page 80: Move to home, includes expected response
def mot_move_home(cID: int, dest: int, source: int) -> MessageDict:
    return {
        'bytes': _pack_message(0x0443, dest, source, param1=cID),
        'exp_rsp': {'mID': 0x0444, 'name': 'mot_move_homed'}
    }

# [0x0450] Page 75: Set absolute movement parameter
def mot_set_moveabsparams(cID: int, dest: int, source: int, pos: float) -> MessageDict:
    data = struct.pack("<Hl", cID, pos)
    return {
        'bytes': _pack_message(0x0450, dest, source, data=data)
    }

# [0x0453] Page 80: Move predefined absolute, includes expected response
def mot_move_absolute(cID: int, dest: int, source: int, pos: Optional[int]=None) -> MessageDict:
    mID = 0x0453
    if pos is None:  # Move using the set parameters from 0x0450
        msg_bytes = _pack_message(mID, dest, source, param1=cID)
    else:  # Pos provided, use that
        data = struct.pack("<Hl", cID, pos)
        msg_bytes = _pack_message(mID, dest, source, data=data)
    return {
        'bytes': msg_bytes,
        'exp_rsp': {'mID': 0x0464, 'name': 'mot_move_completed'}
    }

# [0x0465] Page 88: Stop movement (abrupt: param2 0x01, profiled: 0x02)
def mot_move_stop(cID: int, dest: int, source: int, stop_mode: int) -> MessageDict:
    return {
        'bytes': _pack_message(0x0465, dest, source, param1=cID, param2=stop_mode)
    }