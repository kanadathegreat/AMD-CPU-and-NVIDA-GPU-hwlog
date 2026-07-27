# AMD-CPU-and-NVIDA-GPU-hwlog
This is a vibe coded project devoloped on Linux Mint. It monitors CPU and GPU usage, Ram usage, and tempeture then presents a interactrive graph when you end the data collection phase. Data is collected to a file and will be preserved in a crash or freez. NVIDIA GPUs only. AMD by defualt by Intel may work with tinkering. Use at your own risk.

# Hardware Monitor

A lightweight CPU/GPU/RAM logger and interactive chart viewer for Ubuntu-based
Linux systems. A Bash script samples your hardware every 2 seconds and writes
it to a CSV file; a dark-themed Python app turns that CSV into a zoomable,
pannable chart.

## Features

- Logs CPU usage & temperature, RAM usage, and GPU usage/temperature/VRAM every 2 seconds
- Live terminal dashboard while logging — press `q` or `Ctrl+C` to stop
- Interactive chart viewer: scroll to zoom, click-drag to pan, double-click to
  reset, hover for exact readings
- Show/hide individual metrics, save the chart as a PNG, and load a different
  log file from inside the app — no command line needed after setup

## Requirements

- Ubuntu, Linux Mint, or another Ubuntu/Debian-based distribution
- An **NVIDIA GPU with drivers installed** (`nvidia-smi` must work) — GPU
  monitoring currently only supports NVIDIA
- A CPU with `lm-sensors` support (tested on AMD Ryzen via `k10temp`; see
  [Troubleshooting](#troubleshooting) if you're on Intel)

## Installation

### 1. Install and configure lm-sensors

`lm-sensors` reads temperature data from your CPU's onboard sensors.

```bash
sudo apt update
sudo apt install lm-sensors
sudo sensors-detect
```

`sensors-detect` will ask a series of yes/no questions about which sensor
modules to probe for. The default answer (usually `YES`) is safe to accept
for all of them. When it asks whether to add the detected modules to
`/etc/modules` so they load automatically at boot, say yes.

Reboot (or run the `modprobe` commands it printed) so the sensor modules are
loaded, then confirm it's working:

```bash
sensors
```

You should see a block of temperature readings. On AMD systems this is
usually labeled `k10temp-...` with a `Tctl:` line — that's the value this
project reads. If your output looks different, see
[Troubleshooting](#troubleshooting).

### 2. Get the project files

Clone this repository directly into the folder structure the scripts expect:

```bash
mkdir -p ~/hwlogs
git clone <this-repo-url> ~/hwlogs/Software
```

(Replace `<this-repo-url>` with this repository's URL. If you'd rather
download a ZIP from GitHub instead of using `git clone`, just extract it so
its contents end up at `~/hwlogs/Software/` — see [File structure](#file-structure)
below for exactly what belongs where.)

### 3. Install system packages needed for the Python side

```bash
sudo apt install python3-venv python3-tk
```

- `python3-venv` — lets you create an isolated Python virtual environment
  (see step 4)
- `python3-tk` — Tkinter, the GUI toolkit the chart viewer is built on; Ubuntu
  ships it as a separate package from core Python

### 4. Create the virtual environment and install dependencies

This project deliberately avoids installing Python packages system-wide
(`pip install --break-system-packages`). Instead, it uses a **virtual
environment** — a self-contained folder with its own copy of Python and
packages, isolated from the rest of your system.

```bash
cd ~/hwlogs/Software
python3 -m venv Python
source Python/bin/activate
pip install --upgrade pip setuptools wheel
pip install pandas matplotlib
deactivate
```

What this does:
1. `python3 -m venv Python` creates the virtual environment in a folder
   named `Python` (this is where it lives from now on — see the file
   structure below).
2. `source Python/bin/activate` switches your shell into that environment,
   so `pip` and `python3` refer to the venv's copies rather than the
   system-wide ones.
3. `pip install --upgrade pip setuptools wheel` brings the base install
   tools up to date — this avoids most package-build issues before they
   happen.
4. `pip install pandas matplotlib` installs the two libraries the chart
   viewer needs, only inside this environment.
5. `deactivate` returns your shell to normal.

You won't need to run `activate`/`deactivate` yourself day-to-day — the
launcher script handles that automatically (see [Usage](#usage)).

### 5. Add your logo (optional)

Drop a `logo.png` (roughly 34×34px works best — larger images aren't resized
automatically) into `~/hwlogs/Software/Python/`, next to `hwchart-v1.py`. If
no logo file is found, the app just shows an empty placeholder square.

### 6. Make the scripts executable

```bash
chmod +x ~/hwlogs/Software/hwmonitor.sh
chmod +x ~/hwlogs/Software/"start with this.sh"
chmod +x ~/hwlogs/Software/Python/hwchart-v1.py
```

## File structure

```
~/hwlogs/                        ← log files land here automatically
├── hwlog_2026-07-25_08-02-56.csv
├── hwlog_2026-07-26_09-14-02.csv
└── Software/
    ├── hwmonitor.sh              ← logs CPU/GPU/RAM stats to ~/hwlogs
    ├── start with this.sh        ← runs hwmonitor.sh, then opens the chart
    └── Python/
        ├── hwchart-v1.py         ← the chart viewer
        ├── logo.png              ← optional, shown in the app header
        ├── bin/                  ← virtual environment (from `python3 -m venv Python`)
        ├── lib/
        └── pyvenv.cfg
```

## Usage

### Log and chart in one go

```bash
cd ~/hwlogs/Software
./"start with this.sh"
```

(The quotes are needed because the filename has spaces in it.)

This starts the live logging dashboard — press `q` or `Ctrl+C` when you're
done — then automatically opens the chart viewer on the log file that was
just created.

### Just viewing an existing log

Open the chart app on its own and use its **Load File** button to browse to
any log in `~/hwlogs`:

```bash
source ~/hwlogs/Software/Python/bin/activate
python3 ~/hwlogs/Software/Python/hwchart-v1.py
deactivate
```

Or open a specific file directly:

```bash
source ~/hwlogs/Software/Python/bin/activate
python3 ~/hwlogs/Software/Python/hwchart-v1.py ~/hwlogs/hwlog_2026-07-25_08-02-56.csv
deactivate
```

## Troubleshooting

**`sensors` doesn't show `Tctl:` or `Tdie:`** — these labels are specific to
AMD's `k10temp` driver. On Intel systems, `sensors` typically reports
`Package id 0:` instead. Open `hwmonitor.sh`, find the `read_cpu_temp()`
function, and add a fallback for your system's label following the same
pattern as the existing `Tctl`/`Tdie` checks.

**`nvidia-smi: command not found`** — the NVIDIA driver isn't installed, or
this is a non-NVIDIA GPU. GPU monitoring currently requires NVIDIA.

**`ModuleNotFoundError: No module named 'tkinter'`** — install it with
`sudo apt install python3-tk`, then try again.

**`pip install` fails partway or reports conflicting packages** — this can
happen if system Python packages leak into the venv. Forcing a clean
reinstall usually resolves it:

```bash
source ~/hwlogs/Software/Python/bin/activate
pip install --force-reinstall pandas matplotlib wheel
deactivate
```

**Nothing happens when double-clicking `start with this.sh` in a file
manager** — some file managers open `.sh` files in a text editor by default
rather than running them. Run it from a terminal instead (see
[Usage](#usage)), or check your file manager's settings for how it handles
executable scripts.
