# Fix: Skip Non-WhatsApp Numbers Without Retrying

**Date:** 2026-03-24
**File:** `automator.py`
**Status:** Complete — shipped in v2.0.0

---

## Problem

When a phone number is not registered on WhatsApp, `_attempt_send()` returns
`False` after the `WebDriverWait` times out (waiting for the Send button that
never appears). The retry loop in `send_messages()` treats this identically
to a transient network failure and retries 2 more times, wasting ~30 seconds
per contact (3 × delay) for a condition that will never succeed.

---

## Root Cause

`_attempt_send()` returns only `True` (success) or `False` (any failure).
The retry loop cannot distinguish:

| Failure type | Should retry? |
|---|---|
| Network timeout, page not loaded | YES (transient) |
| Number not on WhatsApp | NO (permanent) |

---

## Solution

### Signal design

Add a third return value: `None` = **permanent failure** (do not retry).

| Return | Meaning | Action |
|---|---|---|
| `True` | Message sent | Call progress_fn, break |
| `None` | Number not on WhatsApp | Log skip message, break immediately |
| `False` | Transient failure | Retry (up to 3 total attempts) |

### Detection: `_is_not_on_whatsapp(driver) -> bool`

WhatsApp Web signals an invalid/unregistered number via:

1. **Native browser alert** — detected via `driver.switch_to.alert`; dismiss it and check text
2. **Page source** — WhatsApp renders a custom popup whose text appears in `driver.page_source`

Known marker strings (case-insensitive):
- `"phone number shared via url is invalid"` — WhatsApp's own error string
- `"isn't on whatsapp"` — shown in some locales

> Note: `"use whatsapp"` was removed during code review — it is too generic and
> can match normal chat message content, causing false-positive permanent skips.

### New private constant

```python
_NOT_ON_WHATSAPP_MARKERS = (
    "phone number shared via url is invalid",  # WhatsApp's own error string
    "isn't on whatsapp",                        # shown in some locales
)
```

### Modified `_attempt_send()`

```python
def _attempt_send(driver, url, name, number, log_fn, delay, send_delay):
    driver.get(url)
    try:
        click_btn = WebDriverWait(driver, delay).until(
            EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Send']")))
    except Exception as e:
        if _is_not_on_whatsapp(driver):
            return None  # permanent — caller must NOT retry
        err_type = type(e).__name__
        log_fn(f"\nCould not send to {name} ({number}): {err_type}")
        log_fn("Make sure your phone and computer is connected to the internet.")
        log_fn("If there is an alert, please dismiss it.")
        return False  # transient — caller may retry
    sleep(PRE_CLICK_DELAY)
    click_btn.click()
    sleep(send_delay)
    sleep(POST_SEND_DELAY)
    log_fn(f'Message sent to: {name} ({number})')
    return True
```

### Modified retry loop in `send_messages()`

```python
for i in range(3):
    if stop_event is not None and stop_event.is_set():
        log_fn("Sending stopped by user.")
        return
    result = _attempt_send(driver, url, name, number, log_fn, _delay, _send_delay)
    if result is True:
        if progress_fn is not None:
            progress_fn(idx + 1, len(contacts))
        break
    if result is None:  # permanent — not on WhatsApp
        log_fn(f"  Skipping {name} ({number}): number not registered on WhatsApp.")
        break
    if i < 2:
        log_fn(f"  Retry {i+1}/3 for {name}...")
else:
    log_fn(f"  Failed to send to {name} ({number}) after 3 attempts — skipped.")
```

---

## New Tests (to write FIRST — TDD)

Located in `tests/test_automator.py`, class `TestNotOnWhatsApp`:

1. `test_not_on_whatsapp_skips_immediately`
   - Mock `_is_not_on_whatsapp` → `True`
   - Mock WebDriverWait timeout
   - Assert: `WebDriverWait.until` called exactly **1 time** (no retries)
   - Assert: log contains `"not registered on WhatsApp"`

2. `test_transient_failure_still_retries`
   - Mock `_is_not_on_whatsapp` → `False`
   - Mock WebDriverWait always timeout
   - Assert: `WebDriverWait.until` called exactly **3 times** (full retries)

---

## Constraints

- Modify **`automator.py` only**
- Do NOT change signatures of `send_messages()` or `get_driver()`
- Preserve **tab indentation** (pre-existing style in `automator.py`)
- Do NOT add new dependencies
- Do NOT touch `app.py`
- All 13 existing tests must continue to pass

---

## Verification Checklist

- [x] 2 new failing tests written
- [x] `pytest tests/ -v` → 2 new FAIL, 13 existing PASS
- [x] Implementation written
- [x] `pytest tests/ -v` → all 15 PASS
- [x] `python-reviewer` agent clean (3 HIGH issues found and fixed)
- [x] `security-reviewer` agent clean (HIGH: NoAlertPresentException added)
- [x] User confirmed diff
- [x] PyInstaller exe built (`dist/WhatsAppBulkMessenger.exe`, 48 MB)
- [x] Shipped in v2.0.0 GitHub release
