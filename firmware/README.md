# Firmware Directory

Place the **OEM firmware update file** (`FW-NEW.bin`) here.

## How to obtain it

1. Go to the Guohetec download page: **https://www.guohedz.com/DOWNLOAD**
2. Download the firmware update.  The download page lists both radio-specific and version-specific archives — choose the most recent generic (version-only) download, which works on all Guohetec models.
3. Extract the archive and copy the `FW-NEW.bin` file into this directory.

The tool will automatically detect it and use it as the base for
patching.

## Expected file

```
firmware/
  FW-NEW.bin   ← place it here
```

> **Note:** `*.bin` files in this directory are gitignored.
