"""Unit tests for the SQLAlchemy Repository implementation."""
# pylint: disable=protected-access,redefined-outer-name
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from sqlalchemy.exc import IntegrityError, InvalidRequestError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from starlite_saqlalchemy.repository.exceptions import (
    RepositoryConflictException,
    RepositoryException,
)
from starlite_saqlalchemy.repository.filters import (
    BeforeAfter,
    CollectionFilter,
    LimitOffset,
)
from starlite_saqlalchemy.repository.sqlalchemy import (
    SQLAlchemyRepository,
    wrap_sqlalchemy_exception,
)

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.fixture()
def mock_repo() -> SQLAlchemyRepository:
    """SQLAlchemy repository with a mock model type."""

    class Repo(SQLAlchemyRepository[MagicMock]):
        """Repo with mocked out stuff."""

        model_type = MagicMock()  # pyright:ignore[reportGeneralTypeIssues]

    return Repo(session=AsyncMock(spec=AsyncSession), select_=MagicMock())


def test_wrap_sqlalchemy_integrity_error() -> None:
    """Test to ensure we wrap IntegrityError."""
    with (pytest.raises(RepositoryConflictException), wrap_sqlalchemy_exception()):
        raise IntegrityError(None, None, Exception())


def test_wrap_sqlalchemy_generic_error() -> None:
    """Test to ensure we wrap generic SQLAlchemy exceptions."""
    with (pytest.raises(RepositoryException), wrap_sqlalchemy_exception()):
        raise SQLAlchemyError


async def test_sqlalchemy_repo_add(mock_repo: SQLAlchemyRepository) -> None:
    """Test expected method calls for add operation."""
    mock_instance = MagicMock()
    instance = await mock_repo.add(mock_instance)
    assert instance is mock_instance
    mock_repo.session.add.assert_called_once_with(mock_instance)
    mock_repo.session.flush.assert_called_once()
    mock_repo.session.refresh.assert_called_once_with(mock_instance)
    mock_repo.session.expunge.assert_called_once_with(mock_instance)
    mock_repo.session.commit.assert_not_called()


async def test_sqlalchemy_repo_delete(
    mock_repo: SQLAlchemyRepository, monkeypatch: MonkeyPatch
) -> None:
    """Test expected method calls for delete operation."""
    mock_instance = MagicMock()
    monkeypatch.setattr(mock_repo, "get", AsyncMock(return_value=mock_instance))
    instance = await mock_repo.delete("instance-id")
    assert instance is mock_instance
    mock_repo.session.delete.assert_called_once_with(mock_instance)
    mock_repo.session.flush.assert_called_once()
    mock_repo.session.expunge.assert_called_once_with(mock_instance)
    mock_repo.session.commit.assert_not_called()


async def test_sqlalchemy_repo_get_member(
    mock_repo: SQLAlchemyRepository, monkeypatch: MonkeyPatch
) -> None:
    """Test expected method calls for member get operation."""
    mock_instance = MagicMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=mock_instance)
    execute_mock = AsyncMock(return_value=result_mock)
    monkeypatch.setattr(mock_repo, "_execute", execute_mock)
    instance = await mock_repo.get("instance-id")
    assert instance is mock_instance
    mock_repo.session.expunge.assert_called_once_with(mock_instance)
    mock_repo.session.commit.assert_not_called()


async def test_sqlalchemy_repo_list(
    mock_repo: SQLAlchemyRepository, monkeypatch: MonkeyPatch
) -> None:
    """Test expected method calls for list operation."""
    mock_instances = [MagicMock(), MagicMock()]
    result_mock = MagicMock()
    result_mock.scalars = MagicMock(return_value=mock_instances)
    execute_mock = AsyncMock(return_value=result_mock)
    monkeypatch.setattr(mock_repo, "_execute", execute_mock)
    instances = await mock_repo.list()
    assert instances == mock_instances
    mock_repo.session.expunge.assert_has_calls(*mock_instances)
    mock_repo.session.commit.assert_not_called()


async def test_sqlalchemy_repo_list_with_pagination(
    mock_repo: SQLAlchemyRepository, monkeypatch: MonkeyPatch
) -> None:
    """Test list operation with pagination."""
    result_mock = MagicMock()
    execute_mock = AsyncMock(return_value=result_mock)
    monkeypatch.setattr(mock_repo, "_execute", execute_mock)
    mock_repo._select.limit.return_value = mock_repo._select
    mock_repo._select.offset.return_value = mock_repo._select
    await mock_repo.list(LimitOffset(2, 3))
    mock_repo._select.limit.assert_called_once_with(2)
    mock_repo._select.limit().offset.assert_called_once_with(3)  # type:ignore[call-arg]


async def test_sqlalchemy_repo_list_with_before_after_filter(
    mock_repo: SQLAlchemyRepository, monkeypatch: MonkeyPatch
) -> None:
    """Test list operation with BeforeAfter filter."""
    field_name = "updated"
    # model has to support comparison with the datetimes
    getattr(mock_repo.model_type, field_name).__lt__ = lambda self, compare: "lt"
    getattr(mock_repo.model_type, field_name).__gt__ = lambda self, compare: "gt"
    result_mock = MagicMock()
    execute_mock = AsyncMock(return_value=result_mock)
    monkeypatch.setattr(mock_repo, "_execute", execute_mock)
    mock_repo._select.where.return_value = mock_repo._select
    await mock_repo.list(BeforeAfter(field_name, datetime.max, datetime.min))
    assert mock_repo._select.where.call_count == 2
    assert mock_repo._select.where.has_calls([call("gt"), call("lt")])


