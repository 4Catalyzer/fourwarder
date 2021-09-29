import logging
from threading import RLock, Timer

from .config import BaseConfig
from .sender import Sender

logger = logging.getLogger("fourwarder.batcher")


class Batcher:
    def __init__(self, sender: Sender, thread_panic, config: BaseConfig) -> None:
        self.staged_logs = []
        self.current_batch_timer = None
        self.lock = RLock()
        self.sender = sender
        self.thread_panic = thread_panic
        self.config = config

    def filter_log(self, log_line):
        return self.config.filter_log(log_line)

    def push_line(self, log_line):
        if not self.filter_log(log_line):
            return

        with self.lock:
            self.staged_logs.append(log_line)

            if not self.current_batch_timer:
                self.current_batch_timer = Timer(
                    self.config.BATCH_TIMEOUT_SECONDS, self.thread_panic(self.flush)
                )
                self.current_batch_timer.start()

            if len(self.staged_logs) >= self.config.BATCH_SIZE:
                self.flush()

    def flush(self):
        logger.info("flushing")
        with self.lock:
            if self.staged_logs:
                self.sender.send_logs(self.staged_logs)
                self.staged_logs = []

            if self.current_batch_timer is not None:
                self.current_batch_timer.cancel()
                self.current_batch_timer = None

    def terminate(self):
        self.flush()
