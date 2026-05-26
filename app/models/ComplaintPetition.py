from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, Float, ForeignKey, Identity, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseEntity import BaseEntity
from app.models.enum.ComplaintPetitionStatus import ComplaintPetitionStatus

if TYPE_CHECKING:
    from app.models.IssuePin import IssuePin
    from app.models.LocationDepartment import LocationDepartment


class ComplaintPetition(BaseEntity):
    __tablename__ = "complaint_petition"
    __table_args__ = (
        UniqueConstraint("issue_pin_id", "generated_on", name="uq_complaint_petition_issuepin_generatedon"),
    )

    petition_id: Mapped[int] = mapped_column(
        "petition_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    location_department_id: Mapped[int] = mapped_column(
        "location_department_id",
        BigInteger,
        ForeignKey("location_department.location_department_id"),
        nullable=False,
    )
    issue_pin_id: Mapped[int] = mapped_column(
        "issue_pin_id",
        BigInteger,
        ForeignKey("issue_pin.issue_pin_id"),
        nullable=False,
    )
    generated_on: Mapped[date] = mapped_column("generated_on", Date, nullable=False)
    pdf_s3_key: Mapped[str] = mapped_column("pdf_s3_key", Text, nullable=False)
    pdf_s3_url: Mapped[str] = mapped_column("pdf_s3_url", Text, nullable=False)
    email_subject: Mapped[str] = mapped_column("email_subject", Text, nullable=False)
    email_body: Mapped[str] = mapped_column("email_body", Text, nullable=False)
    reliability_score: Mapped[float] = mapped_column("reliability_score", Float, nullable=False, default=0.0)
    reliability_basis: Mapped[str] = mapped_column("reliability_basis", Text, nullable=False)
    status: Mapped[str] = mapped_column(
        "status",
        String(32),
        nullable=False,
        default=ComplaintPetitionStatus.CREATED.value,
    )

    location_department: Mapped[LocationDepartment] = relationship(
        "LocationDepartment",
        back_populates="complaint_petitions",
        foreign_keys=[location_department_id],
        lazy="selectin",
    )
    issue_pin: Mapped[IssuePin] = relationship(
        "IssuePin",
        back_populates="complaint_petitions",
        foreign_keys=[issue_pin_id],
        lazy="selectin",
    )

