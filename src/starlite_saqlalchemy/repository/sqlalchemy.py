"""SQLAlchemy-based implementation of the repository protocol."""
from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar, cast

from sqlalchemy import over, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.sql import func as sql_func

from starlite_saqlalchemy.exceptions import ConflictError, StarliteSaqlalchemyError
from starlite_saqlalchemy.repository.abc import AbstractRepository
from starlite_saqlalchemy.repository.filters import (
    BeforeAfter,
    CollectionFilter,
    LimitOffset,
)

if TYPE_CHECKING:
    from collections import abc
    from datetime import datetime

    from sqlalchemy import Select
    from sqlalchemy.engine import Result
    from sqlalchemy.ext.asyncio import AsyncSession

    from starlite_saqlalchemy.db import orm
    from starlite_saqlalchemy.repository.types import FilterTypes

__all__ = [
    "SQLAlchemyRepository",
    "ModelT",
]

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound="orm.Base | orm.AuditBase")
RowT = TypeVar("RowT", bound=tuple[Any, ...])
SQLARepoT = TypeVar("SQLARepoT", bound="SQLAlchemyRepository")
SelectT = TypeVar("SelectT", bound="Select[Any]")


@contextmanager
def wrap_sqlalchemy_exception() -> Any:
    """Do something within context to raise a `RepositoryException` chained
    from an original `SQLAlchemyError`.

        >>> try:
        ...     with wrap_sqlalchemy_exception():
        ...         raise SQLAlchemyError("Original Exception")
        ... except StarliteSaqlalchemyError as exc:
        ...     print(f"caught repository exception from {type(exc.__context__)}")
        ...
        caught repository exception from <class 'sqlalchemy.exc.SQLAlchemyError'>
    """
    try:
        yield
    except IntegrityError as exc:
        raise ConflictError from exc
    except SQLAlchemyError as exc:
        raise StarliteSaqlalchemyError(f"An exception occurred: {exc}") from exc


