"""Application ORM configuration."""
from __future__ import annotations

from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID, uuid4

from sqlalchemy import MetaData
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.event import listens_for
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    declarative_mixin,
    declared_attr,
    mapped_column,
    registry,
)

from starlite_saqlalchemy import dto, settings

BaseT = TypeVar("BaseT", bound="Base")

DTO_KEY = settings.api.DTO_INFO_KEY
"""The key we use to reference `dto.DTOField` in the SQLAlchemy info dict."""

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""Templates for automated constraint name generation."""


@listens_for(Session, "before_flush")
def touch_updated_timestamp(session: Session, *_: Any) -> None:
    """Set timestamp on update.

    Called from SQLAlchemy's
    [`before_flush`][sqlalchemy.orm.SessionEvents.before_flush] event to bump the `updated`
    timestamp on modified instances.

    Args:
        session: The sync [`Session`][sqlalchemy.orm.Session] instance that underlies the async
            session.
    """
    for instance in session.dirty:
        if hasattr(instance, "updated"):
            instance.updated = datetime.now()


@declarative_mixin
class CommonColumns:
    """Common functionality shared between all declarative models."""

    __abstract__ = True
    __name__: str

    id: Mapped[UUID] = mapped_column(
        default=uuid4, primary_key=True, info={DTO_KEY: dto.DTOField(mark=dto.Mark.READ_ONLY)}
    )
    """Primary key column."""

    # noinspection PyMethodParameters
    @declared_attr.directive
    def __tablename__(cls) -> str:  # pylint: disable=no-self-argument
        """Infer table name from class name."""
        return cls.__name__.lower()


@declarative_mixin
class AuditColumns:
    """Created/Updated At Fields Mixin."""

    __abstract__ = True

    created: Mapped[datetime] = mapped_column(
        default=datetime.now, info={DTO_KEY: dto.DTOField(mark=dto.Mark.READ_ONLY)}
    )
    """Date/time of instance creation."""
    updated: Mapped[datetime] = mapped_column(
        default=datetime.now, info={DTO_KEY: dto.DTOField(mark=dto.Mark.READ_ONLY)}
    )
    """Date/time of instance last update."""


meta = MetaData(naming_convention=convention)
registry_ = registry(metadata=meta, type_annotation_map={UUID: pg.UUID, dict: pg.JSONB})


class Base(CommonColumns, DeclarativeBase):
    """Base for all SQLAlchemy declarative models."""

    registry = registry_


class AuditBase(AuditColumns, CommonColumns, DeclarativeBase):
    """Base for declarative models with audit columns."""

    registry = registry_
