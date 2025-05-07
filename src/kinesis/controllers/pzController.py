import typing
import logging

from kinesis.controllers.baseMotorController import BaseMotorController
from kinesis.controllers.motor import Motor

class PzController(BaseMotorController):

    def __init__(self, port: str, device_type: str, bay_system: bool, stages: dict):
        super().__init__(port, device_type, bay_system, stages)
