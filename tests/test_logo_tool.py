"""Unit tests for image conversion, firmware patching, and FW-NEW generation.

Uses a synthetic 2 MB firmware blob — no real firmware dump needed.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from PIL import Image

# Ensure the package is importable from the repo root.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmr171_logo.constants import (
    APP_OFFSET,
    APPLICATION_ADDRESS,
    DEFAULT_IMAGE_SECTOR,
    FLASH_BASE,
    FLASH_SIZE,
    HEADER_SIZE,
    LITPOOL_OFFSET,
    PMETHODS_16BPP,
    SCREEN_H,
    SCREEN_W,
    SECTOR_SIZE,
)
from pmr171_logo.image_convert import (
    image_to_bgr565_le,
    load_and_prepare,
    rgb_to_bgr565,
)
from pmr171_logo.firmware_patch import (
    apply_patches,
    build_bitmap_header,
    check_sector_erased,
    plan_patches,
)
from pmr171_logo.fw_new import make_fw_new


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_synthetic_firmware() -> bytearray:
    """Create a minimal valid 2 MB firmware for testing.

    - Bank 1 @ 0x00000: bootloader stub (mostly 0xFF)
    - Bank 2 @ 0x20000: valid vector table + some code bytes
    - Sectors 10-13: erased (0xFF)
    """
    fw = bytearray(b"\xFF" * FLASH_SIZE)

    # Bank 1 vector table (bootloader).
    struct.pack_into("<II", fw, 0, 0x2001FFF8, 0x08000101)

    # Bank 2 vector table (application).
    struct.pack_into("<II", fw, APP_OFFSET, 0x2407FFF8, 0x08030001)

    # Some non-0xFF code bytes after the vector table.
    for i in range(256):
        fw[APP_OFFSET + 8 + i] = i & 0xFF

    # Fake literal pool value at the real litpool offset.
    struct.pack_into("<I", fw, LITPOOL_OFFSET, 0x08108CC8)

    # Fake coordinate bytes at case 6 offsets.
    fw[0x0009_0584] = 50   # Y
    fw[0x0009_0586] = 110  # X

    return fw


# ---------------------------------------------------------------------------
# Image conversion tests
# ---------------------------------------------------------------------------
class TestImageConversion:

    def test_rgb_to_bgr565_white(self):
        assert rgb_to_bgr565(255, 255, 255) == 0xFFFF

    def test_rgb_to_bgr565_black(self):
        assert rgb_to_bgr565(0, 0, 0) == 0x0000

    def test_rgb_to_bgr565_pure_red(self):
        # Red (255, 0, 0) → BGR565: B=0, G=0, R=31 → 0x001F
        assert rgb_to_bgr565(255, 0, 0) == 0x001F

    def test_rgb_to_bgr565_pure_blue(self):
        # Blue (0, 0, 255) → BGR565: B=31, G=0, R=0 → 0xF800
        assert rgb_to_bgr565(0, 0, 255) == 0xF800

    def test_image_to_bgr565_le_size(self):
        img = Image.new("RGB", (4, 3), (128, 64, 32))
        data = image_to_bgr565_le(img)
        assert len(data) == 4 * 3 * 2  # 24 bytes

    def test_image_to_bgr565_le_white_pixels(self):
        img = Image.new("RGB", (2, 2), (255, 255, 255))
        data = image_to_bgr565_le(img)
        # Every pixel should be 0xFFFF LE → b"\xFF\xFF"
        assert data == b"\xFF\xFF" * 4


class TestLoadAndPrepare:

    def test_fit_produces_correct_size(self, tmp_path):
        img = Image.new("RGB", (640, 480), (100, 100, 100))
        img.save(tmp_path / "test.png")
        result = load_and_prepare(str(tmp_path / "test.png"), "fit")
        assert result.size == (SCREEN_W, SCREEN_H)

    def test_fill_produces_correct_size(self, tmp_path):
        img = Image.new("RGB", (800, 200), (50, 50, 50))
        img.save(tmp_path / "test.png")
        result = load_and_prepare(str(tmp_path / "test.png"), "fill")
        assert result.size == (SCREEN_W, SCREEN_H)

    def test_stretch_produces_correct_size(self, tmp_path):
        img = Image.new("RGB", (100, 100), (0, 0, 0))
        img.save(tmp_path / "test.png")
        result = load_and_prepare(str(tmp_path / "test.png"), "stretch")
        assert result.size == (SCREEN_W, SCREEN_H)

    def test_none_rejects_oversize(self, tmp_path):
        img = Image.new("RGB", (400, 300))
        img.save(tmp_path / "test.png")
        with pytest.raises(ValueError, match="exceeds"):
            load_and_prepare(str(tmp_path / "test.png"), "none")

    def test_rgba_composited(self, tmp_path):
        # Semi-transparent red on white background → pinkish.
        img = Image.new("RGBA", (SCREEN_W, SCREEN_H), (255, 0, 0, 128))
        img.save(tmp_path / "test.png")
        result = load_and_prepare(
            str(tmp_path / "test.png"), "none", bg_rgb=(255, 255, 255)
        )
        assert result.mode == "RGB"
        # Centre pixel should be a blend of red + white.
        r, g, b = result.getpixel((160, 120))
        assert r > 200  # still mostly red-ish
        assert g > 50   # has some white blended in


# ---------------------------------------------------------------------------
# Firmware patching tests
# ---------------------------------------------------------------------------
class TestBitmapHeader:

    def test_header_size(self):
        hdr = build_bitmap_header(320, 240, 0x08140014)
        assert len(hdr) == HEADER_SIZE

    def test_header_fields(self):
        hdr = build_bitmap_header(320, 240, 0x08140014)
        xs, ys, bpl, bpp, pdata, ppal, pmeth = struct.unpack(
            "<HHHHIII", hdr
        )
        assert xs == 320
        assert ys == 240
        assert bpl == 640  # 320 * 2
        assert bpp == 16
        assert pdata == 0x08140014
        assert ppal == 0
        assert pmeth == PMETHODS_16BPP


class TestPatchPlanning:

    def test_basic_patch_list(self):
        fw = _make_synthetic_firmware()
        pixels = b"\xFF\xFF" * (100 * 100)
        patches = plan_patches(fw, pixels, 100, 100)
        # At minimum: image data, litpool, Y coord, X coord
        assert len(patches) >= 4

    def test_litpool_patch_value(self):
        fw = _make_synthetic_firmware()
        pixels = b"\x00\x00" * (100 * 100)
        patches = plan_patches(fw, pixels, 100, 100, sector=10)
        litpool_patch = [p for p in patches if p.offset == LITPOOL_OFFSET]
        assert len(litpool_patch) == 1
        new_ptr = struct.unpack("<I", litpool_patch[0].data)[0]
        assert new_ptr == FLASH_BASE + 10 * SECTOR_SIZE

    def test_coordinate_centering(self):
        fw = _make_synthetic_firmware()
        pixels = b"\x00\x00" * (100 * 80)
        patches = plan_patches(fw, pixels, 100, 80)
        # Expected: cx = (320-100)//2 = 110, cy = (240-80)//2 = 80
        y_patch = [p for p in patches if p.offset == 0x0009_0584]
        x_patch = [p for p in patches if p.offset == 0x0009_0586]
        assert len(y_patch) == 1
        assert y_patch[0].data == bytes([80])
        assert len(x_patch) == 1
        assert x_patch[0].data == bytes([110])

    def test_full_screen_coords_zero(self):
        fw = _make_synthetic_firmware()
        pixels = b"\x00\x00" * (SCREEN_W * SCREEN_H)
        patches = plan_patches(fw, pixels, SCREEN_W, SCREEN_H)
        y_patch = [p for p in patches if p.offset == 0x0009_0584][0]
        x_patch = [p for p in patches if p.offset == 0x0009_0586][0]
        assert y_patch.data == bytes([0])
        assert x_patch.data == bytes([0])


class TestSectorCheck:

    def test_erased_sector_no_warnings(self):
        fw = bytearray(b"\xFF" * FLASH_SIZE)
        warnings = check_sector_erased(fw, 10, 100_000)
        assert warnings == []

    def test_non_erased_sector_warns(self):
        fw = bytearray(b"\xFF" * FLASH_SIZE)
        fw[10 * SECTOR_SIZE] = 0x42  # dirty byte
        warnings = check_sector_erased(fw, 10, 100_000)
        assert len(warnings) == 1
        assert "non-0xFF" in warnings[0]


class TestApplyPatches:

    def test_patches_modify_firmware(self):
        fw = _make_synthetic_firmware()
        original_litpool = struct.unpack_from("<I", fw, LITPOOL_OFFSET)[0]
        pixels = b"\x00\x00" * (10 * 10)
        patches = plan_patches(fw, pixels, 10, 10)
        apply_patches(fw, patches)
        new_litpool = struct.unpack_from("<I", fw, LITPOOL_OFFSET)[0]
        assert new_litpool != original_litpool


# ---------------------------------------------------------------------------
# FW-NEW generation tests
# ---------------------------------------------------------------------------
class TestMakeFwNew:

    def test_basic_generation(self):
        fw = _make_synthetic_firmware()
        result = make_fw_new(bytes(fw))
        # Should start with the Bank 2 vector table.
        sp, reset = struct.unpack_from("<II", result.data, 0)
        assert sp == 0x2407FFF8
        assert reset == 0x08030001

    def test_trailing_ff_stripped(self):
        fw = _make_synthetic_firmware()
        result = make_fw_new(bytes(fw))
        # The last byte should NOT be 0xFF.
        assert result.data[-1] != 0xFF

    def test_size_under_limit(self):
        fw = _make_synthetic_firmware()
        result = make_fw_new(bytes(fw))
        assert len(result.size_warnings) == 0

    def test_wrong_size_raises(self):
        with pytest.raises(ValueError, match="2 MB"):
            make_fw_new(b"\xFF" * 1024)

    def test_bad_vector_table_raises(self):
        fw = bytearray(b"\xFF" * FLASH_SIZE)
        # No valid vector table at Bank 2.
        with pytest.raises(ValueError, match="Invalid"):
            make_fw_new(bytes(fw))

    def test_config_excluded_by_default(self):
        fw = _make_synthetic_firmware()
        # Put data in the config region (0x1C0000 from flash base =
        # 0x1A0000 from Bank 2 start).
        config_off = 0x1C0000
        fw[config_off] = 0x42
        fw[config_off + 1] = 0x43
        result_no_config = make_fw_new(bytes(fw), include_config=False)
        result_with_config = make_fw_new(bytes(fw), include_config=True)
        # With config excluded, the output should be smaller.
        assert len(result_no_config.data) < len(result_with_config.data)


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------
class TestEndToEnd:
    """Full pipeline: image → patches → FW-NEW.bin."""

    def test_full_pipeline(self, tmp_path):
        # Create a test image.
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 128, 255))
        img_path = tmp_path / "test_logo.png"
        img.save(img_path)

        # Prepare image for LCD.
        prepared = load_and_prepare(str(img_path), "fit")
        assert prepared.size == (SCREEN_W, SCREEN_H)

        # Convert to BGR565.
        pixel_data = image_to_bgr565_le(prepared)
        assert len(pixel_data) == SCREEN_W * SCREEN_H * 2

        # Build synthetic firmware and apply patches.
        fw = _make_synthetic_firmware()
        patches = plan_patches(
            fw, pixel_data, SCREEN_W, SCREEN_H,
            remove_all_text=True,
        )
        apply_patches(fw, patches)

        # Verify header was written.
        sector_off = DEFAULT_IMAGE_SECTOR * SECTOR_SIZE
        xs = struct.unpack_from("<H", fw, sector_off)[0]
        assert xs == SCREEN_W

        # Generate FW-NEW.bin.
        result = make_fw_new(bytes(fw))
        assert len(result.data) > 0
        assert result.data[-1] != 0xFF
        assert len(result.size_warnings) == 0

        # Write and verify file.
        out = tmp_path / "FW-NEW.bin"
        result.write(out)
        assert out.exists()
        assert out.stat().st_size == len(result.data)
