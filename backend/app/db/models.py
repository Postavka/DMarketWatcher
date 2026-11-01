from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OfferRow(Base):
    """Cached marketplace offer. Mirrors `app.dmarket.schemas.Offer` plus cache bookkeeping."""

    __tablename__ = "offers"

    offer_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, index=True)
    price_cents: Mapped[int] = mapped_column(Integer, index=True)
    discount_percent: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    item_type: Mapped[str] = mapped_column(String, default="")
    exterior: Mapped[str] = mapped_column(String, default="")
    float_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    paint_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phase: Mapped[str] = mapped_column(String, default="")
    rare_pattern: Mapped[str] = mapped_column(String, default="")
    collection: Mapped[str] = mapped_column(String, default="")
    colors: Mapped[list[str]] = mapped_column(JSON, default=list)
    sticker_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_stattrak: Mapped[bool] = mapped_column(Boolean, default=False)

    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (Index("ix_offers_title_price", "title", "price_cents"),)


class SkinRow(Base):
    """Static catalog entry (ByMykel/CSGO-API). Independent of market state."""

    __tablename__ = "skins"

    skin_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)  # not unique: Doppler phases share it
    weapon: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String, index=True)
    team: Mapped[str] = mapped_column(String, index=True)  # counter-terrorists | terrorists | both
    pattern: Mapped[str] = mapped_column(String, default="")
    paint_index: Mapped[str] = mapped_column(String, default="")
    rarity: Mapped[str] = mapped_column(String, default="")
    min_float: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_float: Mapped[float | None] = mapped_column(Float, nullable=True)
    wears: Mapped[list[str]] = mapped_column(JSON, default=list)
    collections: Mapped[list[str]] = mapped_column(JSON, default=list)
    image: Mapped[str] = mapped_column(String, default="")
    stattrak: Mapped[bool] = mapped_column(Boolean, default=False)
    souvenir: Mapped[bool] = mapped_column(Boolean, default=False)


class SkinColorRow(Base):
    """Colour profile computed once from a catalog skin's image (images never change)."""

    __tablename__ = "skin_colors"

    skin_id: Mapped[str] = mapped_column(String, primary_key=True)
    coverage: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    chromatic: Mapped[float] = mapped_column(Float, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(DateTime)


class FetchLog(Base):
    """When a given DMarket query was last fetched; drives cache freshness."""

    __tablename__ = "fetch_log"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    offers_count: Mapped[int] = mapped_column(Integer, default=0)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
