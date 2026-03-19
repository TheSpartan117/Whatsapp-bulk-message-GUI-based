# GUI Implementation Plan — WhatsApp Bulk Messenger

## Overview

Convert the existing Python CLI (`automator.py`) into a `customtkinter` desktop GUI app.
The CLI remains fully functional alongside the new GUI.

---

## Framework

**`customtkinter`** — modern look, pure Python, Windows-native, minimal new dependencies.

---

## Files Changed

| File | Action | Notes |
|---|---|---|
| `automator.py` | Minimal modification (~10 lines) | Add optional params to `send_messages()`. CLI unaffected. |
| `requirements.txt` | Add `customtkinter>=5.2.0` | One new line |
| `app.py` | Create new (~450 lines) | Full GUI entry point |

---

## Window Layout

```
┌──────────────────────────────────────────────────────────────┐
│  WhatsApp Bulk Messenger                    [Dark / Light]   │
├──────────────────────────┬───────────────────────────────────┤
│  CONTACTS (45%)          │  MESSAGE TEMPLATE (55%)           │
│                          │                                   │
│  [Import] [Add] [Delete] │  ┌─────────────────────────────┐ │
│  ┌─────────────────────┐ │  │  Hello {Name},              │ │
│  │ Name  | Phone | ... │ │  │                             │ │
│  │ John  | 999.. | ... │ │  │  This is {Remarks1} ...     │ │
│  │ Jane  | 888.. | ... │ │  │                             │ │
│  └─────────────────────┘ │  └─────────────────────────────┘ │
│  N contacts loaded       │  Placeholders: {Name}, {Message} │
│                          │  [Save Template]                  │
├──────────────────────────┴───────────────────────────────────┤
│  Delay [10] s    Send Delay [2] s                            │
├──────────────────────────────────────────────────────────────┤
│  [Launch Browser & Login]  [I'm Logged In ✓]                │
│  [Start ▶]  [Stop ■]    Progress ████████░░  5 / 10         │
├──────────────────────────────────────────────────────────────┤
│  LOG                                                         │
│  1/10 => Sending to John Doe (919999999999)...               │
│  Message sent to: John Doe (919999999999)                    │
└──────────────────────────────────────────────────────────────┘
```

---

## Widget Hierarchy

```
App (CTk root, grid layout, 5 rows)
│
├── Row 0 — top_bar_frame
│   ├── CTkLabel  "WhatsApp Bulk Messenger"
│   └── CTkOptionMenu  [Dark | Light | System]
│
├── Row 1 — main_frame  (rowconfigure weight=1, expands on resize)
│   ├── LEFT (columnconfigure weight=45) — contacts_frame
│   │   ├── CTkLabel  "Contacts"
│   │   ├── btn_row
│   │   │   ├── CTkButton  "Import CSV / Excel"   → import_contacts()
│   │   │   ├── CTkButton  "Add Row"              → add_row()
│   │   │   └── CTkButton  "Delete Row"           → delete_row()
│   │   ├── ttk.Treeview  (dynamic columns, scrollbars)
│   │   └── CTkLabel  "N contacts loaded"
│   │
│   └── RIGHT (columnconfigure weight=55) — message_frame
│       ├── CTkLabel  "Message Template"
│       ├── CTkTextbox  (editable, pre-filled from message.txt)
│       ├── CTkLabel  "Placeholders: {Name}, ..."
│       └── CTkButton  "Save Template"            → save_template()
│
├── Row 2 — settings_frame
│   ├── CTkLabel "Delay (s):"  +  CTkEntry (delay_var)
│   └── CTkLabel "Send Delay (s):"  +  CTkEntry (send_delay_var)
│
├── Row 3 — controls_frame
│   ├── CTkButton  "Launch Browser & Login"   → launch_browser()
│   ├── CTkButton  "I'm Logged In ✓"          → confirm_logged_in()
│   ├── CTkButton  "Start ▶"                  → start_sending()
│   ├── CTkButton  "Stop ■"                   → stop_sending()
│   ├── CTkProgressBar  (progress_var)
│   └── CTkLabel  "X / Y"
│
└── Row 4 — log_frame  (fixed height ~180 px)
    └── CTkTextbox  (read-only, auto-scroll)
```

---

## State Machine

Controls which buttons are enabled at each stage of the workflow.

| State | Launch | I'm Logged In | Start | Stop |
|---|:---:|:---:|:---:|:---:|
| `IDLE` | ✓ | — | — | — |
| `BROWSER_OPEN` | — | ✓ | — | — |
| `LOGGED_IN` | — | — | ✓ | — |
| `SENDING` | — | — | — | ✓ |
| `DONE` | ✓ | — | — | — |