class SQLAlchemyRepository(AbstractRepository[ModelT], Generic[ModelT]):
    """SQLAlchemy based implementation of the repository interface."""

    def __init__(self, *, session: AsyncSession, **kwargs: Any) -> None:
        """
        Args:
            session: Session managing the unit-of-work for the operation.
        """
        super().__init__(**kwargs)
        self.session = session

    async def add(self, data: ModelT) -> ModelT:
        """Add `data` to the collection.

        Args:
            data: Instance to be added to the collection.

        Returns:
            The added instance.
        """
        with wrap_sqlalchemy_exception():
            instance = await self._attach_to_session(data)
            await self.session.flush()
            await self.session.refresh(instance)
            self.session.expunge(instance)
            return instance

    async def count(self, *filters: FilterTypes, **kwargs: Any) -> int:
        """

        Args:
            *filters: Types for specific filtering operations.
            **kwargs: Instance attribute value filters.

        Returns:
            Count of records returned by query, ignoring pagination.
        """
        select_ = select(sql_func.count(self.model_type.id))  # type:ignore[attr-defined]
        for filter_ in filters:
            match filter_:
                case LimitOffset(_, _):
                    pass
                    # we do not apply this filter to the count since we need the total rows
                case BeforeAfter(field_name, before, after):
                    select_ = self._filter_on_datetime_field(
                        field_name, before, after, select_=select_
                    )
                case CollectionFilter(field_name, values):
                    select_ = self._filter_in_collection(field_name, values, select_=select_)
                case _:
                    raise StarliteSaqlalchemyError(f"Unexpected filter: {filter}")
        results = await self._execute(select_)
        return results.scalar_one()  # type: ignore[no-any-return]

    async def delete(self, id_: Any) -> ModelT:
        """Delete instance identified by `id_`.

        Args:
            id_: Identifier of instance to be deleted.

        Returns:
            The deleted instance.

        Raises:
            RepositoryNotFoundException: If no instance found identified by `id_`.
        """
        with wrap_sqlalchemy_exception():
            instance = await self.get(id_)
            await self.session.delete(instance)
            await self.session.flush()
            self.session.expunge(instance)
            return instance

    async def get(self, id_: Any) -> ModelT:
        """Get instance identified by `id_`.

        Args:
            id_: Identifier of the instance to be retrieved.

        Returns:
            The retrieved instance.

        Raises:
            RepositoryNotFoundException: If no instance found identified by `id_`.
        """
        select_ = self._create_select_for_model()
        with wrap_sqlalchemy_exception():
            select_ = self._filter_select_by_kwargs(select_, **{self.id_attribute: id_})
            instance = (await self._execute(select_)).scalar_one_or_none()
            instance = self.check_not_found(instance)
            self.session.expunge(instance)
            return instance

    async def list(self, *filters: FilterTypes, **kwargs: Any) -> abc.Sequence[ModelT]:
        """Get a list of instances, optionally filtered.

        Args:
            *filters: Types for specific filtering operations.
            **kwargs: Instance attribute value filters.

        Returns:
            The list of instances, after filtering applied.
        """
        select_ = self._create_select_for_model()
        select_ = self._filter_for_list(*filters, select_=select_)
        select_ = self._filter_select_by_kwargs(select_, **kwargs)

        with wrap_sqlalchemy_exception():
            result = await self._execute(select_)
            instances = list(result.scalars())
            for instance in instances:
                self.session.expunge(instance)
            return instances

    async def list_and_count(
        self, *filters: FilterTypes, **kwargs: Any
    ) -> tuple[abc.Sequence[ModelT], int]:
        """

        Args:
            *filters: Types for specific filtering operations.
            **kwargs: Instance attribute value filters.

        Returns:
            Count of records returned by query, ignoring pagination.
        """
        select_ = select(
            self.model_type,
            over(sql_func.count(self.model_type.id)),  # type:ignore[attr-defined]
        )
        select_ = self._filter_for_list(*filters, select_=select_)
        select_ = self._filter_select_by_kwargs(select_, **kwargs)
        with wrap_sqlalchemy_exception():
            result = await self._execute(select_)
            count: int = 0
            instances: list[ModelT] = []
            for i, (instance, count_value) in enumerate(result):
                self.session.expunge(instance)
                instances.append(instance)
                if i == 0:
                    count = count_value
            return instances, count

    async def update(self, data: ModelT) -> ModelT:
        """Update instance with the attribute values present on `data`.

        Args:
            data: An instance that should have a value for `self.id_attribute` that exists in the
                collection.

        Returns:
            The updated instance.

        Raises:
            RepositoryNotFoundException: If no instance found with same identifier as `data`.
        """
        with wrap_sqlalchemy_exception():
            id_ = self.get_id_attribute_value(data)
            # this will raise for not found, and will put the item in the session
            await self.get(id_)
            # this will merge the inbound data to the instance we just put in the session
            instance = await self._attach_to_session(data, strategy="merge")
            await self.session.flush()
            await self.session.refresh(instance)
            self.session.expunge(instance)
            return instance

    async def upsert(self, data: ModelT) -> ModelT:
        """Update or create instance.

        Updates instance with the attribute values present on `data`, or creates a new instance if
        one doesn't exist.

        Args:
            data: Instance to update existing, or be created. Identifier used to determine if an
                existing instance exists is the value of an attribute on `data` named as value of
                `self.id_attribute`.

        Returns:
            The updated or created instance.

        Raises:
            RepositoryNotFoundException: If no instance found with same identifier as `data`.
        """
        with wrap_sqlalchemy_exception():
            instance = await self._attach_to_session(data, strategy="merge")
            await self.session.flush()
            await self.session.refresh(instance)
            self.session.expunge(instance)
            return instance

    def filter_collection_by_kwargs(  # type:ignore[override]
        self,
        collection: SelectT,
        /,
        **kwargs: Any,
    ) -> SelectT:
        """Filter the collection by kwargs.

        Args:
            collection: select to filter
            **kwargs: key/value pairs such that objects remaining in the collection after filtering
                have the property that their attribute named `key` has value equal to `value`.
        """
        with wrap_sqlalchemy_exception():
            return collection.filter_by(**kwargs)

    @classmethod
    async def check_health(cls, session: AsyncSession) -> bool:
        """Perform a health check on the database.

        Args:
            session: through which we runa check statement

        Returns:
            `True` if healthy.
        """
        return (  # type:ignore[no-any-return]  # pragma: no cover
            await session.execute(text("SELECT 1"))
        ).scalar_one() == 1

    # the following is all sqlalchemy implementation detail, and shouldn't be directly accessed

    def _apply_limit_offset_pagination(
        self, limit: int, offset: int, *, select_: SelectT
    ) -> SelectT:
        return select_.limit(limit).offset(offset)

    async def _attach_to_session(
        self, model: ModelT, strategy: Literal["add", "merge"] = "add"
    ) -> ModelT:
        """Attach detached instance to the session.

        Args:
            model: The instance to be attached to the session.
            strategy: How the instance should be attached.
                - "add": New instance added to session
                - "merge": Instance merged with existing, or new one added.

        Returns:
            Instance attached to the session - if `"merge"` strategy, may not be same instance
            that was provided.
        """
        match strategy:  # noqa: R503
            case "add":
                self.session.add(model)
                return model
            case "merge":
                return await self.session.merge(model)
            case _:
                raise ValueError("Unexpected value for `strategy`, must be `'add'` or `'merge'`")

    def _create_select_for_model(self) -> Select[tuple[ModelT]]:
        return select(self.model_type)

    async def _execute(self, select_: Select[RowT]) -> Result[RowT]:
        return cast("Result[RowT]", await self.session.execute(select_))

    def _filter_for_list(self, *filters: FilterTypes, select_: SelectT) -> SelectT:
        """
        Args:
            *filters: filter types to apply to the query

        Keyword Args:
            select_: select to apply filters against

        Returns:
            The select with filters applied.
        """
        for filter_ in filters:
            match filter_:
                case LimitOffset(limit, offset):
                    select_ = self._apply_limit_offset_pagination(limit, offset, select_=select_)
                case BeforeAfter(field_name, before, after):
                    select_ = self._filter_on_datetime_field(
                        field_name, before, after, select_=select_
                    )
                case CollectionFilter(field_name, values):
                    select_ = self._filter_in_collection(field_name, values, select_=select_)
                case _:
                    raise StarliteSaqlalchemyError(f"Unexpected filter: {filter}")
        return select_

    def _filter_in_collection(
        self, field_name: str, values: abc.Collection[Any], *, select_: SelectT
    ) -> SelectT:
        if not values:
            return select_

        return select_.where(getattr(self.model_type, field_name).in_(values))

    def _filter_on_datetime_field(
        self, field_name: str, before: datetime | None, after: datetime | None, *, select_: SelectT
    ) -> SelectT:
        field = getattr(self.model_type, field_name)
        if before is not None:
            select_ = select_.where(field < before)
        if after is not None:
            return select_.where(field > before)
        return select_

    def _filter_select_by_kwargs(self, select_: SelectT, **kwargs: Any) -> SelectT:
        for key, val in kwargs.items():
            select_ = select_.where(getattr(self.model_type, key) == val)
        return select_
