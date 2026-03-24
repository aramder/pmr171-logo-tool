#!/usr/bin/env python3
"""PMR-171 Boot Logo Tool — patch any image into the radio's boot screen.

Takes an image (PNG, JPEG, BMP, etc.) and the OEM firmware update file
(FW-NEW.bin), produces a patched firmware with the custom boot logo,
and generates a new FW-NEW.bin for USB bootloader update.

Examples
--------
  # Patch firmware with a custom image (uses firmware/FW-NEW.bin by default):
  pmr171-logo myimage.png

  # Use "fill" mode (crop-to-cover) with no text overlays:
  pmr171-logo myimage.png --resize fill --no-text

  # Specify a different firmware file:
  pmr171-logo myimage.png -f path/to/FW-NEW.bin
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pmr171_logo import __version__
from pmr171_logo.constants import (
    DEFAULT_IMAGE_SECTOR,
    FLASH_BASE,
    HEADER_SIZE,
    SCREEN_H,
    SCREEN_W,
    SECTOR_SIZE,
)
from pmr171_logo.firmware_patch import (
    FIRMWARE_SIZE,
    apply_patches,
    check_sector_erased,
    plan_patches,
)
from pmr171_logo.fw_new import load_firmware, make_fw_new
from pmr171_logo.image_convert import image_to_bgr565_le, load_and_prepare

# Default location for the OEM firmware file within the repo.
DEFAULT_FIRMWARE_PATH = Path(__file__).resolve().parent / "firmware" / "FW-NEW.bin"


def _parse_hex_color(s: str) -> tuple[int, int, int]:
    h = s.lstrip("#")
    if len(h) != 6:
        raise argparse.ArgumentTypeError(
            f"Invalid color '{s}'. Use 6-digit hex like #000000."
        )
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid hex color '{s}'.")


def cmd_patch(args: argparse.Namespace) -> int:
    """Main command: image + firmware -> patched firmware + FW-NEW.bin."""
    fw_path = Path(args.firmware)
    if not fw_path.exists():
        print(f"ERROR: Firmware not found: {fw_path}", file=sys.stderr)
        if fw_path == DEFAULT_FIRMWARE_PATH:
            print(
                "  Place the OEM FW-NEW.bin in the firmware/ directory.",
                file=sys.stderr,
            )
        return 1

    print(f"Loading firmware: {fw_path}")
    try:
        fw = load_firmware(fw_path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if len(fw_path.read_bytes()) < FIRMWARE_SIZE:
        print(f"  OEM FW-NEW.bin ({len(fw_path.read_bytes()):,} bytes) "
              f"-> reconstructed 2 MB flash image")

    # -- Image processing --
    print(f"Processing image: {args.image}")
    bg_rgb = _parse_hex_color(args.bg_color)
    img = load_and_prepare(
        args.image, args.resize, SCREEN_W, SCREEN_H, bg_rgb
    )
    img_w, img_h = img.size
    print(f"  Input -> {img_w}x{img_h} ({args.resize} mode)")

    if args.preview:
        img.save(args.preview)
        print(f"  Preview saved: {args.preview}")

    # -- Convert --
    print("Converting to BGR565...")
    pixel_data = image_to_bgr565_le(img)
    total_size = HEADER_SIZE + len(pixel_data)
    print(f"  Image data: {total_size:,} bytes ({total_size / 1024:.1f} KB)")

    # -- Validate target sector --
    sector = args.sector
    warnings = check_sector_erased(fw, sector, total_size)
    for w in warnings:
        print(f"  WARNING: {w}", file=sys.stderr)

    # -- Build & apply patches --
    patches = plan_patches(
        fw, pixel_data, img_w, img_h,
        sector=sector,
        patch_all_cases=args.all_models,
        remove_model_text=args.no_model_text,
        remove_all_text=args.no_text,
    )
    apply_patches(fw, patches)

    # -- Print patch summary --
    print()
    print("Patches applied:")
    for i, p in enumerate(patches, 1):
        addr = FLASH_BASE + p.offset
        print(f"  {i:2d}. [{addr:#010x}] {len(p.data):>7,} B  {p.desc}")

    # -- Generate FW-NEW.bin --
    output_path = Path(args.output)
    result = make_fw_new(bytes(fw), include_config=args.include_config)

    for w in result.size_warnings:
        print(f"  WARNING: {w}", file=sys.stderr)

    result.write(output_path)
    print(f"\nFW-NEW.bin: {output_path}  ({len(result.data):,} bytes)")
    print(f"  SHA-256: {result.sha256_short}...")
    print(f"  Vector:  SP=0x{result.sp:08X}  Reset=0x{result.reset:08X}")
    print()
    print("To update the radio:")
    print(f"  1. Copy {output_path.name} to a USB stick (FAT32, root dir)")
    print("  2. Insert the USB stick into the PMR-171")
    print("  3. Power on — the bootloader will flash automatically")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="pmr171-logo",
        description=(
            "PMR-171 Boot Logo Tool — patch any image into the "
            "radio's boot screen and generate a USB update file."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    sub = parser.add_subparsers(dest="command")

    # ── patch ──
    p_patch = sub.add_parser(
        "patch",
        help="Patch a boot logo image into the firmware.",
        description="Replace the boot logo and generate FW-NEW.bin.",
    )
    p_patch.add_argument(
        "image",
        help="Input image (PNG, JPEG, BMP, etc.)",
    )
    p_patch.add_argument(
        "-f", "--firmware",
        default=str(DEFAULT_FIRMWARE_PATH),
        help=(
            "OEM FW-NEW.bin firmware update file "
            f"(default: firmware/FW-NEW.bin)"
        ),
    )
    p_patch.add_argument(
        "-o", "--output",
        default="FW-NEW.bin",
        help="Output FW-NEW.bin path (default: FW-NEW.bin)",
    )
    p_patch.add_argument(
        "--resize",
        choices=["fit", "fill", "stretch", "none"],
        default="fit",
        help=(
            "Resize mode: fit (letterbox, default), fill (crop), "
            "stretch, none"
        ),
    )
    p_patch.add_argument(
        "--bg-color",
        default="#000000",
        help="Letterbox background color (hex, default: #000000)",
    )
    p_patch.add_argument(
        "--no-text",
        action="store_true",
        help="Remove model name AND version text overlays",
    )
    p_patch.add_argument(
        "--no-model-text",
        action="store_true",
        help="Remove model name text overlay only",
    )
    p_patch.add_argument(
        "--all-models",
        action="store_true",
        help="Patch logo coordinates for all model variants (not just PMR-171)",
    )
    p_patch.add_argument(
        "--sector",
        type=int,
        default=DEFAULT_IMAGE_SECTOR,
        choices=range(10, 14),
        metavar="{10-13}",
        help="Flash sector for image data (default: 10)",
    )
    p_patch.add_argument(
        "--include-config",
        action="store_true",
        help="Include config/calibration region in FW-NEW.bin",
    )
    p_patch.add_argument(
        "--preview",
        metavar="FILE",
        help="Save a PNG preview of the processed image",
    )

    args = parser.parse_args()

    if args.command == "patch":
        return cmd_patch(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
