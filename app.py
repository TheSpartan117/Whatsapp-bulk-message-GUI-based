import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import os
import platform as _platform
import shutil
import sys

import automator
from automator import get_driver, get_contacts, send_messages

# ── Constants ──────────────────────────────────────────────────────────────────
APP_TITLE    = "WhatsApp Bulk Messenger"
WIN_W, WIN_H = 1100, 780
_LOG_MAX_LINES = 1000
_MAX_DELAY     = 60   # maximum allowed delay in seconds

# Network-related Chrome error strings indicating no internet
_NET_ERRORS = (
    "ERR_NAME_NOT_RESOLVED",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_NETWORK_CHANGED",
    "ERR_CONNECTION_REFUSED",
    "ERR_CONNECTION_TIMED_OUT",
)

_BASE_DIR   = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
SAMPLE_FILE = os.path.join(_BASE_DIR, "contacts.example.csv")

def _user_data_dir() -> str:
    """Return a stable, writable directory for user data files."""
    system = _platform.system()
    if system == 'Darwin':
        base = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'WhatsAppBulkMessenger')
    elif system == 'Windows':
        base = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'WhatsAppBulkMessenger')
    else:
        base = os.path.join(os.path.expanduser('~'), '.config', 'WhatsAppBulkMessenger')
    os.makedirs(base, exist_ok=True)
    return base

# When running as a frozen .app bundle, sys._MEIPASS is a temp dir that is
# re-extracted on every launch — user-edited files written there are lost.
# Use a stable user data directory for mutable files like message.txt.
if hasattr(sys, '_MEIPASS'):
    _DATA_DIR    = _user_data_dir()
    MESSAGE_FILE = os.path.join(_DATA_DIR, "message.txt")
    # Seed with the bundled default template on first run
    if not os.path.exists(MESSAGE_FILE):
        _bundled_msg = os.path.join(_BASE_DIR, "message.txt")
        if os.path.exists(_bundled_msg):
            shutil.copy2(_bundled_msg, MESSAGE_FILE)
else:
    MESSAGE_FILE = os.path.join(_BASE_DIR, "message.txt")

IDLE         = "IDLE"
BROWSER_OPEN = "BROWSER_OPEN"
LOGGED_IN    = "LOGGED_IN"
SENDING      = "SENDING"
DONE         = "DONE"

# ── Monospace font (Menlo on macOS, Consolas elsewhere) ────────────────────────
_MONO = "Menlo" if _platform.system() == "Darwin" else "Consolas"

# ── State → status-bar metadata ───────────────────────────────────────────────
_STATE_META = {
    IDLE:         ("●  Ready",                    "#007acc"),
    BROWSER_OPEN: ("●  Waiting for login…",        "#cca700"),
    LOGGED_IN:    ("●  Logged in — ready to send", "#16825d"),
    SENDING:      ("●  Sending messages…",         "#0078d4"),
    DONE:         ("●  Done",                      "#16825d"),
}


