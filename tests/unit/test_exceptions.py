"""Tests for exception translation behavior."""
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from starlette.status import (
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from starlite import Starlite, get
from starlite.testing import RequestFactory, create_test_client

from starlite_saqlalchemy import exceptions
from starlite_saqlalchemy.repository.exceptions import (
    RepositoryConflictException,
    RepositoryException,
    RepositoryNotFoundException,
)
from starlite_saqlalchemy.service import ServiceException, UnauthorizedException

if TYPE_CHECKING:
    from collections import abc


def test_after_exception_hook_handler_called(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests that the handler gets added to the app and called."""
    logger_mock = MagicMock()
    monkeypatch.setattr(exceptions, "bind_contextvars", logger_mock)
    exc = RuntimeError()

    @get("/error")
    def raises() -> None:
        raise exc

    with create_test_client(
        route_handlers=[raises], after_exception=exceptions.after_exception_hook_handler
    ) as client:
        resp = client.get("/error")
        assert resp.status_code == HTTP_500_INTERNAL_SERVER_ERROR

    logger_mock.assert_called_once_with(exc_info=exc)


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (RepositoryConflictException, HTTP_409_CONFLICT),
        (RepositoryNotFoundException, HTTP_404_NOT_FOUND),
        (RepositoryException, HTTP_500_INTERNAL_SERVER_ERROR),
    ],
)
def test_repository_exception_to_http_response(exc: type[RepositoryException], status: int) -> None:
    """Test translation of repository exceptions to Starlite HTTP exception
    types."""
    app = Starlite(route_handlers=[])
    request = RequestFactory(app=app, server="testserver").get("/wherever")
    response = exceptions.repository_exception_to_http_response(request, exc())
    assert response.status_code == status


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (UnauthorizedException, HTTP_403_FORBIDDEN),
        (ServiceException, HTTP_500_INTERNAL_SERVER_ERROR),
    ],
)
def test_service_exception_to_http_response(exc: type[ServiceException], status: int) -> None:
    """Test translation of service exceptions to Starlite HTTP exception
    types."""
    app = Starlite(route_handlers=[])
    request = RequestFactory(app=app, server="testserver").get("/wherever")
    response = exceptions.service_exception_to_http_response(request, exc())
    assert response.status_code == status


@pytest.mark.parametrize(
    ("exc", "func", "expected_message"),
    [
        (
            RepositoryException("message"),
            exceptions.repository_exception_to_http_response,
            b"starlite_saqlalchemy.repository.exceptions.RepositoryException: message\n",
        ),
        (
            ServiceException("message"),
            exceptions.service_exception_to_http_response,
            b"starlite_saqlalchemy.service.ServiceException: message\n",
        ),
    ],
)
def test_exception_serves_debug_middleware_response(
    exc: Exception, func: "abc.Callable", expected_message: bytes
) -> None:
    """Test behavior of exception translation in debug mode."""
    app = Starlite(route_handlers=[], debug=True)
    request = RequestFactory(app=app, server="testserver").get("/wherever")
    response = func(request, exc)
    assert response.body == expected_message
