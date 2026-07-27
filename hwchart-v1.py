#!/usr/bin/env python3
"""
hwchart.py — interactive viewer for hwmonitor.sh log files.

Opens a dark-themed window with four stacked, time-synced charts
(temperature, utilization, RAM, VRAM) built from a CSV produced by
hwmonitor.sh. Scroll to zoom, click-and-drag to pan, double-click to
reset the view, hover to read exact values, and use the CPU/GPU/RAM/VRAM
chips to show or hide each metric.

Usage:
    python3 hwchart.py                     # opens the most recent log in ~/hwlogs
    python3 hwchart.py path/to/hwlog.csv   # opens a specific log file

Requirements (install once):
    pip install pandas matplotlib --break-system-packages
    sudo apt install python3-tk            # if Tkinter isn't already present
"""

import sys
import argparse
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import tkinter as tk
from tkinter import filedialog, messagebox


# ---------------------------------------------------------------------------
# Design tokens — dark "instrument panel" theme
# ---------------------------------------------------------------------------
COLORS = {
    "bg":     "#12141c",   # window background
    "panel":  "#1a1e29",   # chart panel background
    "hover":  "#232838",   # button hover background
    "grid":   "#323950",   # gridlines
    "border": "#2a2f3d",   # spines / dividers / button outline
    "text":   "#e8eaf0",   # primary text
    "muted":  "#7d8496",   # secondary text / off-state
    "cpu":    "#5fd4c0",   # teal
    "gpu":    "#ff8a5c",   # orange
    "ram":    "#7aa2f7",   # blue
    "vram":   "#c993ff",   # violet
}
FONT_UI = ("DejaVu Sans", 10)
FONT_TITLE = ("DejaVu Sans", 16, "bold")
FONT_SUB = ("DejaVu Sans", 9)
FONT_MONO = "DejaVu Sans Mono"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def find_latest_log():
    """Return the most recently created hwlog_*.csv in ~/hwlogs, or None."""
    log_dir = Path.home() / "hwlogs"
    candidates = sorted(log_dir.glob("hwlog_*.csv"))
    return candidates[-1] if candidates else None


def format_duration(td):
    total_seconds = int(td.total_seconds())
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if hours or minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def load_log(csv_path):
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    ram_total = float(df["ram_total_mb"].iloc[0])
    vram_total = float(df["gpu_mem_total_mb"].iloc[0])
    # System RAM is always shown in GB (totals are large); VRAM stays in MB,
    # matching the convention used by GPU monitoring tools like nvidia-smi.
    ram_unit, ram_div = "GB", 1024.0
    vram_unit, vram_div = "MB", 1.0

    df["ram_disp"] = df["ram_used_mb"] / ram_div
    df["vram_disp"] = df["gpu_mem_used_mb"] / vram_div

    duration = df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]

    meta = {
        "n_samples": len(df),
        "duration": format_duration(duration),
        "ram_total": ram_total, "ram_unit": ram_unit, "ram_div": ram_div,
        "vram_total": vram_total, "vram_unit": vram_unit, "vram_div": vram_div,
    }
    return df, meta


