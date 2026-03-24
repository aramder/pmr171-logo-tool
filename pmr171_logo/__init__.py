"""PMR-171 boot logo patcher — image to firmware in one step."""

from .constants import (
    APPLICATION_ADDRESS,
    APP_OFFSET,
    CASE6_MODEL_BL_OFFSET,
    CASE_COORDS,
    CONFIG_FLASH_ADDR,
    DEFAULT_IMAGE_SECTOR,
    FLASH_BASE,
    FLASH_SIZE,
    FLASHRESERVED_OPTIONS,
    HEADER_SIZE,
    LITPOOL_OFFSET,
    NOP_NOP,
    PMETHODS_16BPP,
    SCREEN_H,
    SCREEN_W,
    SECTOR_SIZE,
    SHARED_VERSION_BL_OFFSET,
)
from .firmware_patch import (
    Patch,
    apply_patches,
    build_bitmap_header,
    check_sector_erased,
    patch_firmware,
    plan_patches,
)
from .fw_new import FwNewResult, load_firmware, make_fw_new
from .image_convert import (
    image_to_bgr565_le,
    load_and_prepare,
    rgb_to_bgr565,
)

__all__ = [
    # constants
    "APPLICATION_ADDRESS",
    "APP_OFFSET",
    "CASE6_MODEL_BL_OFFSET",
    "CASE_COORDS",
    "CONFIG_FLASH_ADDR",
    "DEFAULT_IMAGE_SECTOR",
    "FLASH_BASE",
    "FLASH_SIZE",
    "FLASHRESERVED_OPTIONS",
    "HEADER_SIZE",
    "LITPOOL_OFFSET",
    "NOP_NOP",
    "PMETHODS_16BPP",
    "SCREEN_H",
    "SCREEN_W",
    "SECTOR_SIZE",
    "SHARED_VERSION_BL_OFFSET",
    # firmware_patch
    "Patch",
    "apply_patches",
    "build_bitmap_header",
    "check_sector_erased",
    "patch_firmware",
    "plan_patches",
    # fw_new
    "FwNewResult",
    "load_firmware",
    "make_fw_new",
    # image_convert
    "image_to_bgr565_le",
    "load_and_prepare",
    "rgb_to_bgr565",
]

__version__ = "0.1.0"
