from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Identity, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity

if TYPE_CHECKING:
    from app.models.ComplaintPetition import ComplaintPetition
    from app.models.Department import Department
    from app.models.Location import Location


class LocationDepartment(BaseEntity):
    __tablename__ = "location_department"
    __table_args__ = (
        UniqueConstraint("location_id", "department_id", name="uq_location_department_pair"),
    )

    location_department_id: Mapped[int] = mapped_column(
        "location_department_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    location_id: Mapped[int] = mapped_column(
        "location_id",
        BigInteger,
        ForeignKey("location.location_id"),
        nullable=False,
    )
    department_id: Mapped[int] = mapped_column(
        "department_id",
        BigInteger,
        ForeignKey("department.department_id"),
        nullable=False,
    )
    location_department_email: Mapped[str] = mapped_column(
        "location_department_email",
        String(255),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        "is_active",
        Boolean,
        nullable=False,
        default=True,
    )

    location: Mapped[Location] = relationship(
        "Location",
        back_populates="location_departments",
        foreign_keys=[location_id],
        lazy="selectin",
    )
    department: Mapped[Department] = relationship(
        "Department",
        back_populates="location_departments",
        foreign_keys=[department_id],
        lazy="selectin",
    )
    complaint_petitions: Mapped[list[ComplaintPetition]] = relationship(
        "ComplaintPetition",
        back_populates="location_department",
        lazy="selectin",
    )

