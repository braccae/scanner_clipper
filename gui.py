#!/usr/bin/env python3
"""
Dashboard GUI Backend - Unified pure Tkinter desktop application.
Serves a beautiful, dark-themed native dashboard window and handles
all back-end CLI script executions in background threads with real-time log capturing.
"""

import sys
import os
import re
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from pathlib import Path
import base64
import cv2

# Import local CLI utility modules
import scanner_clipper
import image_resizer
import exif_date_editor

WORKSPACE_DIR = Path(__file__).parent.resolve()

# Thread-safe logging queue
log_queue = queue.Queue()

# Harmonious Dark Color Palette
BG_DARK = "#0C0D14"       # Deep dark space blue
BG_PANEL = "#161824"      # Dark card/panel background
BG_SIDEBAR = "#07080C"    # Very dark sidebar background
COLOR_ACCENT = "#00E5FF"  # Cyan highlight
COLOR_HOVER = "#00B3CC"   # Darker cyan
COLOR_TEXT = "#FFFFFF"    # White text
COLOR_MUTED = "#8E95A5"   # Muted gray text
COLOR_SUCCESS = "#00E676" # Vibrant green
COLOR_ERROR = "#FF1744"   # Vibrant red
COLOR_BORDER = "#252836"  # Panel outline/border


class QueueStream:
    def __init__(self, q):
        self.q = q
        self.buffer = ""

    def write(self, text):
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.q.put(line.rstrip('\r\n'))

    def flush(self):
        if self.buffer:
            self.q.put(self.buffer.rstrip('\r\n'))
            self.buffer = ""


def run_tool_async(module, args):
    """Executes a CLI tool module's main() in a background thread while capturing print logs."""
    def target():
        q_stream = QueueStream(log_queue)
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = q_stream
        sys.stderr = q_stream
        
        old_argv = sys.argv
        sys.argv = [f"{module.__name__}.py"] + args
        
        log_queue.put(f"[INFO] Started execution of {module.__name__}...")
        try:
            module.main()
            q_stream.flush()
            log_queue.put(f"[SUCCESS] {module.__name__} process completed.")
        except SystemExit as se:
            q_stream.flush()
            if se.code == 0:
                log_queue.put(f"[SUCCESS] {module.__name__} process completed.")
            else:
                log_queue.put(f"[ERROR] {module.__name__} exited with code {se.code}")
        except Exception as e:
            q_stream.flush()
            log_queue.put(f"[ERROR] Execution crashed: {e}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.argv = old_argv
            log_queue.put(None) # Sentinel to flag completion
            
    threading.Thread(target=target, daemon=True).start()


def browse_directory(entry_widget):
    """Native file dialogue to select folders."""
    initial = entry_widget.get().strip() or str(WORKSPACE_DIR)
    path = filedialog.askdirectory(initialdir=initial)
    if path:
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, path)


def guess_date_from_folder_name(name):
    """Regex helper to parse dates out of folder names to pre-populate inputs."""
    # Find year (4 digits starting with 19 or 20)
    match_yr = re.search(r"(19\d{2}|20\d{2})", name)
    if not match_yr:
        return ""
    year = match_yr.group(1)
    
    # Normalized English Month Names
    months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december",
              "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
              
    name_lower = name.lower()
    for m in months:
        pattern = r"(?:\b|_)" + m + r"(?:\b|_)"
        if re.search(pattern, name_lower):
            full_month = m.capitalize()
            if len(m) == 3: # expand abbreviation
                mapping = {
                    "Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April",
                    "Jun": "June", "Jul": "July", "Aug": "August", "Sep": "September",
                    "Oct": "October", "Nov": "November", "Dec": "December"
                }
                full_month = mapping.get(full_month, full_month)
            return f"{full_month} {year}"
            
    # Search for numerical month format, e.g. YYYY-MM or MM-YYYY
    month_names = {
        "01": "January", "02": "February", "03": "March", "04": "April",
        "05": "May", "06": "June", "07": "July", "08": "August",
        "09": "September", "10": "October", "11": "November", "12": "December",
        "1": "January", "2": "February", "3": "March", "4": "April",
        "5": "May", "6": "June", "7": "July", "8": "August",
        "9": "September"
    }
    
    # Search for YYYY-MM
    match_iso = re.search(r"(?:19\d{2}|20\d{2})[-_/\s](0?[1-9]|1[0-2])(?:\b|_)", name)
    if match_iso:
        mo = match_iso.group(1)
        if len(mo) == 1:
            mo = "0" + mo
        return f"{month_names[mo]} {year}"
        
    # Search for MM-YYYY
    match_rev = re.search(r"(?:\b|_)(0?[1-9]|1[0-2])[-_/\s](?:19\d{2}|20\d{2})", name)
    if match_rev:
        mo = match_rev.group(1)
        if len(mo) == 1:
            mo = "0" + mo
        return f"{month_names[mo]} {year}"
        
    return year


class StyledEntry(tk.Entry):
    """Custom themed Tkinter Entry widget with focus highlight effects."""
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            bg="#0E0F16",
            fg=COLOR_TEXT,
            insertbackground=COLOR_ACCENT,
            relief="flat",
            borderwidth=0,
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_ACCENT,
            highlightthickness=1,
            selectbackground=COLOR_ACCENT,
            selectforeground=BG_DARK,
            font=("Helvetica", 10),
            **kwargs
        )


