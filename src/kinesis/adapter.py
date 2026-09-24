from odin_control.adapters.adapter import ApiAdapter
from kinesis.controller import KinesisController, KinesisError

class KinesisAdapter(ApiAdapter):
    """Acquisition adapter class."""

    controller_cls = KinesisController
    error_cls = KinesisError