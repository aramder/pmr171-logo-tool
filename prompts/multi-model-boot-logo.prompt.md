# Multi-Model Boot Logo Support

## Goal

Extend the PMR-171 boot logo tool to replace the boot logo on **all eight Guohetec radio models**, not just the PMR-171. The key constraint: we only have PMR-171 hardware for testing.

## Background

The splash screen function at `0x080904D4` (v3.7.2) reads a model index byte from EEPROM and executes a switch statement. Each case loads a logo bitmap address, sets draw coordinates, fills a background color, and optionally draws model name + version text. The model byte determines which case runs at boot. On our test hardware it's always case 6 (PMR-171).

### Current state of knowledge

| Case | Model | Literal pool | Pixel format | Coords in `CASE_COORDS` | Model-text BL offset |
|------|-------|-------------|-------------|------------------------|--------------------|
| 0 | Q900 | `LITPOOL_OFFSET` (shared) | 16-bit RGB565 | Yes | **Unknown** |
| 1 | HS2 | **Unknown** | **Unknown** | No | **Unknown** |
| 2 | QR20 | **Unknown** | **Unknown** | No | **Unknown** |
| 3 | TBR-119 | `LITPOOL_OFFSET` (shared) | 16-bit RGB565 | Yes | **Unknown** |
| 4 | PMR-119 | `LITPOOL_OFFSET` (shared) | 16-bit RGB565 | Yes | **Unknown** |
| 5 | SJR-188 | **Unknown** | **Unknown** | No | **Unknown** |
| 6 | PMR-171 | `LITPOOL_OFFSET` (shared) | 16-bit RGB565 | Yes | `0x00090594` |
| 7 | MX-1000 | `LITPOOL_OFFSET` (shared) | 16-bit RGB565 | Yes | **Unknown** |

## Design Decision: Two Approaches

### Approach A: Patch Every Case Individually

Reverse engineer each case's literal pool entry, coordinate instructions, background-fill call, and model-text BL. Patch them all independently.

**Pros**: Minimal code changes to the function. Each case is patched at its own offsets.
**Cons**: 8× the RE work. Cases 1/2/5 have not been analyzed (literal pools, pixel format, text BL offsets all unknown). Cannot test cases other than 6 on our hardware — everything except case 6 is untested.

### Approach B: Intercept Before the Switch (Recommended)

Patch the splash function to bypass the switch statement entirely. Overwrite the early instructions (after the EEPROM read but before the switch dispatch) with a short Thumb-2 stub that unconditionally:

1. Calls `GUI_SetColor` / `GUI_FillRect` with our background color (or skip if full-screen)
2. Loads the new bitmap address
3. Calls `GUI_DrawBitmap` at (0, 0)
4. Branches past all the text-draw code to the function epilogue

This makes every model — regardless of EEPROM byte — execute the same code path: our custom full-screen image, no text, no switch.

