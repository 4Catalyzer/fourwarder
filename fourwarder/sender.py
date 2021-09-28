import logging
from threading import Thread
from queue import Queue, Empty
import time
import requests
from .config import BaseConfig

logger = logging.getLogger("fourwarder.sender")


class Sender:
    def __init__(self, thread_panic, config: BaseConfig) -> None:
        self.queue = Queue()
        self.terminate_flag = False
        self.thread_panic = thread_panic
        self.config = config

    def start(self):
        self.thread = Thread(target=self.thread_panic(self.run))
        self.thread.start()
        logger.info("started")

    def send_logs(self, logs):
        self.queue.put_nowait(logs)

    def run(self):
        while True:
            try:
                logs = self.queue.get(timeout=0.2)
                self.try_send_data(logs, retries=self.config.RETRIES)
                self.queue.task_done()
            except Empty:
                if self.terminate_flag:
                    return

    def send_data(self, logs):
        raise NotImplementedError()

    def try_send_data(self, logs, backoff=3, retries=5):
        exception = None
        try:
            self.send_data(logs)
        except Exception as e:
            exception = e

        # we run this outside of the try-catch block above to avoid
        # dirty stack traces due to recursion
        if exception:
            logger.error("error when sending data")
            logger.exception(exception)
            if retries > 0:
                logger.info(f"retrying in {backoff} seconds")
                time.sleep(backoff)
                self.try_send_data(logs, backoff * 2, retries - 1)
            else:
                if self.config.DIE_ON_FAIL:
                    raise exception
                logger.warn("max retries exceeded, skipping batch")

    def terminate(self):
        self.terminate_flag = True
        logger.info("terminating")
        self.thread.join()


class HttpSender(Sender):
    def __init__(self, request_kwargs, **kwargs) -> None:
        super().__init__(**kwargs)
        self.request_kwargs = request_kwargs

    def send_data(self, logs):
        requests.request(**self.request_kwargs, json=logs).raise_for_status()
