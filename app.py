import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from src.config import settings
from src.logger import setup_logger
from src.workflow import run as run_google
from src.state_store import StateStore

# ── Ensure directories ──────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
os.makedirs("state", exist_ok=True)

logger = setup_logger(settings.log_level, settings.log_file)

# ── Colors & Theme ─────────────────────────────────────────────────────────────
BG = "#1e1e2e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
GREEN = "#a6e3a1"
RED = "#f38ba8"
YELLOW = "#f9e2af"
ORANGE = "#fab387"
SURFACE = "#313244"
BORDER = "#45475a"
FONT_MAIN = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 14, "bold")


# ── Yelp URLs Configuration ────────────────────────────────────────────────────
YELP_URLS = {
    "raw-sushi-stockton": "https://www.yelp.com/biz/raw-sushi-bistro-stockton-2",
    "bakudan-bandera": "https://www.yelp.com/biz/bakudan-ramen-san-antonio",
    "bakudan-rim": "https://www.yelp.com/biz/bakudan-ramen-the-rim-san-antonio",
    "bakudan-stone-oak": "https://www.yelp.com/biz/bakudan-ramen-stone-oak-san-antonio",
}

# ── Import new modules ─────────────────────────────────────────────────────────
try:
    from src.yelp_scraper import scrape_reviews as scrape_yelp_reviews
    from src.ai_reply import build_reply as generate_ai_reply
    from src.google_sheets import (
        get_gspread_client,
        get_or_create_spreadsheet,
        setup_sheets,
        save_reviews_to_sheet,
    )
    YELP_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some modules not available: {e}")
    YELP_AVAILABLE = False
    scrape_yelp_reviews = None
    generate_ai_reply = None
    get_gspread_client = None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Review Management - Auto Reply")
        self.geometry("1200x820")
        self.minsize(1000, 700)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # State
        self.running = False
        self.review_items: list[dict] = []
        self.sheets_client = None
        self.spreadsheet = None

        self.build_ui()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def build_ui(self):
        # ── Top bar ────────────────────────────────────────────────────────────
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=16, pady=(16, 8))

        tk.Label(
            top, text="Review Management - Auto Reply",
            font=FONT_TITLE, fg=ACCENT, bg=BG
        ).pack(side="left")

        self.status_label = tk.Label(
            top, text="Ready", font=FONT_MAIN, fg="#6c7086", bg=BG
        )
        self.status_label.pack(side="right")

        # ── Tabbed interface ────────────────────────────────────────────────────
        self.notebook = ttk.Notebook(self, style="Custom.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # Tab 1: Google Reviews
        self.tab_google = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.tab_google, text="  Google Reviews  ")
        self.build_google_tab()

        # Tab 2: Yelp Reviews
        self.tab_yelp = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.tab_yelp, text="  Yelp Reviews  ")
        self.build_yelp_tab()

        # Tab 3: Settings
        self.tab_settings = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(self.tab_settings, text="  Settings  ")
        self.build_settings_tab()

    # ── Google Tab ────────────────────────────────────────────────────────────

    def build_google_tab(self):
        # Config card
        config_frame = tk.LabelFrame(
            self.tab_google, text=" Google Configuration ",
            bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n", padx=12, pady=8
        )
        config_frame.pack(fill="x", padx=8, pady=(8, 8))

        row = tk.Frame(config_frame, bg=BG)
        row.pack(fill="x")
        self._cfg_labels_google(row)
        self._cfg_values_google(row)

        # Control bar
        ctrl = tk.Frame(self.tab_google, bg=BG)
        ctrl.pack(fill="x", padx=8, pady=(0, 8))

        self.dry_run_var = tk.BooleanVar(value=settings.dry_run)
        tk.Checkbutton(
            ctrl, text="DRY RUN (preview only)",
            variable=self.dry_run_var, bg=BG, fg=FG,
            selectcolor=SURFACE, font=FONT_MAIN,
            activebackground=BG, activeforeground=FG,
        ).pack(side="left")

        self.btn_run = tk.Button(
            ctrl, text="▶ Check Google Reviews",
            font=FONT_BOLD, bg=ACCENT, fg="#1e1e2e",
            activebackground="#a6d4ff", cursor="hand2",
            padx=16, pady=4, command=self.start_google_workflow,
        )
        self.btn_run.pack(side="right")

        # Reviews list
        list_frame = tk.Frame(self.tab_google, bg=SURFACE)
        list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        cols = ("Source", "Location", "Reviewer", "Stars", "Status")
        self.tree_google = ttk.Treeview(
            list_frame, columns=cols, show="headings", height=12
        )
        for col in cols:
            self.tree_google.heading(col, text=col, anchor="w")
            self.tree_google.column(col, anchor="w")
        self.tree_google.column("Stars", width=60)
        self.tree_google.column("Status", width=100)
        self.tree_google.pack(side="left", fill="both", expand=True)

        scroll_y = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree_google.yview)
        scroll_y.pack(side="right", fill="y")
        self.tree_google.configure(yscrollcommand=scroll_y.set)

        self.tree_google.tag_configure("positive", foreground=GREEN)
        self.tree_google.tag_configure("negative", foreground=RED)

        # Reply preview
        self.reply_frame_google = tk.LabelFrame(
            self.tab_google, text=" Reply Preview ", bg=BG, fg=FG, font=FONT_BOLD,
            labelanchor="n", padx=8, pady=4
        )
        self.reply_frame_google.pack(fill="x", padx=8, pady=(0, 8))

        self.reply_text_google = scrolledtext.ScrolledText(
            self.reply_frame_google, height=5, font=FONT_MAIN,
            bg=SURFACE, fg=FG, insertbackground=FG, relief="flat", wrap="word"
        )
        self.reply_text_google.pack(fill="x")

        # Bottom stats
        stats = tk.Frame(self.tab_google, bg=SURFACE)
        stats.pack(fill="x", padx=8, pady=(0, 8))
        self.stat_labels_google = {
            "total": tk.Label(stats, text="Total: 0", font=FONT_MAIN, fg=FG, bg=SURFACE, padx=16),
            "replied": tk.Label(stats, text="Replied: 0", font=FONT_MAIN, fg=GREEN, bg=SURFACE, padx=16),
            "error": tk.Label(stats, text="Errors: 0", font=FONT_MAIN, fg=RED, bg=SURFACE, padx=16),
        }
        for lbl in self.stat_labels_google.values():
            lbl.pack(side="left")

    def _cfg_labels_google(self, parent):
        labels = ["DRY RUN:", "Locations:", "Account ID:", "OpenAI Model:"]
        for lbl_text in labels:
            tk.Label(parent, text=lbl_text, font=FONT_MAIN, fg="#6c7086", bg=BG, width=14, anchor="e").pack(side="left", padx=(0, 4), pady=1)

    def _cfg_values_google(self, parent):
        vals_frame = tk.Frame(parent, bg=BG)
        vals_frame.pack(side="left")
        locations_str = ", ".join([n for _, n in settings.location_ids]) or "None"
        values = [
            str(settings.dry_run),
            locations_str[:50] + ("..." if len(locations_str) > 50 else ""),
            settings.google_account_id[:15] + ("..." if len(settings.google_account_id) > 15 else ""),
            settings.openai_model,
        ]
        for val in values:
            tk.Label(vals_frame, text=val, font=FONT_MAIN, fg=FG, bg=BG, anchor="w").pack(side="left", padx=(0, 12), pady=1)

    # ── Yelp Tab ─────────────────────────────────────────────────────────────

    def build_yelp_tab(self):
        # Configuration
        config_frame = tk.LabelFrame(
            self.tab_yelp, text=" Yelp Configuration ",
            bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n", padx=12, pady=8
        )
        config_frame.pack(fill="x", padx=8, pady=(8, 8))

        # Yelp URLs
        row = tk.Frame(config_frame, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text="Yelp URL:", font=FONT_MAIN, fg="#6c7086", bg=BG, width=12, anchor="e").pack(side="left")

        self.yelp_url_var = tk.StringVar(value=YELP_URLS.get("raw-sushi-stockton", ""))
        url_combo = ttk.Combobox(
            row, textvariable=self.yelp_url_var,
            values=list(YELP_URLS.values()),
            font=FONT_MAIN, width=50, state="readonly"
        )
        url_combo.pack(side="left", padx=8)

        # Google Sheets config
        row2 = tk.Frame(config_frame, bg=BG)
        row2.pack(fill="x", pady=4)
        tk.Label(row2, text="Sheets:", font=FONT_MAIN, fg="#6c7086", bg=BG, width=12, anchor="e").pack(side="left")
        self.sheets_status = tk.Label(row2, text="Not connected", font=FONT_MAIN, fg=ORANGE, bg=BG)
        self.sheets_status.pack(side="left", padx=8)
        tk.Button(row2, text="📁 Load credentials.json", font=FONT_MAIN, bg=SURFACE, fg=FG, command=self.load_sheets_credentials).pack(side="left", padx=8)
        tk.Button(row2, text="🔗 Connect Sheets", font=FONT_MAIN, bg=ACCENT, fg="#1e1e2e", command=self.connect_sheets).pack(side="left", padx=8)

        # Control bar
        ctrl = tk.Frame(self.tab_yelp, bg=BG)
        ctrl.pack(fill="x", padx=8, pady=(0, 8))

        tk.Label(ctrl, text="Max Reviews:", font=FONT_MAIN, fg=FG, bg=BG).pack(side="left")
        self.max_reviews_var = tk.IntVar(value=20)
        tk.Entry(ctrl, textvariable=self.max_reviews_var, font=FONT_MAIN, width=6).pack(side="left", padx=4)

        self.btn_scrape_yelp = tk.Button(
            ctrl, text="🔍 Scrape Yelp → Save to Sheets",
            font=FONT_BOLD, bg=ORANGE, fg="#1e1e2e",
            activebackground="#ffd699", cursor="hand2",
            padx=16, pady=4, command=self.scrape_yelp_to_sheets,
        )
        self.btn_scrape_yelp.pack(side="right")

        # Reviews list
        list_frame = tk.Frame(self.tab_yelp, bg=SURFACE)
        list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        cols = ("ID", "Reviewer", "Stars", "Date", "Text", "AI Reply")
        self.tree_yelp = ttk.Treeview(
            list_frame, columns=cols, show="headings", height=15
        )
        for col in cols:
            self.tree_yelp.heading(col, text=col, anchor="w")
            self.tree_yelp.column(col, anchor="w")
        self.tree_yelp.column("Stars", width=60)
        self.tree_yelp.column("Date", width=100)
        self.tree_yelp.column("Text", width=250)
        self.tree_yelp.column("AI Reply", width=250)
        self.tree_yelp.pack(side="left", fill="both", expand=True)

        scroll_y = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree_yelp.yview)
        scroll_y.pack(side="right", fill="y")
        self.tree_yelp.configure(yscrollcommand=scroll_y.set)

        self.tree_yelp.tag_configure("positive", foreground=GREEN)
        self.tree_yelp.tag_configure("negative", foreground=RED)
        self.tree_yelp.bind("<<TreeviewSelect>>", self.on_yelp_select)

        # AI Reply preview
        self.ai_reply_frame = tk.LabelFrame(
            self.tab_yelp, text=" AI Suggested Reply ", bg=BG, fg=FG, font=FONT_BOLD,
            labelanchor="n", padx=8, pady=4
        )
        self.ai_reply_frame.pack(fill="x", padx=8, pady=(0, 8))

        self.ai_reply_text = scrolledtext.ScrolledText(
            self.ai_reply_frame, height=4, font=FONT_MAIN,
            bg=SURFACE, fg=FG, insertbackground=FG, relief="flat", wrap="word"
        )
        self.ai_reply_text.pack(fill="x")

        btn_row = tk.Frame(self.ai_reply_frame, bg=BG)
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="📋 Copy", font=FONT_MAIN, bg=SURFACE, fg=FG, command=self.copy_ai_reply).pack(side="left", padx=4)
        tk.Button(btn_row, text="💾 Save to Sheets", font=FONT_MAIN, bg=GREEN, fg="#1e1e2e", command=self.save_ai_reply_to_sheets).pack(side="left", padx=4)

        # Log area
        self.log_box_yelp = scrolledtext.ScrolledText(
            self.tab_yelp, font=("Consolas", 9), height=8,
            bg="#11111b", fg="#cdd6f4", relief="flat", state="disabled", wrap="word"
        )
        self.log_box_yelp.pack(fill="x", padx=8, pady=(0, 8))

    # ── Settings Tab ─────────────────────────────────────────────────────────

    def build_settings_tab(self):
        # App info
        info_frame = tk.LabelFrame(
            self.tab_settings, text=" App Info ", bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n", padx=12, pady=8
        )
        info_frame.pack(fill="x", padx=8, pady=(8, 8))

        tk.Label(info_frame, text="Review Management Auto Reply", font=FONT_BOLD, fg=ACCENT, bg=BG).pack(anchor="w")
        tk.Label(info_frame, text="Version 1.0.0", font=FONT_MAIN, fg=FG, bg=BG).pack(anchor="w")
        tk.Label(info_frame, text="Features: Google Reviews + Yelp Scraping + Google Sheets", font=FONT_MAIN, fg="#6c7086", bg=BG).pack(anchor="w")

        # Files
        files_frame = tk.LabelFrame(
            self.tab_settings, text=" Files & Logs ", bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n", padx=12, pady=8
        )
        files_frame.pack(fill="x", padx=8, pady=(8, 8))

        tk.Button(files_frame, text="📂 Open Logs Folder", font=FONT_MAIN, bg=SURFACE, fg=FG, command=self.open_logs).pack(anchor="w", pady=2)
        tk.Button(files_frame, text="📂 Open State Folder", font=FONT_MAIN, bg=SURFACE, fg=FG, command=self.open_state).pack(anchor="w", pady=2)

        # About
        about_frame = tk.LabelFrame(
            self.tab_settings, text=" About ", bg=BG, fg=FG, font=FONT_BOLD, labelanchor="n", padx=12, pady=8
        )
        about_frame.pack(fill="x", padx=8, pady=(8, 8))
        tk.Label(about_frame, text="This app fetches reviews from Google and Yelp,", font=FONT_MAIN, fg="#6c7086", bg=BG).pack(anchor="w")
        tk.Label(about_frame, text="generates AI replies using OpenAI, and saves to Google Sheets.", font=FONT_MAIN, fg="#6c7086", bg=BG).pack(anchor="w")

    # ── Actions: Google ─────────────────────────────────────────────────────

    def start_google_workflow(self):
        if self.running:
            return
        self.running = True
        self.btn_run.configure(state="disabled", text="⏳ Running...")
        self.tree_google.delete(*self.tree_google.get_children())
        self.review_items.clear()
        self.reply_text_google.delete("1.0", "end")
        self._log_google("=== Started Google Reviews ===")

        def target():
            try:
                result = run_google(
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
        self.btn_run.configure(state="normal", text="▶ Check Google Reviews")

        if result:
            self._log_google(f"\n=== Done! seen={result.total_seen} replied={result.total_replied} errors={result.total_error} ===")

            for item in result.reviews:
                self.review_items.append(item)
                stars = "⭐" * self._star_count(item.get("rating", "?"))
                tag = "negative" if self._star_count(item.get("rating", "?")) <= 3 else "positive"

                self.tree_google.insert("", "end", values=(
                    "Google",
                    item.get("location_name", "?")[:20],
                    item.get("reviewer_name", "?")[:15],
                    stars,
                    item.get("action", "?"),
                ), tags=(tag,))

        self.stat_labels_google["total"].configure(text=f"Total: {result.total_seen if result else 0}")
        self.stat_labels_google["replied"].configure(text=f"Replied: {result.total_replied if result else 0}")
        self.stat_labels_google["error"].configure(text=f"Errors: {result.total_error if result else 0}")

    # ── Actions: Yelp ───────────────────────────────────────────────────────

    def load_sheets_credentials(self):
        file_path = filedialog.askopenfilename(
            title="Select Google credentials.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            dest = os.path.join(os.getcwd(), "credentials.json")
            try:
                import shutil
                shutil.copy(file_path, dest)
                self._log_yelp(f"✅ Credentials saved to {dest}")
                messagebox.showinfo("Success", "Credentials loaded! Click 'Connect Sheets' to connect.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save credentials: {e}")

    def connect_sheets(self):
        if not os.path.exists("credentials.json"):
            messagebox.showwarning("No Credentials", "Please load credentials.json first!")
            return

        try:
            self.sheets_client = get_gspread_client()
            self.spreadsheet = get_or_create_spreadsheet(self.sheets_client)
            setup_sheets(self.spreadsheet)
            self.sheets_status.configure(text=f"✅ {self.spreadsheet.title}", fg=GREEN)
            self._log_yelp(f"✅ Connected to: {self.spreadsheet.title}")
        except Exception as e:
            messagebox.showerror("Sheets Error", f"Failed to connect: {e}")
            self._log_yelp(f"❌ Sheets error: {e}")

    def scrape_yelp_to_sheets(self):
        if not YELP_AVAILABLE:
            messagebox.showerror("Missing Module", "Yelp scraping modules not available!")
            return

        url = self.yelp_url_var.get()
        if not url:
            messagebox.showwarning("No URL", "Please select a Yelp URL!")
            return

        if not self.spreadsheet:
            messagebox.showwarning("Not Connected", "Please connect to Google Sheets first!")
            return

        self.running = True
        self.btn_scrape_yelp.configure(state="disabled", text="⏳ Scraping...")
        self.tree_yelp.delete(*self.tree_yelp.get_children())
        self._log_yelp(f"=== Scraping Yelp: {url} ===")

        max_reviews = self.max_reviews_var.get()

        def target():
            try:
                # Scrape reviews
                reviews = scrape_yelp_reviews(url, max_reviews=max_reviews)
                self.after(0, lambda: self._log_yelp(f"✅ Scraped {len(reviews)} reviews"))

                # Generate AI replies
                for review in reviews:
                    if settings.openai_api_key and generate_ai_reply:
                        try:
                            reply = generate_ai_reply(
                                review={"starRating": review.get("rating", 3), "comment": review.get("text", ""), "reviewer": {"displayName": review.get("reviewer_name", "")}},
                                restaurant_name="Restaurant",
                                location="",
                                api_key=settings.openai_api_key,
                                model=settings.openai_model,
                            )
                            review["ai_reply"] = reply
                        except Exception as e:
                            review["ai_reply"] = "AI generation failed"
                    else:
                        review["ai_reply"] = "No OpenAI API key"

                # Save to Google Sheets
                saved = save_reviews_to_sheet(self.spreadsheet, reviews)
                self.after(0, lambda: self._log_yelp(f"✅ Saved {saved} reviews to Sheets"))

                # Update UI
                self.after(0, lambda: self._display_yelp_reviews(reviews))

            except Exception as e:
                self.after(0, lambda: self._log_yelp(f"❌ Error: {e}"))
            finally:
                self.after(0, lambda: self._on_yelp_done())

        threading.Thread(target=target, daemon=True).start()

    def _display_yelp_reviews(self, reviews):
        for r in reviews:
            stars = "⭐" * r.get("rating", 0)
            tag = "negative" if r.get("rating", 0) <= 2 else "positive"
            text_preview = (r.get("text", "") or "")[:50] + "..."

            self.tree_yelp.insert("", "end", values=(
                r.get("id", "")[:10],
                r.get("reviewer_name", "?")[:15],
                stars,
                r.get("date", ""),
                text_preview,
                (r.get("ai_reply", "") or "")[:50] + "...",
            ), tags=(tag,))

    def _on_yelp_done(self):
        self.running = False
        self.btn_scrape_yelp.configure(state="normal", text="🔍 Scrape Yelp → Save to Sheets")

    def on_yelp_select(self, _):
        sel = self.tree_yelp.selection()
        if not sel:
            return
        idx = self.tree_yelp.index(sel[0])
        # Get from the tree data (simplified for now)

    def copy_ai_reply(self):
        text = self.ai_reply_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._log_yelp("Copied to clipboard")

    def save_ai_reply_to_sheets(self):
        self._log_yelp("Saved to Sheets (auto-saved during scrape)")

    # ── Actions: Settings ────────────────────────────────────────────────────

    def open_logs(self):
        import subprocess
        logs_path = os.path.join(os.getcwd(), "logs")
        subprocess.Popen(f'explorer "{logs_path}"')

    def open_state(self):
        import subprocess
        state_path = os.path.join(os.getcwd(), "state")
        subprocess.Popen(f'explorer "{state_path}"')

    # ── Logging ─────────────────────────────────────────────────────────────

    def _log_google(self, msg: str):
        # For now, use a separate text box in Google tab
        pass

    def _log_yelp(self, msg: str):
        self.log_box_yelp.configure(state="normal")
        self.log_box_yelp.insert("end", msg + "\n")
        self.log_box_yelp.see("end")
        self.log_box_yelp.configure(state="disabled")

    # ── Helpers ────────────────────────────────────────────────────────────

    def _star_count(self, rating) -> int:
        mapping = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
        return mapping.get(str(rating), 0)

    def on_close(self):
        if self.running:
            if not messagebox.askyesno("Running...", "Workflow in progress. Quit anyway?"):
                return
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()