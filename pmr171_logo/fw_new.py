"""Generate FW-NEW.bin for PMR-171 USB bootloader firmware update.

The UHSDR-derived bootloader reads ``FW-NEW.bin`` from a USB stick and
programs it to Bank 2 (starting at 0x08020000).  The file is a raw
binary — no header, no CRC — with trailing 0xFF bytes stripped.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from .constants import (
    APPLICATION_ADDRESS,
    APP_OFFSET,
    CONFIG_FLASH_ADDR,
    CONFIG_OFFSET_FROM_APP,
    FLASH_BASE,
    FLASH_SIZE,
    FLASHRESERVED_OPTIONS,
    SRAM_RANGES,
)


def _sp_valid(addr: int) -> bool:
    return any(lo <= addr <= hi for lo, hi in SRAM_RANGES)


def _reset_valid(addr: int) -> bool:
    return bool(
        (addr & 1)
        and APPLICATION_ADDRESS <= (addr & ~1) < FLASH_BASE + FLASH_SIZE
    )


def _last_nonff(data: bytes | bytearray) -> int:
    for i in range(len(data) - 1, -1, -1):
        if data[i] != 0xFF:
            return i
    return -1


class FwNewResult:
    """Result of a FW-NEW.bin generation."""

    __slots__ = ("data", "sp", "reset", "size_warnings")

    def __init__(
        self,
        data: bytes,
        sp: int,
        reset: int,
        size_warnings: list[str],
    ) -> None:
        self.data = data
        self.sp = sp
        self.reset = reset
        self.size_warnings = size_warnings

    @property
    def sha256_short(self) -> str:
        return hashlib.sha256(self.data).hexdigest()[:16]

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.data)


def make_fw_new(
    firmware: bytes | bytearray,
    *,
    include_config: bool = False,
) -> FwNewResult:
    """Generate FW-NEW.bin content from a full 2 MB firmware dump.

    Parameters
    ----------
    firmware:
        Complete 2 MB flash dump (or patched dump).
    include_config:
        If True, include the config/calibration region at 0x081C0000.
        Default is False (preserves user settings on the radio).

    Returns
    -------
    A ``FwNewResult`` containing the output bytes and validation info.

    Raises
    ------
    ValueError
        If the input isn't a valid 2 MB dump with a Bank 2 vector table.
    """
    if len(firmware) != FLASH_SIZE:
        raise ValueError(
            f"Input must be exactly {FLASH_SIZE:,} bytes (2 MB). "
            f"Got {len(firmware):,}."
        )

    sp, reset = struct.unpack_from("<II", firmware, APP_OFFSET)
    if not _sp_valid(sp):
        raise ValueError(
            f"Invalid initial SP at Bank 2 offset: 0x{sp:08X} — "
            f"does not point into any SRAM region."
        )
    if not _reset_valid(reset):
        raise ValueError(
            f"Invalid reset vector at Bank 2 offset: 0x{reset:08X} — "
            f"does not point into Bank 2 flash."
        )

    # Extract Bank 2 application region.
    app = firmware[APP_OFFSET:]

    # Optionally truncate before config region.
    if not include_config and len(app) > CONFIG_OFFSET_FROM_APP:
        app = app[:CONFIG_OFFSET_FROM_APP]

    # Trim trailing 0xFF.
    last = _last_nonff(app)
    if last < 0:
        raise ValueError("Bank 2 application region is entirely 0xFF.")
    trimmed = app[: last + 1]

    # Check against known bootloader size limits.
    size_warnings: list[str] = []
    for reserved_kb, limit in sorted(FLASHRESERVED_OPTIONS.items()):
        if len(trimmed) > limit:
            size_warnings.append(
                f"Exceeds FLASHRESERVED={reserved_kb} KB limit "
                f"({len(trimmed):,} > {limit:,})."
            )

    return FwNewResult(
        data=bytes(trimmed),
        sp=sp,
        reset=reset,
        size_warnings=size_warnings,
    )
