from __future__ import annotations

from sqlalchemy import BigInteger, Float, ForeignKey, Identity, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PopulationDensity(Base):
    __tablename__ = "population_density"

    population_density_id: Mapped[int] = mapped_column(
        "population_density_id",
        BigInteger,
        Identity(),
        primary_key=True,
    )
    population_density: Mapped[float | None] = mapped_column(
        "population_density",
        Float,
        nullable=True,
    )
    target_community: Mapped[int | None] = mapped_column(
        "target_community",
        Integer,
        nullable=True,
    )
    target_petition: Mapped[int | None] = mapped_column(
        "target_petition",
        Integer,
        nullable=True,
    )
    location_id: Mapped[int] = mapped_column(
        "location_id",
        BigInteger,
        ForeignKey("location.location_id"),
        nullable=False,
    )
