# PMR-171 Boot Logo Tool

Patch any image into your **Guohetec PMR-171** SDR transceiver's boot screen and generate a ready-to-flash USB update file.

> **No soldering.  No SWD debugger.  Just a USB stick.**

## What It Does

```
your_logo.png  +  firmware.bin  →  FW-NEW.bin (USB stick)  →  Radio boots with your image
```

1. Takes any image (PNG, JPEG, BMP, etc.)
2. Resizes/converts it for the PMR-171's 320×240 LCD (BGR565 format)
3. Patches it into a copy of the stock firmware binary
4. Generates `FW-NEW.bin` — the USB bootloader update file
5. Put the file on a FAT32 USB stick, plug it in, and power on

## Requirements

- **Python 3.10+**
- **Pillow** (image processing)
- A **stock PMR-171 firmware dump** (2 MB `.bin` file)
- Optional: **numpy** for faster image conversion

## Installation

```bash
# Clone / download this repo, then:
cd pmr171-logo-tool
pip install -e .

# Or just use it directly:
pip install Pillow
python cli.py patch mylogo.png -f firmware.bin
```

## Quick Start

```bash
# Basic: letterbox your image on a black background, remove text overlays
python cli.py patch mylogo.png -f firmware.bin --no-text

# Fill the screen (crop-to-cover):
python cli.py patch mylogo.png -f firmware.bin --resize fill --no-text

# Stretch to fill (may distort):
python cli.py patch mylogo.png -f firmware.bin --resize stretch

# Custom background colour for letterboxing:
python cli.py patch mylogo.png -f firmware.bin --bg-color "#1a1a2e"

# Also save the full 2 MB patched dump (for SWD flashing):
python cli.py patch mylogo.png -f firmware.bin --output-dump patched.bin

# Generate a preview PNG of what the LCD will display:
python cli.py patch mylogo.png -f firmware.bin --preview preview.png
```

### Output

The tool writes `FW-NEW.bin` (default name, customize with `-o`):

```
FW-NEW.bin: FW-NEW.bin  (1,279,652 bytes)
  SHA-256: a3b8c9d1e2f34567...
  Vector:  SP=0x2407FFF8  Reset=0x080303E9

To update the radio:
  1. Copy FW-NEW.bin to a USB stick (FAT32, root directory)
  2. Insert the USB stick into the PMR-171
  3. Power on — the bootloader will flash automatically
```

## Sub-Commands

### `patch` — Image → Firmware (main command)

```
python cli.py patch <image> -f <firmware.bin> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `-f`, `--firmware` | *(required)* | Stock 2 MB firmware dump |
| `-o`, `--output` | `FW-NEW.bin` | Output USB update file |
| `--output-dump` | *(none)* | Also save full 2 MB patched dump for SWD |
| `--resize` | `fit` | `fit` (letterbox), `fill` (crop), `stretch`, `none` |
| `--bg-color` | `#000000` | Letterbox background colour |
| `--no-text` | off | Remove model name + version text overlays |
| `--no-model-text` | off | Remove model name only |
| `--all-models` | off | Patch coordinates for all PMR-171 model variants |
| `--sector` | `10` | Flash sector for image data (10–13) |
| `--include-config` | off | Include config/calibration region in FW-NEW.bin |
| `--preview` | *(none)* | Save a PNG preview of the processed image |

### `fw-new` — Dump → FW-NEW.bin (no image patching)

Convert an already-patched 2 MB firmware dump to the USB update format:

```
python cli.py fw-new patched_firmware.bin -o FW-NEW.bin
```

## How It Works

### PMR-171 Firmware Layout

```
┌────────────────────────────────┐ 0x08000000
│  Bank 1: Bootloader (128 KB)  │  ← UHSDR-derived, reads USB stick
├────────────────────────────────┤ 0x08020000
│                                │
│  Bank 2: Application           │  ← Main radio firmware
│  (code, data, boot images)     │
│                                │
│  Sector 10-13: Erased space    │  ← New logo goes here
│                                │
├────────────────────────────────┤ 0x081C0000
│  Config / Calibration (256 KB) │  ← User settings (preserved)
└────────────────────────────────┘ 0x081FFFFF
```

### Boot Logo Format

The PMR-171 uses **STemWin** (emWin) for its GUI.  Boot logos are stored as:

- **20-byte emWin `GUI_BITMAP` header** — dimensions, stride, pixel data pointer, draw-method vtable
- **Raw BGR565 pixel data** — 16-bit little-endian, blue in high bits (matching the LT7680/ST7789V LCD panel)

For a full-screen 320×240 image: 20 + 153,600 = **153,620 bytes** (~150 KB, fits in one 128 KB sector).

### Patching Procedure

1. Convert the input image to BGR565 LE pixel data
2. Build an emWin `GUI_BITMAP` header pointing to the pixel data
3. Write header + pixels into an erased flash sector (default: sector 10)
4. Patch the literal pool pointer in the splash screen function to point to the new header
5. Update draw coordinates to centre the image on screen
6. Optionally NOP the model-name and version-text overlay `bl` instructions
7. Extract Bank 2, trim trailing `0xFF`, write as `FW-NEW.bin`

### USB Bootloader Update

The PMR-171's UHSDR-derived bootloader:

1. Checks for `FW-NEW.bin` on a FAT32 USB stick at boot
2. Validates the file size against available flash
3. Erases Bank 2 sectors
4. Programs the file contents starting at `0x08020000`
5. Reboots into the new firmware

## Obtaining a Firmware Dump

You need a stock firmware dump to use as the base for patching.  Options:

1. **From the manufacturer**: Check if Guohetec provides firmware update files.  If they distribute `FW-NEW.bin`, you'll need the full 2 MB dump instead.
2. **SWD dump**: Read the flash via SWD using an ST-Link or J-Link debug probe.
3. **Community**: Check PMR-171 community forums and groups.

## Image Tips

- **Best results**: Use a 320×240 image — no resizing needed
- **Aspect ratio**: The `fit` mode (default) letterboxes with black bars; `fill` crops to cover
- **Transparency**: RGBA images are composited onto the background colour
- **Colours**: The 16-bit BGR565 format has 65,536 colours — gradients may show banding
- **File size**: A full-screen image uses ~150 KB of the ~1.7 MB available flash

## Firmware Compatibility

This tool is designed for **PMR-171 firmware v3.7.2** (stock).  The patch points (literal pool offset, coordinate instructions, text overlay BL addresses) are firmware-version-specific.  Using it with a different firmware version may produce incorrect results.

Compatible model variants (same firmware, different splash screens):
- PMR-171
- Q900
- TBR-119
- PMR-119
- XP-100

## Safety

- **Your stock firmware can always be restored** by putting the original `FW-NEW.bin` on a USB stick
- The tool only modifies erased flash sectors and a few code bytes — it doesn't touch the bootloader or config/calibration data
- The bootloader validates the file size before flashing — oversized files are rejected (error code 3)
- Always keep a backup of your stock firmware dump

## License

MIT — see [LICENSE](LICENSE).
