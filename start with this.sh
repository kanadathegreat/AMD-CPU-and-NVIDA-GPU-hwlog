#!/bin/bash
#
# LogHW.sh — runs the hardware logger, then opens the chart viewer on the
# exact log file it just created.
#

# --- FORCE TERMINAL LAUNCH ---
# If standard input or output is not a terminal (e.g. double-clicked in GUI or run in background),
# relaunch this script inside a terminal emulator and replace the current process.
if [ ! -t 0 ] || [ ! -t 1 ]; then
    for term in x-terminal-emulator gnome-terminal xfce4-terminal xterm konsole; do
        if command -v "$term" >/dev/null 2>&1; then
            case "$term" in
                gnome-terminal|konsole)
                    exec "$term" -- "$0" "$@"
                    ;;
                *)
                    exec "$term" -e "$0" "$@"
                    ;;
            esac
        fi
    done
    echo "Error: No graphical terminal emulator found to run this script." >&2
    exit 1
fi
# -----------------------------

# Work from the folder this script lives in, no matter where it's launched from.
cd "$(dirname "$0")" || exit 1

VENV_ACTIVATE="./Python/bin/activate"
MONITOR_SCRIPT="./hwmonitor.sh"
CHART_SCRIPT="./Python/hwchart-v1.py"

# Make sure everything we need is actually here before we start anything.
if [ ! -f "$VENV_ACTIVATE" ]; then
    echo "Error: couldn't find the virtual environment at $VENV_ACTIVATE"
    exit 1
fi
if [ ! -x "$MONITOR_SCRIPT" ]; then
    echo "Error: couldn't find or run $MONITOR_SCRIPT"
    exit 1
fi
if [ ! -x "$CHART_SCRIPT" ]; then
    echo "Error: couldn't find or run $CHART_SCRIPT"
    exit 1
fi

# Activate the venv, and guarantee it's deactivated again no matter how this
# script ends — normal exit, an error above, or Ctrl+C.
source "$VENV_ACTIVATE"
trap deactivate EXIT

echo "Will start logging hardware data until interrupted (press 'q' or Ctrl+C in the monitor)..."
sleep 1
"$MONITOR_SCRIPT"

echo ""
echo "Hardware data has been logged and saved."

# Grab just the file created this run, rather than listing the whole history.
LATEST_LOG=$(ls -t ~/hwlogs/hwlog_*.csv 2>/dev/null | head -1)
if [ -z "$LATEST_LOG" ]; then
    echo "Warning: no log file found in ~/hwlogs — something may have gone wrong."
    exit 1
fi
echo "Saved to: $LATEST_LOG"

sleep 1
echo "Opening the chart..."
sleep 0.5

# Hand off the exact file we just created, instead of letting the chart
# script guess which one is newest.
"$CHART_SCRIPT" "$LATEST_LOG"

exit 0