# PMR-171 Boot Logo Tool

Patch any image into your **Guohetec** SDR transceiver's boot screen and generate a ready-to-flash USB update file.

Works with the **PMR-171** and all related models — they share a single firmware binary.

> **No soldering.  No debugger.  Just a USB stick.**

> [!CAUTION]
> **This tool is ONLY compatible with Guohetec firmware v3.7.2.**
> Using it with any other firmware version may produce a non-functional update file that could
> brick your radio.
> **Do NOT use this tool with a firmware version other than the one listed below.**
> See [Firmware Compatibility](#firmware-compatibility) for details.

## What It Does

```
your_logo.png  +  FW-NEW.bin (OEM)  →  FW-NEW.bin (patched)  →  Radio boots with your image
```

1. Download the **OEM firmware update** (`FW-NEW.bin`) and place it in the `firmware/` directory
2. Takes any image (PNG, JPEG, BMP, etc.)
3. Resizes/converts it for the radio's 320×240 LCD (BGR565 format)
4. Patches it into a copy of the firmware
5. Generates a new `FW-NEW.bin` — the USB bootloader update file
6. Put the file on a FAT32 USB stick, plug it in, and power on

## Requirements

- **Python 3.10+**
- **Pillow** (image processing)
- The **OEM firmware update file** (`FW-NEW.bin`) from Guohetec — see [Obtaining the Firmware](#obtaining-the-firmware)
- Optional: **numpy** for faster image conversion

## Installation

```bash
# Clone / download this repo, then:
cd pmr171-logo-tool
pip install -r requirements.txt
```

Or install as a package (editable mode):

```bash
pip install -e .
```

## Quick Start

```bash
# 1. Place the OEM FW-NEW.bin in the firmware/ directory:
#    firmware/FW-NEW.bin

# 2. Recommended: universal mode (works on all 8 radio models, no text overlays)
python cli.py patch mylogo.png --universal --resize fill

# Letterbox on black background (all models):
python cli.py patch mylogo.png --universal

# PMR-171 only (legacy mode): letterbox, remove text overlays
python cli.py patch mylogo.png --no-text

# Fill the screen (crop-to-cover):
python cli.py patch mylogo.png --resize fill --no-text

# Stretch to fill (may distort):
python cli.py patch mylogo.png --resize stretch

# Custom background color for letterboxing:
python cli.py patch mylogo.png --bg-color "#1a1a2e"

# Specify a different firmware file:
python cli.py patch mylogo.png -f path/to/other-firmware.bin

# Generate a preview PNG of what the LCD will display:
python cli.py patch mylogo.png --preview preview.png
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
python cli.py patch <image> [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `-f`, `--firmware` | `firmware/FW-NEW.bin` | OEM firmware update file |
| `-o`, `--output` | `FW-NEW.bin` | Output USB update file |
| `--resize` | `fit` | `fit` (letterbox), `fill` (crop), `stretch`, `none` |
| `--bg-color` | `#000000` | Letterbox background color |
| `--universal` | off | All-model mode: bypasses the per-model switch (recommended) |
| `--no-text` | off | Remove model name + version text overlays |
| `--no-model-text` | off | Remove model name only |
| `--all-models` | off | Patch coordinates for all PMR-171 model variants |
| `--sector` | `10` | Flash sector for image data (10–13) |
| `--include-config` | off | Include config/calibration region in FW-NEW.bin |
| `--preview` | *(none)* | Save a PNG preview of the processed image |

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

For a full-screen 320×240 image: 20 + 153,600 = **153,620 bytes** (~150 KB, spanning two 128 KB flash sectors).

### Patching Procedure

1. Convert the input image to BGR565 LE pixel data
2. Build an emWin `GUI_BITMAP` header pointing to the pixel data
3. Write header + pixels into an erased flash sector (default: sector 10)
4. **Universal mode** (`--universal`): Overwrite the switch dispatch with a 20-byte Thumb-2 stub that unconditionally draws the bitmap at (0, 0) and branches to the function epilogue — skips all per-model logic and text rendering
5. **Legacy mode** (default): Patch the literal pool pointer, update per-model draw coordinates, and optionally NOP text overlay `bl` instructions
6. Extract Bank 2, trim trailing `0xFF`, write as `FW-NEW.bin`

### USB Bootloader Update

The PMR-171's UHSDR-derived bootloader:

1. Checks for `FW-NEW.bin` on a FAT32 USB stick at boot
2. Validates the file size against available flash
3. Erases Bank 2 sectors
4. Programs the file contents starting at `0x08020000`
5. Reboots into the new firmware

## Obtaining the Firmware

Place the OEM firmware update file in the `firmware/` directory:

```
firmware/
  FW-NEW.bin   ← place it here
```

The tool accepts the **OEM `FW-NEW.bin`** (~1.1 MB) — the USB update file distributed by Guohetec.  The tool automatically reconstructs a full flash image from it internally.

> [!IMPORTANT]
> You **must** use firmware **v3.7.2** (1,127,552 bytes).  See [Firmware Compatibility](#firmware-compatibility).

**How to get the OEM file:**

1. Download **firmware v3.7.2** from the Guohetec download page: **https://www.guohedz.com/DOWNLOAD**
2. Extract the archive and locate the `FW-NEW.bin` file for your radio model.
3. **Verify the file size is exactly 1,127,552 bytes** before proceeding.
4. Copy it into the `firmware/` directory in this repo.

## Image Tips

- **Best results**: Use a 320×240 image — no resizing needed
- **Aspect ratio**: The `fit` mode (default) letterboxes with black bars; `fill` crops to cover
- **Transparency**: RGBA images are composited onto the background color
- **Colors**: The 16-bit BGR565 format has 65,536 colors — gradients may show banding
- **File size**: A full-screen image uses ~150 KB of the ~1.7 MB available flash

## Supported Radios

All of the following Guohetec SDR transceivers run the **same firmware binary** (`UHSDR-ForQ900-H7-V6-171`).  The active model is selected at runtime by an index byte stored in EEPROM — the hardware, flash layout, and boot-logo mechanism are identical across all of them.

| Model | Manufacturer / Brand | Notes |
|-------|----------------------|-------|
| **Q900** | Guohetec | Original UHSDR/OVI40-based design |
| **HS2** | Retevis / Ailunce | Rebadged Q900 |
| **QR20** | Guohetec | |
| **TBR-119** | Guohetec | Different SDR tuner front-end config |
| **PMR-119** | Guohetec | Same tuner variant as TBR-119 |
| **SJR-188** | Guohetec | |
| **PMR-171** | Guohetec | |
| **MX-1000** | Guohetec | Also known internally as XP-100 |

All eight share the same STM32H7 MCU, 320×240 LCD, emWin GUI, and UHSDR-derived bootloader.  Differences between models are limited to Bluetooth device name, RF band-switching tables, IMU axis orientation, and on-screen branding — none of which affect the boot logo.

### Universal Mode (Recommended)

Use `--universal` to bypass the per-model switch statement entirely.  This mode works on **all 8 models** — regardless of the EEPROM model-index byte, the radio will display your custom boot logo with no text overlays:

```bash
python cli.py patch mylogo.png --universal --resize fill
```

The stub replaces the firmware's model-selection logic with a short sequence that unconditionally draws your image at (0, 0) and returns.  Since the switch is never reached, it works identically on every model and is fully testable on any single unit.

## Firmware Compatibility

> [!WARNING]
> **The patch offsets used by this tool are hard-coded for a specific firmware version.**
> Guohetec may release updated firmware at any time.  If the internal code layout changes,
> applying these patches to a different version **will corrupt the firmware image** and could
> leave your radio unbootable until you re-flash a known-good `FW-NEW.bin` via USB.

| Field | Required Value |
|-------|----------------|
| **Firmware version** | **v3.7.2** |
| **Build date** | `Dec 22 2025 09:25:53` |
| **FW-NEW.bin size** | 1,127,552 bytes |

If Guohetec releases a newer firmware, **do not use this tool until it has been updated and re-validated** for that version.  Check this repo for updates.

**How to verify your firmware version:**
- On the radio: *Menu → Version Info* displays the firmware version and build date.
- On your computer: compare your `FW-NEW.bin` file size to the table above.

## Safety

- **Wrong firmware version = potential brick.** The patch offsets are specific to v3.7.2. A patched image built from any other version will almost certainly corrupt the firmware. The radio can be recovered via USB re-flash, but **only if you have a known-good `FW-NEW.bin`**.
- **Always keep a backup of your stock `FW-NEW.bin`** — before patching, copy the original somewhere safe.
- **Your stock firmware can always be restored** by putting the original `FW-NEW.bin` on a USB stick and powering on.
- The tool only modifies erased flash sectors and a few code bytes — it doesn't touch the bootloader or config/calibration data.
- The bootloader validates the file size before flashing — oversized files are rejected (error code 3).

## License

MIT — see [LICENSE](LICENSE).
