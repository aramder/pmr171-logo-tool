"""Binary patching of PMR-171 firmware for boot logo replacement."""

from __future__ import annotations

import struct
from pathlib import Path

from .constants import (
    CASE6_MODEL_BL_OFFSET,
    CASE_COORDS,
    DEFAULT_IMAGE_SECTOR,
    FLASH_BASE,
    GUI_DRAWBITMAP_ADDR,
    HEADER_SIZE,
    NOP_NOP,
    LITPOOL_OFFSET,
    PMETHODS_16BPP,
    SCREEN_H,
    SCREEN_W,
    SECTOR_SIZE,
    SHARED_VERSION_BL_OFFSET,
    SPLASH_EPILOGUE_ADDR,
    SPLASH_STUB_OFFSET,
    SPLASH_STUB_SIZE,
)

FIRMWARE_SIZE = 2 * 1024 * 1024  # 2 MB


# ---------------------------------------------------------------------------
# emWin header
# ---------------------------------------------------------------------------
def build_bitmap_header(
    width: int,
    height: int,
    data_flash_addr: int,
    pmethods: int = PMETHODS_16BPP,
) -> bytes:
    """Build a 20-byte emWin GUI_BITMAP header for RGB565."""
    return struct.pack(
        "<HHHHIII",
        width,
        height,
        width * 2,  # BytesPerLine
        16,  # BitsPerPixel
        data_flash_addr,
        0,  # pPal (NULL for RGB565)
        pmethods,
    )


# ---------------------------------------------------------------------------
# Patch list
# ---------------------------------------------------------------------------
class Patch:
    """A single binary edit: replace bytes at *offset* in the firmware."""

    __slots__ = ("offset", "data", "desc")

    def __init__(self, offset: int, data: bytes, desc: str) -> None:
        self.offset = offset
        self.data = data
        self.desc = desc

    def __repr__(self) -> str:
        addr = FLASH_BASE + self.offset
        return f"<Patch {addr:#010x} {len(self.data):,}B {self.desc!r}>"