**Pros**:
- One code path, works for all 8 models identically
- Fully testable on PMR-171 hardware (the EEPROM value doesn't matter — the switch is never reached)
- No need to reverse engineer cases 1/2/5 pixel format or find their individual offsets
- Simpler patch logic: one contiguous block of Thumb-2 instructions replaces the switch preamble

**Cons**:
- More invasive: we're replacing actual instructions, not just tweaking data/immediates
- Requires knowing the exact function layout (entry, switch jump, GUI API addresses, epilogue)
- If the user wants different behavior per model (e.g., different logo per model), this approach doesn't support it without more work

## Implementation Plan (Approach B)

### Phase 1: Disassembly Analysis (RE, no code changes)

Using a full 2 MB flash dump of v3.7.2, disassemble the splash screen function at `0x080904D4`:

1. **Map the function structure**: Find the function prologue (push), EEPROM read call, switch table base, each case block, shared text-draw code, and epilogue (pop/bx lr).

2. **Identify the interception point**: The goal is an address range early in the function where we can overwrite instructions with our stub. Ideal location: after the stack frame is set up but before the switch dispatch. We need enough bytes for our stub (likely 20-30 bytes of Thumb-2).

3. **Collect API addresses** (from literal pools or direct calls in the function):
   - `GUI_DrawBitmap(const GUI_BITMAP *pBM, int x, int y)` — already called by every case
   - `GUI_SetBkColor(GUI_COLOR Color)` — called for background fill
   - `GUI_FillRect(int x0, int y0, int x1, int y1)` — or `GUI_Clear()`, used for background
   - Identify which registers hold what at our interception point

4. **Find the function epilogue address**: Where to branch after drawing — skip all text rendering code.

5. **Determine if we need `GUI_FillRect`**: If the image is full-screen (320×240), we might not need background fill at all — the image covers everything. This simplifies the stub to just: load bitmap pointer, `mov r1, #0`, `mov r2, #0`, `bl GUI_DrawBitmap`, branch to epilogue.

**Deliverable**: A text file with:
- Full disassembly listing of the splash function (annotated)
- The interception address range (start, end, byte count available)
- The epilogue/return address to branch to
- `GUI_DrawBitmap` resolved address
- The stub instruction sequence (as ARM Thumb-2 assembly + hex bytes)

### Phase 2: Implement the Stub Patch

Update `constants.py`, `firmware_patch.py`, and `cli.py`:

1. **`constants.py`**: Add new constants:
   - `SPLASH_STUB_OFFSET`: Start of our stub in the function (offset from `FLASH_BASE`)
   - `SPLASH_STUB_SIZE`: Number of bytes we overwrite
   - `SPLASH_EPILOGUE_OFFSET`: Where to branch after drawing
   - `GUI_DRAWBITMAP_ADDR`: Resolved address of `GUI_DrawBitmap`
   - Keep all existing constants for backward compatibility

2. **`firmware_patch.py`**: Add a new function (or extend `plan_patches`):
   - `plan_universal_patches(fw, pixel_data, img_w, img_h, *, sector)` → `list[Patch]`
   - Builds the Thumb-2 stub bytes:
     ```
     ldr  r0, [pc, #N]   ; load new bitmap header address from our literal
     movs r1, #0          ; x = 0
     movs r2, #0          ; y = 0
     bl   GUI_DrawBitmap  ; draw full-screen
     b    epilogue         ; skip text draws, go to function return
     .word new_header_addr ; inline literal for the bitmap pointer
     ```
   - Includes the image data patch (same as today)
   - Includes the stub patch at `SPLASH_STUB_OFFSET`
   - Does NOT patch the literal pool or per-case coordinates (those are bypassed)

3. **`cli.py`**: Add `--universal` flag (or make it the default, with `--pmr171-only` for the old behavior):
   - `--universal`: Use the stub approach (all models, recommended)
   - Default behavior: PMR-171 only (existing behavior, backward compatible)
   - `--no-text` becomes implicit with `--universal` (text draws are skipped entirely)

### Phase 3: Testing

Since the stub bypasses the switch, testing on PMR-171 hardware validates ALL models:

1. **Unit tests**: Verify stub bytes are valid Thumb-2 (use capstone disassembler to decode and check)
2. **Binary comparison**: Patch a firmware, verify only expected offsets are modified
3. **Flash test on PMR-171**: USB-flash the patched firmware, confirm boot logo appears
4. **Regression**: Ensure existing PMR-171-only mode still works unchanged

### Phase 4: Stretch Goals

- **Per-model logos**: If `--universal` is active, optionally allow the user to specify different images per model. This would require preserving the switch dispatch but rewriting each case to use 16-bit format and our images. Much more complex — defer unless requested.
- **Background color control**: Allow the user to set a custom background fill color (for non-full-screen images). With the stub approach, add a `GUI_SetBkColor` + `GUI_Clear` or `GUI_FillRect` before the bitmap draw.

## Files to Modify

| File | Changes |
|------|---------|
| `pmr171_logo/constants.py` | Add stub offsets, epilogue address, GUI_DrawBitmap address |
| `pmr171_logo/firmware_patch.py` | Add `plan_universal_patches()` or extend `plan_patches()` |
| `cli.py` | Add `--universal` flag, wire up new patch path |
| `tests/test_logo_tool.py` | Add tests for universal patch mode |
| `README.md` | Update supported radios, add universal mode docs |
| `TODO.md` | Mark multi-model as done |

## Constraints

- Only PMR-171 hardware available for testing
- Firmware version: v3.7.2 only (all offsets are version-specific)
- The stub must fit within the instruction bytes we overwrite — no room to grow into adjacent code
- Thumb-2 alignment: all instructions must be halfword-aligned
- The patched firmware must still pass the UHSDR bootloader's vector table validation

## Required Input

**A full 2 MB flash dump of v3.7.2 firmware** is needed for Phase 1 disassembly analysis. The OEM FW-NEW.bin (Bank 2 only) is sufficient for patching, but the dump is needed to resolve absolute addresses for GUI API functions that may live anywhere in flash.
