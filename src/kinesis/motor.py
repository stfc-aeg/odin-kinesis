"""Class to handle the state of a given motor."""

class Motor():
    """Class to represent the state of a motor stage."""

    # POS = EncCnt x Pos
    # VEL = EncCnt x T x 65536 x Vel
    # ACC = EncCnt x T^2 x 65536 x Acc
    # where T = 2048/6e6 (KDC101)
    # ==> VEL (PRM1-Z8) = 6.2942e4 x Vel
    # ==> ACC (PRM1-Z8) = 14.6574 x Acc

    def __init__(self, chan_ident: int=1, stage_type: dict=None):
        self.channel_identity = chan_ident  # For commands
        self.command_queue = []
        self.current_command = None
        self.expected_response = None

        # Device parameters should be provided by motor controller
        if not stage_type:
            stage_type=STAGETYPES.MTS50_Z8
        self.enc_cnt = stage_type['enc_cnt']
        self.sf_vel  = stage_type['sf_vel']
        self.sf_acc  = stage_type['sf_acc']
        # These will need to be fetched from a list somewhere


class STAGETYPES():

    MTS50_Z8 = {
        'enc_cnt': 34554.96,
        'sf_vel': 772981.3692,
        'sf_acc': 263.8443072
    }
