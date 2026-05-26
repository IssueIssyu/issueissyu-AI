from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity

if TYPE_CHECKING:
    from app.models.LocationDepartment import LocationDepartment


class Department(BaseEntity):
    __tablename__ = "department"

    department_id: Mapped[int] = mapped_column(
        "department_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    department_name: Mapped[str] = mapped_column(
        "department_name",
        String(128),
        nullable=False,
        unique=True,
    )

    location_departments: Mapped[list[LocationDepartment]] = relationship(
        "LocationDepartment",
        back_populates="department",
        lazy="selectin",
    )

