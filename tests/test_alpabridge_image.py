from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from benchstudio.integrations import (
    build_rectifier,
    default_target_config,
    rectification_disabled,
    rectify_image,
    resize_and_center_crop,
)


@pytest.mark.parametrize("shape", [(320, 568), (300, 800), (1000, 1600)])
def test_resize_and_center_crop_covers_all_aspect_ratios(shape):
    pytest.importorskip("PIL")
    image = np.random.default_rng(0).integers(0, 256, size=(*shape, 3), dtype=np.uint8)
    result = resize_and_center_crop(image, 900, 1600)
    assert result.shape == (900, 1600, 3)


def test_resize_and_center_crop_is_noop_at_exact_size():
    image = np.zeros((900, 1600, 3), dtype=np.uint8)
    assert resize_and_center_crop(image, 900, 1600) is image


@pytest.mark.parametrize("raw", ["1", "true", "YES"])
def test_rectification_can_be_disabled(raw, monkeypatch):
    monkeypatch.setenv("ALPABRIDGE_DISABLE_RECTIFICATION", raw)
    assert rectification_disabled() is True


@pytest.mark.parametrize("raw", ["0", "", "no", "off"])
def test_rectification_is_enabled_by_default(raw, monkeypatch):
    monkeypatch.setenv("ALPABRIDGE_DISABLE_RECTIFICATION", raw)
    assert rectification_disabled() is False


def test_missing_or_unavailable_rectifier_falls_back(caplog):
    assert build_rectifier(None, (1080, 1920)) is None
    with patch(__name__ + ".default_target_config", return_value=None):
        assert build_rectifier(object(), (1080, 1920)) is None
    image = np.zeros((4, 6, 3), dtype=np.uint8)
    assert rectify_image(None, image) is image


def test_reference_target_and_build_failure_are_fail_soft(monkeypatch, caplog):
    module = SimpleNamespace(
        RectificationTargetConfig=lambda **kwargs: SimpleNamespace(**kwargs),
        build_ftheta_rectifier_for_resolution=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("no polynomial")
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules, "alpabridge.third_party.alpasim_rectification", module
    )
    target = default_target_config()
    assert target.focal_length == (1545.0, 1545.0)
    with caplog.at_level("WARNING"):
        assert build_rectifier(object(), (1080, 1920)) is None
    assert any("unrectified" in record.getMessage() for record in caplog.records)


def test_rectifier_output_and_failure_fallback(caplog):
    image = np.zeros((4, 6, 3), dtype=np.uint8)
    rectified = np.ones((8, 8, 3), dtype=np.uint8)
    assert np.array_equal(
        rectify_image(SimpleNamespace(rectify=lambda _: rectified), image), rectified
    )
    with caplog.at_level("WARNING"):
        assert (
            rectify_image(
                SimpleNamespace(rectify=lambda _: (_ for _ in ()).throw(ValueError("bad"))), image
            )
            is image
        )
    assert any("as rendered" in record.getMessage() for record in caplog.records)
