"""Dominant-colour profile of a skin image.

Skin renders show a whole gun on a transparent background, and much of it is unpainted gunmetal. So we
measure two things per hue: `coverage` (share of opaque pixels) and `dominance` (share of the *coloured*
pixels). A skin "is blue" when blue covers a visible area and is the main colour among the coloured parts.
"""
import io
from collections.abc import Iterable
from dataclasses import dataclass, field

from PIL import Image

ANALYSIS_WIDTH = 128
ALPHA_MIN = 128
SATURATION_MIN = 0.25
VALUE_MIN = 0.25

# Hue ranges in degrees; red wraps around 0.
HUES: dict[str, tuple[float, float]] = {
    "red": (345, 15),
    "orange": (15, 45),
    "yellow": (45, 70),
    "green": (70, 165),
    "cyan": (165, 200),
    "blue": (200, 255),
    "purple": (255, 290),
    "pink": (290, 345),
}
ACHROMATIC = ("black", "white", "gray")


def _hue_name(degrees: float) -> str:
    for name, (lo, hi) in HUES.items():
        if lo <= hi:
            if lo <= degrees < hi:
                return name
        elif degrees >= lo or degrees < hi:
            return name
    return "red"


@dataclass
class ColorProfile:
    coverage: dict[str, float] = field(default_factory=dict)  # share of opaque pixels, per colour
    chromatic: float = 0.0  # share of opaque pixels that are clearly coloured

    def coverage_of(self, colors: str | Iterable[str]) -> float:
        names = [colors] if isinstance(colors, str) else colors
        return sum(self.coverage.get(name, 0.0) for name in names)

    def dominance(self, colors: str | Iterable[str]) -> float:
        """Share of the coloured pixels that are `colors` (0 if the skin has no colour at all)."""
        return self.coverage_of(colors) / self.chromatic if self.chromatic else 0.0

    def matches(
        self, colors: str | Iterable[str], min_coverage: float = 0.03, min_dominance: float = 0.25
    ) -> bool:
        """Visible area of the colour AND a large part of the painted surface. `colors` may be a
        group of neighbouring hues, e.g. ("blue", "cyan")."""
        names = [colors] if isinstance(colors, str) else list(colors)
        return self.coverage_of(names) >= min_coverage and self.dominance(names) >= min_dominance


def analyze_image(data: bytes | Image.Image) -> ColorProfile:
    image = data if isinstance(data, Image.Image) else Image.open(io.BytesIO(data))
    image = image.convert("RGBA")
    image.thumbnail((ANALYSIS_WIDTH, ANALYSIS_WIDTH), Image.Resampling.BOX)
    hsv = image.convert("RGB").convert("HSV")
    counts: dict[str, int] = {}
    opaque = 0
    pixels = zip(hsv.get_flattened_data(), image.get_flattened_data(), strict=True)
    for (hue, sat, val), (_, _, _, alpha) in pixels:
        if alpha < ALPHA_MIN:
            continue
        opaque += 1
        s, v = sat / 255, val / 255
        if s >= SATURATION_MIN and v >= VALUE_MIN:
            name = _hue_name(hue * 360 / 255)
        elif v < VALUE_MIN:
            name = "black"
        elif s < 0.15 and v > 0.75:
            name = "white"
        else:
            name = "gray"
        counts[name] = counts.get(name, 0) + 1
    if not opaque:
        return ColorProfile()
    coverage = {name: n / opaque for name, n in counts.items()}
    chromatic = sum(share for name, share in coverage.items() if name not in ACHROMATIC)
    return ColorProfile(coverage, chromatic)
