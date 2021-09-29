import os
import logging
import argparse
import docker
from docker.models.containers import Container
import traceback
import signal

from .batcher import Batcher
from .container_handler import ContainerHandler
from .config import create_config, BaseConfig

logger = logging.getLogger("fourwarder")


class EventHandler:
    def __init__(self, batcher, thread_panic, config: BaseConfig):
        self.client = docker.from_env()
        self.log_handlers = {}
        self.batcher = batcher
        self.own_container_id = os.environ.get("HOSTNAME")
        self.thread_panic = thread_panic
        self.config = config

    def get_event_handler(self, event):
        action = event["Action"]
        type = event["Type"]
        if type != "container":
            return None
        if action == "start":
            return self.handle_start
        if action == "die":
            return self.handle_die

    def handle_event(self, event):
        event_handler = self.get_event_handler(event)
        if not event_handler:
            logger.debug(f'skipping event {event["Type"]} {event["Action"]}')
            return

        event_handler(event)

    def run(self):
        logger.info("starting to read events")
        self.event_stream = self.client.events(decode=True)
        for event in self.event_stream:
            self.handle_event(event)

    def filter_container(self, container: Container):
        if container.attrs["Config"]["Hostname"] == self.own_container_id:
            # make sure we we are not monitoring ourselves
            return False

        return self.config.filter_container(container)

    def handle_start(self, event):
        container = self.client.containers.get(event["Actor"]["ID"])

        if not self.filter_container(container):
            logger.info(f"container {container.name} excluded")
            return

        log_handler = ContainerHandler(
            container, self.batcher, self.thread_panic, self.config
        )
        self.log_handlers[container.id] = log_handler
        log_handler.start()

    def handle_die(self, event):
        container_id = event["Actor"]["ID"]
        if container_id not in self.log_handlers:
            return

        self.log_handlers[container_id].terminate()
        del self.log_handlers[container_id]

    def terminate(self):
        self.event_stream.close()


class Main:
    def __init__(self, config: BaseConfig):
        self.sender = config.create_sender(
            thread_panic=self.thread_panic, config=config
        )
        self.batcher = Batcher(self.sender, self.thread_panic, config)
        self.event_handler = EventHandler(self.batcher, self.thread_panic, config)
        self.termination_exc = None

    def thread_panic(self, func):
        """wraps the passed function into a try catch that terminates the main thread."""

        def wrapper():
            try:
                func()
            except Exception:
                self.event_handler.terminate()
                self.termination_exc = traceback.format_exc()

        return wrapper

    def run(self):
        self.sender.start()
        self.event_handler.run()

    def terminate(self):
        self.batcher.terminate()
        self.sender.terminate()
        self.event_handler.terminate()


def run():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument("config_path")
    config_path = parser.parse_args().config_path
    config = create_config(config_path)

    main = Main(config)

    terminate_signal_sent = False

    def terminate_signal_handler(x, y):
        logger.warn("received termination signal")
        nonlocal terminate_signal_sent
        if not terminate_signal_sent:
            terminate_signal_sent = True
            main.terminate()
        else:
            # exit if pressed twice
            exit(1)

    signal.signal(signal.SIGINT, terminate_signal_handler)

    main.run()

    if main.termination_exc:
        logger.error(main.termination_exc)
        exit(1)
