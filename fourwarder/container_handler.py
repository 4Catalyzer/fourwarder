import logging
from threading import Thread

from docker.models.containers import Container

from .batcher import Batcher
from .config import BaseConfig


class ContainerHandler:
    def __init__(
        self,
        container: Container,
        batcher: Batcher,
        thread_panic,
        config: BaseConfig,
    ):
        self.container = container
        self.batcher = batcher
        self.logger = logging.getLogger(f"fourwarder.handler.{self.container.name}")
        self.thread_panic = thread_panic
        self.config = config

    def start(self):
        self.log_thread = Thread(target=self.thread_panic(self.watch_logs), daemon=True)
        self.log_stream = self.container.logs(stream=True)
        self.log_thread.start()
        self.logger.info("started")

    def terminate(self):
        self.log_thread.join()
        self.logger.info("terminated")

    def watch_logs(self):
        for line in self.log_stream:
            self.handle_log_line(line)

    def handle_log_line(self, line: str):
        line = line.decode().strip()
        line_data = self.config.format_log(line, self.container)

        self.batcher.push_line(line_data)
