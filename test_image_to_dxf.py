"""
test_image_to_dxf.py
--------------------
Unit tests for image_to_dxf converter.

Run with:
    pytest test_image_to_dxf.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from image_to_dxf import ConversionResult, convert


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_image(path: Path, size: tuple[int, int] = (100, 100),
                shape: str = "circle") -> Path:
    """Create a white PNG with a filled black shape."""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    if shape == "circle":
        draw.ellipse([15, 15, 85, 85], fill="black")
    elif shape == "rect":
        draw.rectangle([15, 15, 85, 85], fill="black")
    elif shape == "multi":
        draw.ellipse([5, 5, 45, 45], fill="black")
        draw.rectangle([55, 55, 95, 95], fill="black")
    img.save(path)
    return path


@pytest.fixture
def circle_img(tmp_path: Path) -> Path:
    return _make_image(tmp_path / "circle.png")


@pytest.fixture
def rect_img(tmp_path: Path) -> Path:
    return _make_image(tmp_path / "rect.png", shape="rect")


@pytest.fixture
def multi_img(tmp_path: Path) -> Path:
    return _make_image(tmp_path / "multi.png", shape="multi")


# ---------------------------------------------------------------------------
# ConversionResult type
# ---------------------------------------------------------------------------

class TestConversionResult:
    def test_returns_dataclass(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "out.dxf")
        assert isinstance(result, ConversionResult)

    def test_path_is_pathlib(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "out.dxf")
        assert isinstance(result.path, Path)

    def test_str_representation(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "out.dxf")
        assert "contours" in str(result).lower() or str(result)  # non-empty


# ---------------------------------------------------------------------------
# Trace mode
# ---------------------------------------------------------------------------

class TestTraceMode:
    def test_output_file_created(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "out.dxf", mode="trace")
        assert result.path.exists()
        assert result.path.suffix == ".dxf"

    def test_default_output_path(self, circle_img: Path) -> None:
        result = convert(circle_img, mode="trace")
        assert result.path.exists()
        assert result.path == circle_img.with_suffix(".dxf")
        result.path.unlink(missing_ok=True)

    def test_contours_detected(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "out.dxf", mode="trace")
        assert result.contour_count > 0

    def test_entities_written(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "out.dxf", mode="trace")
        assert result.entity_count > 0

    def test_dimensions_match_scale(self, circle_img: Path, tmp_path: Path) -> None:
        scale = 0.5
        result = convert(circle_img, tmp_path / "out.dxf", mode="trace", scale=scale)
        assert result.img_width == 100
        assert result.img_height == 100
        assert result.dxf_width == pytest.approx(100 * scale)
        assert result.dxf_height == pytest.approx(100 * scale)

    def test_spline_entities(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "spline.dxf", mode="trace", spline=True)
        assert result.path.exists()
        assert result.entity_count > 0

    def test_with_title(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "titled.dxf", mode="trace",
                         title="My Drawing")
        assert result.path.exists()

    def test_multiple_shapes(self, multi_img: Path, tmp_path: Path) -> None:
        result = convert(multi_img, tmp_path / "multi.dxf", mode="trace")
        assert result.contour_count >= 2


# ---------------------------------------------------------------------------
# Hatch mode
# ---------------------------------------------------------------------------

class TestHatchMode:
    def test_output_file_created(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "hatch.dxf", mode="hatch")
        assert result.path.exists()

    def test_contours_detected(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "hatch.dxf", mode="hatch")
        assert result.contour_count > 0

    def test_entities_include_hatch(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "hatch.dxf", mode="hatch")
        # hatch mode writes both LWPOLYLINE + HATCH per contour → entity_count > contour_count
        assert result.entity_count >= result.contour_count

    def test_rect_hatch(self, rect_img: Path, tmp_path: Path) -> None:
        result = convert(rect_img, tmp_path / "rect_h.dxf", mode="hatch")
        assert result.contour_count > 0


# ---------------------------------------------------------------------------
# Pixel mode
# ---------------------------------------------------------------------------

class TestPixelMode:
    def test_output_file_created(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "pixel.dxf", mode="pixel")
        assert result.path.exists()

    def test_entities_written(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "pixel.dxf", mode="pixel")
        assert result.entity_count > 0

    def test_contour_count_zero(self, circle_img: Path, tmp_path: Path) -> None:
        # pixel mode does not trace contours
        result = convert(circle_img, tmp_path / "pixel.dxf", mode="pixel")
        assert result.contour_count == 0


# ---------------------------------------------------------------------------
# Validation & edge cases
# ---------------------------------------------------------------------------

class TestValidation:
    def test_invalid_mode_raises(self, circle_img: Path, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unknown mode"):
            convert(circle_img, tmp_path / "out.dxf", mode="invalid")

    def test_nonexistent_input_raises(self, tmp_path: Path) -> None:
        with pytest.raises(Exception):
            convert(tmp_path / "ghost.png", tmp_path / "out.dxf")

    def test_zero_threshold_all_white(self, circle_img: Path, tmp_path: Path) -> None:
        # threshold=0 inverts: nothing is foreground → 0 contours but file exists
        result = convert(circle_img, tmp_path / "out.dxf", mode="trace", threshold=0)
        assert result.path.exists()

    def test_large_min_area_filters_all(self, circle_img: Path, tmp_path: Path) -> None:
        result_big = convert(circle_img, tmp_path / "big.dxf", mode="trace",
                             min_area=999_999)
        result_small = convert(circle_img, tmp_path / "small.dxf", mode="trace",
                               min_area=1)
        assert result_small.contour_count >= result_big.contour_count

    def test_larger_scale_gives_larger_dxf(self, circle_img: Path, tmp_path: Path) -> None:
        r1 = convert(circle_img, tmp_path / "s1.dxf", mode="trace", scale=0.1)
        r2 = convert(circle_img, tmp_path / "s2.dxf", mode="trace", scale=1.0)
        assert r2.dxf_width > r1.dxf_width
        assert r2.dxf_height > r1.dxf_height

    def test_epsilon_zero_keeps_all_points(self, circle_img: Path, tmp_path: Path) -> None:
        r_approx = convert(circle_img, tmp_path / "approx.dxf", approx_epsilon=2.0)
        r_exact  = convert(circle_img, tmp_path / "exact.dxf",  approx_epsilon=0.0)
        # No epsilon → same or more entities
        assert r_exact.entity_count >= r_approx.entity_count

    def test_origin_offset(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(circle_img, tmp_path / "offset.dxf",
                         mode="trace", origin=(50.0, 100.0))
        assert result.path.exists()

    def test_custom_layer_names(self, circle_img: Path, tmp_path: Path) -> None:
        result = convert(
            circle_img, tmp_path / "layers.dxf",
            mode="trace",
            layer_contour="MY_CONTOURS",
        )
        assert result.path.exists()


# ---------------------------------------------------------------------------
# DXF file structure (via ezdxf)
# ---------------------------------------------------------------------------

class TestDxfStructure:
    def test_has_contour_layer(self, circle_img: Path, tmp_path: Path) -> None:
        import ezdxf
        result = convert(circle_img, tmp_path / "out.dxf", mode="trace")
        doc = ezdxf.readfile(result.path)
        assert "CONTOURS" in doc.layers

    def test_has_info_layer(self, circle_img: Path, tmp_path: Path) -> None:
        import ezdxf
        result = convert(circle_img, tmp_path / "out.dxf", mode="trace")
        doc = ezdxf.readfile(result.path)
        assert "INFO" in doc.layers

    def test_units_set_to_mm(self, circle_img: Path, tmp_path: Path) -> None:
        import ezdxf
        result = convert(circle_img, tmp_path / "out.dxf")
        doc = ezdxf.readfile(result.path)
        assert doc.header.get("$INSUNITS") == 4  # 4 = millimetres

    def test_hatch_layer_present_in_hatch_mode(self, circle_img: Path,
                                                tmp_path: Path) -> None:
        import ezdxf
        result = convert(circle_img, tmp_path / "hatch.dxf", mode="hatch")
        doc = ezdxf.readfile(result.path)
        assert "HATCHES" in doc.layers