# ---------------------------------------------------------------------------
# Custom rounded-corner button (plain tkinter has no native rounded button,
# so this draws one on a small Canvas). Two flavors:
#   - plain action button (e.g. "Reset View")
#   - toggle "chip" with a color dot, used as a combined legend + show/hide
#     switch for a metric (e.g. the CPU chip toggles both CPU lines)
# ---------------------------------------------------------------------------
class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command=None, width=104, height=32,
                 radius=14, dot_color=None, toggle=False, active=True):
        super().__init__(parent, width=width, height=height,
                          bg=parent["bg"], highlightthickness=0, cursor="hand2")
        self.command = command
        self.radius = radius
        self.w = width
        self.h = height
        self.text = text
        self.dot_color = dot_color
        self.toggle = toggle
        self.is_on = active

        self._draw()
        self.bind("<Enter>", lambda e: self._draw(hover=True))
        self.bind("<Leave>", lambda e: self._draw(hover=False))
        self.bind("<Button-1>", self._on_click)

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
               x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
               x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.create_polygon(pts, smooth=True, **kw)

    def _draw(self, hover=False):
        self.delete("all")
        fill = COLORS["hover"] if hover else COLORS["panel"]
        self._round_rect(1, 1, self.w - 1, self.h - 1, self.radius,
                          fill=fill, outline=COLORS["border"], width=1)
        if self.dot_color:
            dot_r, dot_x = 4, 15
            cy = self.h / 2
            color = self.dot_color if self.is_on else COLORS["muted"]
            self.create_oval(dot_x - dot_r, cy - dot_r, dot_x + dot_r, cy + dot_r,
                              fill=color, outline="")
            fg = COLORS["text"] if self.is_on else COLORS["muted"]
            self.create_text(dot_x + dot_r + 8, cy, text=self.text, fill=fg,
                              font=FONT_UI, anchor="w")
        else:
            self.create_text(self.w / 2, self.h / 2, text=self.text,
                              fill=COLORS["text"], font=FONT_UI)

    def _on_click(self, _event):
        if self.toggle:
            self.is_on = not self.is_on
            self._draw()
        if self.command:
            self.command(self.is_on)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class HWMonitorApp:
    PANEL_COLUMNS = {
        "temp":  [("cpu_temp_c", "cpu"), ("gpu_temp_c", "gpu")],
        "usage": [("cpu_usage_pct", "cpu"), ("gpu_usage_pct", "gpu")],
        "ram":   [("ram_disp", "ram")],
        "vram":  [("vram_disp", "vram")],
    }

    def __init__(self, root, df, meta, csv_path):
        self.root = root
        self.df = df
        self.meta = meta
        self.csv_path = csv_path

        self.visible = {"cpu": True, "gpu": True, "ram": True, "vram": True}
        self.dragging = False
        self.drag_start_x_px = None
        self.drag_start_xlim = None
        self.full_xlim = None

        root.title(f"Hardware Monitor — {Path(csv_path).name}")
        root.configure(bg=COLORS["bg"])
        root.geometry("1180x820")
        root.minsize(860, 600)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_header()
        self._build_controls()
        self._build_chart()

    # ---- UI construction ---------------------------------------------
    def _build_header(self):
        header = tk.Frame(self.root, bg=COLORS["bg"])
        header.pack(fill="x", padx=20, pady=(16, 4))

        logo = tk.Canvas(header, width=34, height=34, bg=COLORS["bg"],
                          highlightthickness=0)
        self.logo_img = None

        script_dir = Path(__file__).resolve().parent
        for logo_name in ("logo.png", "Logo.png"):
            logo_path = script_dir / logo_name
            if logo_path.exists():
                self.logo_img = tk.PhotoImage(file=str(logo_path))
                break

        if self.logo_img is not None:
            logo.create_image(17, 17, image=self.logo_img)
        else:
            pts = [10, 1, 24, 1, 33, 1, 33, 10, 33, 24, 33, 33, 24, 33, 10, 33,
                   1, 33, 1, 24, 1, 10, 1, 1]
            logo.create_polygon(pts, smooth=True, fill=COLORS["panel"],
                                 outline=COLORS["border"])
        logo.pack(side="left", padx=(0, 10))

        title_frame = tk.Frame(header, bg=COLORS["bg"])
        title_frame.pack(side="left")
        tk.Label(title_frame, text="HARDWARE MONITOR", font=FONT_TITLE,
                 fg=COLORS["text"], bg=COLORS["bg"]).pack(anchor="w")
        subtitle = (f"{self.meta['n_samples']:,} samples  ·  "
                    f"{self.meta['duration']}  ·  {Path(self.csv_path).name}")
        self.subtitle_label = tk.Label(title_frame, text=subtitle, font=FONT_SUB,
                                        fg=COLORS["muted"], bg=COLORS["bg"])
        self.subtitle_label.pack(anchor="w")

    def _build_controls(self):
        bar = tk.Frame(self.root, bg=COLORS["bg"])
        bar.pack(fill="x", padx=20, pady=(10, 10))

        left = tk.Frame(bar, bg=COLORS["bg"])
        left.pack(side="left")
        chips = [
            ("CPU", "cpu", COLORS["cpu"]),
            ("GPU", "gpu", COLORS["gpu"]),
            ("RAM", "ram", COLORS["ram"]),
            ("VRAM", "vram", COLORS["vram"]),
        ]
        for label, group, color in chips:
            btn = RoundedButton(left, label, dot_color=color, toggle=True,
                                 active=True, width=96,
                                 command=lambda is_on, g=group: self._toggle(g, is_on))
            btn.pack(side="left", padx=(0, 8))

        right = tk.Frame(bar, bg=COLORS["bg"])
        right.pack(side="right")
        RoundedButton(right, "Load File", width=110,
                      command=lambda *_: self._load_file()).pack(side="left")
        RoundedButton(right, "Save PNG", width=110,
                      command=lambda *_: self._save_png()).pack(side="left", padx=(8, 0))
        RoundedButton(right, "Reset View", width=110,
                      command=lambda *_: self._reset_view()).pack(side="left", padx=(8, 0))

    def _build_chart(self):
        plt.rcParams.update({
            "figure.facecolor": COLORS["bg"],
            "axes.facecolor": COLORS["panel"],
            "axes.edgecolor": COLORS["border"],
            "axes.labelcolor": COLORS["muted"],
            "xtick.color": COLORS["muted"],
            "ytick.color": COLORS["muted"],
            "text.color": COLORS["text"],
            "font.family": "DejaVu Sans",
            "font.size": 9,
        })

        self.fig, axes = plt.subplots(4, 1, sharex=True, figsize=(11, 7),
                                       gridspec_kw={"hspace": 0.18})
        self.ax_temp, self.ax_usage, self.ax_ram, self.ax_vram = axes
        self.axes = axes
        self.panel_axes = {"temp": self.ax_temp, "usage": self.ax_usage,
                            "ram": self.ax_ram, "vram": self.ax_vram}

        t = self.df["timestamp"]
        self.lines = {}
        self.lines["cpu_temp"], = self.ax_temp.plot(
            t, self.df["cpu_temp_c"], color=COLORS["cpu"], linewidth=1.7,
            solid_capstyle="round")
        self.lines["gpu_temp"], = self.ax_temp.plot(
            t, self.df["gpu_temp_c"], color=COLORS["gpu"], linewidth=1.7,
            solid_capstyle="round")
        self.ax_temp.set_ylabel("TEMP (°C)", labelpad=10)

        self.lines["cpu_usage"], = self.ax_usage.plot(
            t, self.df["cpu_usage_pct"], color=COLORS["cpu"], linewidth=1.5,
            solid_capstyle="round")
        self.lines["gpu_usage"], = self.ax_usage.plot(
            t, self.df["gpu_usage_pct"], color=COLORS["gpu"], linewidth=1.5,
            solid_capstyle="round")
        self.ax_usage.set_ylabel("USAGE (%)", labelpad=10)

        self.lines["ram"], = self.ax_ram.plot(
            t, self.df["ram_disp"], color=COLORS["ram"], linewidth=1.6,
            solid_capstyle="round")
        self.ram_total_line = self.ax_ram.axhline(
            self.meta["ram_total"] / self.meta["ram_div"], color=COLORS["ram"],
            linewidth=0.8, linestyle="--", alpha=0.35)
        self.ax_ram.set_ylabel(f"RAM ({self.meta['ram_unit']})", labelpad=10)

        self.lines["vram"], = self.ax_vram.plot(
            t, self.df["vram_disp"], color=COLORS["vram"], linewidth=1.6,
            solid_capstyle="round")
        self.vram_total_line = self.ax_vram.axhline(
            self.meta["vram_total"] / self.meta["vram_div"], color=COLORS["vram"],
            linewidth=0.8, linestyle="--", alpha=0.35)
        self.ax_vram.set_ylabel(f"VRAM ({self.meta['vram_unit']})", labelpad=10)

        for ax in self.axes:
            ax.grid(True, alpha=0.6, linewidth=0.6, color=COLORS["grid"])
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color(COLORS["border"])
            ax.spines["bottom"].set_color(COLORS["border"])
            ax.tick_params(length=0)

        for ax in self.axes:
            loc = mdates.AutoDateLocator()
            ax.xaxis.set_major_locator(loc)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
        for ax in self.axes[:-1]:
            ax.tick_params(labelbottom=False)

        self.fig.subplots_adjust(left=0.08, right=0.97, top=0.98, bottom=0.07)
        self.full_xlim = self.ax_vram.get_xlim()

        # Crosshair line (one per panel, hidden until hovered) + readout box
        self.vlines = [ax.axvline(t.iloc[0], color=COLORS["text"], linewidth=0.7,
                                   alpha=0.6, visible=False) for ax in self.axes]
        self.readout = self.fig.text(
            0.975, 0.975, "", ha="right", va="top", fontsize=8.5,
            fontfamily=FONT_MONO, color=COLORS["text"],
            bbox=dict(boxstyle="round,pad=0.5", fc=COLORS["panel"], ec=COLORS["border"]))
        self.readout.set_visible(False)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.configure(bg=COLORS["bg"], highlightthickness=0)
        self.canvas_widget.pack(fill="both", expand=True, padx=20, pady=(0, 18))

        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.canvas.mpl_connect("figure_leave_event", lambda e: self._hide_crosshair())

        self.canvas.draw()

    # ---- interaction: pan / zoom / reset -------------------------------
    def _on_press(self, event):
        if event.button != 1 or event.inaxes is None:
            return
        if event.dblclick:
            self._reset_view()
            return
        self.dragging = True
        self.drag_start_x_px = event.x
        self.drag_start_xlim = self.ax_vram.get_xlim()
        self._hide_crosshair()

    def _on_release(self, _event):
        self.dragging = False

    def _on_motion(self, event):
        if self.dragging:
            self._do_pan(event)
        else:
            self._update_crosshair(event)

    def _do_pan(self, event):
        if event.x is None or self.drag_start_xlim is None:
            return
        dx_px = event.x - self.drag_start_x_px
        bbox = self.ax_vram.get_window_extent()
        if bbox.width <= 0:
            return
        x0, x1 = self.drag_start_xlim
        dx_data = -(dx_px / bbox.width) * (x1 - x0)
        self._set_xlim_clamped(x0 + dx_data, x1 + dx_data)
        self.canvas.draw_idle()

    def _on_scroll(self, event):
        if event.inaxes is None or event.xdata is None:
            return
        x0, x1 = self.ax_vram.get_xlim()
        factor = 0.85 if event.button == "up" else 1 / 0.85
        new_x0 = event.xdata - (event.xdata - x0) * factor
        new_x1 = event.xdata + (x1 - event.xdata) * factor
        full_width = self.full_xlim[1] - self.full_xlim[0]
        if new_x1 - new_x0 < full_width * 0.01:
            return
        self._set_xlim_clamped(new_x0, new_x1)
        self.canvas.draw_idle()

    def _set_xlim_clamped(self, x0, x1):
        width = x1 - x0
        fx0, fx1 = self.full_xlim
        if width >= fx1 - fx0:
            x0, x1 = fx0, fx1
        else:
            if x0 < fx0:
                x0, x1 = fx0, fx0 + width
            if x1 > fx1:
                x0, x1 = fx1 - width, fx1
        self.ax_vram.set_xlim(x0, x1)
        self._rescale_y()

    def _reset_view(self):
        self.ax_vram.set_xlim(self.full_xlim)
        self._rescale_y()
        self.canvas.draw_idle()

    def _rescale_y(self):
        x0, x1 = self.ax_vram.get_xlim()
        lo = mdates.num2date(x0).replace(tzinfo=None)
        hi = mdates.num2date(x1).replace(tzinfo=None)
        mask = (self.df["timestamp"] >= lo) & (self.df["timestamp"] <= hi)
        sub = self.df.loc[mask]
        if len(sub) < 2:
            return
        for panel, cols in self.PANEL_COLUMNS.items():
            active_cols = [c for c, grp in cols if self.visible[grp]]
            if not active_cols:
                continue
            vals = sub[active_cols].to_numpy().ravel()
            vals = vals[~pd.isna(vals)]
            if len(vals) == 0:
                continue
            lo_v, hi_v = float(vals.min()), float(vals.max())
            pad = (hi_v - lo_v) * 0.15 if hi_v > lo_v else max(abs(hi_v) * 0.1, 1.0)
            self.panel_axes[panel].set_ylim(lo_v - pad, hi_v + pad)

    # ---- interaction: hover crosshair ----------------------------------
    def _update_crosshair(self, event):
        if event.inaxes is None or event.xdata is None:
            self._hide_crosshair()
            return
        target = mdates.num2date(event.xdata).replace(tzinfo=None)
        idx = self.df["timestamp"].searchsorted(target)
        idx = min(max(idx, 0), len(self.df) - 1)
        row = self.df.iloc[idx]

        for vl in self.vlines:
            vl.set_xdata([row["timestamp"], row["timestamp"]])
            vl.set_visible(True)

        lines = [row["timestamp"].strftime("%H:%M:%S")]
        if self.visible["cpu"]:
            lines.append(f"CPU   {row['cpu_usage_pct']:5.1f}%   {row['cpu_temp_c']:5.1f}C")
        if self.visible["gpu"]:
            lines.append(f"GPU   {row['gpu_usage_pct']:5.1f}%   {row['gpu_temp_c']:5.1f}C")
        if self.visible["ram"]:
            lines.append(f"RAM   {row['ram_disp']:7.2f} {self.meta['ram_unit']}")
        if self.visible["vram"]:
            lines.append(f"VRAM  {row['vram_disp']:7.2f} {self.meta['vram_unit']}")

        self.readout.set_text("\n".join(lines))
        self.readout.set_visible(True)
        self.canvas.draw_idle()

    def _hide_crosshair(self):
        for vl in self.vlines:
            vl.set_visible(False)
        self.readout.set_visible(False)
        self.canvas.draw_idle()

    # ---- toggle chips ----------------------------------------------------
    def _toggle(self, group, is_on):
        self.visible[group] = is_on
        for key, line in self.lines.items():
            if key.startswith(group):
                line.set_visible(is_on)
        if group == "ram":
            self.ram_total_line.set_visible(is_on)
        elif group == "vram":
            self.vram_total_line.set_visible(is_on)
        self._rescale_y()
        self.canvas.draw_idle()

    # ---- load / save / close ------------------------------------------
    def _load_file(self):
        initial_dir = Path.home() / "hwlogs"
        if not initial_dir.exists():
            initial_dir = Path.home()
        path = filedialog.askopenfilename(
            initialdir=str(initial_dir),
            title="Open a hardware log",
            filetypes=[("Hardware log CSV", "hwlog_*.csv"),
                       ("CSV files", "*.csv"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        self._open_csv(Path(path))

    def _open_csv(self, csv_path):
        try:
            df, meta = load_log(csv_path)
        except Exception as exc:
            messagebox.showerror(
                "Couldn't open file",
                f"Something went wrong reading this file:\n\n{exc}")
            return

        self.df = df
        self.meta = meta
        self.csv_path = csv_path

        self.root.title(f"Hardware Monitor — {csv_path.name}")
        subtitle = (f"{meta['n_samples']:,} samples  ·  "
                    f"{meta['duration']}  ·  {csv_path.name}")
        self.subtitle_label.config(text=subtitle)

        self._refresh_lines()

    def _refresh_lines(self):
        """Push self.df / self.meta into the existing plot artists, instead
        of tearing down and rebuilding the whole figure."""
        t = self.df["timestamp"]

        self.lines["cpu_temp"].set_data(t, self.df["cpu_temp_c"])
        self.lines["gpu_temp"].set_data(t, self.df["gpu_temp_c"])
        self.lines["cpu_usage"].set_data(t, self.df["cpu_usage_pct"])
        self.lines["gpu_usage"].set_data(t, self.df["gpu_usage_pct"])
        self.lines["ram"].set_data(t, self.df["ram_disp"])
        self.lines["vram"].set_data(t, self.df["vram_disp"])

        ram_level = self.meta["ram_total"] / self.meta["ram_div"]
        vram_level = self.meta["vram_total"] / self.meta["vram_div"]
        self.ram_total_line.set_ydata([ram_level, ram_level])
        self.vram_total_line.set_ydata([vram_level, vram_level])

        for vl in self.vlines:
            vl.set_xdata([t.iloc[0], t.iloc[0]])
        self._hide_crosshair()

        # Compute the new full time range directly from the data rather than
        # relying on axes autoscale, which would also try to "fit" the
        # dashed reference lines (their x-span is in axes-fraction units,
        # not dates, and would throw the range off).
        x0 = mdates.date2num(t.iloc[0])
        x1 = mdates.date2num(t.iloc[-1])
        self.full_xlim = (x0, x1)

        self._reset_view()

    def _save_png(self):
        default_name = Path(self.csv_path).stem + ".png"
        path = filedialog.asksaveasfilename(
            defaultextension=".png", initialfile=default_name,
            filetypes=[("PNG image", "*.png")], title="Save chart as image")
        if not path:
            return
        self.fig.savefig(path, facecolor=COLORS["bg"], dpi=150)
        messagebox.showinfo("Saved", f"Chart saved to:\n{path}")

    def _on_close(self):
        plt.close(self.fig)
        self.root.destroy()


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="View hwmonitor.sh CSV logs as an interactive dark-themed chart.")
    parser.add_argument("csv_file", nargs="?",
                         help="Path to a hwlog_*.csv file. If omitted, the most "
                              "recent file in ~/hwlogs is used.")
    args = parser.parse_args()

    if args.csv_file:
        csv_path = Path(args.csv_file)
    else:
        csv_path = find_latest_log()
        if csv_path is None:
            print("No file given, and no logs found in ~/hwlogs.")
            print("Usage: python3 hwchart.py path/to/hwlog_YYYY-MM-DD_HH-MM-SS.csv")
            sys.exit(1)
        print(f"No file given — opening most recent log: {csv_path}")

    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        sys.exit(1)

    df, meta = load_log(csv_path)

    root = tk.Tk()
    HWMonitorApp(root, df, meta, csv_path)
    root.mainloop()


if __name__ == "__main__":
    main()
