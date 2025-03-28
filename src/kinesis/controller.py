"""Class to manage some number of motor controllers."""

from tornado.ioloop import PeriodicCallback

from odin.adapters.adapter import (ApiAdapter, ApiAdapterRequest,
                                   ApiAdapterResponse, request_types, response_types,
                                   wants_metadata)
from odin.util import decode_request_body

from odin.adapters.parameter_tree import ParameterTree, ParameterTreeError

# Motor imports
from concurrent import futures
from tornado.concurrent import run_on_executor

import serial
import time
import logging
import json

from kinesis.cmds import CMD_RSP
from kinesis.motor_controller import MotorController

class KinesisError(Exception):
    """Simple exception class to wrap lower-level exceptions."""
    pass

class KinesisController():
    """Motor adapter class for the ODIN server.
    """

    # For additional output information
    DEBUG = False

    # Thread executor used for background tasks
    executor = futures.ThreadPoolExecutor(max_workers=1)

    def __init__(self, options):
        """Initialize the KinesisAdapter object.

        This constructor Initializes the KinesisAdapter object, including launching a background
        task if enabled by the adapter options passed as arguments.

        :param kwargs: keyword arguments specifying options
        """
        self.options = options
        # Options
        self.bg_await_reply_enable = bool(int(self.options.get('bg_await_reply_enable', 1)))
        self.bg_await_reply_interval = int(self.options.get('bg_await_reply_interval', 0.5))
        device_config = self.options.get('device_config', 'test/config/devices.json')


        # Create controller children
        self.controllers = {}
        with open(device_config, "r") as file:
            devices = json.load(file)

            for name,details in devices.items():
                controller_type = details['device_type']
                stages = details['stages']
                port = details['port']
                self.controllers[name] = MotorController(port, controller_type, stages)


        self._start_background_task()

        self.param_tree = ParameterTree({
            'vars': {
                'current_command': (lambda: self.current_command, None),
                'expected_response': (lambda: self.expected_response, None),
                'task_interval': (lambda: self.bg_await_reply_interval, None)
            },
            'commands': {
                'move_abs': (lambda: None, self.move_absolute),
                'move_rel': (lambda: None, self.move_relative),
                'home': (lambda: None, self.move_home),
                'position': (lambda: self.get_position(), None)
            }
        })

        logging.debug('DummyAdapter loaded')

    # ------------ background functions ------------

    @run_on_executor
    def background_await_reply(self):
        """Background task to check for an expected response.
        :return bool: True when response provided, False otherwise
        """
        while self.bg_await_reply_enable:
            # Only need to check for replies if there's an active command
            
            if self.current_command:
                # Behaviour is otherwise standard receive-reply affair
                reply = self.recv_reply()
                rsp, params = self.decode_reply(reply)
                logging.debug(f"cur_command: {self.current_command}. rsp: {rsp}. exp_rsp:{self.expected_response}")
                if rsp == self.expected_response:
                    logging.debug(f"Expected response achieved, moving through queue.")
                    self.current_command = None

                    # Is the queue empty?
                    if not self.command_queue:
                        logging.debug("Queue cleared.")
                    # If it's not empty, do something
                    else:
                        cmd = self.command_queue.pop()
                        logging.debug(f"New command from queue: {cmd}")
                        # Commands saved to queue are a command and parameters
                        self.send_cmd(
                            command=cmd[0],
                            command_params=cmd[1],
                            await_response=True
                        )

            # Check every 0.2s
            time.sleep(self.bg_await_reply_interval)

    def _start_background_task(self):
        """Start the background tasks."""
        logging.debug(
            "Launching background tasks with interval %.2f secs", self.bg_await_reply_interval
        )
        self.bg_await_reply_enable = True

        # Run the background thread task in the thread execution pool
        self.background_await_reply()

    def _stop_background_task(self):
        """Stop the background tasks."""
        logging.debug("Halting background tasks.")
        self.bg_await_reply_enable = False

    # ------------ Adapter functions ------------

    def initialize(self, adapters):
        logging.debug("DummyAdapter initialized with %d adapters", len(adapters))

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
            raise LiveXError(error)

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
            raise LiveXError(error)

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

class KinesisError(Exception):
    pass