def plan_patches(
    fw: bytes | bytearray,
    pixel_data: bytes,
    img_w: int,
    img_h: int,
    *,
    sector: int = DEFAULT_IMAGE_SECTOR,
    patch_all_cases: bool = False,
    remove_model_text: bool = False,
    remove_all_text: bool = False,
) -> list[Patch]:
    """Build the list of patches required to install a new boot logo.

    Parameters
    ----------
    fw:
        Original 2 MB firmware binary.
    pixel_data:
        BGR565 LE pixel bytes (from ``image_to_bgr565_le``).
    img_w, img_h:
        Image dimensions in pixels.
    sector:
        Flash sector for image storage (10-13, must be erased).
    patch_all_cases:
        If True, update draw coordinates for all 5 model cases
        (Q900/TBR-119/PMR-119/PMR-171/XP-100).  Default: PMR-171 only.
    remove_model_text:
        NOP the model-name text draw (case 6 only).
    remove_all_text:
        NOP both model-name AND version-text draws.

    Returns
    -------
    List of ``Patch`` objects ready to apply.
    """
    sector_offset = sector * SECTOR_SIZE
    header_addr = FLASH_BASE + sector_offset
    data_addr = header_addr + HEADER_SIZE
    header = build_bitmap_header(img_w, img_h, data_addr)

    patches: list[Patch] = []

    # 1. Image data (header + pixels) in the target sector.
    patches.append(Patch(
        sector_offset,
        header + pixel_data,
        f"{img_w}x{img_h} BGR565 image in sector {sector}",
    ))

    # 2. Redirect the literal pool pointer to the new header.
    old_ptr = struct.unpack_from("<I", fw, LITPOOL_OFFSET)[0]
    patches.append(Patch(
        LITPOOL_OFFSET,
        struct.pack("<I", header_addr),
        f"literal pool {old_ptr:#010x} -> {header_addr:#010x}",
    ))

    # 3. Draw coordinates (centre the image on the 320x240 screen).
    cx = max(0, (SCREEN_W - img_w) // 2)
    cy = max(0, (SCREEN_H - img_h) // 2)
    if cx > 255 or cy > 255:
        raise ValueError(
            f"Centering offset ({cx}, {cy}) exceeds Thumb movs "
            f"immediate range (0-255).  Image too small?"
        )

    cases = CASE_COORDS.keys() if patch_all_cases else [6]
    for case_num in cases:
        y_off, x_off, label = CASE_COORDS[case_num]
        patches.append(Patch(
            y_off, bytes([cy]),
            f"case {case_num} ({label}) Y: {fw[y_off]} -> {cy}",
        ))
        patches.append(Patch(
            x_off, bytes([cx]),
            f"case {case_num} ({label}) X: {fw[x_off]} -> {cx}",
        ))

    # 4. NOP text overlay BL instructions.
    if remove_model_text or remove_all_text:
        patches.append(Patch(
            CASE6_MODEL_BL_OFFSET, NOP_NOP,
            "NOP case 6 model-name bl",
        ))
    if remove_all_text:
        patches.append(Patch(
            SHARED_VERSION_BL_OFFSET, NOP_NOP,
            "NOP shared version-text bl (all models)",
        ))

    return patches


# ---------------------------------------------------------------------------
# Universal stub (Approach B — bypass switch for all models)
# ---------------------------------------------------------------------------
def _encode_thumb2_bl(source: int, target: int) -> bytes:
    """Encode a Thumb-2 BL (branch with link) as 4 bytes (LE halfwords).

    Parameters
    ----------
    source : Absolute address of the BL instruction.
    target : Absolute address of the call target.
    """
    offset = target - (source + 4)
    if not (-0x100_0000 <= offset < 0x100_0000):
        raise ValueError(
            f"BL offset {offset} from {source:#x} to {target:#x} "
            f"exceeds ±16 MB range."
        )
    s = (offset >> 24) & 1
    imm10 = (offset >> 12) & 0x3FF
    i1 = (~(offset >> 23) ^ s) & 1
    i2 = (~(offset >> 22) ^ s) & 1
    imm11 = (offset >> 1) & 0x7FF
    upper = 0xF000 | (s << 10) | imm10
    lower = 0xD000 | (i1 << 13) | (i2 << 11) | imm11
    return struct.pack("<HH", upper, lower)


def build_universal_stub(bitmap_header_addr: int) -> bytes:
    """Build the 20-byte Thumb-2 stub that bypasses the switch statement.

    The stub replaces the ``cmp r0, #7`` / ``bhi`` / ``tbb`` dispatch at
    the start of the splash function body.  It unconditionally:

    1. Loads the custom bitmap header address from an inline literal.
    2. Draws it at (0, 0) via ``GUI_DrawBitmap``.
    3. Branches to the function epilogue, skipping all text rendering.

    Layout (20 bytes starting at SPLASH_STUB_OFFSET = 0x080904D8)::

        0x080904D8: ldr   r0, [pc, #12]       ; 2B — bitmap header from literal
        0x080904DA: movs  r1, #0              ; 2B — x = 0
        0x080904DC: movs  r2, #0              ; 2B — y = 0
        0x080904DE: bl    GUI_DrawBitmap      ; 4B — draw the logo
        0x080904E2: b     epilogue            ; 2B — skip text, return
        0x080904E4: nop                       ; 2B — padding
        0x080904E6: nop                       ; 2B — padding
        0x080904E8: .word bitmap_header_addr  ; 4B — inline literal
    """
    stub_addr = FLASH_BASE + SPLASH_STUB_OFFSET

    # ldr r0, [pc, #12] — T1: 0100_1_Rt(3)_imm8, Rt=0, imm8=12/4=3
    ldr_r0 = struct.pack("<H", 0x4803)

    # movs r1, #0
    movs_r1 = struct.pack("<H", 0x2100)

    # movs r2, #0
    movs_r2 = struct.pack("<H", 0x2200)

    # bl GUI_DrawBitmap (4 bytes)
    bl_draw = _encode_thumb2_bl(stub_addr + 6, GUI_DRAWBITMAP_ADDR)

    # b epilogue — offset = epilogue - (source + 4)
    b_source = stub_addr + 10  # 0x080904E2
    b_offset = SPLASH_EPILOGUE_ADDR - (b_source + 4)
    if not (-2048 <= b_offset <= 2046):
        raise ValueError(
            f"Branch offset {b_offset} to epilogue doesn't fit 16-bit B."
        )
    b_epilogue = struct.pack("<H", 0xE000 | ((b_offset >> 1) & 0x7FF))

    # Two NOPs for padding / alignment
    nop = struct.pack("<H", 0xBF00)

    # Inline literal: the bitmap header flash address
    literal = struct.pack("<I", bitmap_header_addr)

    stub = ldr_r0 + movs_r1 + movs_r2 + bl_draw + b_epilogue + nop + nop + literal
    assert len(stub) == SPLASH_STUB_SIZE
    return stub


def plan_universal_patches(
    fw: bytes | bytearray,
    pixel_data: bytes,
    img_w: int,
    img_h: int,
    *,
    sector: int = DEFAULT_IMAGE_SECTOR,
) -> list[Patch]:
    """Build patches for the universal (all-model) boot logo.

    Uses Approach B: overwrites the switch dispatch with a stub that
    unconditionally draws the custom bitmap at (0, 0) and returns.
    Works identically for all 8 Guohetec radio models regardless of
    the EEPROM model-index byte.

    Parameters
    ----------
    fw:
        Original 2 MB firmware binary.
    pixel_data:
        BGR565 LE pixel bytes.
    img_w, img_h:
        Image dimensions in pixels.
    sector:
        Flash sector for image data (10–13).

    Returns
    -------
    List of ``Patch`` objects ready to apply.
    """
    sector_offset = sector * SECTOR_SIZE
    header_addr = FLASH_BASE + sector_offset
    data_addr = header_addr + HEADER_SIZE
    header = build_bitmap_header(img_w, img_h, data_addr)

    patches: list[Patch] = []

    # 1. Image data (header + pixels) in the target sector.
    patches.append(Patch(
        sector_offset,
        header + pixel_data,
        f"{img_w}x{img_h} BGR565 image in sector {sector}",
    ))

    # 2. Thumb-2 stub: bypasses the switch, draws at (0,0), returns.
    stub = build_universal_stub(header_addr)
    patches.append(Patch(
        SPLASH_STUB_OFFSET,
        stub,
        f"universal stub ({SPLASH_STUB_SIZE}B) -> draw at (0,0), skip text",
    ))

    return patches


def apply_patches(fw: bytearray, patches: list[Patch]) -> None:
    """Apply a list of patches to a mutable firmware buffer."""
    for p in patches:
        fw[p.offset: p.offset + len(p.data)] = p.data


# ---------------------------------------------------------------------------
# Sector validation
# ---------------------------------------------------------------------------
def check_sector_erased(
    fw: bytes | bytearray,
    sector: int,
    needed: int,
) -> list[str]:
    """Return a list of warning strings if target sectors aren't erased."""
    warnings: list[str] = []
    sectors_needed = (needed + SECTOR_SIZE - 1) // SECTOR_SIZE

    for s in range(sectors_needed):
        s_num = sector + s
        s_off = s_num * SECTOR_SIZE
        s_end = s_off + SECTOR_SIZE

        if s_end > len(fw):
            warnings.append(
                f"Sector {s_num} extends beyond firmware "
                f"({s_end:#x} > {len(fw):#x})."
            )
            continue

        non_ff = sum(1 for b in fw[s_off:s_end] if b != 0xFF)
        if non_ff > 0:
            warnings.append(
                f"Sector {s_num} has {non_ff:,} non-0xFF bytes "
                f"(not fully erased)."
            )

    return warnings


# ---------------------------------------------------------------------------
# High-level: patch a complete firmware
# ---------------------------------------------------------------------------
def patch_firmware(
    firmware_path: Path,
    pixel_data: bytes,
    img_w: int,
    img_h: int,
    output_path: Path,
    *,
    sector: int = DEFAULT_IMAGE_SECTOR,
    patch_all_cases: bool = False,
    remove_model_text: bool = False,
    remove_all_text: bool = False,
) -> list[Patch]:
    """Load firmware, apply boot-logo patches, save the result.

    Returns the list of patches that were applied.
    """
    fw = bytearray(firmware_path.read_bytes())
    if len(fw) != FIRMWARE_SIZE:
        raise ValueError(
            f"Firmware size {len(fw):,} != expected {FIRMWARE_SIZE:,}."
        )

    total_size = HEADER_SIZE + len(pixel_data)

    # Warn (but don't block) if sectors aren't erased.
    warnings = check_sector_erased(fw, sector, total_size)

    patches = plan_patches(
        fw, pixel_data, img_w, img_h,
        sector=sector,
        patch_all_cases=patch_all_cases,
        remove_model_text=remove_model_text,
        remove_all_text=remove_all_text,
    )

    apply_patches(fw, patches)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(fw)

    return patches
