"""Config that can be shared between all test types."""
from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING, TypeVar
from uuid import uuid4

import pytest
from asyncpg.pgproto import pgproto

from tests.utils.domain import authors, books

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import ModuleType
    from typing import Any

    from pytest import MonkeyPatch


@pytest.fixture(name="raw_authors")
def fx_raw_authors() -> list[dict[str, Any]]:
    """Unstructured author representations."""

    return [
        {
            "id": "97108ac1-ffcb-411d-8b1e-d9183399f63b",
            "name": "Agatha Christie",
            "dob": "1890-09-15",
            "created": "0001-01-01T00:00:00",
            "updated": "0001-01-01T00:00:00",
        },
        {
            "id": "5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2",
            "name": "Leo Tolstoy",
            "dob": "1828-09-09",
            "created": "0001-01-01T00:00:00",
            "updated": "0001-01-01T00:00:00",
        },
    ]


@pytest.fixture(name="authors")
def fx_authors(raw_authors: list[dict[str, Any]]) -> list[authors.Author]:
    """Collection of parsed Author models."""
    mapped_authors = [authors.ReadDTO(**raw).to_mapped() for raw in raw_authors]
    # convert these to pgproto UUIDs as that is what we get back from sqlalchemy
    for author in mapped_authors:
        author.id = pgproto.UUID(str(author.id))
    return mapped_authors


@pytest.fixture(name="raw_books")
def fx_raw_books(raw_authors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unstructured book representations."""
    return [
        {
            "id": "f34545b9-663c-4fce-915d-dd1ae9cea42a",
            "title": "Murder on the Orient Express",
            "author_id": "97108ac1-ffcb-411d-8b1e-d9183399f63b",
            "author": raw_authors[0],
            "created": "0001-01-01T00:00:00",
            "updated": "0001-01-01T00:00:00",
        },
    ]


@pytest.fixture(name="books")
def fx_books(raw_books: list[dict[str, Any]]) -> list[books.Book]:
    """Collection of parsed Book models."""
    mapped_books = [books.ReadDTO(**raw).to_mapped() for raw in raw_books]
    # convert these to pgproto UUIDs as that is what we get back from sqlalchemy
    for book in mapped_books:
        book.id = pgproto.UUID(str(book.id))
    return mapped_books


@pytest.fixture(name="create_module")
def fx_create_module(tmp_path: Path, monkeypatch: MonkeyPatch) -> Callable[[str], ModuleType]:
    """Utility fixture for dynamic module creation."""

    def wrapped(source: str) -> ModuleType:
        """

        Args:
            source: Source code as a string.

        Returns:
            An imported module.
        """
        T = TypeVar("T")

        def not_none(val: T | None) -> T:
            assert val is not None
            return val

        module_name = uuid4().hex
        path = tmp_path / f"{module_name}.py"
        path.write_text(source)
        # https://docs.python.org/3/library/importlib.html#importing-a-source-file-directly
        spec = not_none(importlib.util.spec_from_file_location(module_name, path))  # pyright:ignore
        module = not_none(importlib.util.module_from_spec(spec))  # pyright:ignore
        monkeypatch.setitem(sys.modules, module_name, module)
        not_none(spec.loader).exec_module(module)
        return module

    return wrapped
