# CHANGES — WhatsApp Bulk Messenger

**Date:** 2026-03-20
**Branch:** main
**Commits included:** c6f5f53 (fix), c8889e2 (feat), 8fb0b93 (feat)

This document is a technical reference for other Claude instances to understand all code changes made in this session.

---

## VSCode-Inspired UI Redesign (app.py)

### Complete GUI Rewrite

The application now uses a modern dark theme inspired by VSCode's "Modern Dark Pro" color palette, replacing the previous minimal layout.

**Color Palette:**
- Background: `#1e1e1e`
- Sidebar: `#252526`
- Panel headers: `#2d2d2d`
- Accent: `#007acc` (blue)
- Status states: amber (`#cca700`), green (`#16825d`)

**Layout Structure (6 rows):**

```
Row 0: Title bar with theme selector (Dark / Light / System)
Row 1: Two-panel main area (CONTACTS left, MESSAGE TEMPLATE right, draggable sash)
Row 2: Settings bar (Delay, Send Delay, Country Code inputs)
Row 3: Control buttons (⚡ Launch, ✓ Logged In, ▶ Start, ■ Stop, Progress bar)
Row 4: OUTPUT log panel (scrollable, max 1000 lines, > prefix on messages)
Row 5: Status bar (color-coded state indicator)
```

**Panel Configuration (Row 1):**

