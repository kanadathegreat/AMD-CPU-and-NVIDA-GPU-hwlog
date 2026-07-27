#!/bin/bash
#
# hwmonitor.sh
#
# Logs CPU, RAM, and GPU usage/temperature to a CSV file every 2 seconds,
# and shows a live-updating dashboard in the terminal while it runs.
#
# Requires: lm-sensors (already installed/configured), nvidia-smi (comes
# with the NVIDIA driver).
#
# Usage:
#   ./hwmonitor.sh
#
# Quit:
#   press 'q'  -- or --  Ctrl+C
#
# Output:
#   ~/hwlogs/hwlog_<date>_<time>.csv   (a new file every time you run this)
#

set -u   # treat use of an unset variable as an error, to catch typos early

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
LOG_DIR="$HOME/hwlogs"
INTERVAL=2   # seconds between samples

# ----------------------------------------------------------------------
# Setup: make sure the log directory exists, create today's log file
# ----------------------------------------------------------------------
mkdir -p "$LOG_DIR"

start_stamp=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_FILE="$LOG_DIR/hwlog_${start_stamp}.csv"

# Write the CSV header row so the Python side knows what each column is
echo "timestamp,cpu_usage_pct,cpu_temp_c,ram_used_mb,ram_total_mb,ram_pct,gpu_usage_pct,gpu_temp_c,gpu_mem_used_mb,gpu_mem_total_mb" > "$LOG_FILE"

# ----------------------------------------------------------------------
# Cleanup: runs when the script exits, however it exits (q, Ctrl+C, etc)
# ----------------------------------------------------------------------
cleanup() {
    tput cnorm   # bring the terminal cursor back (we hid it below)
    echo ""
    echo "Logging stopped. Data saved to: $LOG_FILE"
    exit 0
}
trap cleanup INT   # catches Ctrl+C

# ----------------------------------------------------------------------
# read_cpu_stat: reads the first line of /proc/stat (aggregate CPU time
# across all cores since boot) and returns "<total> <idle>" in jiffies.
# We call this once per loop and compare it to the previous call to work
# out how busy the CPU was *during the last 2 seconds* -- this is the
# same method "top" and "htop" use internally.
# ----------------------------------------------------------------------
read_cpu_stat() {
    local user nice system idle iowait irq softirq steal idle_all total
    read -r _ user nice system idle iowait irq softirq steal _ _ < /proc/stat
    idle_all=$((idle + iowait))
    total=$((user + nice + system + idle_all + irq + softirq + steal))
    echo "$total $idle_all"
}

# ----------------------------------------------------------------------
# read_cpu_temp: pulls the CPU temperature out of `sensors`.
# AMD chips usually report this as "Tctl" (sometimes "Tdie").
# If neither label is found, this prints "NA" instead of crashing.
# ----------------------------------------------------------------------
read_cpu_temp() {
    local temp
    temp=$(sensors | awk '/Tctl:/ {gsub(/[+°C]/,"",$2); print $2; exit}')
    if [ -z "$temp" ]; then
        temp=$(sensors | awk '/Tdie:/ {gsub(/[+°C]/,"",$2); print $2; exit}')
    fi
    if [ -z "$temp" ]; then
        temp="NA"
    fi
    echo "$temp"
}

# Prime the CPU usage counter -- we need one reading before the loop
# starts so the very first loop iteration already has something to
# compare against.
read prev_total prev_idle < <(read_cpu_stat)

tput civis   # hide the cursor for a cleaner-looking dashboard

echo "Starting hardware monitor. Logging to: $LOG_FILE"
echo "Press 'q' or Ctrl+C to stop."
sleep 1

# ----------------------------------------------------------------------
# Main loop: sample everything, write a CSV row, redraw the dashboard,
# then wait 2 seconds (while also listening for a 'q' keypress).
# ----------------------------------------------------------------------
while true; do

    # --- CPU usage % (based on delta since last loop) ---
    read curr_total curr_idle < <(read_cpu_stat)
    total_delta=$((curr_total - prev_total))
    idle_delta=$((curr_idle - prev_idle))
    if [ "$total_delta" -gt 0 ]; then
        cpu_usage=$(awk -v td="$total_delta" -v id="$idle_delta" 'BEGIN { printf "%.1f", (1 - id/td) * 100 }')
    else
        cpu_usage="0.0"
    fi
    prev_total=$curr_total
    prev_idle=$curr_idle

    # --- CPU temperature ---
    cpu_temp=$(read_cpu_temp)

    # --- RAM usage ---
    read ram_used ram_total < <(free -m | awk '/^Mem:/ {print $3, $2}')
    ram_pct=$(awk -v u="$ram_used" -v t="$ram_total" 'BEGIN { printf "%.1f", (u/t)*100 }')

    # --- GPU usage / temp / VRAM (NVIDIA) ---
    gpu_stats=$(nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits)
    IFS=', ' read -r gpu_usage gpu_temp gpu_mem_used gpu_mem_total <<< "$gpu_stats"

    # --- Timestamp for this sample ---
    now=$(date +"%Y-%m-%d %H:%M:%S")

    # --- Append this sample to the CSV log ---
    echo "$now,$cpu_usage,$cpu_temp,$ram_used,$ram_total,$ram_pct,$gpu_usage,$gpu_temp,$gpu_mem_used,$gpu_mem_total" >> "$LOG_FILE"

    # --- Redraw the live dashboard ---
    printf '\033[H\033[2J'   # move cursor home + clear screen
    echo "=== Hardware Monitor ==="
    echo "Logging to: $LOG_FILE"
    echo "Press 'q' or Ctrl+C to stop"
    echo ""
    echo "Last updated: $now"
    echo ""
    printf "CPU     Usage: %5s %%    Temp: %5s C\n" "$cpu_usage" "$cpu_temp"
    printf "RAM     Used:  %5s MB / %5s MB   (%s%%)\n" "$ram_used" "$ram_total" "$ram_pct"
    printf "GPU     Usage: %5s %%    Temp: %5s C\n" "$gpu_usage" "$gpu_temp"
    printf "GPU Mem Used:  %5s MB / %5s MB\n" "$gpu_mem_used" "$gpu_mem_total"

    # --- Wait 2 seconds, but bail out early if 'q' is pressed ---
    if read -t "$INTERVAL" -n 1 -s key; then
        if [ "$key" = "q" ]; then
            cleanup
        fi
    fi

done
