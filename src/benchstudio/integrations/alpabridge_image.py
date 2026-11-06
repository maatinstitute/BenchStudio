"""AlpaBridge camera-frame preparation boundaries."""

from __future__ import annotations

import logging
import os
from math import ceil
from typing import Any

import numpy as np

LOGGER = logging.getLogger("alpabridge_camera_rectification")
_WARNED: set[str] = set()

_TARGET_FOCAL_LENGTH = (1545.0, 1545.0)
_TARGET_PRINCIPAL_POINT = (960.0, 560.0)
_TARGET_RESOLUTION_HW = (1080, 1920)
_TARGET_RADIAL = (-0.356123, 0.172545, -0.05231, 0.0, 0.0, 0.0)
_TARGET_TANGENTIAL = (-0.00213, 0.000464)
_TARGET_THIN_PRISM = (0.0, 0.0, 0.0, 0.0)


def resize_and_center_crop(image: np.ndarray, target_height: int, target_width: int) -> np.ndarray:
    """Resize to cover a target shape and center-crop to exact dimensions."""
    height, width = image.shape[:2]
    if height == target_height and width == target_width:
        return image
    from PIL import Image as PILImage

    scale = max(target_height / height, target_width / width)
    new_height, new_width = ceil(height * scale), ceil(width * scale)
    pil_image = PILImage.fromarray(image).resize(
        (new_width, new_height), PILImage.Resampling.BILINEAR
    )
    if new_height < target_height or new_width < target_width:
        raise ValueError(
            f"image {new_width}x{new_height} too small after resize, "
            f"need {target_width}x{target_height}"
        )
    top, left = (new_height - target_height) // 2, (new_width - target_width) // 2
    return np.array(pil_image.crop((left, top, left + target_width, top + target_height)))


def _warn_once(key: str, message: str) -> None:
    if key not in _WARNED:
        _WARNED.add(key)
        LOGGER.warning(message)


def rectification_disabled() -> bool:
    """Return whether the operator opted out of optional rectification."""
    raw = os.environ.get("ALPABRIDGE_DISABLE_RECTIFICATION", "0").strip().lower()
    return raw in {"1", "true", "yes"}


def default_target_config() -> Any:
    """Build the reference pinhole target, or return None if unavailable."""
    try:
        from alpabridge.third_party.alpasim_rectification import RectificationTargetConfig
    except ImportError as exc:
        _warn_once(
            "rectification-unavailable",
            "Camera rectification is unavailable, so f-theta frames reach policies "
            f"as rendered: {exc}. Install the optional rectification runtime.",
        )
        return None
    return RectificationTargetConfig(
        focal_length=_TARGET_FOCAL_LENGTH,
        principal_point=_TARGET_PRINCIPAL_POINT,
        resolution_hw=_TARGET_RESOLUTION_HW,
        radial=_TARGET_RADIAL,
        tangential=_TARGET_TANGENTIAL,
        thin_prism=_TARGET_THIN_PRISM,
    )


def build_rectifier(camera_proto: Any, source_hw: tuple[int, int]) -> Any | None:
    """Build an optional rectifier, falling back without failing a rollout."""
    if camera_proto is None:
        return None
    target = default_target_config()
    if target is None:
        return None
    try:
        from alpabridge.third_party.alpasim_rectification import (
            build_ftheta_rectifier_for_resolution,
        )

        return build_ftheta_rectifier_for_resolution(camera_proto, target, source_hw)
    except Exception as exc:  # noqa: BLE001 - optional boundary is fail-soft
        _warn_once(
            f"rectifier-build-failed-{source_hw}",
            f"Could not build a rectifier for {source_hw[1]}x{source_hw[0]} frame; "
            f"passing it through unrectified: {exc!r}",
        )
        return None


def rectify_image(rectifier: Any, image: np.ndarray) -> np.ndarray:
    """Apply a rectifier, returning the original image on transform failure."""
    if rectifier is None:
        return image
    try:
        return np.asarray(rectifier.rectify(image))
    except Exception as exc:  # noqa: BLE001 - optional boundary is fail-soft
        _warn_once(
            "rectify-failed",
            f"Rectifying a camera frame failed; using it as rendered: {exc!r}",
        )
        return image
