import logging
import time
from itertools import chain
from subprocess import call, check_call
from threading import Thread

from fourwarder.config import BaseConfig
from fourwarder.main import Main
from fourwarder.sender import Sender

logging.basicConfig(level=logging.DEBUG)


class DummySender(Sender):
    def __init__(self, thread_panic, config):
        super().__init__(thread_panic, config)
        self.sent_data = []

    def send_data(self, logs):
        self.sent_data.append(logs)


class Config(BaseConfig):
    @staticmethod
    def create_sender(**kwargs):
        return DummySender(**kwargs)

    BATCH_SIZE = 5


def docker_bash(cmd, **kwargs):
    docker_args = [[f"--{k}", v] for k, v in kwargs.items()]
    docker_args = list(chain(*docker_args))
    check_call(["docker", "run", *docker_args, "bash", "bash", "-c", cmd])


def test_main():
    main = Main(Config)
    main_thread = Thread(target=main.run)
    main_thread.start()

    docker_bash("for i in {1..7}; do echo $i;  done")

    time.sleep(0.1)
    main.terminate()
    main_thread.join()

    assert main.termination_exc is None
    assert main.sender.sent_data == [["1", "2", "3", "4", "5"], ["6", "7"]]


def test_main_filter_container():
    class MyConfig(Config):
        def filter_container(container):
            return container.name == "bar"

    main = Main(MyConfig)
    main_thread = Thread(target=main.run)
    main_thread.start()

    call(["docker", "rm", "foo"])
    docker_bash("echo container 1", name="foo")
    call(["docker", "rm", "bar"])
    docker_bash("echo container 2", name="bar")

    time.sleep(0.1)
    main.terminate()
    main_thread.join()

    assert main.termination_exc is None
    assert main.sender.sent_data == [["container 2"]]


def test_main_filter_log():
    class MyConfig(Config):
        def filter_log(log_line):
            return "2" not in log_line

        BATCH_SIZE = 20

    main = Main(MyConfig)
    main_thread = Thread(target=main.run)
    main_thread.start()

    docker_bash("for i in {1..13}; do echo $i;  done")

    time.sleep(0.1)
    main.terminate()
    main_thread.join()

    assert main.termination_exc is None
    assert main.sender.sent_data == [
        ["1", "3", "4", "5", "6", "7", "8", "9", "10", "11", "13"]
    ]


def test_format_log():
    class MyConfig(Config):
        def format_log(log_line, container):
            return f"{container.name} | {container.image.tags[0]} | {log_line}"

    main = Main(MyConfig)
    main_thread = Thread(target=main.run)
    main_thread.start()

    call(["docker", "rm", "foo"])
    docker_bash("echo container 1", name="foo")
    call(["docker", "rm", "bar"])
    docker_bash("echo container 2", name="bar")

    time.sleep(0.1)
    main.terminate()
    main_thread.join()

    assert main.termination_exc is None
    assert main.sender.sent_data == [
        [
            "foo | bash:latest | container 1",
            "bar | bash:latest | container 2",
        ]
    ]
