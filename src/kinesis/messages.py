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

# [0x08C0->05] Page 372-373: Set the pzmot position counter. Submessage ID of 05
def pzmot_set_poscounts(cID: int, dest: int, source: int, pos: int) -> MessageDict:
    # pos, 0 because enccount is not used
    data = struct.pack("<HHll", 5, cID, pos, 0)
    return {
        'bytes': _pack_message(0x08C0, dest, source, data=data)
    }

# [0x08C1->05] Page 372-373: request pzmot pos counter.
def pzmot_req_poscounts(cID: int, dest: int, source: int)  -> MessageDict:
    return {
        'bytes': _pack_message(0x08C1, dest, source, param1=5, param2=cID),
        'exp_rsp': {'mID': 0x08C2, 'name': 'pzmot_get_params'}
    }

# [0x08D4] Page 417: Move to a specified number of steps away from the zero position
def pzmot_move_absolute(cID: int, dest: int, source: int, pos: int) -> MessageDict:
    data = struct.pack("<Hl", cID, pos)
    return {
        'bytes': _pack_message(0x08D4, dest, source, data=data),
        'exp_rsp': {'mID': 0x08D6, 'name': 'pzmot_move_completed'}
    }

# [0x08D9] Page 419: Start a jog move
def pzmot_move_jog(cID: int, dest: int, source: int, jog_dir: int) -> MessageDict:
    # 0x01 Forward, 0x02 Reverse
    return {
        'bytes': _pack_message(0x08D9, dest, source, param1=cID, param2=jog_dir),
        'exp_rsp': {'mID': 0x08D6, 'name': 'pzmot_move_completed'}
    }

# [0x08C0->2D] Page 396: Set jog parameters for KIM
def pzmot_set_kcubejogparams(
        cID: int, dest: int, source: int,
        jog_mode: int,
        jog_step_size_fwd: int, jog_step_size_rev: int,
        jog_step_rate: int, jog_step_accn: int
) -> MessageDict:
    data = struct.pack("<HHHllll", 0x2D,
            cID, jog_mode, jog_step_size_fwd, jog_step_size_rev, jog_step_rate, jog_step_accn)
    return {
        'bytes': _pack_message(0x08C0, dest, source, data=data)
    }

# [0x08C1->2D] Page 396: Get jog parameters for KIM
def pzmot_get_kcubejogparams(cID: int, dest: int, source: int) -> MessageDict:
    return {
        'bytes': _pack_message(0x08C1, dest, source, param1=0x2D, param2=cID),
        'exp_rsp': {'mID': 0x08C2, 'name': 'pzmot_get_params'}
    }