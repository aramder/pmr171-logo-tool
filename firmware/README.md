# Firmware Directory

Place the **OEM firmware update file** (`FW-NEW.bin`) here.

## How to obtain it

1. Go to the Guohetec download page: **https://www.guohedz.com/DOWNLOAD**
2. Download the firmware update. This is slightly confusing as some downloads are radio-specific, and some are version-specific. Version-only downloads should work on all Guohetec models. Choose the most recent that applies to you.
3. Extract the archive and copy the `FW-NEW.bin` file into this directory.

The tool will automatically detect it and use it as the base for
patching.

## Expected file

```
firmware/
  FW-NEW.bin   ← place it here
```

> **Note:** `*.bin` files in this directory are gitignored.
