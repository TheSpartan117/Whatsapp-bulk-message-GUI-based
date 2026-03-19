# WhatsApp Bulk Messenger

Send personalised bulk WhatsApp messages via WhatsApp Web automation using Selenium and Chrome.

Two entry points are available:

| Entry point | How to run | Best for |
|---|---|---|
| **GUI** (`app.py`) | `python app.py` | Day-to-day use |
| **CLI** (`automator.py`) | `python automator.py` | Scripting / automation |

A pre-built Windows executable (`WhatsAppBulkMessenger.exe`) is available in the [Releases](../../releases) section — no Python installation required.

A pre-built macOS app (`WhatsAppBulkMessenger.dmg`) is also available in the Releases section — no Python installation required. Drag the app to your Applications folder after opening the DMG.

---

## Prerequisites

- **Windows and macOS** (Linux untested)
- **Python 3.8+** (not needed if using the `.exe`)
- **Google Chrome** installed (required for both the Python app and the `.exe`)
- Active WhatsApp account

---

## Setup (Python)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

<!-- AUTO-GENERATED: requirements.txt -->
| Package | Pinned version |
|---------|----------------|
| `selenium` | `4.41.0` |
| `pandas` | `3.0.1` |
| `openpyxl` | `3.1.5` |
| `customtkinter` | `5.2.2` |
<!-- END AUTO-GENERATED -->

ChromeDriver is managed automatically by Selenium — no manual installation needed.

### 2. Prepare your contacts file

Create a `contacts.csv` or `contacts.xlsx` file with at minimum a `Name` column and a `Phone Number` column. Add any additional columns to use as `{placeholders}` in your message template.

