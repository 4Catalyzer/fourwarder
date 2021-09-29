import sys
from pathlib import Path
from importlib import import_module
from docker.models.containers import Container


def load_module(config_file: str):
    f = Path(config_file).absolute()
    sys.path.insert(0, str(f.parent))
    return import_module(f.stem)


class BaseConfig:
    @staticmethod
    def create_sender(**kwargs):
        raise NotImplementedError()

    @staticmethod
    def format_log(log_line: str, container: Container):
        return log_line

    @staticmethod
    def filter_log(log_line):
        return True

    @staticmethod
    def filter_container(container: Container) -> bool:
        return True

    BATCH_SIZE = 100
    BATCH_TIMEOUT_SECONDS = 10

    DIE_ON_FAIL = True
    RETRIES = 5


def create_config(config_file: str) -> BaseConfig:
    if not config_file:
        return BaseConfig

    CustomConfig = load_module(config_file).Config

    class Config(CustomConfig, BaseConfig):
        pass

    return Config
