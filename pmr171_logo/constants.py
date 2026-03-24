"""Hardware and firmware constants for the PMR-171 boot logo patcher."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# STM32H743 flash layout
# ---------------------------------------------------------------------------
FLASH_BASE = 0x0800_0000
FLASH_SIZE = 0x0020_0000  # 2 MB total
SECTOR_SIZE = 0x0002_0000  # 128 KB per sector (STM32H7)

# Bank 2 application region — bootloader lives in Bank 1 (first 128 KB).
APPLICATION_ADDRESS = 0x0802_0000
APP_OFFSET = APPLICATION_ADDRESS - FLASH_BASE  # 0x20000

# Config/calibration region written at runtime.  Excluding it from a
# firmware update preserves user settings (channels, calibration, etc.).
CONFIG_FLASH_ADDR = 0x081C_0000
CONFIG_OFFSET_FROM_APP = CONFIG_FLASH_ADDR - APPLICATION_ADDRESS  # 0x1A0000

# ---------------------------------------------------------------------------
# LCD / display
# ---------------------------------------------------------------------------
SCREEN_W = 320
SCREEN_H = 240

# ---------------------------------------------------------------------------
# emWin GUI_BITMAP
# ---------------------------------------------------------------------------
# 20-byte header: xSize(u16), ySize(u16), BytesPerLine(u16),
#                 BitsPerPixel(u16), pData(u32), pPal(u32), pMethods(u32)
HEADER_SIZE = 20

# pMethods vtable pointer for 16 bpp streaming bitmap renderer.
# Points to the draw-method table used by the stock firmware's emWin build.
PMETHODS_16BPP = 0x0811_4408

# ---------------------------------------------------------------------------
# Patch points (offsets from FLASH_BASE)
#
# These are firmware-version-specific.  Determined by reverse engineering
# the stock v3.7.2 firmware (Splash_Screen / Display_ModelName function).
# ---------------------------------------------------------------------------

# Literal pool entry holding the pointer to the current Logo #1
# GUI_BITMAP header.  Shared by switch cases 0, 3, 4, 6, 7.
LITPOOL_OFFSET = 0x0009_05B0

# Draw-coordinate Thumb ``movs Rd, #imm8`` instructions per model case.
# Tuple: (y_offset, x_offset, label)
CASE_COORDS: dict[int, tuple[int, int, str]] = {
    0: (0x0009_04E8, 0x0009_04EA, "Q900"),
    3: (0x0009_054C, 0x0009_054E, "TBR-119"),
    4: (0x0009_0562, 0x0009_0564, "PMR-119"),
    6: (0x0009_0584, 0x0009_0586, "PMR-171"),
    7: (0x0009_059A, 0x0009_059C, "XP-100"),
}

# Case 6 (PMR-171) model-name text draw: ``bl GUI_DrawString``
CASE6_MODEL_BL_OFFSET = 0x0009_0594

# Shared version-string text draw: ``bl GUI_DrawString`` (ALL models).
SHARED_VERSION_BL_OFFSET = 0x0009_0518

# Two 16-bit Thumb NOPs — replaces a 32-bit BL instruction.
NOP_NOP = b"\x00\xBF\x00\xBF"

# Default flash sector for new image data (sector 10 = 0x08140000).
# Sectors 10-13 are typically erased in the stock firmware.
DEFAULT_IMAGE_SECTOR = 10

# ---------------------------------------------------------------------------
# UHSDR bootloader size limits
# ---------------------------------------------------------------------------
# flashIf_userFlashSize() = (STM32_GetFlashSize() - FLASHRESERVED) * 1024
# The stock PMR-171 bootloader uses FLASHRESERVED = 128 KB.
FLASHRESERVED_OPTIONS: dict[int, int] = {
    128: (2048 - 128) * 1024,  # 1,966,080  — PMR-171 actual
    256: (2048 - 256) * 1024,  # 1,835,008
    384: (2048 - 384) * 1024,  # 1,703,936  — UHSDR H7 default
}

# SRAM regions (for vector table validation)
SRAM_RANGES: list[tuple[int, int]] = [
    (0x0000_0000, 0x0001_0000),  # ITCM
    (0x2000_0000, 0x2002_0000),  # DTCM
    (0x2400_0000, 0x2408_0000),  # AXI SRAM
    (0x3000_0000, 0x3004_8000),  # SRAM1-3
    (0x3800_0000, 0x3801_0000),  # SRAM4
]
