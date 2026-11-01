"""Pure function: does an offer satisfy a rule, and why."""
from dataclasses import dataclass, field

from app.dmarket.schemas import Offer, normalize_enum
from app.rules.schema import Rule


@dataclass
class MatchResult:
    matched: bool
    reasons: list[str] = field(default_factory=list)
    failed: str | None = None


def _fail(reason: str) -> MatchResult:
    return MatchResult(False, failed=reason)


def match(offer: Offer, rule: Rule) -> MatchResult:
    """All filters that are set must pass (AND). Unset filters are ignored."""
    s, loc = rule.server, rule.local
    reasons: list[str] = []

    if s.title:
        if offer.title.casefold() != s.title.casefold():
            return _fail("title")
        reasons.append(f"title {offer.title}")
    if s.price_from_cents is not None and offer.price_cents < s.price_from_cents:
        return _fail("price below minimum")
    if s.price_to_cents is not None:
        if offer.price_cents > s.price_to_cents:
            return _fail("price above maximum")
        reasons.append(f"price ${offer.price_cents / 100:.2f} <= ${s.price_to_cents / 100:.2f}")
    if s.paint_seeds:
        if offer.paint_seed not in s.paint_seeds:
            return _fail("paint seed")
        reasons.append(f"seed {offer.paint_seed}")

    if loc.float_min is not None or loc.float_max is not None:
        if offer.float_value is None:
            return _fail("no float")
        if loc.float_min is not None and offer.float_value < loc.float_min:
            return _fail("float below minimum")
        if loc.float_max is not None and offer.float_value > loc.float_max:
            return _fail("float above maximum")
        reasons.append(f"float {offer.float_value:.4f}")
    if loc.exterior and offer.exterior not in {normalize_enum(e) for e in loc.exterior}:
        return _fail("exterior")
    if loc.min_discount_percent is not None:
        if offer.discount_percent < loc.min_discount_percent:
            return _fail("discount")
        reasons.append(f"discount {offer.discount_percent:g}%")
    if loc.colors and not set(offer.colors) & {normalize_enum(c) for c in loc.colors}:
        return _fail("colors")
    if loc.phase and offer.phase.casefold() not in {p.casefold() for p in loc.phase}:
        return _fail("phase")
    if loc.rare_pattern and offer.rare_pattern not in {normalize_enum(r) for r in loc.rare_pattern}:
        return _fail("rare pattern")
    if loc.sticker_names:
        found = [
            name
            for name in offer.sticker_names
            if any(wanted.casefold() in name.casefold() for wanted in loc.sticker_names)
        ]
        if not found:
            return _fail("stickers")
        reasons.append(f"stickers {', '.join(found)}")
    if loc.stattrak is not None and offer.is_stattrak != loc.stattrak:
        return _fail("stattrak")

    return MatchResult(True, reasons)