class StyledButton(tk.Button):
    """Flat modern button widget with hover transition states."""
    def __init__(self, parent, text, command=None, variant="primary", **kwargs):
        if variant == "primary":
            bg = COLOR_ACCENT
            fg = BG_DARK
            active_bg = COLOR_HOVER
            active_fg = BG_DARK
        elif variant == "success":
            bg = COLOR_SUCCESS
            fg = BG_DARK
            active_bg = "#00C853"
            active_fg = BG_DARK
        elif variant == "danger":
            bg = COLOR_ERROR
            fg = COLOR_TEXT
            active_bg = "#D50000"
            active_fg = COLOR_TEXT
        else: # secondary / fallback
            bg = "#252836"
            fg = COLOR_TEXT
            active_bg = "#2E3245"
            active_fg = COLOR_TEXT
            
        font = kwargs.pop("font", ("Helvetica", 10, "bold"))
        padx = kwargs.pop("padx", 12)
        pady = kwargs.pop("pady", 6)
        
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=active_fg,
            relief="flat",
            borderwidth=0,
            padx=padx,
            pady=pady,
            font=font,
            cursor="hand2",
            **kwargs
        )
        self.default_bg = bg
        self.hover_bg = active_bg
        self.bind("<Enter>", lambda e: self.config(bg=self.hover_bg) if self["state"] == "normal" else None)
        self.bind("<Leave>", lambda e: self.config(bg=self.default_bg) if self["state"] == "normal" else None)


class PhotoUtilitiesApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Photo Scanning & Metadata Utilities")
        self.root.geometry("1120x760")
        self.root.configure(bg=BG_DARK)
        self.root.minsize(1000, 680)
        
        # State variables
        self.current_thumbnails = []
        self.walkthrough_dirs = []
        self.walkthrough_root = None
        self.walkthrough_index = 0
        self.is_running = False
        
        # Styled elements config
        self.style = ttk.Style()
        self.style.theme_use('default')
        self.style.configure(
            "TCombobox", 
            fieldbackground="#0E0F16", 
            background="#252836", 
            foreground=COLOR_TEXT, 
            arrowcolor=COLOR_TEXT,
            relief="flat",
            borderwidth=0
        )
        self.root.option_add("*TCombobox*Listbox.background", "#0E0F16")
        self.root.option_add("*TCombobox*Listbox.foreground", COLOR_TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", COLOR_ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", BG_DARK)
        
        self.setup_layout()
        self.root.after(100, self.check_log_queue)

    def setup_layout(self):
        # Configure Grid weightings
        self.root.grid_columnconfigure(0, weight=0, minsize=220)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        
        # 1. Left Sidebar
        sidebar = tk.Frame(self.root, bg=BG_SIDEBAR, padx=15, pady=20)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        
        # Brand logo/header
        logo_lbl = tk.Label(sidebar, text="📷 Photo Tools", font=("Helvetica", 14, "bold"), fg=COLOR_ACCENT, bg=BG_SIDEBAR, anchor="w")
        logo_lbl.pack(fill="x", pady=(0, 25))
        
        self.sidebar_buttons = {}
        tabs = [
            ("clipper", "✂️ Scanner Clipper"),
            ("resizer", "📐 Image Resizer"),
            ("exif", "📅 EXIF Date Editor")
        ]
        
        for name, label in tabs:
            btn = tk.Button(
                sidebar,
                text=label,
                font=("Helvetica", 10, "bold"),
                fg=COLOR_TEXT,
                bg=BG_SIDEBAR,
                activebackground=BG_PANEL,
                activeforeground=COLOR_ACCENT,
                relief="flat",
                borderwidth=0,
                padx=10,
                pady=10,
                anchor="w",
                cursor="hand2",
                command=lambda n=name: self.switch_tab(n)
            )
            btn.pack(fill="x", pady=2)
            self.sidebar_buttons[name] = btn
            
        # 2. Right Split container (Panels + Console)
        right_container = tk.Frame(self.root, bg=BG_DARK)
        right_container.grid(row=0, column=1, sticky="nsew")
        right_container.grid_columnconfigure(0, weight=1)
        right_container.grid_rowconfigure(0, weight=3) # Panels
        right_container.grid_rowconfigure(1, weight=1) # Console
        
        # Content panel switcher Frame
        self.content_area = tk.Frame(right_container, bg=BG_DARK)
        self.content_area.grid(row=0, column=0, sticky="nsew", padx=20, pady=(20, 10))
        self.content_area.grid_columnconfigure(0, weight=1)
        self.content_area.grid_rowconfigure(0, weight=1)
        
        self.panels = {
            "clipper": tk.Frame(self.content_area, bg=BG_DARK),
            "resizer": tk.Frame(self.content_area, bg=BG_DARK),
            "exif": tk.Frame(self.content_area, bg=BG_DARK)
        }
        
        self.setup_clipper_panel()
        self.setup_resizer_panel()
        self.setup_exif_panel()
        
        # Console Panel
        console_frame = tk.Frame(right_container, bg=BG_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1, padx=15, pady=10)
        console_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        
        # Console Header
        console_header = tk.Frame(console_frame, bg=BG_PANEL)
        console_header.pack(fill="x", pady=(0, 5))
        
        self.status_canvas = tk.Canvas(console_header, width=12, height=12, bg=BG_PANEL, highlightthickness=0)
        self.status_canvas.pack(side="left", padx=(0, 8))
        self.status_indicator = self.status_canvas.create_oval(2, 2, 10, 10, fill=COLOR_MUTED, outline="")
        
        self.status_label = tk.Label(console_header, text="Console [Idle]", font=("Helvetica", 9, "bold"), fg=COLOR_MUTED, bg=BG_PANEL)
        self.status_label.pack(side="left")
        
        StyledButton(console_header, "Clear Logs", self.clear_console, variant="secondary", font=("Helvetica", 8, "bold"), padx=6, pady=2).pack(side="right")
        
        # Text logger window
        self.console = ScrolledText(
            console_frame,
            bg="#090A0F",
            fg="#A2A8B9",
            insertbackground=COLOR_ACCENT,
            relief="flat",
            borderwidth=0,
            font=("Courier", 9),
            state="disabled",
            height=6
        )
        self.console.pack(fill="both", expand=True)
        
        # Log style syntax tags
        self.console.tag_config("info", foreground=COLOR_ACCENT)
        self.console.tag_config("success", foreground=COLOR_SUCCESS)
        self.console.tag_config("error", foreground=COLOR_ERROR)
        self.console.tag_config("normal", foreground="#A2A8B9")
        
        # Open default clipper tab
        self.switch_tab("clipper")

    def switch_tab(self, tab_name):
        for name, panel in self.panels.items():
            panel.grid_remove()
            
        self.panels[tab_name].grid(row=0, column=0, sticky="nsew")
        
        for name, btn in self.sidebar_buttons.items():
            if name == tab_name:
                btn.config(bg=BG_PANEL, fg=COLOR_ACCENT)
            else:
                btn.config(bg=BG_SIDEBAR, fg=COLOR_TEXT)

    def create_panel_header(self, parent, title, description):
        h_frame = tk.Frame(parent, bg=BG_DARK)
        h_frame.pack(fill="x", pady=(0, 15))
        
        title_lbl = tk.Label(h_frame, text=title, font=("Helvetica", 16, "bold"), fg=COLOR_TEXT, bg=BG_DARK, anchor="w")
        title_lbl.pack(fill="x")
        
        desc_lbl = tk.Label(h_frame, text=description, font=("Helvetica", 10), fg=COLOR_MUTED, bg=BG_DARK, anchor="w")
        desc_lbl.pack(fill="x", pady=(2, 0))

    def update_status_indicator(self, text, color):
        self.status_canvas.itemconfig(self.status_indicator, fill=color)
        self.status_label.config(text=f"Console [{text}]", fg=color)

    def enable_run_buttons(self, enable):
        state = "normal" if enable else "disabled"
        self.btn_run_clipper.config(state=state)
        self.btn_run_resizer.config(state=state)
        self.btn_run_exif_bulk.config(state=state)
        if hasattr(self, 'btn_start_walkthrough'):
            self.btn_start_walkthrough.config(state=state)

    def clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", tk.END)
        self.console.configure(state="disabled")

    def write_log(self, text, tag="normal"):
        self.console.configure(state="normal")
        self.console.insert("end", text + "\n", tag)
        self.console.configure(state="disabled")
        self.console.see("end")

    def check_log_queue(self):
        try:
            while True:
                line = log_queue.get_nowait()
                if line is None:
                    self.is_running = False
                    self.update_status_indicator("Idle", COLOR_MUTED)
                    self.enable_run_buttons(True)
                    break
                
                # Dynamic syntax categorization
                tag = "normal"
                if "ERROR" in line or "Error:" in line or "Failed" in line:
                    tag = "error"
                elif "Saved:" in line or "Done!" in line or "Success" in line:
                    tag = "success"
                elif "Processing:" in line or "[INFO]" in line or "Started" in line:
                    tag = "info"
                
                self.write_log(line, tag)
        except queue.Empty:
            pass
        self.root.after(50, self.check_log_queue)

    # ==========================================
    # PANEL 1: SCANNER CLIPPER
    # ==========================================
    def setup_clipper_panel(self):
        panel = self.panels["clipper"]
        self.create_panel_header(panel, "Scanner Clipper", "Detect, extract, and auto-crop individual photos from flatbed scanner batch sheets.")
        
        card = tk.Frame(panel, bg=BG_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1, padx=20, pady=20)
        card.pack(fill="both", expand=True)
        
        # Directories Section
        tk.Label(card, text="Directories", font=("Helvetica", 11, "bold"), fg=COLOR_ACCENT, bg=BG_PANEL).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        
        tk.Label(card, text="Input Folder (Scans):", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=1, column=0, sticky="w", pady=5)
        self.clipper_input = StyledEntry(card)
        self.clipper_input.insert(0, "input")
        self.clipper_input.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        StyledButton(card, "Browse", lambda: browse_directory(self.clipper_input), variant="secondary").grid(row=1, column=2, pady=5)
        
        tk.Label(card, text="Output Folder (Extracted):", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=2, column=0, sticky="w", pady=5)
        self.clipper_output = StyledEntry(card)
        self.clipper_output.insert(0, "output")
        self.clipper_output.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        StyledButton(card, "Browse", lambda: browse_directory(self.clipper_output), variant="secondary").grid(row=2, column=2, pady=5)
        
        card.grid_columnconfigure(1, weight=1)
        
        # Divider Line
        tk.Frame(card, bg=COLOR_BORDER, height=1).grid(row=3, column=0, columnspan=3, sticky="ew", pady=15)
        
        # Settings Section
        tk.Label(card, text="Settings", font=("Helvetica", 11, "bold"), fg=COLOR_ACCENT, bg=BG_PANEL).grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 10))
        
        settings_frame = tk.Frame(card, bg=BG_PANEL)
        settings_frame.grid(row=5, column=0, columnspan=3, sticky="ew")
        
        tk.Label(settings_frame, text="Edge Shave (Pixels):", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        self.clipper_shave = StyledEntry(settings_frame, width=8)
        self.clipper_shave.insert(0, "10")
        self.clipper_shave.grid(row=0, column=1, sticky="w", pady=5)
        
        tk.Label(settings_frame, text="Grayscale Threshold (0-255):", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=0, column=2, sticky="w", padx=(20, 10), pady=5)
        self.clipper_threshold = StyledEntry(settings_frame, width=8)
        self.clipper_threshold.insert(0, "240")
        self.clipper_threshold.grid(row=0, column=3, sticky="w", pady=5)
        
        tk.Label(settings_frame, text="Output Format:", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        self.clipper_format = ttk.Combobox(settings_frame, values=["webp", "jpg", "png"], width=8, state="readonly")
        self.clipper_format.set("webp")
        self.clipper_format.grid(row=1, column=1, sticky="w", pady=5)
        
        tk.Label(settings_frame, text="Quality (0-100):", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=1, column=2, sticky="w", padx=(20, 10), pady=5)
        self.clipper_quality = StyledEntry(settings_frame, width=8)
        self.clipper_quality.insert(0, "90")
        self.clipper_quality.grid(row=1, column=3, sticky="w", pady=5)
        
        # Diagnostic Checkbox
        self.clipper_debug_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            card,
            text="Save diagnostic masks (Debug Mode)",
            variable=self.clipper_debug_var,
            fg=COLOR_TEXT,
            bg=BG_PANEL,
            activebackground=BG_PANEL,
            activeforeground=COLOR_TEXT,
            selectcolor=BG_DARK,
            relief="flat"
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=10)
        
        # Run Button
        self.btn_run_clipper = StyledButton(card, "Run Clipper", self.run_clipper, variant="primary")
        self.btn_run_clipper.grid(row=7, column=0, columnspan=3, pady=(15, 0))

    def run_clipper(self):
        if self.is_running:
            return
        inp = self.clipper_input.get().strip()
        out = self.clipper_output.get().strip()
        shave = self.clipper_shave.get().strip()
        threshold = self.clipper_threshold.get().strip()
        fmt = self.clipper_format.get().strip()
        quality = self.clipper_quality.get().strip()
        debug = self.clipper_debug_var.get()
        
        args = ["-i", inp, "-o", out, "--shave", shave, "--threshold", threshold, "-f", fmt, "-q", quality]
        if debug:
            args.append("--debug")
            
        self.is_running = True
        self.update_status_indicator("Running Clipper", COLOR_ACCENT)
        self.enable_run_buttons(False)
        self.clear_console()
        run_tool_async(scanner_clipper, args)

    # ==========================================
    # PANEL 2: IMAGE RESIZER
    # ==========================================
    def setup_resizer_panel(self):
        panel = self.panels["resizer"]
        self.create_panel_header(panel, "Image Resizer & Converter", "Downsize and format images in bulk for digital picture frames or fast sharing.")
        
        card = tk.Frame(panel, bg=BG_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1, padx=20, pady=20)
        card.pack(fill="both", expand=True)
        
        # Directories Section
        tk.Label(card, text="Directories", font=("Helvetica", 11, "bold"), fg=COLOR_ACCENT, bg=BG_PANEL).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        
        tk.Label(card, text="Input Folder:", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=1, column=0, sticky="w", pady=5)
        self.resizer_input = StyledEntry(card)
        self.resizer_input.insert(0, "output")
        self.resizer_input.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        StyledButton(card, "Browse", lambda: browse_directory(self.resizer_input), variant="secondary").grid(row=1, column=2, pady=5)
        
        tk.Label(card, text="Output Folder:", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=2, column=0, sticky="w", pady=5)
        self.resizer_output = StyledEntry(card)
        self.resizer_output.insert(0, "downsized")
        self.resizer_output.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        StyledButton(card, "Browse", lambda: browse_directory(self.resizer_output), variant="secondary").grid(row=2, column=2, pady=5)
        
        card.grid_columnconfigure(1, weight=1)
        
        # Divider Line
        tk.Frame(card, bg=COLOR_BORDER, height=1).grid(row=3, column=0, columnspan=3, sticky="ew", pady=15)
        
        # Settings Section
        tk.Label(card, text="Settings", font=("Helvetica", 11, "bold"), fg=COLOR_ACCENT, bg=BG_PANEL).grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 10))
        
        settings_frame = tk.Frame(card, bg=BG_PANEL)
        settings_frame.grid(row=5, column=0, columnspan=3, sticky="ew")
        
        tk.Label(settings_frame, text="Resizing Mode:", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        self.resizer_mode = ttk.Combobox(settings_frame, values=["Scale Factor", "Limit Maximum Dimension (px)"], width=24, state="readonly")
        self.resizer_mode.set("Scale Factor")
        self.resizer_mode.grid(row=0, column=1, columnspan=2, sticky="w", pady=5)
        self.resizer_mode.bind("<<ComboboxSelected>>", self.on_resizer_mode_changed)
        
        self.resizer_value_label = tk.Label(settings_frame, text="Scale Factor (e.g. 0.5 for 50%):", fg=COLOR_TEXT, bg=BG_PANEL)
        self.resizer_value_label.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        self.resizer_value = StyledEntry(settings_frame, width=12)
        self.resizer_value.insert(0, "0.5")
        self.resizer_value.grid(row=1, column=1, sticky="w", pady=5)
        
        tk.Label(settings_frame, text="Output Format:", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=2, column=0, sticky="w", padx=(0, 10), pady=5)
        self.resizer_format = ttk.Combobox(settings_frame, values=["jpg", "webp", "png"], width=8, state="readonly")
        self.resizer_format.set("jpg")
        self.resizer_format.grid(row=2, column=1, sticky="w", pady=5)
        
        tk.Label(settings_frame, text="Quality (0-100):", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=2, column=2, sticky="w", padx=(20, 10), pady=5)
        self.resizer_quality = StyledEntry(settings_frame, width=8)
        self.resizer_quality.insert(0, "90")
        self.resizer_quality.grid(row=2, column=3, sticky="w", pady=5)
        
        # Recursive processing Checkbox
        self.resizer_recursive_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            card,
            text="Process folder recursively",
            variable=self.resizer_recursive_var,
            fg=COLOR_TEXT,
            bg=BG_PANEL,
            activebackground=BG_PANEL,
            activeforeground=COLOR_TEXT,
            selectcolor=BG_DARK,
            relief="flat"
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=10)
        
        # Run Button
        self.btn_run_resizer = StyledButton(card, "Run Resizer", self.run_resizer, variant="primary")
        self.btn_run_resizer.grid(row=7, column=0, columnspan=3, pady=(15, 0))

    def on_resizer_mode_changed(self, event):
        mode = self.resizer_mode.get()
        if mode == "Scale Factor":
            self.resizer_value_label.config(text="Scale Factor (e.g. 0.5 for 50%):")
            self.resizer_value.delete(0, tk.END)
            self.resizer_value.insert(0, "0.5")
        else:
            self.resizer_value_label.config(text="Max Side Constraint (pixels):")
            self.resizer_value.delete(0, tk.END)
            self.resizer_value.insert(0, "1920")

    def run_resizer(self):
        if self.is_running:
            return
        inp = self.resizer_input.get().strip()
        out = self.resizer_output.get().strip()
        mode = self.resizer_mode.get()
        val = self.resizer_value.get().strip()
        fmt = self.resizer_format.get().strip()
        quality = self.resizer_quality.get().strip()
        recursive = self.resizer_recursive_var.get()
        
        args = ["-i", inp, "-o", out, "-f", fmt, "-q", quality]
        if mode == "Scale Factor":
            args.extend(["-s", val])
        else:
            args.extend(["--max-dim", val])
            
        if not recursive:
            args.append("--no-recursive")
            
        self.is_running = True
        self.update_status_indicator("Running Resizer", COLOR_ACCENT)
        self.enable_run_buttons(False)
        self.clear_console()
        run_tool_async(image_resizer, args)

    # ==========================================
    # PANEL 3: EXIF DATE EDITOR
    # ==========================================
    def setup_exif_panel(self):
        panel = self.panels["exif"]
        self.create_panel_header(panel, "EXIF Date Editor", "Bulk edit metadata to add or change the original 'Date Taken' field on photos.")
        
        # Sub-tab switch headers
        mode_bar = tk.Frame(panel, bg=BG_DARK)
        mode_bar.pack(fill="x", pady=(0, 10))
        
        self.btn_exif_mode_bulk = StyledButton(mode_bar, "Direct Bulk Update", lambda: self.set_exif_mode("bulk"), variant="secondary")
        self.btn_exif_mode_bulk.pack(side="left", padx=(0, 10))
        
        self.btn_exif_mode_walk = StyledButton(mode_bar, "Visual Walkthrough Mode", lambda: self.set_exif_mode("walkthrough"), variant="secondary")
        self.btn_exif_mode_walk.pack(side="left")
        
        # Subview content frames
        self.exif_content = tk.Frame(panel, bg=BG_DARK)
        self.exif_content.pack(fill="both", expand=True)
        
        self.exif_bulk_frame = tk.Frame(self.exif_content, bg=BG_DARK)
        self.exif_walk_frame = tk.Frame(self.exif_content, bg=BG_DARK)
        
        self.setup_exif_bulk_view()
        self.setup_exif_walk_view()
        
        self.set_exif_mode("bulk")

    def set_exif_mode(self, mode):
        self.exif_mode = mode
        if mode == "bulk":
            self.exif_walk_frame.pack_forget()
            self.exif_bulk_frame.pack(fill="both", expand=True)
            self.btn_exif_mode_bulk.config(bg=COLOR_ACCENT, fg=BG_DARK)
            self.btn_exif_mode_walk.config(bg="#252836", fg=COLOR_TEXT)
        else:
            self.exif_bulk_frame.pack_forget()
            self.exif_walk_frame.pack(fill="both", expand=True)
            self.btn_exif_mode_bulk.config(bg="#252836", fg=COLOR_TEXT)
            self.btn_exif_mode_walk.config(bg=COLOR_ACCENT, fg=BG_DARK)

    def setup_exif_bulk_view(self):
        card = tk.Frame(self.exif_bulk_frame, bg=BG_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1, padx=20, pady=20)
        card.pack(fill="both", expand=True)
        
        # Directories Section
        tk.Label(card, text="Directories", font=("Helvetica", 11, "bold"), fg=COLOR_ACCENT, bg=BG_PANEL).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        
        tk.Label(card, text="Input Folder:", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=1, column=0, sticky="w", pady=5)
        self.exif_input = StyledEntry(card)
        self.exif_input.insert(0, "output")
        self.exif_input.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        StyledButton(card, "Browse", lambda: browse_directory(self.exif_input), variant="secondary").grid(row=1, column=2, pady=5)
        
        tk.Label(card, text="Output Folder (Optional):", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=2, column=0, sticky="w", pady=5)
        self.exif_output = StyledEntry(card)
        self.exif_output.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        StyledButton(card, "Browse", lambda: browse_directory(self.exif_output), variant="secondary").grid(row=2, column=2, pady=5)
        
        card.grid_columnconfigure(1, weight=1)
        
        # Divider Line
        tk.Frame(card, bg=COLOR_BORDER, height=1).grid(row=3, column=0, columnspan=3, sticky="ew", pady=15)
        
        # Settings Section
        tk.Label(card, text="Settings", font=("Helvetica", 11, "bold"), fg=COLOR_ACCENT, bg=BG_PANEL).grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 10))
        
        settings_frame = tk.Frame(card, bg=BG_PANEL)
        settings_frame.grid(row=5, column=0, columnspan=3, sticky="ew")
        
        tk.Label(settings_frame, text="Date to Apply:", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        self.exif_date = StyledEntry(settings_frame, width=28)
        self.exif_date.grid(row=0, column=1, columnspan=2, sticky="w", pady=5)
        tk.Label(settings_frame, text="e.g. 1995-08, August 1995, 1995-08-15", fg=COLOR_MUTED, bg=BG_PANEL, font=("Helvetica", 8, "italic")).grid(row=0, column=3, sticky="w", padx=10, pady=5)
        
        tk.Label(settings_frame, text="Save Quality (0-100):", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        self.exif_quality = StyledEntry(settings_frame, width=8)
        self.exif_quality.insert(0, "95")
        self.exif_quality.grid(row=1, column=1, sticky="w", pady=5)
        
        tk.Label(settings_frame, text="Sequential Increment (s):", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=1, column=2, sticky="w", padx=(20, 10), pady=5)
        self.exif_increment = StyledEntry(settings_frame, width=8)
        self.exif_increment.insert(0, "60")
        self.exif_increment.grid(row=1, column=3, sticky="w", pady=5)
        
        # Option Checkboxes
        self.exif_random_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            card,
            text="Randomize starting hour (Daylight)",
            variable=self.exif_random_var,
            fg=COLOR_TEXT,
            bg=BG_PANEL,
            activebackground=BG_PANEL,
            activeforeground=COLOR_TEXT,
            selectcolor=BG_DARK,
            relief="flat"
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))
        
        self.exif_dry_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            card,
            text="Dry Run (Test without writing)",
            variable=self.exif_dry_var,
            fg=COLOR_TEXT,
            bg=BG_PANEL,
            activebackground=BG_PANEL,
            activeforeground=COLOR_TEXT,
            selectcolor=BG_DARK,
            relief="flat"
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(5, 10))
        
        # Run Button
        self.btn_run_exif_bulk = StyledButton(card, "Apply Dates in Bulk", self.run_exif_bulk, variant="primary")
        self.btn_run_exif_bulk.grid(row=8, column=0, columnspan=3, pady=(15, 0))

    def run_exif_bulk(self):
        if self.is_running:
            return
        inp = self.exif_input.get().strip()
        out = self.exif_output.get().strip()
        date_val = self.exif_date.get().strip()
        quality = self.exif_quality.get().strip()
        increment = self.exif_increment.get().strip()
        random_time = self.exif_random_var.get()
        dry_run = self.exif_dry_var.get()
        
        if not inp:
            messagebox.showerror("Error", "Input folder is required.")
            return
        if not date_val:
            messagebox.showerror("Error", "A date is required in bulk mode.")
            return
            
        args = ["-i", inp, "-q", quality, "--increment", increment, "-d", date_val]
        if out:
            args.extend(["-o", out])
        if random_time:
            args.append("--random-time")
        if dry_run:
            args.append("--dry-run")
            
        self.is_running = True
        self.update_status_indicator("Running EXIF Editor", COLOR_ACCENT)
        self.enable_run_buttons(False)
        self.clear_console()
        run_tool_async(exif_date_editor, args)

    # ==========================================
    # INTERACTIVE VISUAL WALKTHROUGH WIZARD
    # ==========================================
    def setup_exif_walk_view(self):
        # Walkthrough Setup View (displayed initially)
        self.walk_setup_frame = tk.Frame(self.exif_walk_frame, bg=BG_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1, padx=20, pady=20)
        self.walk_setup_frame.pack(fill="both", expand=True)
        
        card = self.walk_setup_frame
        
        # Header Section
        tk.Label(card, text="Walkthrough Setup", font=("Helvetica", 11, "bold"), fg=COLOR_ACCENT, bg=BG_PANEL).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        
        tk.Label(card, text="Input Folder:", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=1, column=0, sticky="w", pady=5)
        self.walk_input = StyledEntry(card)
        self.walk_input.insert(0, "output")
        self.walk_input.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        StyledButton(card, "Browse", lambda: browse_directory(self.walk_input), variant="secondary").grid(row=1, column=2, pady=5)
        
        tk.Label(card, text="Output Folder (Optional):", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=2, column=0, sticky="w", pady=5)
        self.walk_output = StyledEntry(card)
        self.walk_output.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        StyledButton(card, "Browse", lambda: browse_directory(self.walk_output), variant="secondary").grid(row=2, column=2, pady=5)
        
        card.grid_columnconfigure(1, weight=1)
        
        # Divider Line
        tk.Frame(card, bg=COLOR_BORDER, height=1).grid(row=3, column=0, columnspan=3, sticky="ew", pady=15)
        
        # Settings Section
        tk.Label(card, text="Settings", font=("Helvetica", 11, "bold"), fg=COLOR_ACCENT, bg=BG_PANEL).grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 10))
        
        settings_frame = tk.Frame(card, bg=BG_PANEL)
        settings_frame.grid(row=5, column=0, columnspan=3, sticky="ew")
        
        tk.Label(settings_frame, text="Save Quality (0-100):", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=5)
        self.walk_quality = StyledEntry(settings_frame, width=8)
        self.walk_quality.insert(0, "95")
        self.walk_quality.grid(row=0, column=1, sticky="w", pady=5)
        
        tk.Label(settings_frame, text="Sequential Increment (s):", fg=COLOR_TEXT, bg=BG_PANEL).grid(row=0, column=2, sticky="w", padx=(20, 10), pady=5)
        self.walk_increment = StyledEntry(settings_frame, width=8)
        self.walk_increment.insert(0, "60")
        self.walk_increment.grid(row=0, column=3, sticky="w", pady=5)
        
        # Options Checkboxes
        self.walk_random_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            card,
            text="Randomize starting hour (Daylight)",
            variable=self.walk_random_var,
            fg=COLOR_TEXT,
            bg=BG_PANEL,
            activebackground=BG_PANEL,
            activeforeground=COLOR_TEXT,
            selectcolor=BG_DARK,
            relief="flat"
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))
        
        self.walk_dry_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            card,
            text="Dry Run (Test without writing)",
            variable=self.walk_dry_var,
            fg=COLOR_TEXT,
            bg=BG_PANEL,
            activebackground=BG_PANEL,
            activeforeground=COLOR_TEXT,
            selectcolor=BG_DARK,
            relief="flat"
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(5, 10))
        
        # Start Wizard Trigger
        self.btn_start_walkthrough = StyledButton(card, "Start Visual Walkthrough", self.start_walkthrough, variant="success")
        self.btn_start_walkthrough.grid(row=8, column=0, columnspan=3, pady=(15, 0))
        
        # Wizard Subframe (hidden initially, gridded dynamically)
        self.walk_wizard_frame = tk.Frame(self.exif_walk_frame, bg=BG_DARK)
        self.setup_wizard_ui()

    def setup_wizard_ui(self):
        # Folder listbox sidebar
        left_frame = tk.Frame(self.walk_wizard_frame, bg=BG_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1, width=240)
        left_frame.pack(side="left", fill="y", padx=(0, 10))
        left_frame.pack_propagate(False)
        
        tk.Label(left_frame, text="Directories containing images", font=("Helvetica", 9, "bold"), fg=COLOR_ACCENT, bg=BG_PANEL).pack(fill="x", padx=10, pady=10)
        
        self.wizard_listbox = tk.Listbox(
            left_frame,
            bg="#090A0F",
            fg=COLOR_TEXT,
            selectbackground=COLOR_ACCENT,
            selectforeground=BG_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Helvetica", 9)
        )
        self.wizard_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.wizard_listbox.bind("<<ListboxSelect>>", self.on_wizard_listbox_select)
        
        # Action details & image previews area
        right_frame = tk.Frame(self.walk_wizard_frame, bg=BG_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1)
        right_frame.pack(side="left", fill="both", expand=True)
        
        self.wizard_title = tk.Label(right_frame, text="Folder Name", font=("Helvetica", 12, "bold"), fg=COLOR_TEXT, bg=BG_PANEL, anchor="w")
        self.wizard_title.pack(fill="x", padx=15, pady=(15, 2))
        
        self.wizard_subtitle = tk.Label(right_frame, text="0 photo(s) found", font=("Helvetica", 9), fg=COLOR_MUTED, bg=BG_PANEL, anchor="w")
        self.wizard_subtitle.pack(fill="x", padx=15, pady=(0, 10))
        
        # Grid container to hold 8 generated thumbnails
        tk.Label(right_frame, text="Album photos:", font=("Helvetica", 9, "bold"), fg=COLOR_MUTED, bg=BG_PANEL, anchor="w").pack(fill="x", padx=15, pady=(0, 4))
        
        self.wizard_previews_outer = tk.Frame(right_frame, bg="#0E0F16", highlightbackground=COLOR_BORDER, highlightthickness=1)
        self.wizard_previews_outer.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        self.wizard_previews = tk.Frame(self.wizard_previews_outer, bg="#0E0F16")
        self.wizard_previews.pack(padx=10, pady=10, expand=True)
        
        # Date configuration inputs
        form_frame = tk.Frame(right_frame, bg=BG_PANEL)
        form_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        tk.Label(form_frame, text="Album Date:", font=("Helvetica", 10, "bold"), fg=COLOR_TEXT, bg=BG_PANEL).pack(side="left", padx=(0, 10))
        self.wizard_date_input = StyledEntry(form_frame, width=24)
        self.wizard_date_input.pack(side="left")
        
        self.wizard_date_guess_lbl = tk.Label(form_frame, text="Guess: None", font=("Helvetica", 8, "italic"), fg=COLOR_ACCENT, bg=BG_PANEL)
        self.wizard_date_guess_lbl.pack(side="left", padx=10)
        
        # Action controls
        actions_frame = tk.Frame(right_frame, bg=BG_PANEL)
        actions_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        StyledButton(actions_frame, "Apply & Next", self.apply_wizard_step, variant="primary").pack(side="left", padx=(0, 10))
        StyledButton(actions_frame, "Skip Folder", self.skip_wizard_step, variant="secondary").pack(side="left", padx=(0, 10))
        StyledButton(actions_frame, "End Walkthrough", self.stop_walkthrough, variant="danger").pack(side="right")

    def start_walkthrough(self):
        inp = self.walk_input.get().strip()
        if not inp:
            messagebox.showerror("Error", "Input folder is required.")
            return
            
        input_path = Path(inp)
        if not input_path.is_absolute():
            input_path = WORKSPACE_DIR / input_path
        input_path = input_path.resolve()
        
        if not input_path.exists() or not input_path.is_dir():
            messagebox.showerror("Error", "Input folder does not exist or is not a directory.")
            return
            
        # Recursive search for directories containing direct supported images
        self.walkthrough_dirs = []
        dirs_to_check = [input_path]
        for p in sorted(input_path.rglob("*")):
            if p.is_dir():
                dirs_to_check.append(p)
                
        # Safe directory checks (excluding the output directory to prevent circular updates)
        out_str = self.walk_output.get().strip()
        resolved_out = None
        if out_str:
            resolved_out = Path(out_str)
            if not resolved_out.is_absolute():
                resolved_out = WORKSPACE_DIR / resolved_out
            resolved_out = resolved_out.resolve()

        for d in dirs_to_check:
            if resolved_out and d.resolve() == resolved_out:
                continue
            try:
                if resolved_out and d.relative_to(resolved_out):
                    continue
            except ValueError:
                pass
                
            has_images = any(p.is_file() and p.suffix.lower() in exif_date_editor.SUPPORTED_EXTENSIONS for p in d.iterdir())
            if has_images:
                self.walkthrough_dirs.append(d)
                
        if not self.walkthrough_dirs:
            messagebox.showwarning("No folders", "No directories containing photos were found under the selected folder.")
            return
            
        self.walkthrough_root = input_path
        self.walkthrough_index = 0
        
        # Open Walkthrough UI
        self.walk_setup_frame.pack_forget()
        self.walk_wizard_frame.pack(fill="both", expand=True)
        
        # Populate Listbox directories
        self.wizard_listbox.delete(0, tk.END)
        for d in self.walkthrough_dirs:
            rel = d.relative_to(self.walkthrough_root)
            name = str(rel) if rel != Path(".") else "Root Folder"
            self.wizard_listbox.insert(tk.END, name)
            
        self.show_walkthrough_folder()

    def show_walkthrough_folder(self):
        if not self.walkthrough_dirs or self.walkthrough_index >= len(self.walkthrough_dirs):
            messagebox.showinfo("Walkthrough Completed", "All folders processed! Walkthrough completed.")
            self.stop_walkthrough()
            return
            
        # Highlight current directory selection
        self.wizard_listbox.selection_clear(0, tk.END)
        self.wizard_listbox.selection_set(self.walkthrough_index)
        self.wizard_listbox.see(self.walkthrough_index)
        
        active_dir = self.walkthrough_dirs[self.walkthrough_index]
        rel = active_dir.relative_to(self.walkthrough_root)
        dir_display_name = str(rel) if rel != Path(".") else "Root Folder"
        
        # Fetch matching images in folder
        images = [
            p for p in sorted(active_dir.iterdir())
            if p.is_file() and p.suffix.lower() in exif_date_editor.SUPPORTED_EXTENSIONS
        ]
        
        self.wizard_title.config(text=dir_display_name)
        self.wizard_subtitle.config(text=f"{len(images)} photo(s) found")
        
        # Clear previous previews
        for child in self.wizard_previews.winfo_children():
            child.destroy()
            
        self.current_thumbnails = []
        
        # Render up to 8 image previews gridded
        preview_limit = min(len(images), 8)
        for i in range(preview_limit):
            img_path = images[i]
            thumb = self.get_thumbnail(img_path)
            if thumb:
                self.current_thumbnails.append(thumb) # Prevent garbage collection
                lbl = tk.Label(self.wizard_previews, image=thumb, bg="#0E0F16", highlightthickness=1, highlightbackground=COLOR_BORDER)
                lbl.grid(row=i // 4, column=i % 4, padx=6, pady=6)
                
        # Populate automatic album date guess based on folder name
        guessed = guess_date_from_folder_name(active_dir.name)
        self.wizard_date_input.delete(0, tk.END)
        if guessed:
            self.wizard_date_input.insert(0, guessed)
            self.wizard_date_guess_lbl.config(text=f"Guess: {guessed}")
        else:
            self.wizard_date_guess_lbl.config(text="Guess: None")
            
        self.write_log(f"[INFO] Walkthrough loaded folder {self.walkthrough_index + 1}/{len(self.walkthrough_dirs)}: '{dir_display_name}'", "info")

    def get_thumbnail(self, path):
        """Attempts to open, downsize, and encode images using OpenCV for native rendering."""
        try:
            img = cv2.imread(str(path))
            if img is None:
                return None
            h, w = img.shape[:2]
            scale = min(85/w, 85/h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            
            # Convert OpenCV standard BGR to RGB
            img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
            
            # Encode to PNG and Base64 string for Tkinter native rendering
            _, buf = cv2.imencode(".png", img_rgb)
            png_b64 = base64.b64encode(buf.tobytes()).decode('ascii')
            return tk.PhotoImage(data=png_b64)
        except Exception as e:
            print(f"Error rendering thumbnail: {e}")
            return None

    def on_wizard_listbox_select(self, event):
        selection = self.wizard_listbox.curselection()
        if selection:
            self.walkthrough_index = selection[0]
            self.show_walkthrough_folder()

    def apply_wizard_step(self):
        if not self.walkthrough_dirs or self.walkthrough_index >= len(self.walkthrough_dirs):
            return
            
        date_val = self.wizard_date_input.get().strip()
        if not date_val:
            messagebox.showerror("Error", "Please enter a date for this album folder, or click Skip.")
            return
            
        active_dir = self.walkthrough_dirs[self.walkthrough_index]
        
        # Load walkthrough config options
        out = self.walk_output.get().strip()
        quality = self.walk_quality.get().strip()
        increment = self.walk_increment.get().strip()
        random_time = self.walk_random_var.get()
        dry_run = self.walk_dry_var.get()
        
        args = ["-i", str(active_dir), "-q", quality, "--increment", increment, "-d", date_val, "--no-recursive"]
        if out:
            # Recreate output matching directory hierarchy
            rel = active_dir.relative_to(self.walkthrough_root)
            target_out = Path(out) / rel
            args.extend(["-o", str(target_out)])
        if random_time:
            args.append("--random-time")
        if dry_run:
            args.append("--dry-run")
            
        self.write_log(f"[INFO] Visual Walkthrough applying date to '{active_dir.name}': {date_val}", "info")
        
        # In-process threading log capture (does not block interface)
        q_stream = QueueStream(log_queue)
        def target():
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = q_stream
            sys.stderr = q_stream
            
            old_argv = sys.argv
            sys.argv = ["exif_date_editor.py"] + args
            try:
                exif_date_editor.main()
                q_stream.flush()
                log_queue.put(f"[SUCCESS] Successfully updated '{active_dir.name}' album folder EXIF tags.")
            except Exception as e:
                q_stream.flush()
                log_queue.put(f"[ERROR] Failed to update folder '{active_dir.name}': {e}")
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                sys.argv = old_argv
                
        threading.Thread(target=target, daemon=True).start()
        
        # Proceed immediately to next album folder
        self.walkthrough_index += 1
        self.show_walkthrough_folder()

    def skip_wizard_step(self):
        active_dir = self.walkthrough_dirs[self.walkthrough_index]
        self.write_log(f"[INFO] Visual Walkthrough skipped folder '{active_dir.name}'", "info")
        self.walkthrough_index += 1
        self.show_walkthrough_folder()

    def stop_walkthrough(self):
        self.walkthrough_dirs = []
        self.walkthrough_index = 0
        self.current_thumbnails = []
        
        for child in self.wizard_previews.winfo_children():
            child.destroy()
            
        self.walk_wizard_frame.pack_forget()
        self.walk_setup_frame.pack(fill="both", expand=True)
        self.write_log("[INFO] Visual Walkthrough closed.", "info")


def main():
    root = tk.Tk()
    PhotoUtilitiesApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
