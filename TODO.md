# TODO

## ~~Multi-Model Boot Logo Support~~ ✓

Implemented via `--universal` mode (Approach B). A 20-byte Thumb-2 stub overwrites the switch dispatch at `0x080904D8`, unconditionally drawing the custom bitmap at (0, 0) via `GUI_DrawBitmap` and branching to the function epilogue. Bypasses all per-model differences — works identically on all 8 Guohetec models regardless of the EEPROM model-index byte.

### Stretch goals (not yet implemented)

- **Per-model logos**: Allow different images per model while preserving the switch dispatch. Would require rewriting each case block.
- **Background color control**: Add `GUI_SetBkColor` + `GUI_FillRect` to the stub for non-full-screen images in universal mode.

## Bitmap Extractor Color Decoding (`_scratch/extract_bitmaps.py`)

The firmware bitmap extractor can locate and render all 46 emWin `GUI_BITMAP` images, but **24bpp color decoding is still incorrect**. Paletted icons (1/2/4bpp) and the 16bpp DMR logo render correctly. Remaining issues:

- 24bpp pixel data is stored as B,G,R bytes — a BGR→RGB swap is applied but the output colors still don't match the on-screen appearance.
- Need to compare extracted PNGs against live screenshots from the radio LCD to ground-truth the color channel interpretation.
- The 24bpp `pMethods` vtable at `0x08114448` has a complex draw function (`0x080992C9`, ~200+ bytes) that likely does per-pixel color space conversion for the BGR565 LCD. Disassembling this function would reveal the exact transform.
- Palette `LCD_COLOR` format is confirmed `0x00BBGGRR` (le u32) — paletted icons render correctly with this interpretation.
