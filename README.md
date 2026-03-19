# WhatsApp Bulk Messenger

Send bulk WhatsApp messages via WhatsApp Web automation using Selenium and Chrome.

Built by [Aishik Das](https://www.github.com/theSpartan117).

---

## Prerequisites

- Windows (required — Chrome profile path is Windows-specific)
- Python 3.7+
- Google Chrome installed
- Active WhatsApp account

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

<!-- AUTO-GENERATED: requirements.txt -->
| Package | Version |
|---------|---------|
| `selenium` | `>=4.10.0` |
| `webdriver-manager` | latest |
<!-- END AUTO-GENERATED -->

ChromeDriver is managed automatically by Selenium 4.6+ — no manual installation needed.

### 2. Add your message

Edit `message.txt` with the message you want to send. Supports Unicode and emoji.

```
Hello,

This is my message.

Thank you
```

### 3. Add phone numbers

Edit `numbers.txt` with one number per line. **Indian numbers only — enter 10 digits without the country code.** The `91` prefix is added automatically.

```
9876543210
8123456789
```

Blank lines are ignored.

### 4. Run

```bash
python automator.py
```

A Chrome window will open to WhatsApp Web. Log in by scanning the QR code (only required on first run). Once your chats are visible, press **Enter** in the terminal to begin sending.

---

## Configuration

<!-- AUTO-GENERATED: automator.py constants -->
| Constant | Default | Description |
|----------|---------|-------------|
| `DELAY` | `10` | Seconds to wait for the Send button to appear per message |
| `CHROME_USER_DATA_DIR` | `%LOCALAPPDATA%\Google\Chrome\User Data` | Chrome profile directory used by the browser |
<!-- END AUTO-GENERATED -->

To change the Chrome profile location, edit `CHROME_USER_DATA_DIR` at the top of `automator.py`:

```python
# Custom isolated profile (won't share your regular Chrome session)
CHROME_USER_DATA_DIR = os.path.join(os.environ['LOCALAPPDATA'], 'WABulker', 'User Data')
```

> **Note:** Chrome must be fully closed before running the script. Selenium cannot attach to an already-open Chrome instance using the same profile.

---

## How It Works

1. Reads `message.txt` and URL-encodes the content
2. Reads `numbers.txt`, auto-prefixes 10-digit numbers with `91`
3. Opens Chrome using your existing Chrome profile
4. Navigates to `web.whatsapp.com/send?phone=<number>&text=<message>` for each number
5. Waits up to `DELAY` seconds for the Send button, clicks it, retries up to 3 times on failure

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Profile is already in use" | Close all Chrome windows before running |
| Send button not found | Check internet connection; dismiss any WhatsApp alerts |
| Number not receiving message | Ensure the number is on WhatsApp and format is correct (10 digits) |
| ChromeDriver error | Update Chrome to the latest version |
