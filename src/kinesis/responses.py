"""File to manage Thorlabs APT communications protocol message responses."""
import struct
import functools
from typing import Dict, Any

# Associate message IDs with parser functions, like register() for commands.py
mID_to_func = {}
HEADER_SIZE = 6  # The header size is always 6

# Wrapper for other functions to process header and add to id_to_func
def parser(mID):
    def wrapper(func):
        @functools.wraps(func)
        def inner(data: bytes) -> Dict[str, Any]:
            # Process header. Bytes 2/3 are variable
            read_mID, _, dest, source = struct.unpack_from("<HHBB", data)
            dest = dest & ~0x80
            assert mID == read_mID  # Check the mID read is what is expected
            # Create a return object
            ret = {
                "msg": func.__name__,
                "mID": mID,
                "dest": dest,
                "source": source
                }
            # Update the return object with the function output
            ret.update(func(data))
            return ret
        # Add message ID to function list
        if mID in mID_to_func:
            raise ValueError(f"Duplicate ID registry: {hex(mID)}")
        mID_to_func[mID] = inner
        return inner  # Calling decorated function runs the logic
    return wrapper

# Page 125: Returned on request or by certain other messages (e.g. mot_move_completed)
def _read_status_update(data: bytes) -> Dict[str, Any]:
    cID, pos, enc_count, status_bits = struct.unpack_from("<HllL", data, HEADER_SIZE)
    ret = {
        "cID": cID,
        "position": pos,
        "enc_count": enc_count
    }
    ret.update(_parse_status_bits(status_bits))
    return ret

# Pages 126-129: Status bits, often part of other messages (e.g.: mot_move_completed)
def _parse_status_bits(status_bits: int) -> Dict[str, Any]:
    # A range of status variables 
    return {
        "forward_limit_switch": bool(status_bits & 0x1),
        "reverse_limit_switch": bool(status_bits & 0x2),
        "forward_limit_soft": bool(status_bits & 0x4),
        "reverse_limit_soft": bool(status_bits & 0x8),
        "moving_forward": bool(status_bits & 0x10),
        "moving_reverse": bool(status_bits & 0x20),
        "jogging_forward": bool(status_bits & 0x40),
        "jogging_reverse": bool(status_bits & 0x80),
        "motor_connected": bool(status_bits & 0x100),
        "homing": bool(status_bits & 0x200),
        "homed": bool(status_bits & 0x400),
        "initializing": bool(status_bits & 0x800),
        "tracking": bool(status_bits & 0x1000),
        "settled": bool(status_bits & 0x2000),
        "motion_error": bool(status_bits & 0x4000),
        "instrument_error": bool(status_bits & 0x8000),
        "interlock": bool(status_bits & 0x10000),
        "overtemp": bool(status_bits & 0x20000),
        "voltage_fault": bool(status_bits & 0x40000),
        "commutation_error": bool(status_bits & 0x80000),
        "digital_in_1": bool(status_bits & 0x100000),
        "digital_in_2": bool(status_bits & 0x200000),
        "digital_in_3": bool(status_bits & 0x300000),
        "digital_in_4": bool(status_bits & 0x400000),
        "motor_current_limit_reached": bool(status_bits & 0x1000000),
        "encoder_fault": bool(status_bits & 0x2000000),
        "overcurrent": bool(status_bits & 0x4000000),
        "current_fault": bool(status_bits & 0x8000000),
        "power_ok": bool(status_bits & 0x10000000),
        "active": bool(status_bits & 0x20000000),
        "error": bool(status_bits & 0x40000000),
        "channel_enabled": bool(status_bits & 0x80000000),
    }

# Page 80: Homing completed
@parser(0x0444)
def mot_move_homed(data: bytes) -> Dict[str, Any]:
    return {"cID": data[2]}

# Page 83: Completion of relative or absolute move sequence
@parser(0x0464)
def mot_move_completed(data: bytes) -> Dict[str, Any]:
    return _read_status_update(data)  # Extra information beyond confirming that a move is complete

# Page 64: get the encoder count in the controller
@parser(0x040B)
def mot_get_enccounter(data: bytes) -> Dict[str, Any]:
    cID, enc_count = struct.unpack_from("<Hl", data, HEADER_SIZE)
    return {"cID": cID, "enc_count": enc_count}

# Page 68: get the jog parameters for the specified motor channel
@parser(0x0418)
def mot_get_jogparams(data: bytes) -> Dict[str, Any]:
    (
        cID,
        jog_mode,
        step_size,
        min_vel, accel, max_vel,
        stop_mode
    ) = struct.unpack_from("<HH4lH", data, HEADER_SIZE)
    return {
        "cID": cID,
        "jog_mode": jog_mode,
        "step_size": step_size,
        "min_velocity": min_vel,
        "acceleration": accel,
        "max_velocity": max_vel,
        "stop_mode": stop_mode
    }

# Page 417: move is complete
@parser(0x08D6)
def pzmot_move_completed(data: bytes) -> Dict[str, Any]:
    cID, position, _, _ = struct.unpack_from("<Hlll", data, HEADER_SIZE)
    return {
        "cID": cID,
        "position": position,
    }


# Pages 371-416: generic message using sub-message IDs as first data bytes to identify function
# Used by the TIM101 and KIM101 controllers
@parser(0x08C2)
def pzmot_get_params(data: bytes) -> Dict[str, Any]:
    submessage_id, = struct.unpack_from("<H", data, HEADER_SIZE)
    ret = {"submessage_id": submessage_id}
    match submessage_id:
        # Page 372: return position counter value. KIM101/TIM101
        case 5:  # Get_PZMOT_PosCounts
            _, cID, pos, _ = struct.unpack_from("<HHll", data, HEADER_SIZE)
            ret.update({
                "cID": cID,
                "position": pos
            })
        # Page 396: Read various jog parameters. KIM101 only
        case 0x2D:  # Get_PZMOT_KCubeJogParams
            (_, cID, jog_mode,
             jog_step_size_fwd, jog_step_size_rev,
             jog_step_rate, jog_step_accn) = struct.unpack_from("<HHHllll", data, HEADER_SIZE)
            ret.update({
                'cID': cID,
                'jog_mode': jog_mode,
                'jog_step_size_fwd': jog_step_size_fwd,
                'jog_step_size_rev': jog_step_size_rev,
                'jog_step_rate': jog_step_rate,
                'jog_step_accn': jog_step_accn
            })
    return ret