# ── Main window ────────────────────────────────────────────────────────────────
class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(f"{WIN_W}x{WIN_H}")
        self.minsize(920, 660)
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # State
        self.driver           = None
        self.contacts         = []
        self.columns          = []
        self._state           = IDLE
        self.log_queue        = queue.Queue()
        self.stop_event       = threading.Event()
        self.delay_var        = ctk.StringVar(value=str(automator.DELAY))
        self.send_delay_var   = ctk.StringVar(value=str(automator.SEND_DELAY))
        self.country_code_var = ctk.StringVar(value="91")
        self.progress_var     = ctk.DoubleVar(value=0.0)
        self.progress_lbl_var = ctk.StringVar(value="")

        # Layout rows: 0=titlebar, 1=main panels, 2=settings, 3=controls, 4=log, 5=statusbar
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_top_bar()
        self._build_main_panels()
        self._build_settings_frame()
        self._build_controls_frame()
        self._build_log_frame()
        self._build_status_bar()

        self.set_state(IDLE)
        self._load_message_file()
        self._poll_log_queue()

    # ── Top bar ────────────────────────────────────────────────────────────────
    def _build_top_bar(self):
        bar = ctk.CTkFrame(self, corner_radius=0, height=44,
                           fg_color=("#dedede", "#2d2d2d"))
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_propagate(False)

        ctk.CTkLabel(bar,
                     text=APP_TITLE,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=("#1a1a1a", "#d4d4d4")
                     ).grid(row=0, column=0, sticky="w", padx=16, pady=0)

        self.theme_var = ctk.StringVar(value="Dark")
        ctk.CTkOptionMenu(bar,
                          values=["Dark", "Light", "System"],
                          variable=self.theme_var,
                          command=self._on_theme_change,
                          width=95, height=28,
                          fg_color=("#cccccc", "#3c3c3c"),
                          button_color=("#aaaaaa", "#555555"),
                          button_hover_color=("#999999", "#666666"),
                          text_color=("#1a1a1a", "#d4d4d4"),
                          dropdown_fg_color=("#f0f0f0", "#252526"),
                          dropdown_text_color=("#1a1a1a", "#d4d4d4"),
                          dropdown_hover_color=("#dddddd", "#094771"),
                          ).grid(row=0, column=1, padx=16, pady=0)

    def _on_theme_change(self, mode: str):
        ctk.set_appearance_mode(mode)
        self._apply_treeview_style()

    def _apply_treeview_style(self):
        mode = ctk.get_appearance_mode()
        if mode == "Dark":
            bg, fg      = "#252526", "#d4d4d4"
            heading_bg  = "#2d2d2d"
            sel_bg      = "#094771"
        else:
            bg, fg      = "#ffffff", "#1a1a1a"
            heading_bg  = "#eeeeee"
            sel_bg      = "#0078d4"

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background=bg, foreground=fg,
                        fieldbackground=bg, rowheight=26,
                        borderwidth=0,
                        font=(_MONO, 11))
        style.configure("Treeview.Heading",
                        background=heading_bg, foreground=fg,
                        relief="flat",
                        font=(_MONO, 11, "bold"),
                        padding=(6, 3))
        style.map("Treeview",
                  background=[("selected", sel_bg)],
                  foreground=[("selected", "#ffffff")])

        if hasattr(self, '_paned'):
            sash_bg = "#3c3c3c" if mode == "Dark" else "#cccccc"
            self._paned.configure(bg=sash_bg)

    # ── Main two-panel area ────────────────────────────────────────────────────
    def _build_main_panels(self):
        main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        paned = tk.PanedWindow(main, orient=tk.HORIZONTAL,
                               sashwidth=5, sashpad=0,
                               relief="flat", bd=0, bg="#3c3c3c")
        paned.grid(row=0, column=0, sticky="nsew")
        self._paned = paned

        self._build_contacts_frame(paned)
        self._build_message_frame(paned)

    # ── Contacts panel (left) ─────────────────────────────────────────────────
    def _build_contacts_frame(self, paned):
        frame = ctk.CTkFrame(paned, corner_radius=0,
                             fg_color=("#f0f0f0", "#252526"))
        paned.add(frame, minsize=300, stretch="always")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(3, weight=1)   # treeview row expands

        # ── Section header ────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(frame, corner_radius=0, height=34,
                           fg_color=("#e3e3e3", "#2d2d2d"))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(0, weight=1)
        hdr.grid_propagate(False)

        ctk.CTkLabel(hdr, text="CONTACTS",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=("#717171", "#858585")
                     ).grid(row=0, column=0, sticky="w", padx=12, pady=0)

        self.contacts_count_lbl = ctk.CTkLabel(
            hdr, text="",
            font=ctk.CTkFont(size=10),
            text_color=("#888888", "#6a6a6a"),
            fg_color=("#d0d0d0", "#3c3c3c"),
            corner_radius=8, padx=6
        )
        self.contacts_count_lbl.grid(row=0, column=1, sticky="e", padx=10, pady=0)

        # ── Thin separator ────────────────────────────────────────────────────
        ctk.CTkFrame(frame, height=1, corner_radius=0,
                     fg_color=("#cccccc", "#3c3c3c")
                     ).grid(row=1, column=0, sticky="ew")

        # ── Button row ────────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(frame, corner_radius=0,
                               fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=8, pady=(6, 4))

        _b = dict(height=28, corner_radius=4, font=ctk.CTkFont(size=12))
        ctk.CTkButton(btn_row, text="↑  Import", width=100, **_b,
                      command=self._import_contacts
                      ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text="⬇  Sample", width=100, **_b,
                      fg_color=("#2a7a34", "#16825d"),
                      hover_color=("#246b2e", "#1a9870"),
                      command=self._download_sample
                      ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text="+  Add", width=76, **_b,
                      fg_color=("#555555", "#3c3c3c"),
                      hover_color=("#444444", "#505050"),
                      command=self._add_row
                      ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text="✕  Delete", width=90, **_b,
                      fg_color=("#b02020", "#922b21"),
                      hover_color=("#8c1a1a", "#7b241c"),
                      command=self._delete_row
                      ).pack(side="left")

        # ── Treeview ──────────────────────────────────────────────────────────
        self._build_treeview(frame)

        # ── Footer label ──────────────────────────────────────────────────────
        self.status_lbl = ctk.CTkLabel(frame, text="0 contacts loaded",
                                       font=ctk.CTkFont(size=11),
                                       text_color=("#888888", "#6a6a6a"))
        self.status_lbl.grid(row=4, column=0, sticky="w", padx=12, pady=(2, 8))

    # ── Treeview construction ─────────────────────────────────────────────────
    def _build_treeview(self, parent):
        tree_frame = ctk.CTkFrame(parent, corner_radius=0,
                                  fg_color="transparent")
        tree_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 2))
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        self._apply_treeview_style()

        self.tree = ttk.Treeview(tree_frame, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.tree["columns"] = ("empty",)
        self.tree.heading("empty", text="No file loaded — click Import to begin")
        self.tree.column("empty", width=400)

    # ── Message template panel (right) ────────────────────────────────────────
    def _build_message_frame(self, paned):
        frame = ctk.CTkFrame(paned, corner_radius=0,
                             fg_color=("#f0f0f0", "#252526"))
        paned.add(frame, minsize=300, stretch="always")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)   # textbox row expands

        # ── Section header ────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(frame, corner_radius=0, height=34,
                           fg_color=("#e3e3e3", "#2d2d2d"))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)

        ctk.CTkLabel(hdr, text="MESSAGE TEMPLATE",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=("#717171", "#858585")
                     ).grid(row=0, column=0, sticky="w", padx=12, pady=0)

        # ── Thin separator ────────────────────────────────────────────────────
        ctk.CTkFrame(frame, height=1, corner_radius=0,
                     fg_color=("#cccccc", "#3c3c3c")
                     ).grid(row=1, column=0, sticky="ew")

        # ── Template textbox ──────────────────────────────────────────────────
        self.template_box = ctk.CTkTextbox(
            frame, wrap="word",
            font=ctk.CTkFont(family=_MONO, size=13),
            corner_radius=0,
            fg_color=("#fafafa", "#1e1e1e"),
            text_color=("#1a1a1a", "#d4d4d4"),
            border_width=0
        )
        self.template_box.grid(row=2, column=0, sticky="nsew", padx=10, pady=(8, 4))

        # ── Placeholder hint ──────────────────────────────────────────────────
        self.placeholder_lbl = ctk.CTkLabel(
            frame, text="",
            text_color=("#888888", "#6a9955"),
            font=ctk.CTkFont(family=_MONO, size=11),
            wraplength=420, justify="left"
        )
        self.placeholder_lbl.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 4))

        # ── Save button ───────────────────────────────────────────────────────
        ctk.CTkButton(frame, text="↑  Save Template", width=148,
                      height=28, corner_radius=4,
                      font=ctk.CTkFont(size=12),
                      command=self._save_template
                      ).grid(row=4, column=0, sticky="e", padx=12, pady=(0, 10))

    # ── Settings bar ──────────────────────────────────────────────────────────
    def _build_settings_frame(self):
        bar = ctk.CTkFrame(self, corner_radius=0, height=38,
                           fg_color=("#e8e8e8", "#2a2a2a"))
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_propagate(False)

        _lbl = dict(font=ctk.CTkFont(size=12), text_color=("#555555", "#9d9d9d"))
        _dim = dict(font=ctk.CTkFont(size=11), text_color=("#888888", "#686868"))
        _ent = dict(height=26, corner_radius=4, justify="center",
                    font=ctk.CTkFont(family=_MONO, size=12),
                    fg_color=("#ffffff", "#3c3c3c"),
                    border_color=("#bbbbbb", "#555555"), border_width=1)

        ctk.CTkLabel(bar, text="⚙", font=ctk.CTkFont(size=15),
                     text_color=("#888888", "#686868")
                     ).pack(side="left", padx=(14, 8))

        ctk.CTkLabel(bar, text="Delay:", **_lbl).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(bar, textvariable=self.delay_var, width=52, **_ent
                     ).pack(side="left")
        ctk.CTkLabel(bar, text="s", **_dim).pack(side="left", padx=(3, 18))

        ctk.CTkLabel(bar, text="Send Delay:", **_lbl).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(bar, textvariable=self.send_delay_var, width=52, **_ent
                     ).pack(side="left")
        ctk.CTkLabel(bar, text="s", **_dim).pack(side="left", padx=(3, 18))

        ctk.CTkLabel(bar, text="Country Code:", **_lbl).pack(side="left", padx=(0, 4))
        ctk.CTkLabel(bar, text="+", **_dim).pack(side="left")
        ctk.CTkEntry(bar, textvariable=self.country_code_var, width=52, **_ent
                     ).pack(side="left", padx=(2, 0))

    # ── Controls bar ──────────────────────────────────────────────────────────
    def _build_controls_frame(self):
        outer = ctk.CTkFrame(self, corner_radius=0,
                             fg_color=("#e5e5e5", "#252526"))
        outer.grid(row=3, column=0, sticky="ew")
        outer.grid_columnconfigure(0, weight=1)

        # ── Button row ────────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(outer, corner_radius=0,
                               fg_color="transparent")
        btn_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))

        _b = dict(height=30, corner_radius=4, font=ctk.CTkFont(size=12))

        self.btn_launch = ctk.CTkButton(
            btn_row, text="⚡  Launch & Login", width=170, **_b,
            command=self._launch_browser)
        self.btn_launch.pack(side="left", padx=(0, 6))

        self.btn_logged_in = ctk.CTkButton(
            btn_row, text="✓  Logged In", width=130, **_b,
            fg_color=("#16825d", "#16825d"), hover_color=("#1a9870", "#1a9870"),
            command=self._confirm_logged_in)
        self.btn_logged_in.pack(side="left", padx=(0, 6))

        self.btn_start = ctk.CTkButton(
            btn_row, text="▶  Start", width=100, **_b,
            fg_color=("#0078d4", "#0078d4"), hover_color=("#005fa3", "#005fa3"),
            command=self._start_sending)
        self.btn_start.pack(side="left", padx=(0, 6))

        self.btn_stop = ctk.CTkButton(
            btn_row, text="■  Stop", width=90, **_b,
            fg_color=("#c72e2e", "#c72e2e"), hover_color=("#a52626", "#a52626"),
            command=self._stop_sending)
        self.btn_stop.pack(side="left")

        # ── Progress row ──────────────────────────────────────────────────────
        prog_row = ctk.CTkFrame(outer, corner_radius=0,
                                fg_color="transparent")
        prog_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        self.progress_bar = ctk.CTkProgressBar(
            prog_row, variable=self.progress_var,
            height=6, corner_radius=3,
            fg_color=("#cccccc", "#3c3c3c"),
            progress_color=("#0078d4", "#0078d4")
        )
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.progress_bar.set(0)

        ctk.CTkLabel(prog_row, textvariable=self.progress_lbl_var,
                     font=ctk.CTkFont(family=_MONO, size=11),
                     text_color=("#666666", "#858585"), width=60
                     ).pack(side="left")

    # ── Log panel ─────────────────────────────────────────────────────────────
    def _build_log_frame(self):
        frame = ctk.CTkFrame(self, corner_radius=0,
                             fg_color=("#ebebeb", "#1e1e1e"))
        frame.grid(row=4, column=0, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        # Log header
        log_hdr = ctk.CTkFrame(frame, corner_radius=0, height=28,
                               fg_color=("#e0e0e0", "#2d2d2d"))
        log_hdr.grid(row=0, column=0, sticky="ew")
        log_hdr.grid_propagate(False)
        ctk.CTkLabel(log_hdr, text="OUTPUT",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=("#717171", "#858585")
                     ).grid(row=0, column=0, sticky="w", padx=12, pady=0)

        self.log_box = ctk.CTkTextbox(
            frame, height=130, state="disabled", wrap="word",
            font=ctk.CTkFont(family=_MONO, size=12),
            corner_radius=0,
            fg_color=("#f5f5f5", "#1a1a1a"),
            text_color=("#2a2a2a", "#b5cea8"),
            border_width=0
        )
        self.log_box.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

    # ── Status bar (bottom) ────────────────────────────────────────────────────
    def _build_status_bar(self):
        self._status_bar = ctk.CTkFrame(self, corner_radius=0, height=22,
                                        fg_color=("#007acc", "#007acc"))
        self._status_bar.grid(row=5, column=0, sticky="ew")
        self._status_bar.grid_propagate(False)
        self._status_bar.grid_columnconfigure(0, weight=1)

        self.status_bar_lbl = ctk.CTkLabel(
            self._status_bar, text="● Ready",
            font=ctk.CTkFont(size=11),
            text_color="#ffffff"
        )
        self.status_bar_lbl.grid(row=0, column=0, sticky="w", padx=10, pady=0)

        ctk.CTkLabel(
            self._status_bar, text=APP_TITLE,
            font=ctk.CTkFont(size=10),
            text_color="#c8daea"
        ).grid(row=0, column=1, sticky="e", padx=10, pady=0)

    # ── Contacts: import ──────────────────────────────────────────────────────
    def _import_contacts(self):
        path = filedialog.askopenfilename(
            title="Import Contacts",
            filetypes=[("CSV and Excel files", "*.csv *.xlsx"),
                       ("CSV files", "*.csv"),
                       ("Excel files", "*.xlsx")])
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
        extra = [k for k in contacts[0]['fields'] if k != 'Name']
        self.columns = ['Name', 'Phone Number'] + extra

        self._rebuild_treeview()
        n = len(contacts)
        self.status_lbl.configure(text=f"{n} contacts loaded")
        self.contacts_count_lbl.configure(text=f" {n} ")
        self._update_placeholder_hint()
        self._log(f"Loaded {n} contacts from {os.path.basename(path)}")

    def _download_sample(self):
        if not os.path.exists(SAMPLE_FILE):
            messagebox.showerror("Not Available",
                                 "Sample file not found in this installation.")
            return
        dest = filedialog.asksaveasfilename(
            title="Save Sample CSV",
            defaultextension=".csv",
            initialfile="contacts.example.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not dest:
            return
        try:
            shutil.copy2(SAMPLE_FILE, dest)
            self._log(f"Sample saved to {dest}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save sample:\n{e}")

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
        dialog.transient(self)
        dialog.lift()
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
            row = [name, phone] + [fields.get(col, '') for col in self.columns[2:]]
            self.tree.insert("", "end", values=row)
            n = len(self.contacts)
            self.status_lbl.configure(text=f"{n} contacts loaded")
            self.contacts_count_lbl.configure(text=f" {n} ")
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
        n = len(self.contacts)
        self.status_lbl.configure(text=f"{n} contacts loaded")
        self.contacts_count_lbl.configure(text=f" {n} " if n else "")

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
        self._log("Launching Chrome with WABulker profile…")

        def _worker():
            # Step 1 — launch Chrome (profile/driver errors → IDLE)
            try:
                drv = get_driver()
            except Exception as e:
                self.log_queue.put(
                    f"ERROR: Could not launch Chrome: {type(e).__name__}\n"
                    "Make sure Chrome is installed and fully closed.")
                self.after(0, lambda: self.set_state(IDLE))
                return

            # Assign driver on the main thread to avoid cross-thread visibility issues
            self.after(0, lambda d=drv: setattr(self, 'driver', d))

            # Step 2 — navigate to WhatsApp Web (network errors keep BROWSER_OPEN)
            try:
                drv.get("https://web.whatsapp.com")
                self.log_queue.put(
                    "Browser opened. Scan the QR code if prompted, "
                    "then click '✓ Logged In'.")
            except Exception as e:
                err_str = str(e)
                if any(code in err_str for code in _NET_ERRORS):
                    self.log_queue.put(
                        "No internet connection — Chrome is open but cannot reach WhatsApp Web.\n"
                        "Connect to the internet, navigate to web.whatsapp.com, "
                        "then click '✓ Logged In' once your chats are visible.")
                else:
                    self.log_queue.put(
                        f"WARNING: Could not navigate to WhatsApp Web: {type(e).__name__}\n"
                        "Chrome is open. Navigate to web.whatsapp.com manually, "
                        "then click '✓ Logged In'.")
                # Browser is open — stay in BROWSER_OPEN so the user can still log in

        threading.Thread(target=_worker, daemon=True).start()

    def _confirm_logged_in(self):
        if self.driver is None:
            messagebox.showwarning("Browser Not Ready",
                                   "Chrome hasn't launched yet. Please wait a moment.")
            return
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

        # Validate settings BEFORE committing state to avoid brief UI glitch
        try:
            _delay = int(self.delay_var.get())
            _send_delay = int(self.send_delay_var.get())
        except ValueError:
            messagebox.showwarning("Invalid Settings",
                                   "Delay and Send Delay must be whole numbers (e.g. 10).")
            return
        _country_code = self.country_code_var.get().strip()
        if _country_code and not _country_code.isdigit():
            messagebox.showwarning("Invalid Country Code",
                                   "Country Code must contain digits only (e.g. 91 for India, 1 for US).\n"
                                   "Do not include the '+' sign.")
            return
        if _delay < 1 or _send_delay < 1:
            messagebox.showwarning("Invalid Settings",
                                   "Delay and Send Delay must be at least 1 second.")
            return
        if _delay > _MAX_DELAY or _send_delay > _MAX_DELAY:
            messagebox.showwarning("Invalid Settings",
                                   f"Delay values cannot exceed {_MAX_DELAY} seconds.")
            return

        self.stop_event.clear()
        self.set_state(SENDING)
        self.progress_var.set(0.0)
        total = len(self.contacts)
        self.progress_lbl_var.set(f"0 / {total}")

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
                    country_code=_country_code,
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
        self._log("Stop signal sent — finishing current message…")

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

        # Update status bar
        if hasattr(self, 'status_bar_lbl'):
            text, color = _STATE_META.get(state, ("● Ready", "#007acc"))
            self.status_bar_lbl.configure(text=text)
            self._status_bar.configure(fg_color=(color, color))

    # ── Log helpers ───────────────────────────────────────────────────────────
    def _log(self, msg: str):
        self.log_queue.put(msg)

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", "> " + msg + "\n")
                line_count = int(self.log_box.index("end-1c").split(".")[0])
                if line_count > _LOG_MAX_LINES:
                    self.log_box.delete("1.0", f"{line_count - _LOG_MAX_LINES}.0")
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
                self._log(f"Warning: browser cleanup error — {type(e).__name__}")
        self.destroy()


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = App()
    app.mainloop()
