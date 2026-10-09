"""Derived numerical contracts; no arbitrary coordinate or design-range caps."""
import math


def finite(description, *values):
    if any(not math.isfinite(value) for value in values):
        raise ValueError(f"{description} must remain finite after calculation")


def midpoint(a, b):
    # Halving first also works when two same-sign finite endpoints would overflow.
    return a / 2 + b / 2


def bounded_count(span, spacing, limit, description):
    finite(description, span, spacing)
    if spacing <= 0:
        raise ValueError(f"{description} requires positive spacing")
    ratio = max(0, span) / spacing
    if not math.isfinite(ratio) or ratio > limit:
        raise ValueError(f"{description} exceeds the {limit} member generation budget")
    return math.ceil(ratio)


def advance(position, spacing, description):
    next_position = position + spacing
    finite(description, next_position)
    if next_position <= position:
        raise ValueError(f"{description} cannot advance at this coordinate precision")
    return next_position
