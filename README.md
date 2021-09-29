# fourwarder

Collect and send docker logs.

## Install

```sh
pip install fourwarder
# OR
poetry add fourwarder
```

## Getting Started

In order to run, you need to specify a minimal configuration. Here's an example

```py
from fourwarder.sender import HttpSender

class Config:
    def create_sender(**kwargs):
        return HttpSender(
          {"method": "POST", "url": "http://example.com"},
          **kwargs
        )
```

after saving the file somewhere, then you can run fourwarder:

```
fourwarder path_to_my_config.py
```

## Configuration

Fourwarder offers several configuration options. All the following methods and properties need to be added to the `Config` static class that resides in the module passed as argument (as shown above)

### Filtering containers

If you only are interested to some containers, you can add the following method to the config class:

```py
class Config:
  def filter_container(container: Container) -> bool:
    return container.name == "fofo"
```

the container argument is a [docker Container](https://github.com/docker/docker-py/blob/b27faa62e792c141a5d20c4acdd240fdac7d282f/docker/models/containers.py#L17)

### Filtering logs

if you want to log only specific line, you can add the following method

```py
class Config:
  def filter_log(log_line: str) -> bool:
    return log_line.startswith('ERROR')
```

### Formatting

by default only the raw log lines are passed, if you want to add extra metadata, use the following method:

```py
class Config:
  def format_log(log_line: str, container: Container) -> bool:
    return f'{time.time()}:{container.name}: {log_line}'
```

You can even pass a json-dumpable payload:

```py
class Config:
  def format_log(log_line: str, container: Container) -> bool:
    return {"name": container.name, "log": log_line}
```

### Sending

Fourwarder comes with an HttpSender class that sends the data over HTTP. You can subclass HttpSender to modify its behavior:

```py
class MySender(HttpSender):
  def send_data(self, logs):
    super().send_data({"data": logs, "batch_time": time.time()})

class Config:
    def create_sender(**kwargs):
        return MySender({"method": "POST", "url": "http://example.com"}, **kwargs)
```

or you can even modify the base Sender class:

```py
class FileSender(Sender):
  def __init__(self, file, **kwargs) -> None:
        super().__init__(**kwargs)
        self.file = Path(file)

  def send_data(self, logs):
    with self.file.open("a") as f:
      f.write(json.dumps(logs))

class Config:
    def create_sender(**kwargs):
        return FileSender({"file": "file.txt"}, **kwargs)
```

### Batching

Fourwarder offers some batching capabilities for more efficient processing. You can configure the following properties:

```py
class Config:
  # defaults shown
  BATCH_SIZE = 100
  BATCH_TIMEOUT_SECONDS = 10
```

Note that by setting `BATCH_SIZE` to 1 you can basically turn off batching.

### Failures

Additional options to handle failures when sending

```py
class Config:
  # defaults shown
  DIE_ON_FAIL = True # whether to terminate the program on failure
  RETRIES = 5 # how many times the request is retried (with exponential backoff)
```

## Running inside docker

to run inside docker, you will need to mount the docker socket:

```sh
docker run \
  --volume=/var/run/docker.sock:/var/run/docker.sock \
  ...
```

(we currently do not maintain a docker image, so you'll have to build your own)

## Architecture

The application has the following threads running different components

- **main**: the main thread runs the docker event loop to listen for all the docker events
- **container handlers**: when a container is being monitored, a thread starts, listening to the incoming logs
- **batcher**: collects all the log lines, applies filtering and batches them before sending
- **sender**: sends the batches of log to the destination, managing failures and retries

![](./arch.png)