See [Input Files](#input-files) for full details.

### 3. Write your message template

Edit `message.txt` with the message you want to send. Use `{ColumnName}` placeholders matching column names in your contacts file.

### 4. Run

**GUI (recommended):**
```bash
python app.py
```

**CLI:**
```bash
python automator.py
```

---

## GUI Workflow

1. **Launch Browser & Login** — opens Chrome to WhatsApp Web
2. **Scan QR / confirm session** — only required on first run; the profile is persisted
3. **I'm Logged In ✓** — confirms login and enables the Start button
4. **Sample CSV** — downloads `contacts.example.csv` as a starting template
5. **Import CSV / Excel** — loads your contacts file; the table populates dynamically
6. **Edit template** — write or paste your message in the right panel; `{placeholders}` are shown automatically
7. **Start ▶** — begins sending; progress bar and log update in real time
8. **Stop ■** — stops after the current message completes

The GUI supports Dark / Light / System themes and keeps the log capped at 1 000 lines.

---

## Input Files

### `message.txt`

The message template. Use `{ColumnName}` placeholders — each must match a column name exactly (case-sensitive).

```
Hello {Name},

This is {Remarks1} my text, {Remarks2} to you from automated {Message} messaging system.

Thank You
```

Supports Unicode and emoji.

### `contacts.csv` or `contacts.xlsx`

Required columns:

| Column | Description |
|--------|-------------|
| `Name` | Contact's display name; available as `{Name}` in the template |
| `Phone Number` | **10-digit Indian mobile number** (e.g. `9876543210`) — the `91` country code is prepended automatically. Numbers already containing the country code (12-digit, e.g. `919876543210`) are sent as-is. For international contacts, include the full country code (e.g. `447911123456` for UK). |

Any additional columns are automatically available as `{ColumnName}` placeholders. There is no limit on the number of custom columns.

A sample file (`contacts.example.csv`) is included in the repository as a starting point.

**Example CSV:**
```
Name,Phone Number,Message,Remarks1,Remarks2
Alice,9876543210,Hello,great,wonderful
Bob,8123456789,Hi,nice,amazing
```

**Phone number validation:** Numbers containing non-digit characters (spaces, dashes, `+` prefix) are skipped with a warning in the log. Strip any formatting from phone numbers before importing.

---

## Personalisation

Every column except `Phone Number` is available as a `{ColumnName}` placeholder. The name must match the column header exactly, including capitalisation.

To add a new field:
1. Add a column to your contacts file (`contacts.csv` / `contacts.xlsx`; copy `contacts.example.csv` as a starting point).
2. Reference it in `message.txt` as `{YourNewColumnName}`.

---

## Configuration

<!-- AUTO-GENERATED: automator.py constants -->
| Constant | Default | Description |
|----------|---------|-------------|
| `DELAY` | `10` | Seconds to wait for the Send button to appear per message (configurable in the GUI settings bar) |
| `SEND_DELAY` | `2` | Seconds to wait after clicking Send before moving to the next contact (configurable in the GUI settings bar) |
| `PRE_CLICK_DELAY` | `1` | Fixed pause before clicking Send so the button registers correctly |
| `POST_SEND_DELAY` | `3` | Fixed pause after Send to allow WhatsApp Web to process before navigating away |
| `CHROME_USER_DATA_DIR` | OS-specific | Chrome profile directory used to persist the WhatsApp Web session; automatically set per platform |
<!-- END AUTO-GENERATED -->

The Chrome profile location is automatically set based on your operating system:

- **Windows:** `%LOCALAPPDATA%\WABulker\User Data`
- **macOS:** `~/Library/Application Support/WABulker`
- **Linux:** `~/.config/WABulker`

To override, edit `CHROME_USER_DATA_DIR` in `automator.py`.

> Chrome must be fully closed before launching the app. Selenium cannot attach to an already-open Chrome instance using the same profile.

---

## Building the Executable

### Windows

To produce a standalone `WhatsAppBulkMessenger.exe`:

```bash
# Install build dependencies
pip install -r requirements-dev.txt

# Build
pyinstaller --noconfirm --onefile --windowed --collect-data customtkinter --name "WhatsAppBulkMessenger" app.py
```

Output is placed in `dist/WhatsAppBulkMessenger.exe` (~44 MB). The exe bundles all Python dependencies; the target machine only needs Google Chrome.

A `message.txt` file is read from and written to the same directory as the `.exe`.

### macOS

To produce a standalone `WhatsAppBulkMessenger.dmg`:

```bash
./build_mac.sh
```

The script creates a `.dmg` containing the macOS app bundle with bundled `message.txt` and `contacts.example.csv`. Simply drag the app to your Applications folder after mounting the DMG.

Requires Xcode command-line tools and `python3` in your PATH.

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

Tests cover `automator.py` only (Selenium operations, contact loading, phone number validation, retry logic). No GUI tests.

---

## How It Works

1. Reads `message.txt` as a template.
2. Reads `contacts.csv` or `contacts.xlsx` to load contacts and personalisation data.
3. Validates each phone number (digits only, 10–15 characters after country-code normalisation); invalid numbers are skipped with a log warning.
4. For each valid contact, substitutes `{ColumnName}` placeholders to produce a personalised message.
5. Opens Chrome using the configured profile (persists WhatsApp Web login between runs).
6. Navigates to `web.whatsapp.com/send?phone=<number>&text=<message>` for each contact.
7. Waits up to `DELAY` seconds for the Send button, clicks it, then waits `SEND_DELAY` seconds before the next contact.
8. Retries up to 3 times on failure; stops immediately if the Stop button is clicked.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Profile is already in use" | Close all Chrome windows before launching |
| Send button not found | Check internet connection; dismiss any WhatsApp alerts or pop-ups |
| Contact not receiving the message | Ensure the number is a valid Indian mobile number registered on WhatsApp |
| Number skipped with "invalid" warning | Remove spaces, dashes, or `+` from the phone number in your contacts file |
| Placeholder not replaced | Check that `{ColumnName}` in `message.txt` matches the column header exactly (case-sensitive) |
| ChromeDriver error | Update Google Chrome to the latest version |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
