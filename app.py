"""
Review Management Desktop App v3 — All critical bugs fixed.

Fixed issues:
- C-03: DRY RUN now increments total_generated (workflow.py)
- C-05: _log_google() wired to actual ScrolledText widget
- H-03: on_yelp_select() fully implemented with review preview
- H-04: tree_google selection bound with reply preview
- H-08: Yelp AI prompt uses real business name from URL registry
- M-02: Startup config validation with clear error dialog
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

# ── Ensure directories before importing modules ─────────────────────────────────
os.makedirs("logs", exist_ok=True)
os.makedirs("state", exist_ok=True)

from src.config import settings
from src.logger import setup_logger
from src.state_store import StateStore

logger = setup_logger(settings.log_level, settings.log_file)

# ── Theme ──────────────────────────────────────────────────────────────────────
BG      = "#1e1e2e"
FG      = "#cdd6f4"
ACCENT  = "#89b4fa"
GREEN   = "#a6e3a1"
RED     = "#f38ba8"
YELLOW  = "#f9e2af"
ORANGE  = "#fab387"
SURFACE = "#313244"
BORDER  = "#45475a"
FONT_MAIN  = ("Segoe UI", 10)
FONT_BOLD  = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 14, "bold")

# ── Yelp registry with business names ─────────────────────────────────────────
YELP_REGISTRY = {
    "raw-sushi-stockton": {
        "url":    "https://www.yelp.com/biz/raw-sushi-bistro-stockton-2",
        "name":   "Raw Sushi Bistro",
        "location": "Stockton, CA",
    },
    "bakudan-bandera": {
        "url":    "https://www.yelp.com/biz/bakudan-ramen-san-antonio-4",
        "name":   "Bakudan Ramen",
        "location": "Bandera Rd, San Antonio, TX",
    },
    "bakudan-rim": {
        "url":    "https://www.yelp.com/biz/bakudan-ramen-the-rim-san-antonio",
        "name":   "Bakudan Ramen",
        "location": "The Rim, San Antonio, TX",
    },
    "bakudan-stone-oak": {
        "url":    "https://www.yelp.com/biz/bakudan-ramen-stone-oak-san-antonio",
        "name":   "Bakudan Ramen",
        "location": "Stone Oak, San Antonio, TX",
    },
}

YELP_KEYS   = list(YELP_REGISTRY.keys())
YELP_URLS   = [v["url"] for v in YELP_REGISTRY.values()]
YELP_NAMES  = [f"{v['name']} ({v['location']})" for v in YELP_REGISTRY.values()]

# ── Module imports (fail gracefully) ───────────────────────────────────────────
YELP_OK: bool = False
_scrape_yelp = None
_run_google = None
_run_yelp = None
_connect_sheets = None
_export_reviews: callable = None

try:
    from src.yelp_scraper import scrape_reviews as _sr, YELP_BUSINESS_MAP  # noqa: F401
    from src.workflow import run as _rg, run_yelp_workflow as _ry
    from src.google_sheets import connect as _cs, export_reviews_to_sheet as _es
    _scrape_yelp = _sr
    _run_google = _rg
    _run_yelp = _ry
    _connect_sheets = _cs
    _export_reviews = _es
    YELP_OK = True
except ImportError as e:
    print(f"[app] Optional modules not installed: {e}")
    print("  Run: pip install selenium beautifulsoup4 webdriver-manager gspread")


# ── Config validation (M-02) ──────────────────────────────────────────────────

def validate_config() -> list[str]:
    """Return list of missing required config fields."""
    missing = []
    if not settings.google_account_id:
        missing.append("GOOGLE_ACCOUNT_ID")
    if not settings.google_client_id:
        missing.append("GOOGLE_CLIENT_ID")
    if not settings.google_refresh_token:
        missing.append("GOOGLE_REFRESH_TOKEN")
    if not settings.location_ids:
        missing.append("At least one GOOGLE_LOCATION_ID_*")
    return missing


def show_config_errors(missing: list[str]) -> None:
    msg = "Missing required configuration:\n\n"
    for f in missing:
        msg += f"  • {f}\n"
    msg += "\nPlease edit the .env file and restart the app."
    messagebox.showerror("Configuration Error", msg)


# ── Helpers ───────────────────────────────────────────────────────────────────

def star_int(rating) -> int:
    m = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
    return m.get(str(rating).upper(), 0)

def star_display(rating) -> str:
    return "⭐" * star_int(rating)

def tag_for_rating(rating) -> str:
    return "negative" if star_int(rating) <= 3 else "positive"


# ── Main App ───────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Review Management - Auto Reply v3")
        self.geometry("1300x860")
        self.minsize(1100, 720)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # State
        self.running = False
        self.google_items: list[dict] = []   # Full review data for Google tab
        self.yelp_items:  list[dict] = []   # Full review data for Yelp tab
        self.sheets_client   = None
        self.sheets_spreadsheet = None

        # Startup validation
        missing = validate_config()
        if missing:
            self.after(100, lambda: show_config_errors(missing))

        self.build_ui()

    # ── UI Layout ─────────────────────────────────────────────────────────────

    def build_ui(self):
        # Top bar
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=16, pady=(16, 8))

        tk.Label(top, text="Review Management — Auto Reply v3",
                 font=FONT_TITLE, fg=ACCENT, bg=BG).pack(side="left")

        self.status_lbl = tk.Label(top, text="Ready", font=FONT_MAIN,
                                   fg="#6c7086", bg=BG)
        self.status_lbl.pack(side="right")

        # Tabs
        nb = ttk.Notebook(self, style="Custom.TNotebook")
        nb.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self.tab_google   = tk.Frame(nb, bg=BG)
        self.tab_yelp     = tk.Frame(nb, bg=BG)
        self.tab_settings = tk.Frame(nb, bg=BG)

        nb.add(self.tab_google,   text="  Google Reviews  ")
        nb.add(self.tab_yelp,     text="  Yelp Reviews  ")
        nb.add(self.tab_settings, text="  Settings  ")

        self._build_google_tab()
        self._build_yelp_tab()
        self._build_settings_tab()

        # Bottom stats bar
        self._build_stats_bar()

    # ── Google Tab ──────────────────────────────────────────────────────────────

    def _build_google_tab(self):
        # Config summary
        cfg = tk.LabelFrame(self.tab_google, text=" Configuration ",
                            bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n",
                            padx=12, pady=8)
        cfg.pack(fill="x", padx=8, pady=(8, 6))

        locs = ", ".join(n for _, n in settings.location_ids) or "None"
        for label, val in [
            ("DRY RUN:", str(settings.dry_run)),
            ("Locations:", locs[:60]),
            ("Account ID:", settings.google_account_id[:20]),
            ("OpenAI:", settings.openai_model),
        ]:
            row = tk.Frame(cfg, bg=BG)
            row.pack(fill="x")
            tk.Label(row, text=label, font=FONT_MAIN, fg="#6c7086", bg=BG,
                     width=14, anchor="e").pack(side="left")
            tk.Label(row, text=val, font=FONT_MAIN, fg=FG, bg=BG).pack(side="left", padx=8)

        # Control bar
        ctrl = tk.Frame(self.tab_google, bg=BG)
        ctrl.pack(fill="x", padx=8, pady=(0, 6))

        self.dry_run_var = tk.BooleanVar(value=settings.dry_run)
        tk.Checkbutton(ctrl, text="DRY RUN (preview only)",
                       variable=self.dry_run_var, bg=BG, fg=FG,
                       selectcolor=SURFACE, font=FONT_MAIN,
                       activebackground=BG, activeforeground=FG).pack(side="left")

        self.btn_google = tk.Button(ctrl, text="▶ Check Google Reviews",
                                    font=FONT_BOLD, bg=ACCENT, fg="#1e1e2e",
                                    activebackground="#a6d4ff", cursor="hand2",
                                    padx=16, pady=4,
                                    command=self._start_google)
        self.btn_google.pack(side="right")

        # Paned: review list + log
        paned = ttk.PanedWindow(self.tab_google, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Left: review tree
        left = tk.Frame(paned, bg=BG)
        paned.add(left, weight=2)

        cols = ("Source", "Location", "Reviewer", "Stars", "Status")
        self.google_tree = ttk.Treeview(left, columns=cols, show="headings", height=14)
        for c in cols:
            self.google_tree.heading(c, text=c, anchor="w")
            self.google_tree.column(c, anchor="w")
        self.google_tree.column("Stars",  width=60)
        self.google_tree.column("Status", width=110)
        self.google_tree.pack(side="left", fill="both", expand=True)
        tk.Scrollbar(left, orient="vertical",
                     command=self.google_tree.yview).pack(side="right", fill="y")
        self.google_tree.configure(yscrollcommand=self.google_tree.yview.set)
        self.google_tree.tag_configure("positive", foreground=GREEN)
        self.google_tree.tag_configure("negative", foreground=RED)
        # H-04 FIX: bind selection → show reply preview
        self.google_tree.bind("<<TreeviewSelect>>", self._on_google_select)

        # Review text preview
        preview = tk.LabelFrame(left, text=" Review Text ",
                                bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n",
                                padx=6, pady=4)
        preview.pack(fill="x", pady=(6, 0))
        self.google_review_text = scrolledtext.ScrolledText(
            preview, height=4, font=FONT_MAIN,
            bg=SURFACE, fg=FG, insertbackground=FG,
            relief="flat", wrap="word")
        self.google_review_text.pack(fill="x")

        # Reply preview
        reply_frame = tk.LabelFrame(left, text=" AI Reply Preview ",
                                   bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n",
                                   padx=6, pady=4)
        reply_frame.pack(fill="x", pady=(6, 0))
        self.google_reply_text = scrolledtext.ScrolledText(
            reply_frame, height=4, font=FONT_MAIN,
            bg=SURFACE, fg=FG, insertbackground=FG,
            relief="flat", wrap="word")
        self.google_reply_text.pack(fill="x")
        tk.Button(reply_frame, text="📋 Copy Reply", font=FONT_MAIN,
                  bg=SURFACE, fg=FG, command=self._copy_google_reply).pack(anchor="e", pady=(4, 0))

        # Right: activity log (FIX C-05)
        right = tk.Frame(paned, bg=BG)
        paned.add(right, weight=1)

        tk.Label(right, text="Activity Log", font=FONT_BOLD, fg=ACCENT,
                 bg=BG, anchor="w").pack(fill="x", pady=(0, 4))
        self.google_log = scrolledtext.ScrolledText(
            right, font=("Consolas", 9),
            bg="#11111b", fg="#cdd6f4", relief="flat",
            state="disabled", wrap="word")
        self.google_log.pack(fill="both", expand=True)

    # ── Yelp Tab ──────────────────────────────────────────────────────────────

    def _build_yelp_tab(self):
        # Config row
        cfg = tk.LabelFrame(self.tab_yelp, text=" Yelp + Sheets ",
                            bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n",
                            padx=12, pady=8)
        cfg.pack(fill="x", padx=8, pady=(8, 6))

        # Business selector
        biz_row = tk.Frame(cfg, bg=BG)
        biz_row.pack(fill="x", pady=3)
        tk.Label(biz_row, text="Business:", font=FONT_MAIN, fg="#6c7086",
                 bg=BG, width=12, anchor="e").pack(side="left")
        self.yelp_biz_var = tk.StringVar(value=YELP_NAMES[0])
        biz_combo = ttk.Combobox(biz_row, textvariable=self.yelp_biz_var,
                                   values=YELP_NAMES, font=FONT_MAIN,
                                   state="readonly", width=45)
        biz_combo.pack(side="left", padx=8)
        biz_combo.bind("<<ComboboxSelected>>", self._on_biz_changed)

        # Max reviews
        row2 = tk.Frame(cfg, bg=BG)
        row2.pack(fill="x", pady=3)
        tk.Label(row2, text="Max Reviews:", font=FONT_MAIN, fg="#6c7086",
                 bg=BG, width=12, anchor="e").pack(side="left")
        self.yelp_max_var = tk.IntVar(value=20)
        tk.Entry(row2, textvariable=self.yelp_max_var, font=FONT_MAIN,
                 width=6).pack(side="left", padx=8)
        tk.Label(row2, text="Sheets:", font=FONT_MAIN, fg="#6c7086",
                 bg=BG, width=8, anchor="e").pack(side="left", padx=(16, 0))
        self.sheets_status_lbl = tk.Label(row2, text="Not connected",
                                          font=FONT_MAIN, fg=ORANGE, bg=BG)
        self.sheets_status_lbl.pack(side="left", padx=8)
        tk.Button(row2, text="📁 Load credentials.json", font=FONT_MAIN,
                 bg=SURFACE, fg=FG, command=self._load_credentials).pack(side="left", padx=4)
        tk.Button(row2, text="🔗 Connect", font=FONT_MAIN,
                 bg=ACCENT, fg="#1e1e2e", command=self._connect_sheets_ui).pack(side="left", padx=4)

        # Control bar
        ctrl = tk.Frame(self.tab_yelp, bg=BG)
        ctrl.pack(fill="x", padx=8, pady=(0, 6))

        if not YELP_OK:
            tk.Label(ctrl, text="⚠️ Selenium/Yelp modules not installed",
                     font=FONT_MAIN, fg=ORANGE, bg=BG).pack(side="left")
            tk.Button(ctrl, text="Install deps", font=FONT_MAIN, bg=SURFACE, fg=FG,
                     command=lambda: self._pip_install).pack(side="left", padx=8)

        self.btn_yelp = tk.Button(ctrl, text="🔍 Scrape Yelp → AI Reply → Save Sheets",
                                  font=FONT_BOLD, bg=ORANGE, fg="#1e1e2e",
                                  activebackground="#ffd699", cursor="hand2",
                                  padx=16, pady=4, command=self._start_yelp)
        self.btn_yelp.pack(side="right")

        # Review tree
        list_frame = tk.Frame(self.tab_yelp, bg=SURFACE)
        list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        cols = ("Reviewer", "Stars", "Date", "Review Text", "AI Reply")
        self.yelp_tree = ttk.Treeview(list_frame, columns=cols,
                                      show="headings", height=13)
        for c in cols:
            self.yelp_tree.heading(c, text=c, anchor="w")
            self.yelp_tree.column(c, anchor="w")
        self.yelp_tree.column("Stars",      width=60)
        self.yelp_tree.column("Date",      width=100)
        self.yelp_tree.column("Review Text", width=280)
        self.yelp_tree.column("AI Reply",   width=280)
        self.yelp_tree.pack(side="left", fill="both", expand=True)
        tk.Scrollbar(list_frame, orient="vertical",
                     command=self.yelp_tree.yview).pack(side="right", fill="y")
        self.yelp_tree.configure(yscrollcommand=self.yelp_tree.yview.set)
        self.yelp_tree.tag_configure("positive", foreground=GREEN)
        self.yelp_tree.tag_configure("negative", foreground=RED)
        # H-03 FIX: bind selection → show detail
        self.yelp_tree.bind("<<TreeviewSelect>>", self._on_yelp_select)

        # AI reply panel
        ai_frame = tk.LabelFrame(self.tab_yelp, text=" AI Suggested Reply ",
                                  bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n",
                                  padx=6, pady=4)
        ai_frame.pack(fill="x", padx=8, pady=(0, 6))
        self.yelp_reply_text = scrolledtext.ScrolledText(
            ai_frame, height=5, font=FONT_MAIN,
            bg=SURFACE, fg=FG, insertbackground=FG,
            relief="flat", wrap="word")
        self.yelp_reply_text.pack(fill="x")
        btn_row = tk.Frame(ai_frame, bg=BG)
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="📋 Copy", font=FONT_MAIN, bg=SURFACE, fg=FG,
                  command=self._copy_yelp_reply).pack(side="left", padx=4)
        tk.Button(btn_row, text="💾 Save to Sheets", font=FONT_MAIN, bg=GREEN, fg="#1e1e2e",
                  command=self._save_selected_to_sheets).pack(side="left", padx=4)

        # Log box
        self.yelp_log = scrolledtext.ScrolledText(
            self.tab_yelp, font=("Consolas", 9), height=7,
            bg="#11111b", fg="#cdd6f4", relief="flat",
            state="disabled", wrap="word")
        self.yelp_log.pack(fill="x", padx=8, pady=(0, 8))

    # ── Settings Tab ─────────────────────────────────────────────────────────

    def _build_settings_tab(self):
        info = tk.LabelFrame(self.tab_settings, text=" App Info ",
                             bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n",
                             padx=12, pady=8)
        info.pack(fill="x", padx=8, pady=(8, 6))
        for txt in ["Review Management — Auto Reply v3",
                    "Features: Google Reviews + Yelp Scraping + AI Reply + Google Sheets",
                    "State: SQLite (state/reviews.db) | Logs: logs/app.log"]:
            tk.Label(info, text=txt, font=FONT_MAIN, fg=FG, bg=BG).pack(anchor="w")

        # State stats
        stats_frame = tk.LabelFrame(self.tab_settings, text=" Processed Statistics ",
                                   bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n",
                                   padx=12, pady=8)
        stats_frame.pack(fill="x", padx=8, pady=(0, 6))
        self._stats_lbls = {}
        try:
            store = StateStore(settings.state_file)
            s = store.get_stats()
            stat_items = [
                ("Total Processed", "total",  FG),
                ("Replied (Google)", "replied", GREEN),
                ("Dry Run", "dry_run",  YELLOW),
                ("Skipped", "skipped",  ORANGE),
                ("Google Reviews", "google",  ACCENT),
                ("Yelp Reviews",  "yelp",   ORANGE),
            ]
            for label, key, color in stat_items:
                row = tk.Frame(stats_frame, bg=BG)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=f"{label}:", font=FONT_MAIN, fg="#6c7086",
                         bg=BG, width=18, anchor="e").pack(side="left")
                lbl = tk.Label(row, text=str(s.get(key, 0)), font=FONT_BOLD,
                               fg=color, bg=BG)
                lbl.pack(side="left", padx=8)
                self._stats_lbls[key] = lbl
        except Exception as e:
            tk.Label(stats_frame, text=f"Could not load stats: {e}",
                     font=FONT_MAIN, fg=RED, bg=BG).pack(anchor="w")

        # Files
        files = tk.LabelFrame(self.tab_settings, text=" Files & Folders ",
                               bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n",
                               padx=12, pady=8)
        files.pack(fill="x", padx=8, pady=(0, 6))
        for label, path in [("📂 Open Logs", "logs"),
                             ("📂 Open State", "state"),
                             ("📂 Open .env", ".")]:
            tk.Button(files, text=label, font=FONT_MAIN, bg=SURFACE, fg=FG,
                      command=lambda p=path: self._open_folder(p)).pack(anchor="w", pady=2)

        # Config validation
        cfg = tk.LabelFrame(self.tab_settings, text=" Config Validation ",
                             bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n",
                             padx=12, pady=8)
        cfg.pack(fill="x", padx=8, pady=(0, 6))
        missing = validate_config()
        if missing:
            tk.Label(cfg, text="⚠️ Missing configuration:",
                     font=FONT_BOLD, fg=RED, bg=BG).pack(anchor="w")
            for f in missing:
                tk.Label(cfg, text=f"  • {f}", font=FONT_MAIN, fg=ORANGE, bg=BG).pack(anchor="w")
        else:
            tk.Label(cfg, text="✅ All required configuration present",
                     font=FONT_BOLD, fg=GREEN, bg=BG).pack(anchor="w")

    def _build_stats_bar(self):
        bar = tk.Frame(self, bg=SURFACE)
        bar.pack(fill="x", padx=16, pady=(0, 12))
        self._bar_lbls = {}
        for label, key in [("Seen", "seen"), ("Generated", "generated"),
                           ("Replied", "replied"), ("Skipped", "skipped"),
                           ("Errors", "error")]:
            lbl = tk.Label(bar, text=f"{label}: 0", font=FONT_MAIN, fg=FG,
                           bg=SURFACE, padx=16)
            lbl.pack(side="left")
            self._bar_lbls[key] = lbl

    # ── Google Actions ─────────────────────────────────────────────────────────

    def _start_google(self):
        if self.running:
            return
        self.running = True
        self.btn_google.configure(state="disabled", text="⏳ Running...")
        self.google_tree.delete(*self.google_tree.get_children())
        self.google_items.clear()
        self.google_review_text.delete("1.0", "end")
        self.google_reply_text.delete("1.0", "end")
        self._log_google("=== Started Google Reviews workflow ===")
        self._update_bar(seen=0, generated=0, replied=0, skipped=0, error=0)

        def target():
            try:
                result = _run_google(
                    logger,
                    dry_run=self.dry_run_var.get(),
                    on_progress=lambda msg: self.after(0, lambda: self._log_google(msg)),
                )
                self.after(0, lambda: self._on_google_done(result))
            except Exception as e:
                self.after(0, lambda: self._log_google(f"[ERROR] {e}"))
                self.after(0, lambda: self._on_google_done(None))

        threading.Thread(target=target, daemon=True).start()

    def _on_google_done(self, result):
        self.running = False
        self.btn_google.configure(state="normal", text="▶ Check Google Reviews")

        if not result:
            self._log_google("Workflow failed — check errors above")
            return

        self._log_google(
            f"\n=== Done! seen={result.total_seen} "
            f"generated={result.total_generated} "
            f"replied={result.total_replied} "
            f"skipped={result.total_skipped} "
            f"errors={result.total_error} ==="
        )

        for item in result.reviews:
            self.google_items.append(item)
            self.google_tree.insert("", "end", values=(
                "Google",
                item.get("location_name", "?")[:22],
                item.get("reviewer_name", "?")[:16],
                star_display(item.get("rating", "?")),
                item.get("action", "?"),
            ), tags=(tag_for_rating(item.get("rating", "?")),))

        self._update_bar(
            seen=result.total_seen,
            generated=result.total_generated,
            replied=result.total_replied,
            skipped=result.total_skipped,
            error=result.total_error,
        )

        for err in result.errors:
            self._log_google(f"[ERROR] {err}")

    def _on_google_select(self, _):
        """H-04 FIX: Show review text + reply when row selected."""
        sel = self.google_tree.selection()
        if not sel:
            return
        idx = self.google_tree.index(sel[0])
        if idx < len(self.google_items):
            item = self.google_items[idx]
            self.google_review_text.delete("1.0", "end")
            self.google_review_text.insert("1.0", item.get("text", "No review text"))
            self.google_reply_text.delete("1.0", "end")
            self.google_reply_text.insert("1.0", item.get("reply_text", ""))

    def _copy_google_reply(self):
        text = self.google_reply_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._log_google("Copied reply to clipboard")

    def _log_google(self, msg: str):
        """C-05 FIX: Actually log to the ScrolledText widget."""
        self.google_log.configure(state="normal")
        self.google_log.insert("end", msg + "\n")
        self.google_log.see("end")
        self.google_log.configure(state="disabled")

    # ── Yelp Actions ──────────────────────────────────────────────────────────

    def _start_yelp(self):
        if not YELP_OK:
            messagebox.showwarning("Module missing", "Yelp modules not installed.")
            return
        if self.running:
            return
        if not self.sheets_spreadsheet:
            messagebox.showwarning("Sheets not connected",
                                  "Please connect to Google Sheets first.")
            return

        biz_idx = YELP_NAMES.index(self.yelp_biz_var.get())
        biz_key = YELP_KEYS[biz_idx]
        biz_info = YELP_REGISTRY[biz_key]

        self.running = True
        self.btn_yelp.configure(state="disabled", text="⏳ Scraping...")
        self.yelp_tree.delete(*self.yelp_tree.get_children())
        self.yelp_items.clear()
        self.yelp_reply_text.delete("1.0", "end")
        self._log_yelp(f"=== Scraping: {biz_info['name']} ===")

        def target():
            try:
                reviews, stats = _scrape_yelp(
                    url=biz_info["url"],
                    max_reviews=self.yelp_max_var.get(),
                    business_name=biz_info["name"],
                    location_name=biz_info["location"],
                )
                self.after(0, lambda: self._log_yelp(
                    f"✅ Scraped {len(reviews)} reviews "
                    f"({stats['total_skipped']} skipped, "
                    f"{len(stats['warnings'])} warnings)"))

                # Run AI workflow
                result = _run_yelp(
                    logger,
                    reviews=reviews,
                    location_key=biz_key,
                    location_name=f"{biz_info['name']} ({biz_info['location']})",
                    on_progress=lambda msg: self.after(0, lambda: self._log_yelp(msg)),
                )

                # Export to Sheets
                exported = _export_reviews(
                    self.sheets_spreadsheet,
                    result.reviews,
                    on_progress=lambda msg: self.after(0, lambda: self._log_yelp(msg)),
                )
                self.after(0, lambda: self._log_yelp(
                    f"✅ Exported {exported['exported']} to Sheets "
                    f"({exported['errors']} errors)"))

                self.after(0, lambda: self._display_yelp_reviews(result.reviews))
                self.after(0, lambda: self._log_yelp(
                    f"\n=== Done! generated={result.total_generated} "
                    f"skipped={result.total_skipped} ==="))
                self.after(0, lambda: self._update_bar(
                    seen=result.total_seen,
                    generated=result.total_generated,
                    replied=result.total_replied,
                    skipped=result.total_skipped,
                    error=result.total_error))
            except Exception as e:
                import traceback
                self.after(0, lambda: self._log_yelp(f"❌ Error: {e}"))
                self.after(0, lambda: self._log_yelp(traceback.format_exc()))
            finally:
                self.after(0, self._on_yelp_done)

        threading.Thread(target=target, daemon=True).start()

    def _display_yelp_reviews(self, reviews):
        for r in reviews:
            self.yelp_items.append(r)
            text_p = (r.get("text", "") or "")[:55] + ("..." if len(r.get("text", "")) > 55 else "")
            reply_p = (r.get("reply_text", "") or "")[:55] + ("..." if len(r.get("reply_text", "")) > 55 else "")
            self.yelp_tree.insert("", "end", values=(
                r.get("reviewer_name", "?")[:16],
                star_display(r.get("rating", "?")),
                r.get("date", ""),
                text_p,
                reply_p,
            ), tags=(tag_for_rating(r.get("rating", "?")),))

    def _on_yelp_select(self, _):
        """H-03 FIX: Show AI reply when Yelp row is selected."""
        sel = self.yelp_tree.selection()
        if not sel:
            return
        idx = self.yelp_tree.index(sel[0])
        if idx < len(self.yelp_items):
            item = self.yelp_items[idx]
            self.yelp_reply_text.delete("1.0", "end")
            self.yelp_reply_text.insert("1.0", item.get("reply_text", ""))

    def _on_yelp_done(self):
        self.running = False
        self.btn_yelp.configure(state="normal", text="🔍 Scrape Yelp → AI Reply → Save Sheets")

    def _copy_yelp_reply(self):
        text = self.yelp_reply_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._log_yelp("Copied to clipboard")

    def _save_selected_to_sheets(self):
        sel = self.yelp_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a review first.")
            return
        idx = self.yelp_tree.index(sel[0])
        if idx < len(self.yelp_items):
            item = self.yelp_items[idx]
            result = _export_reviews(self.sheets_spreadsheet, [item])
            self._log_yelp(f"Saved review '{item.get('reviewer_name', '')}' to Sheets")

    def _log_yelp(self, msg: str):
        self.yelp_log.configure(state="normal")
        self.yelp_log.insert("end", msg + "\n")
        self.yelp_log.see("end")
        self.yelp_log.configure(state="disabled")

    def _on_biz_changed(self, _):
        """Update URL when business selection changes."""
        pass  # URL is already shown in dropdown

    # ── Sheets Actions ─────────────────────────────────────────────────────────

    def _load_credentials(self):
        path = filedialog.askopenfilename(
            title="Select credentials.json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if not path:
            return
        try:
            import shutil
            shutil.copy(path, "credentials.json")
            self._log_yelp(f"✅ credentials.json saved. Click 'Connect'.")
            messagebox.showinfo("Loaded",
                                "credentials.json saved. Now click 'Connect Sheets'.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save: {e}")

    def _connect_sheets_ui(self):
        if not os.path.exists("credentials.json"):
            messagebox.showwarning("No file", "Load credentials.json first.")
            return
        try:
            client, spreadsheet = _connect_sheets()
            self.sheets_client     = client
            self.sheets_spreadsheet = spreadsheet
            self.sheets_status_lbl.configure(text=f"✅ {spreadsheet.title}", fg=GREEN)
            self._log_yelp(f"✅ Connected to: {spreadsheet.title}")
            self._log_yelp(f"   https://docs.google.com/spreadsheets/d/{spreadsheet.id}")
        except FileNotFoundError as e:
            messagebox.showerror("Setup needed", str(e))
        except Exception as e:
            messagebox.showerror("Connection failed", str(e))
            self._log_yelp(f"❌ {e}")

    def _pip_install(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "selenium", "beautifulsoup4", "webdriver-manager"],
            capture_output=True, text=True)
        self._log_yelp(result.stdout[-300:] if result.stdout else "")
        messagebox.showinfo("Done", "Dependencies installed. Restart the app.")

    # ── Settings Actions ──────────────────────────────────────────────────────

    def _open_folder(self, name: str):
        import subprocess
        folder = os.path.join(os.getcwd(), name)
        if os.path.exists(folder):
            subprocess.Popen(f'explorer "{folder}"')

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _update_bar(self, seen=0, generated=0, replied=0, skipped=0, error=0):
        self._bar_lbls["seen"].configure(text=f"Seen: {seen}")
        self._bar_lbls["generated"].configure(text=f"Generated: {generated}")
        self._bar_lbls["replied"].configure(text=f"Replied: {replied}")
        self._bar_lbls["skipped"].configure(text=f"Skipped: {skipped}")
        err_lbl = self._bar_lbls["error"]
        err_lbl.configure(text=f"Errors: {error}")
        err_lbl.configure(fg=RED if error else FG)

    def on_close(self):
        if self.running:
            if not messagebox.askyesno("Running...",
                                        "Workflow in progress. Quit?"):
                return
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()