- Uses `tk.PanedWindow` (NOT `ttk.PanedWindow` — ttk doesn't support paneconfig/minsize in add())
- Minsize for each pane: 300 pixels (prevents collapse)
- Draggable sash for user control
- fg_color must be `"transparent"` string (NOT tuples like `("transparent","transparent")`)

**Section Headers:**

- UPPERCASE styling ("CONTACTS", "MESSAGE TEMPLATE", "OUTPUT")
- 1px separators with minimal padding
- Contact count badge in CONTACTS header (e.g., "CONTACTS (5)")

**Icon Buttons:**

- ↑ Import (Load CSV/Excel)
- ⬇ Sample (Download contacts.example.csv)
- \+ Add (Add new contact row)
- ✕ Delete (Remove selected row)
- ⚡ Launch (Open Chrome & navigate to WhatsApp Web)
- ✓ Logged In (Confirm login, enable Start button)
- ▶ Start (Begin sending messages)
- ■ Stop (Stop sending gracefully)
- ↑ Save Template (Persist template to message.txt)

**Font:**

- Monospace: Menlo on macOS, Consolas on Windows/Linux
- Used in template editor, output log, and code displays

**Theme Selector:**

- Located in top-right corner
- Stored in `self.theme_var` (not a local variable — persists for state tracking)
- Options: Dark, Light, System
- Calls `ctk.set_appearance_mode()` and `ctk.set_default_color_theme("dark-blue")`

**Status Bar (Row 5):**

Color-coded state indicator with status text:

| State | Text | Color |
|-------|------|-------|
| IDLE | ● Ready | #007acc (blue) |
| BROWSER_OPEN | ● Waiting for login… | #cca700 (amber) |
| LOGGED_IN | ● Logged in — ready to send | #16825d (green) |
| SENDING | ● Sending messages… | #0078d4 (blue) |
| DONE | ● Done | #16825d (green) |

### Output Log

- Scrollable text panel in Row 4
- Each message prefixed with `"> "` for clarity
- Capped at `_LOG_MAX_LINES = 1000` to prevent memory bloat
- Supports Unicode and emoji

---

## Cross-Platform Path Fix (automator.py + app.py)

### Data Directory Handling

**Problem:** When bundled as a frozen `.app` on macOS, PyInstaller extracts the bundle to a temporary directory (`sys._MEIPASS`). This directory is re-extracted on every launch, so user-edited files (like `message.txt`) are lost.

**Solution:** Distinguish between read-only bundled data and writable user data.

```python
_BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

# When frozen (.app bundle):
if hasattr(sys, '_MEIPASS'):
    _DATA_DIR = _user_data_dir()
    MESSAGE_FILE = os.path.join(_DATA_DIR, "message.txt")
    # Seed with bundled default on first run
    if not os.path.exists(MESSAGE_FILE):
        _bundled_msg = os.path.join(_BASE_DIR, "message.txt")
        if os.path.exists(_bundled_msg):
            shutil.copy2(_bundled_msg, MESSAGE_FILE)
else:
    # When running from source:
    MESSAGE_FILE = os.path.join(_BASE_DIR, "message.txt")
```

### User Data Directory Function

```python
def _user_data_dir() -> str:
    """Return a stable, writable directory for user data files."""
    system = _platform.system()
    if system == 'Darwin':
        base = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'WhatsAppBulkMessenger')
    elif system == 'Windows':
        base = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'WhatsAppBulkMessenger')
    else:  # Linux
        base = os.path.join(os.path.expanduser('~'), '.config', 'WhatsAppBulkMessenger')
    os.makedirs(base, exist_ok=True)
    return base
```

**Paths per platform:**

- **macOS:** `~/Library/Application Support/WhatsAppBulkMessenger/`
- **Windows:** `%APPDATA%\WhatsAppBulkMessenger\`
- **Linux:** `~/.config/WhatsAppBulkMessenger/`

### Chrome Profile Path

Similarly, the Chrome user data directory (for persistent login) is per-platform:

- **macOS:** `~/Library/Application Support/WABulker`
- **Windows:** `%LOCALAPPDATA%\WABulker\User Data`
- **Linux:** `~/.config/WABulker`

---

## Security Fixes

### H-1: Single-Pass Regex Substitution (Prevents Second-Order Injection)

**File:** automator.py, line 86–90

```python
personalized_message = re.sub(
    r'\{([^{}]+)\}',
    lambda m: fields.get(m.group(1), m.group(0)),
    template
)
```

**Protection:** Uses a single pass with a lambda to replace placeholders. If a field value contains `{OtherKey}`, it is NOT re-expanded in subsequent passes — preventing injection where malicious field data could inject new placeholders.

### H-2: Restricted File Picker (No All Files Option)

**File:** app.py

- Removed `("All files", "*.*")` from filedialog filters
- Only `.csv` and `.xlsx` accepted via GUI
- Prevents user accidentally loading arbitrary file types

### H-3: File Size Guard (10 MB Limit)

**File:** automator.py, line 150–155

```python
file_size = os.path.getsize(filepath)
if file_size > MAX_FILE_SIZE:
    raise ValueError(
        f"File is too large ({file_size // 1024 // 1024} MB). "
        f"Maximum allowed size is {MAX_FILE_SIZE // 1024 // 1024} MB."
    )
```

**Constants:** `MAX_FILE_SIZE = 10 * 1024 * 1024`

**Protection:** Prevents loading oversized files that could cause memory exhaustion or slow processing.

### M-6: Sanitized Exception Messages (No Stack Traces)

**File:** automator.py, line 44

```python
err_type = type(e).__name__
log_fn(f"\nCould not send to {name} ({number}): {err_type}")
```

**Protection:** Only the exception type name is shown to users. Full stack traces are suppressed, preventing exposure of:
- Internal WebDriver paths
- CDP session IDs
- System paths
- Other sensitive debug info

---

## Bug Fixes

### Bug: PanedWindow Widget Class

**File:** app.py, Row 1 (main panel area)

- Changed from `ttk.PanedWindow` to `tk.PanedWindow`
- `ttk.PanedWindow` does not support `paneconfig()` or `minsize` in `add()` calls
- `tk.PanedWindow` (standard tkinter) has full support for these features

### Bug: Directory Creation at Module Level

**File:** app.py, function `_user_data_dir()`

- Wrapped `os.makedirs(base, exist_ok=True)` in try/except for robustness
- Prevents crash if the parent directory doesn't have write permissions

### Bug: Delay Validation Timing

**File:** app.py, method `_validate_delays()`

- Moved delay validation BEFORE `set_state(SENDING)`
- Prevents UI state flicker when invalid delay values are entered
- Now validates and shows warning BEFORE state changes

### Bug: ValueError on Invalid Delay Input

**File:** app.py, delay input handlers

- Previously: Silently defaulted to `DELAY` or `SEND_DELAY` on parse error
- Now: Shows a warning dialog with the error message (e.g., "Delay must be whole numbers")
- Lets user correct the input without silent fallback

### Bug: Race Condition in `_confirm_logged_in()`

**File:** app.py, method `_confirm_logged_in()`

- Added guard: `if self.driver is None: return`
- Prevents crash if called before driver is initialized

### Bug: Main-Thread Driver Assignment

**File:** app.py, method `_launch_browser()` and others

- Driver assignment now wrapped in `self.after(0, ...)`
- Ensures driver is assigned on the main thread, not in a Selenium callback
- Prevents Tkinter widget updates from other threads

### Bug: No-Internet Error Handling

**File:** app.py, method `_on_browser_timeout()`

- Now checks if page contains network error strings (module-level constant `_NET_ERRORS`)
- If no internet: shows friendly message and keeps state as `BROWSER_OPEN`
- User can connect and continue without relaunching
- Previously would crash or show cryptic Selenium error

### Bug: Add Contact Dialog on macOS

**File:** app.py, method `_add_contact_dialog()`

- Added `dialog.transient(self)` to make it a child window
- Added `dialog.lift()` to bring it to front
- Prevents dialog from appearing behind the main window on macOS

---

## New Features

### Country Code Field (Settings Bar)

**File:** app.py, Row 2

- Input field in GUI settings bar, default value `"91"` (India)
- Format: Digits only (no `+` sign)
- Logic: Prepends to 10-digit numbers; leaves 11-15 digit numbers as-is
- Can be left blank to send all numbers as-is

**Implementation:**
```python
self.country_code_var = ctk.StringVar(value="91")
```

**Usage in send_messages():**
```python
if len(number) == 10 and country_code:
    number = country_code + number
```

### Sample Button (⬇ Download)

**File:** app.py, CONTACTS toolbar

- Downloads `contacts.example.csv` from the bundle or current directory
- Allows users to see the expected CSV format
- Opens file in default application after download

**Constant:**
```python
SAMPLE_FILE = os.path.join(_BASE_DIR, "contacts.example.csv")
```

### Unresolved Placeholder Warning

**File:** automator.py, line 91–93

```python
remaining = re.findall(r'\{[^{}]+\}', personalized_message)
if remaining:
    log_fn(f"  Warning: unresolved placeholders {remaining} — check column names.")
```

- Detects placeholders that weren't replaced (e.g., `{BadColumnName}`)
- Warns user before sending so they can correct the template

### Constants Extracted

**File:** app.py, module level

```python
_LOG_MAX_LINES = 1000       # Max lines in output log before circular buffer
_MAX_DELAY = 60             # Maximum allowed delay setting (seconds)
_NET_ERRORS = (             # Network error detection
    "ERR_NAME_NOT_RESOLVED",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_NETWORK_CHANGED",
    "ERR_CONNECTION_REFUSED",
    "ERR_CONNECTION_TIMED_OUT",
)
```

---

## macOS Build (build_mac.sh)

### Build Script Updates

**File:** build_mac.sh

**Key features:**

1. **Virtual Environment:** Uses `.venv` directory (Homebrew Python is externally managed and won't allow direct package installs)
   ```bash
   python3 -m venv "${VENV_DIR}"
   source "${VENV_DIR}/bin/activate"
   ```

2. **PyInstaller Flags:**
   - `--windowed` — no console window
   - `--collect-data customtkinter` — bundle customtkinter assets
   - `--collect-all selenium` — required; collects all Selenium webdriver modules
   - `--add-data "message.txt:."` — includes default message template
   - `--add-data "contacts.example.csv:."` — includes sample CSV

3. **DMG Creation:**
   ```bash
   hdiutil create -format UDZO -volname "WhatsApp Bulk Messenger" ...
   ```
   - `UDZO` format is compressed (smaller file size)
   - Pre-configured volume name

4. **Cleanup:**
   - `deactivate 2>/dev/null || true` — safely deactivates venv even if it fails

5. **Pre-flight Check:**
   - Verifies `contacts.example.csv` exists before bundling
   - Exits with error if missing

---

## Architecture Notes for Future Claude Instances

### File Sizes and Structure

- **app.py:** ~810 lines — approaching the 800-line max from coding-style.md
  - Consider splitting into separate modules if adding more features
  - Main classes: App (UI), thread workers

- **automator.py:** ~210 lines — clean, focused, reusable
  - Shared by GUI and CLI entry points
  - Tab indentation (pre-existing; preserve for consistency)

- **Tests:** `tests/test_automator.py`
  - Covers automator.py only (Selenium operations, contact loading, validation, retry logic)
  - No GUI tests (tkinter testing is complex; focus on automator logic)

### GUI vs. CLI Template Paths

**Important:** The GUI and CLI have different paths for reading `message.txt`:

- **GUI:** Reads directly from MESSAGE_FILE (which is `~/Library/Application Support/WhatsAppBulkMessenger/message.txt` when bundled)
- **CLI:** Calls `get_message_template()` in automator.py, which reads from `_BASE_DIR/message.txt`

When frozen, the CLI's `_BASE_DIR` points to the bundled data, so it reads the default template. The GUI uses the user's writable data directory.

### Bundled vs. Runtime Files

When running from source:
- Everything is in the same directory
- `_BASE_DIR` = script directory
- `MESSAGE_FILE` = `./message.txt`
- `SAMPLE_FILE` = `./contacts.example.csv`

When bundled as `.app`:
- `_BASE_DIR` = `sys._MEIPASS` (temporary, read-only)
- `_DATA_DIR` = `~/Library/Application Support/WhatsAppBulkMessenger/` (persistent, writable)
- `MESSAGE_FILE` = `_DATA_DIR/message.txt`
- `SAMPLE_FILE` = `_BASE_DIR/contacts.example.csv` (still from bundle)

### Git Ignore Rules

- `contacts.csv` and `contacts.xlsx` — never commit real contact data
- `contacts.example.csv` — ALWAYS committed (dummy data only: 9999999999, 8888888888)
- `.DS_Store` — macOS metadata

### Indentation

- app.py: 4-space indentation
- automator.py: Tab indentation (pre-existing; preserve)
- Maintain consistency within each file

---

## Summary of Key Changes

| Area | Change | Impact |
|------|--------|--------|
| UI | Complete VSCode-inspired redesign | Better UX, modern appearance |
| Layout | 6-row grid + PanedWindow sash | Flexible, draggable panel sizing |
| Paths | Cross-platform writable user data dir | Persistent settings on all platforms |
| Security | Single-pass regex, file size guard, sanitized exceptions | Defense-in-depth |
| Features | Country code field, sample button, placeholder warnings | Improved usability |
| Build | .venv-based macOS build with proper bundling | Faster, easier builds |
| Bugs | Fixed 8 UI/logic issues (timings, dialogs, race conditions) | More stable runtime |

---

**Total LOC changes in app.py:** ~810 (complete rewrite)
**Total LOC changes in automator.py:** ~20 (security + new feature)
**Total LOC in build_mac.sh:** ~44 (new build support)