async def test_sqlalchemy_repo_list_with_collection_filter(
    mock_repo: SQLAlchemyRepository, monkeypatch: MonkeyPatch
) -> None:
    """Test behavior of list operation given CollectionFilter."""
    field_name = "id"
    result_mock = MagicMock()
    execute_mock = AsyncMock(return_value=result_mock)
    monkeypatch.setattr(mock_repo, "_execute", execute_mock)
    mock_repo._select.where.return_value = mock_repo._select
    values = [1, 2, 3]
    await mock_repo.list(CollectionFilter(field_name, values))
    mock_repo._select.where.assert_called_once()
    getattr(mock_repo.model_type, field_name).in_.assert_called_once_with(values)


async def test_sqlalchemy_repo_unknown_filter_type_raises(mock_repo: SQLAlchemyRepository) -> None:
    """Test that repo raises exception if list receives unknown filter type."""
    with pytest.raises(RepositoryException):
        await mock_repo.list("not a filter")  # type:ignore[arg-type]


async def test_sqlalchemy_repo_update(
    mock_repo: SQLAlchemyRepository, monkeypatch: MonkeyPatch
) -> None:
    """Test the sequence of repo calls for update operation."""
    id_ = 3
    mock_instance = MagicMock()
    get_id_value_mock = MagicMock(return_value=id_)
    monkeypatch.setattr(mock_repo, "get_id_attribute_value", get_id_value_mock)
    get_mock = AsyncMock()
    monkeypatch.setattr(mock_repo, "get", get_mock)
    mock_repo.session.merge.return_value = mock_instance
    instance = await mock_repo.update(mock_instance)
    assert instance is mock_instance
    mock_repo.session.merge.assert_called_once_with(mock_instance)
    mock_repo.session.flush.assert_called_once()
    mock_repo.session.refresh.assert_called_once_with(mock_instance)
    mock_repo.session.expunge.assert_called_once_with(mock_instance)
    mock_repo.session.commit.assert_not_called()


async def test_sqlalchemy_repo_upsert(mock_repo: SQLAlchemyRepository) -> None:
    """Test the sequence of repo calls for upsert operation."""
    mock_instance = MagicMock()
    mock_repo.session.merge.return_value = mock_instance
    instance = await mock_repo.upsert(mock_instance)
    assert instance is mock_instance
    mock_repo.session.merge.assert_called_once_with(mock_instance)
    mock_repo.session.flush.assert_called_once()
    mock_repo.session.refresh.assert_called_once_with(mock_instance)
    mock_repo.session.expunge.assert_called_once_with(mock_instance)
    mock_repo.session.commit.assert_not_called()


async def test_attach_to_session_unexpected_strategy_raises_valueerror(
    mock_repo: SQLAlchemyRepository,
) -> None:
    """Test to hit the error condition in SQLAlchemy._attach_to_session()."""
    with pytest.raises(ValueError):  # noqa: PT011
        await mock_repo._attach_to_session(MagicMock(), strategy="t-rex")  # type:ignore[arg-type]


async def test_execute(mock_repo: SQLAlchemyRepository) -> None:
    """Simple test of the abstraction over `AsyncSession.execute()`"""
    await mock_repo._execute()
    mock_repo.session.execute.assert_called_once_with(mock_repo._select)


def test_filter_in_collection_noop_if_collection_empty(mock_repo: SQLAlchemyRepository) -> None:
    """Ensures we don't filter on an empty collection."""
    mock_repo._filter_in_collection("id", [])
    mock_repo._select.where.assert_not_called()


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (datetime.max, datetime.min),
        (None, datetime.min),
        (datetime.max, None),
    ],
)
def test__filter_on_datetime_field(
    before: datetime, after: datetime, mock_repo: SQLAlchemyRepository
) -> None:
    """Test through branches of _filter_on_datetime_field()"""
    field_mock = MagicMock()
    field_mock.__gt__ = field_mock.__lt__ = lambda self, other: True
    mock_repo.model_type.updated = field_mock
    mock_repo._filter_on_datetime_field("updated", before, after)


def test_filter_collection_by_kwargs(mock_repo: SQLAlchemyRepository) -> None:
    """Test `filter_by()` called with kwargs."""
    mock_repo.filter_collection_by_kwargs(a=1, b=2)
    mock_repo._select.filter_by.assert_called_once_with(a=1, b=2)


def test_filter_collection_by_kwargs_raises_repository_exception_for_attribute_error(
    mock_repo: SQLAlchemyRepository,
) -> None:
    """Test that we raise a repository exception if an attribute name is
    incorrect."""
    mock_repo._select.filter_by = MagicMock(  # type:ignore[assignment]
        side_effect=InvalidRequestError,
    )
    with pytest.raises(RepositoryException):
        mock_repo.filter_collection_by_kwargs(a=1)
