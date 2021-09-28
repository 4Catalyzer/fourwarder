import os
import logging
import argparse
import docker
from docker.models.containers import Container

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
        logger.warn("received termination signal")
        self.event_stream.close()


import traceback


def run():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("config_path")
    config_path = parser.parse_args().config_path
    config = create_config(config_path)

    termination_exc = None
    terminate_signal_sent = False

    def thread_panic(func):
        """wraps the passed function into a try catch that terminates the main thread."""

        def wrapper():
            try:
                func()
            except Exception:
                nonlocal termination_exc
                main.terminate()
                termination_exc = traceback.format_exc()

        return wrapper

    sender = config.create_sender(thread_panic=thread_panic, config=config)
    batcher = Batcher(sender, thread_panic, config)
    main = EventHandler(batcher, thread_panic, config)

    import signal

    def terminate_signal_handler(x, y):
        nonlocal terminate_signal_sent
        if not terminate_signal_sent:
            terminate_signal_sent = True
            main.terminate()
        else:
            # exit if pressed twice
            exit(1)

    signal.signal(signal.SIGINT, terminate_signal_handler)

    sender.start()

    main.run()

    logger.info("shutting down")
    batcher.terminate()
    sender.terminate()

    if termination_exc:
        logger.error(termination_exc)
        exit(1)
