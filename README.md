# WhatsApp Bulk Messenger

Send personalised bulk WhatsApp messages via WhatsApp Web automation using Selenium and Chrome.

---

## Prerequisites

- Windows (required — Chrome profile path is Windows-specific)
- Python 3.8+
- Google Chrome installed
- Active WhatsApp account

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

| Package | Version |
|---------|---------|
| `selenium` | `>=4.10.0` |
| `pandas` | `>=2.0.0` |
| `openpyxl` | `>=3.1.0` |

ChromeDriver is managed automatically by Selenium 4.6+ — no manual installation needed.

### 2. Prepare your contacts file

Create a `contacts.csv` or `contacts.xlsx` file with at minimum a `Name` column and a `Phone Number` column. Add any additional columns you want to use as placeholders in your message template.

Example columns: `Name`, `Phone Number`, `Message`, `Remarks`, `Remarks1`, `Remarks2`, `Remarks3`

See the [Input Files](#input-files) section for full details.

### 3. Write your message template

Edit `message.txt` with the message you want to send. Use `{ColumnName}` placeholders that map to column names in your contacts file.

See the [Personalisation](#personalisation) section for full details.

### 4. Run

```bash
python automator.py
```

A Chrome window will open to WhatsApp Web. Log in by scanning the QR code (only required on first run). Once your chats are visible, press **Enter** in the terminal to begin sending.

---

## Input Files

### `message.txt`

The message template sent to each contact. Use `{ColumnName}` placeholders — each placeholder must match a column name in your contacts file exactly (case-sensitive).

```
Hello {Name},

This is {Remarks1} my text, {Remarks2} to you from automated {Message} messaging system.

Thank You
```

Supports Unicode and emoji.

### `contacts.csv` or `contacts.xlsx`

The contacts file. Required columns:

| Column | Description |
|--------|-------------|
| `Name` | Contact's name, available as `{Name}` in the template |
| `Phone Number` | 10-digit Indian mobile number (e.g. `9876543210`) — the `91` country code is added automatically |

Any additional columns are automatically available as `{ColumnName}` placeholders in `message.txt`. There is no limit on the number of custom columns.

Example CSV:

```
Name,Phone Number,Message,Remarks1,Remarks2
Alice,9876543210,Hello,great,wonderful
Bob,8123456789,Hi,nice,amazing
```

> Note: `numbers.txt` is no longer used. Phone numbers must be provided in the contacts file.

---

## Personalisation

Every column in the contacts file (except `Phone Number`) is available as a `{ColumnName}` placeholder in `message.txt`. The placeholder name must match the column header exactly, including capitalisation.

To add a new personalisation field:

1. Add a new column to `contacts.csv` or `contacts.xlsx`.
2. Reference it in `message.txt` using `{YourNewColumnName}`.

Each contact receives a uniquely rendered message with their own values substituted in.

---

## Configuration

The following constants are defined at the top of `automator.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `DELAY` | `10` | Seconds to wait for the Send button to appear per message |
| `SEND_DELAY` | `2` | Seconds to wait after clicking Send before moving to the next contact |
| `CHROME_USER_DATA_DIR` | `%LOCALAPPDATA%\WABulker\User Data` | Chrome profile directory used to persist the WhatsApp Web session |

To change the Chrome profile location, edit `CHROME_USER_DATA_DIR` at the top of `automator.py`:

```python
CHROME_USER_DATA_DIR = os.path.join(os.environ['LOCALAPPDATA'], 'WABulker', 'User Data')
```

> Note: Chrome must be fully closed before running the script. Selenium cannot attach to an already-open Chrome instance that is using the same profile.

---

## How It Works

1. Reads `message.txt` as a template.
2. Reads `contacts.csv` or `contacts.xlsx` to load contacts and their personalisation data.
3. For each contact, substitutes all `{ColumnName}` placeholders with the contact's values to produce a personalised message.
4. Opens Chrome using the configured profile (persists your WhatsApp Web login between runs).
5. Navigates to `web.whatsapp.com/send?phone=<number>&text=<message>` for each contact.
6. Waits up to `DELAY` seconds for the Send button to appear, clicks it, then waits `SEND_DELAY` seconds before proceeding to the next contact.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Profile is already in use" | Close all Chrome windows before running the script |
| Send button not found | Check your internet connection; dismiss any WhatsApp pop-ups or alerts |
| Contact not receiving the message | Ensure the phone number is a valid 10-digit Indian number and is registered on WhatsApp |
| Placeholder not replaced | Check that the `{ColumnName}` in `message.txt` matches the column header in your contacts file exactly (case-sensitive) |
| ChromeDriver error | Update Google Chrome to the latest version |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` to install all dependencies |
