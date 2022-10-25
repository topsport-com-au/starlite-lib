# starlite-saqlalchemy

<img src="https://www.topsport.com.au/assets/images/logo_pulse.svg" width="200"/>

![PyPI - License](https://img.shields.io/pypi/l/starlite-saqlalchemy?color=blue)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/starlite-saqlalchemy)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/topsport-com-au/starlite-saqlalchemy/main.svg)](https://results.pre-commit.ci/latest/github/topsport-com-au/starlite-saqlalchemy/main)

Configuration for a [Starlite](https://github.com/starlite-api/starlite) application that features:

- SQLAlchemy 2.0
- SAQ async worker
- Lots of features!

## Example

```python
from starlite import Starlite, get

from starlite_saqlalchemy import ConfigureApp


@get("/example")
def example_handler() -> dict:
    """Hello, world!"""
    return {"hello": "world"}


app = Starlite(route_handlers=[example_handler], on_app_init=[ConfigureApp()])
```

## Features

The application configured in the above example includes the following configuration.

### Logging after exception handler

Receives and logs any unhandled exceptions raised out of route handling.

### Redis cache

Integrates a Redis cache backend with Starlite first-class cache support.

### Collection route filters

Support filtering collection routes by created and updated timestamps, list of ids, and limit/offset
pagination.

Includes an aggregate `filters` dependency to easily inject all filters into a route handler, e.g,:

```python
from starlite import get
from starlite_saqlalchemy.dependencies import FilterTypes


@get()
async def get_collection(filters: list[FilterTypes]) -> list[...]:
    ...
```

### Gzip compression

Configures Starlite's built-in Gzip compression support.

### Exception handlers

Exception handlers that translate non-Starlite repository and service object exception
types into Starlite's HTTP exceptions.

### Health check

A health check route handler that returns some basic application info.

### Logging

Configures logging for the application including:

- Queue listener handler, appropriate for asyncio applications
- Health check route filter so that health check requests don't clog your logs
- An informative log format
- Configuration for dependency logs

### Openapi config

Configures OpenAPI docs for the application, including config by environment to allow for easy
personalization per application.

### Starlite Response class

A response class that can handle serialization of SQLAlchemy/Postgres UUID types.

### Sentry configuration

Just supply the DSN via environment, and Sentry is configured for you.

### SQLAlchemy

Engine, logging, pooling etc all configurable via environment. We configure starlite and include a
custom `before_send` wrapper that inspects the outgoing status code to determine whether the
transaction that represents the request should be committed, or rolled back.

### Static files config

Adds a static files config for the app.

### Async SAQ worker config

A customized SAQ queue and worker that is started and shutdown using the Starlite lifecycle event
hooks - no need to run your worker in another process, we attach it to the same event loop as the
Starlite app uses. Be careful not to do things in workers that will block the loop!

## Extra Features

In addition to application config, the library include:

### Repository

An abstract repository object type and a SQLAlchemy repository implementation.

### DTO Factory

A factory for building pydantic models from SQLAlchemy 2.0 style declarative classes. Use these to
annotate the `data` parameter and return type of routes to control the data that can be modified per
route, and the information included in route responses.

### HTTP Client and Endpoint decorator

`http.Client` is a wrapper around `httpx.AsyncClient` with some extra features including unwrapping
enveloped data, and closing the underlying client during shutdown of the Starlite application.

### ORM Configuration

A SQLAlchemy declarative base class that includes:

- a mapping of the builtin `UUID` type to the postgresql dialect UUID type.
- an `id` column
- a `created` timestamp column
- an `updated` timestamp column
- an automated `__tablename__` attribute
- a `from_dto()` class method, to ease construction of model types from DTO objects.

We also add:

- a `before_flush` event listener that ensures that the `updated` timestamp is touched on instances
  on their way into the database.
- a constraint naming convention so that index and constraint names are automatically generated.

### Service object

A Service object that integrates with the Repository ABC and provides standard logic for typical
operations.

### Settings

Configuration by environment.

## Contributing

All contributions big or small are welcome and appreciated! Please check out `CONTRIBUTING.md` for
specific information about configuring your environment and workflows used by this project.