All transitions go through `set_state(state)` — the single source of truth.

---

## Threading Architecture

```
Main Thread (CTk event loop)
    │
    ├── launch_browser()   ──► Worker Thread A (get_driver + navigate)
    │                               │
    │                               └── puts log msgs → queue.Queue
    │
    ├── start_sending()    ──► Worker Thread B (send_messages loop)
    │                               │
    │                               ├── puts log msgs → queue.Queue
    │                               └── reads stop_event.is_set()
    │
    └── after(100ms) ──► poll_log_queue() ──► drains queue → log_box
```

- All Selenium calls happen off the main thread — GUI never freezes
- `queue.Queue` is the thread-safe bridge for log output
- `threading.Event` carries the stop signal from `stop_sending()`
- All `set_state()` calls from worker threads use `self.after(0, lambda: ...)`

---

## Changes to `automator.py`

Only `send_messages()` is touched. New signature:

```python
def send_messages(driver, contacts, template,
                  log_fn=print, stop_event=None, progress_fn=None):
```

Changes inside the function:
- All `print()` calls → `log_fn()`
- Add at the top of the for-loop:
  ```python
  if stop_event is not None and stop_event.is_set():
      log_fn("Sending stopped by user.")
      break
  ```
- After `sent = True`, call:
  ```python
  if progress_fn is not None:
      progress_fn(idx + 1, len(contacts))
  ```

**The CLI `main()` call `send_messages(driver, contacts, template)` is unchanged** — Python's default values handle it automatically.

---

## Key Function Specs

### `import_contacts()`
1. Open `filedialog.askopenfilename()` filtered to CSV / XLSX
2. Call `get_contacts(filepath)` from `automator.py`
3. Rebuild Treeview columns dynamically from the file's column headers
4. Insert all rows
5. Update status label and placeholder hint

### `add_row()`
- Opens a `CTkToplevel` dialog with `CTkEntry` per column
- Validates Name and Phone Number are non-empty
- Appends to both Treeview and `self.contacts` list

### `delete_row()`
- Gets `tree.selection()` → `tree.index()` → removes from both Treeview and `self.contacts`
- Silent no-op if nothing selected

### `save_template()`
- Reads `template_box.get("1.0", "end-1c")`
- Writes to `message.txt`

### `launch_browser()`
- Immediately calls `set_state(BROWSER_OPEN)` to disable button
- Spawns daemon thread: `get_driver()` → `driver.get("https://web.whatsapp.com")`
- On failure: logs error, `after(0, set_state(IDLE))`

### `start_sending()`
- Reads template live from textbox (no save required)
- Validates contacts list and template are non-empty
- Clears `stop_event`, sets state to SENDING
- Spawns daemon thread: calls `send_messages()` with `log_fn`, `stop_event`, `progress_fn`
- `progress_fn` updates `progress_var` and progress label via `after(0, ...)`
- `finally` block always calls `after(0, set_state(DONE))`

### `poll_log_queue()`
```python
def poll_log_queue(self):
    try:
        while True:
            msg = self.log_queue.get_nowait()
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.configure(state="disabled")
            self.log_box.see("end")
    except queue.Empty:
        pass
    self.after(100, self.poll_log_queue)
```

### `on_closing()`
- If SENDING: ask user to confirm quit → set stop_event
- `driver.quit()` if driver exists
- `self.destroy()`

---

## How to Run

```bash
# Install dependencies (first time only)
pip install -r requirements.txt

# Launch GUI
python app.py

# CLI still works unchanged
python automator.py
```

---

## Verification Checklist

- [ ] `pip install -r requirements.txt` completes without error
- [ ] `python automator.py` — CLI works exactly as before
- [ ] `python app.py` — window opens at 1100×750, title correct
- [ ] Import `contacts.csv` — table shows all columns and rows
- [ ] Placeholder hint shows `{Name}`, `{Message}`, etc.
- [ ] Edit template, click Save — `message.txt` updated
- [ ] Click Launch Browser — Chrome opens to WhatsApp Web
- [ ] Click I'm Logged In — Start button enables
- [ ] Click Start — log fills, progress bar advances
- [ ] Click Stop mid-send — stops after current message, state resets
- [ ] Close window while sending — quit confirmation dialog appears, cleanup runs
- [ ] Add Row dialog — new contact appears in table and is sent
- [ ] Delete Row — contact removed from both table and send list
- [ ] Light/Dark toggle — theme switches live
