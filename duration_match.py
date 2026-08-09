#!/usr/bin/env python3
"""Exact timing plans for model-native video frame grids.

The model renders a legal number of frames.  Delivery then removes whole
trailing frames and, when a ledger duration is not frame-aligned, applies a
final container/timestamp trim smaller than one frame.  This distinction is
intentional: ``trim_frames`` alone cannot make values such as 12.72 seconds
exact at 24 fps.

All model-grid arithmetic is represented with :class:`fractions.Fraction`.
Ledger-facing ``target_seconds`` and ``delivered_s`` remain exact
:class:`decimal.Decimal` values.  Floats are accepted for convenience but are
interpreted through ``str(value)``; callers loading JSON should prefer
``json.load(..., parse_float=Decimal)`` to preserve the source decimal text.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Final


class DurationMatchError(ValueError):
    """Base class for invalid or unrepresentable duration requests."""


class InvalidDurationError(DurationMatchError):
    """The requested duration is not a finite, positive decimal value."""


class UnrepresentableDurationError(DurationMatchError):
    """Strict whole-frame delivery cannot represent the requested duration."""


_GRIDS: Final[dict[str, tuple[int, int, int]]] = {
    # mode: (frames-per-second, grid step, grid offset)
    "h3": (24, 17, 5),
    "ltx": (25, 8, 1),
}


def _as_decimal(value: object) -> Decimal:
    """Normalize a user/ledger value without introducing binary-float noise."""
    if isinstance(value, bool):
        raise InvalidDurationError("target_seconds must be numeric, not bool")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, Fraction):
        denominator = value.denominator
        remainder = denominator
        while remainder % 2 == 0:
            remainder //= 2
        while remainder % 5 == 0:
            remainder //= 5
        if remainder != 1:
            raise InvalidDurationError(
                "target_seconds Fraction must have a finite decimal expansion"
            )
        result = Decimal(value.numerator) / Decimal(denominator)
    elif isinstance(value, (int, float, str)):
        try:
            result = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise InvalidDurationError(
                f"target_seconds is not a decimal number: {value!r}"
            ) from exc
    else:
        raise InvalidDurationError(
            f"target_seconds has unsupported type {type(value).__name__}"
        )

    if not result.is_finite() or result <= 0:
        raise InvalidDurationError("target_seconds must be finite and greater than zero")
    return result


def _ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def duration_match(
    target_seconds: object,
    mode: str = "h3",
    *,
    strict_frame_aligned: bool = False,
) -> dict[str, object]:
    """Return an exact render-and-delivery timing plan.

    ``h3`` uses the ``17k+5`` frame grid at 24 fps; ``ltx`` uses ``8n+1``
    at 25 fps.  ``frame_count`` is the smallest legal model render that covers
    the requested endpoint.  ``trim_frames`` is the number of complete trailing
    frames removed.  ``tail_trim_s`` is the remaining timestamp/container trim
    and is always in ``[0, 1/fps)``.

    The returned ``delivered_s`` is the exact Decimal target.  A delivery
    pipeline must enforce that timestamp endpoint and verify the encoded result
    with ffprobe.  ``delivery_quantization_error_s`` therefore describes the
    timing plan (zero), not an unverified encoded artifact.

    Set ``strict_frame_aligned=True`` when the delivery mechanism can remove
    only whole frames.  Non-frame-aligned targets then raise
    :class:`UnrepresentableDurationError` instead of silently rounding.
    """
    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in _GRIDS:
        choices = ", ".join(sorted(_GRIDS))
        raise DurationMatchError(f"unknown mode {mode!r}; expected one of: {choices}")

    target = _as_decimal(target_seconds)
    target_fraction = Fraction(target)
    fps, step, offset = _GRIDS[normalized_mode]
    target_frame_position = target_fraction * fps

    if strict_frame_aligned and target_frame_position.denominator != 1:
        raise UnrepresentableDurationError(
            f"{target} seconds is not whole-frame aligned at {fps} fps"
        )

    covered_frames = _ceil_fraction(target_frame_position)
    if covered_frames <= offset:
        frame_count = offset
    else:
        grid_index = _ceil_fraction(Fraction(covered_frames - offset, step))
        frame_count = offset + step * grid_index

    trim_frames = frame_count - covered_frames
    rendered_s = Fraction(frame_count, fps)
    whole_frame_delivery_s = Fraction(covered_frames, fps)
    tail_trim_s = whole_frame_delivery_s - target_fraction

    if trim_frames < 0:  # Defensive invariant; should be impossible by construction.
        raise AssertionError("duration planner selected fewer than the required frames")
    if not (Fraction(0) <= tail_trim_s < Fraction(1, fps)):
        raise AssertionError("duration planner tail trim escaped the one-frame bound")

    return {
        "target_seconds": target,
        "frame_count": frame_count,
        "trim_frames": trim_frames,
        "rendered_s": rendered_s,
        "delivered_s": target,
        "tail_trim_s": tail_trim_s,
        "delivery_quantization_error_s": Decimal("0"),
    }


__all__ = [
    "DurationMatchError",
    "InvalidDurationError",
    "UnrepresentableDurationError",
    "duration_match",
]
