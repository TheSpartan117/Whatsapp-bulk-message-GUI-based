import customtkinter as ctk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import os
import sys

import automator
from automator import get_driver, get_contacts, send_messages

# ── Constants ──────────────────────────────────────────────────────────────────
APP_TITLE    = "WhatsApp Bulk Messenger"
WIN_W, WIN_H = 1100, 750

# Resolve message.txt relative to the exe (frozen) or the script directory
if getattr(sys, 'frozen', False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MESSAGE_FILE = os.path.join(_BASE_DIR, "message.txt")

IDLE         = "IDLE"
BROWSER_OPEN = "BROWSER_OPEN"
LOGGED_IN    = "LOGGED_IN"
SENDING      = "SENDING"
DONE         = "DONE"


# ── Main window ────────────────────────────────────────────────────────────────
class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(f"{WIN_W}x{WIN_H}")
        self.minsize(900, 650)
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # State
        self.driver      = None
        self.contacts    = []
        self.columns     = []
        self._state      = IDLE
        self.log_queue   = queue.Queue()
        self.stop_event  = threading.Event()
        self.delay_var      = ctk.StringVar(value=str(automator.DELAY))
        self.send_delay_var = ctk.StringVar(value=str(automator.SEND_DELAY))
        self.progress_var   = ctk.DoubleVar(value=0.0)
        self.progress_lbl_var = ctk.StringVar(value="")

        # Layout (5 rows)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)   # main panel expands

        self._build_top_bar()
        self._build_main_panels()
        self._build_settings_frame()
        self._build_controls_frame()
        self._build_log_frame()

        self.set_state(IDLE)
        self._load_message_file()
        self._poll_log_queue()

    # ── Top bar ────────────────────────────────────────────────────────────────
    def _build_top_bar(self):
        bar = ctk.CTkFrame(self, corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(bar, text=APP_TITLE,
                     font=ctk.CTkFont(size=18, weight="bold")
                     ).grid(row=0, column=0, sticky="w", padx=16, pady=10)

        theme_var = ctk.StringVar(value="Dark")
        ctk.CTkOptionMenu(bar, values=["Dark", "Light", "System"],
                          variable=theme_var,
                          command=self._on_theme_change,
                          width=100
                          ).grid(row=0, column=1, padx=16, pady=10)

    def _on_theme_change(self, mode: str):
        ctk.set_appearance_mode(mode)
        self._apply_treeview_style()

    def _apply_treeview_style(self):
        mode = ctk.get_appearance_mode()
        if mode == "Dark":
            bg, fg, heading_bg = "#2b2b2b", "white", "#3b3b3b"
        else:
            bg, fg, heading_bg = "#ffffff", "#1a1a1a", "#e0e0e0"
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background=bg, foreground=fg,
                        fieldbackground=bg, rowheight=24,
                        borderwidth=0)
        style.configure("Treeview.Heading",
                        background=heading_bg, foreground=fg,
                        relief="flat")
        style.map("Treeview", background=[("selected", "#1f6aa5")])

    # ── Main two-panel area ────────────────────────────────────────────────────
    def _build_main_panels(self):
        main = ctk.CTkFrame(self)
        main.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 4))
        main.grid_columnconfigure(0, weight=45)
        main.grid_columnconfigure(1, weight=55)
        main.grid_rowconfigure(0, weight=1)

        self._build_contacts_frame(main)
        self._build_message_frame(main)

    # ── Contacts panel (left) ─────────────────────────────────────────────────
    def _build_contacts_frame(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=0, sticky="nsew", padx=(6, 3), pady=6)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(frame, text="Contacts",
                     font=ctk.CTkFont(size=14, weight="bold")
                     ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        # Button row
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 4))
        ctk.CTkButton(btn_row, text="Import CSV / Excel", width=140,
                      command=self._import_contacts
                      ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text="Add Row", width=80,
                      command=self._add_row
                      ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text="Delete Row", width=90, fg_color="#c0392b",
                      hover_color="#922b21",
                      command=self._delete_row
                      ).pack(side="left")

        self._build_treeview(frame)

        self.status_lbl = ctk.CTkLabel(frame, text="0 contacts loaded",
                                       text_color="gray")
        self.status_lbl.grid(row=3, column=0, sticky="w", padx=10, pady=(2, 8))

    # ── Treeview construction ─────────────────────────────────────────────────
    def _build_treeview(self, parent):
        tree_frame = ctk.CTkFrame(parent, fg_color="transparent")
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 4))
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        self._apply_treeview_style()

        self.tree = ttk.Treeview(tree_frame, show="headings",
                                 selectmode="browse", height=12)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal",
                            command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Empty state
        self.tree["columns"] = ("empty",)
        self.tree.heading("empty", text="No file loaded — click Import to begin")
        self.tree.column("empty", width=400)

    # ── Message template panel (right) ────────────────────────────────────────
    def _build_message_frame(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=1, sticky="nsew", padx=(3, 6), pady=6)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Message Template",
                     font=ctk.CTkFont(size=14, weight="bold")
                     ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        self.template_box = ctk.CTkTextbox(frame, wrap="word",
                                           font=ctk.CTkFont(size=13))
        self.template_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 4))

        self.placeholder_lbl = ctk.CTkLabel(frame, text="",
                                            text_color="gray",
                                            font=ctk.CTkFont(size=11),
                                            wraplength=420, justify="left")
        self.placeholder_lbl.grid(row=2, column=0, sticky="w", padx=10, pady=(0, 4))

        ctk.CTkButton(frame, text="Save Template", width=130,
                      command=self._save_template
                      ).grid(row=3, column=0, sticky="e", padx=10, pady=(0, 8))

    # ── Settings bar ──────────────────────────────────────────────────────────
    def _build_settings_frame(self):
        bar = ctk.CTkFrame(self)
        bar.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))

        ctk.CTkLabel(bar, text="Delay (s):").pack(side="left", padx=(12, 4))
        ctk.CTkEntry(bar, textvariable=self.delay_var, width=55,
                     justify="center").pack(side="left", padx=(0, 16))

        ctk.CTkLabel(bar, text="Send Delay (s):").pack(side="left", padx=(0, 4))
        ctk.CTkEntry(bar, textvariable=self.send_delay_var, width=55,
                     justify="center").pack(side="left", padx=(0, 12))

    # ── Controls bar ──────────────────────────────────────────────────────────
    def _build_controls_frame(self):
        bar = ctk.CTkFrame(self)
        bar.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 4))

        self.btn_launch = ctk.CTkButton(
            bar, text="Launch Browser & Login", width=180,
            command=self._launch_browser)
        self.btn_launch.pack(side="left", padx=(12, 6), pady=10)

        self.btn_logged_in = ctk.CTkButton(
            bar, text="I'm Logged In \u2713", width=150,
            fg_color="#1e8449", hover_color="#196f3d",
            command=self._confirm_logged_in)
        self.btn_logged_in.pack(side="left", padx=(0, 6), pady=10)

        self.btn_start = ctk.CTkButton(
            bar, text="Start \u25b6", width=100,
            fg_color="#1a5276", hover_color="#154360",
            command=self._start_sending)
        self.btn_start.pack(side="left", padx=(0, 6), pady=10)

        self.btn_stop = ctk.CTkButton(
            bar, text="Stop \u25a0", width=90,
            fg_color="#922b21", hover_color="#7b241c",
            command=self._stop_sending)
        self.btn_stop.pack(side="left", padx=(0, 16), pady=10)

        self.progress_bar = ctk.CTkProgressBar(bar, variable=self.progress_var,
                                               width=200)
        self.progress_bar.pack(side="left", padx=(0, 8), pady=10)
        self.progress_bar.set(0)

        ctk.CTkLabel(bar, textvariable=self.progress_lbl_var,
                     font=ctk.CTkFont(size=12)
                     ).pack(side="left", padx=(0, 12))

    # ── Log panel ─────────────────────────────────────────────────────────────
    def _build_log_frame(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 8))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="Log",
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))

        self.log_box = ctk.CTkTextbox(frame, height=160, state="disabled",
                                      wrap="word",
                                      font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

    # ── Contacts: import ──────────────────────────────────────────────────────
    def _import_contacts(self):
        path = filedialog.askopenfilename(
            title="Import Contacts",
            filetypes=[("CSV files", "*.csv"),
                       ("Excel files", "*.xlsx"),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            contacts = get_contacts(path)
        except (ValueError, FileNotFoundError) as e:
            messagebox.showerror("Import Error", str(e))
            return
        except Exception as e:
            messagebox.showerror("Import Error", f"Could not load file:\n{e}")
            return

        if not contacts:
            messagebox.showwarning("Empty File", "The file contains no contacts.")
            return

        self.contacts = contacts

        # Reconstruct ordered column list: Name, Phone Number, then the rest
        extra = [k for k in contacts[0]['fields'] if k != 'Name']
        self.columns = ['Name', 'Phone Number'] + extra

        self._rebuild_treeview()
        self.status_lbl.configure(text=f"{len(contacts)} contacts loaded")
        self._update_placeholder_hint()
        self._log(f"Loaded {len(contacts)} contacts from {os.path.basename(path)}")

    def _rebuild_treeview(self):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = tuple(self.columns)
        for col in self.columns:
            w = 120 if col in ("Name", "Phone Number") else 90
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, minwidth=60, stretch=False)
        for c in self.contacts:
            row = [c['name'], c['number']] + [
                c['fields'].get(col, '') for col in self.columns[2:]
            ]
            self.tree.insert("", "end", values=row)

    # ── Contacts: add row ─────────────────────────────────────────────────────
    def _add_row(self):
        if not self.columns:
            messagebox.showwarning("No File Loaded",
                                   "Import a contacts file first.")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Contact")
        dialog.resizable(False, False)
        dialog.grab_set()

        entries = {}
        for i, col in enumerate(self.columns):
            ctk.CTkLabel(dialog, text=col + ":").grid(
                row=i, column=0, sticky="e", padx=(12, 4), pady=4)
            e = ctk.CTkEntry(dialog, width=240)
            e.grid(row=i, column=1, padx=(0, 12), pady=4)
            entries[col] = e

        def _confirm():
            name = entries['Name'].get().strip()
            phone = entries['Phone Number'].get().strip()
            if not name or not phone:
                messagebox.showwarning("Missing Fields",
                                       "Name and Phone Number are required.",
                                       parent=dialog)
                return
            fields = {col: entries[col].get().strip()
                      for col in self.columns if col != 'Phone Number'}
            self.contacts = self.contacts + [{'name': name, 'number': phone, 'fields': fields}]
            row = [name, phone] + [
                fields.get(col, '') for col in self.columns[2:]
            ]
            self.tree.insert("", "end", values=row)
            self.status_lbl.configure(text=f"{len(self.contacts)} contacts loaded")
            dialog.destroy()

        n = len(self.columns)
        ctk.CTkButton(dialog, text="Add", command=_confirm).grid(
            row=n, column=0, pady=(8, 12), padx=8)
        ctk.CTkButton(dialog, text="Cancel", fg_color="gray",
                      command=dialog.destroy).grid(
            row=n, column=1, pady=(8, 12), padx=8)

    # ── Contacts: delete row ──────────────────────────────────────────────────
    def _delete_row(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = self.tree.index(selected[0])
        self.tree.delete(selected[0])
        self.contacts = [c for i, c in enumerate(self.contacts) if i != idx]
        self.status_lbl.configure(text=f"{len(self.contacts)} contacts loaded")

    # ── Template: save ────────────────────────────────────────────────────────
    def _save_template(self):
        content = self.template_box.get("1.0", "end-1c")
        try:
            with open(MESSAGE_FILE, "w", encoding="utf-8") as f:
                f.write(content)
            self._log(f"Template saved to {MESSAGE_FILE}")
        except OSError as e:
            messagebox.showerror("Save Error", str(e))

    def _load_message_file(self):
        try:
            with open(MESSAGE_FILE, "r", encoding="utf-8") as f:
                self.template_box.insert("1.0", f.read())
        except FileNotFoundError:
            pass

    def _update_placeholder_hint(self):
        if not self.contacts:
            self.placeholder_lbl.configure(text="")
            return
        keys = list(self.contacts[0]['fields'].keys())
        hint = "Placeholders: " + "  ".join(f"{{{k}}}" for k in keys)
        self.placeholder_lbl.configure(text=hint)

    # ── Browser: launch ───────────────────────────────────────────────────────
    def _launch_browser(self):
        self.set_state(BROWSER_OPEN)
        self._log("Launching Chrome with WABulker profile...")

        def _worker():
            try:
                self.driver = get_driver()
                self.driver.get("https://web.whatsapp.com")
                self.log_queue.put(
                    "Browser opened. Scan the QR code if prompted, "
                    "then click 'I'm Logged In \u2713'.")
            except Exception as e:
                self.log_queue.put(
                    f"ERROR: Could not launch browser: {e}\n"
                    "Make sure Chrome is installed and fully closed.")
                self.after(0, lambda: self.set_state(IDLE))

        threading.Thread(target=_worker, daemon=True).start()

    def _confirm_logged_in(self):
        self.set_state(LOGGED_IN)
        self._log("Logged in confirmed. Ready to send messages.")

    # ── Sending ───────────────────────────────────────────────────────────────
    def _start_sending(self):
        if not self.contacts:
            messagebox.showwarning("No Contacts",
                                   "Import a contacts file before sending.")
            return
        template = self.template_box.get("1.0", "end-1c").strip()
        if not template:
            messagebox.showwarning("Empty Template",
                                   "Please write a message template first.")
            return

        self.stop_event.clear()
        self.set_state(SENDING)
        self.progress_var.set(0.0)
        total = len(self.contacts)
        self.progress_lbl_var.set(f"0 / {total}")

        try:
            _delay = int(self.delay_var.get())
            _send_delay = int(self.send_delay_var.get())
        except ValueError:
            _delay = 10
            _send_delay = 2
        if _delay < 1 or _send_delay < 1:
            messagebox.showwarning("Invalid Settings",
                                   "Delay and Send Delay must be at least 1 second.")
            self.set_state(LOGGED_IN)
            return

        contacts_snapshot = list(self.contacts)

        def _progress(sent, total):
            pct = sent / total if total else 0
            self.after(0, lambda s=sent, t=total, p=pct: (
                self.progress_var.set(p),
                self.progress_lbl_var.set(f"{s} / {t}")
            ))

        def _worker():
            try:
                send_messages(
                    self.driver,
                    contacts_snapshot,
                    template,
                    log_fn=self.log_queue.put,
                    stop_event=self.stop_event,
                    progress_fn=_progress,
                    delay=_delay,
                    send_delay=_send_delay,
                )
            except Exception as e:
                self.log_queue.put(f"ERROR during sending: {e}")
            finally:
                self.log_queue.put("Done.")
                self.after(0, lambda: self.set_state(DONE))

        threading.Thread(target=_worker, daemon=True).start()

    def _stop_sending(self):
        self.stop_event.set()
        self.btn_stop.configure(state="disabled")
        self._log("Stop signal sent — finishing current message...")

    # ── State machine ─────────────────────────────────────────────────────────
    def set_state(self, state: str):
        self._state = state
        cfg = {
            #              launch  logged_in  start   stop
            IDLE:         (True,  False,     False,  False),
            BROWSER_OPEN: (False, True,      False,  False),
            LOGGED_IN:    (False, False,     True,   False),
            SENDING:      (False, False,     False,  True),
            DONE:         (True,  False,     False,  False),
        }
        en = cfg.get(state, cfg[IDLE])
        for btn, flag in zip(
            [self.btn_launch, self.btn_logged_in, self.btn_start, self.btn_stop],
            en
        ):
            btn.configure(state="normal" if flag else "disabled")

        if state in (IDLE, DONE):
            self.progress_var.set(0.0)
            self.progress_lbl_var.set("")

    # ── Log helpers ───────────────────────────────────────────────────────────
    def _log(self, msg: str):
        self.log_queue.put(msg)

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", msg + "\n")
                line_count = int(self.log_box.index("end-1c").split(".")[0])
                if line_count > 1000:
                    self.log_box.delete("1.0", f"{line_count - 1000}.0")
                self.log_box.configure(state="disabled")
                self.log_box.see("end")
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    # ── Window close ─────────────────────────────────────────────────────────
    def _on_closing(self):
        if self._state == SENDING:
            if not messagebox.askokcancel(
                "Quit", "Sending is in progress. Stop and quit?"):
                return
            self.stop_event.set()
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception as e:
                print(f"Warning: browser cleanup error: {e}", file=sys.stderr)
        self.destroy()


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
    app = App()
    app.mainloop()
