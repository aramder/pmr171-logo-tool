# TODO

## ~~Multi-Model Boot Logo Support~~ ✓

Implemented via `--universal` mode (Approach B). A 20-byte Thumb-2 stub overwrites the switch dispatch at `0x080904D8`, unconditionally drawing the custom bitmap at (0, 0) via `GUI_DrawBitmap` and branching to the function epilogue. Bypasses all per-model differences — works identically on all 8 Guohetec models regardless of the EEPROM model-index byte.

### Stretch goals (not yet implemented)

- **Per-model logos**: Allow different images per model while preserving the switch dispatch. Would require rewriting each case block.
- **Background color control**: Add `GUI_SetBkColor` + `GUI_FillRect` to the stub for non-full-screen images in universal mode.
