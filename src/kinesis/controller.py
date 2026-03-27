"""Class to manage some number of motor controllers."""

from odin.adapters.adapter import (ApiAdapterResponse)
from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError

# Motor imports
from concurrent import futures
from tornado.concurrent import run_on_executor

import time
import logging
import json

from kinesis.controllers.kdc101 import KDC101

class KinesisError(Exception):
    """Simple exception class to wrap lower-level exceptions."""
    pass

class KinesisController():
    """Motor adapter class for the ODIN server."""
    # For additional output information
    DEBUG = False

    # Thread executor used for background tasks
    executor = futures.ThreadPoolExecutor(max_workers=2)

    def __init__(self, options):
        """Initialise the KinesisAdapter object.

        This constructor Initialises the KinesisAdapter object, including launching a background
        task if enabled by the adapter options passed as arguments.

        :param kwargs: keyword arguments specifying options
        """
        # Options
        self.options = options
        self.bg_tasks_enable = bool(int(self.options.get('bg_tasks_enable', 1)))
        self.bg_await_reply_interval = float(self.options.get('bg_await_reply_interval', 0.3))
        self.bg_check_position_interval = float(self.options.get('bg_check_position_interval', 0.5))
        device_config = self.options.get('device_config', 'test/config/devices.json')

        self.current_command = None

        self.tree = {}

        # Create controller children
        self.controllers: dict[str, KDC101] = {}
        with open(device_config, "r") as file:
            devices = json.load(file)

            for name, details in devices.items():
                controller_type = details.get('device_type', 'kdc101')
                stage_config = details.get('stages', {})
                port = details.get('port', '/dev/ttyUSB0')

                normalised = controller_type.strip().lower()
                if normalised == 'kdc101':
                    controller_class = KDC101

                if controller_class is None:
                    logging.debug(f"Controller {name} not supported type of controller: {controller_type}")
                    continue

                self.controllers[name] = controller_class(name, port, controller_type, stage_config)

        logging.debug('KinesisAdapter loaded')

    # ------------ background functions ------------

    @run_on_executor
    def background_check_positions(self):
        """Background task to check the positions of the motors.
        This also serves as a 'heartbeat', checking that motors are still connected.
        """
        while self.bg_await_reply_enable:  # No need for more than one enable toggle here
            for controller in self.controllers.values():
                if not controller.connected:
                    return
                try:
                    controller.get_current_position()
                    # _recv_replies() handles multiple replies, so other thread can handle that
                except Exception as e:
                    logging.error(f"Error checking position for controller {controller.name}: {e}")
            
            time.sleep(self.bg_check_position_interval)

    @run_on_executor
    def background_await_reply(self):
        """Background task to check for an expected response.
        :return bool: True when response provided, False otherwise
        """
        while self.bg_await_reply_enable:
            # Only need to check for replies if there's an active command

            # Check every controller
            for controller in self.controllers.values():
                if not controller.connected:
                    return
                # Do a queue check for the controller
                controller._check_command_queues()

            # time.sleep(0.02)  # Was necessary delay previously but did not need repeating in every queue

            # With command queues checked, check for replies
            for controller in self.controllers.values():
                # No connection check needed here, would have returned if it's disconnected
                controller._check_reply_queues()

            # Check on interval
            time.sleep(self.bg_await_reply_interval)

    def _start_background_task(self):
        """Start the background tasks."""
        logging.debug(
            "Launching background tasks with interval %.2f secs", self.bg_await_reply_interval
        )
        self.bg_await_reply_enable = True

        # Run the background thread task in the thread execution pool
        self.background_await_reply()
        self.background_check_positions()

    def _stop_background_task(self):
        """Stop the background tasks."""
        logging.debug("Halting background tasks.")
        self.bg_await_reply_enable = False

    # ------------ Adapter functions ------------

    def initialize(self, adapters):
        """Post-init function."""
        self.adapters = adapters
        if 'sequencer' in self.adapters:
            self.adapters['sequencer'].add_context('kinesis', self)

        for name, controller in self.controllers.items():
            controller.initialize()

            self.tree[name] = controller.tree

        try:
            self.param_tree = ParameterTree({
                'bg_task_interval': (lambda: self.bg_await_reply_interval, None),
                'controllers': self.tree
            })
        except Exception as e:
            logging.debug(f"error: {e}")
        logging.debug("Starting background task.")
        self._start_background_task()

    def get(self, path, with_metadata=False):
        """Get parameter data from controller.

        This method gets data from the controller parameter tree.

        :param path: path to retrieve from the tree
        :param with_metadata: flag indicating if parameter metadata should be included
        :return: dictionary of parameters (and optional metadata) for specified path
        """
        try:
            return self.param_tree.get(path, with_metadata)
        except ParameterTreeError as error:
            logging.error(error)
            raise KinesisError(error)

    def set(self, path, data):
        """Set parameters in the controller.

        This method sets parameters in the controller parameter tree. If the parameters to write
        metadata to HDF and/or markdown have been set during the call, the appropriate write
        action is executed.

        :param path: path to set parameters at
        :param data: dictionary of parameters to set
        """
        try:
            self.param_tree.set(path, data)
        except ParameterTreeError as error:
            logging.error(error)
            raise KinesisError(error)

    def delete(self, path, request):
        """Handle an HTTP DELETE request.

        This method handles an HTTP DELETE request, returning a JSON response.

        :param path: URI path of request
        :param request: HTTP request object
        :return: an ApiAdapterResponse object containing the appropriate response
        """
        response = 'DummyAdapter: DELETE on path {}'.format(path)
        status_code = 200

        logging.debug(response)

        return ApiAdapterResponse(response, status_code=status_code)

    def cleanup(self):
        """Clean up the state of the adapter.

        This method cleans up the state of the adapter, which in this case is
        trivially setting the background task counter back to zero for test
        purposes.
        """
        logging.debug("KinesisAdapter cleanup")
        self.bg_await_reply_enable = False
        for controller in self.controllers.values():
            controller.close_serial()
