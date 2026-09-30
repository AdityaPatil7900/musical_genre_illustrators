#!/usr/bin/env python3
"""
Resource Monitoring and Adaptive Response (Case Study 2, Extra Credit #6).

Runs periodically on the VM (via genre-monitor.timer). Checks CPU, system
memory, and GPU (if available) usage. If any exceeds its threshold:
  a. Sends a Discord webhook notification.
  b. Writes a "degraded mode" flag file that vm_app.py checks at request time
     to reduce workload (skip local image generation / return a "near
     capacity" message) until usage drops back below the threshold.

Thresholds are deliberately low by default so this is easy to trigger for
grading/demo purposes -- raise them for real use.
"""
import json
import os
import time
from datetime import datetime, timezone

import psutil
import requests

STATE_DIR = os.environ.get("WATCHDOG_STATE_DIR", "/home/student-admin/musical_genre_illustrators/.watchdog")
FLAG_FILE = os.path.join(STATE_DIR, "degraded_mode.flag")
LOG_FILE = os.path.join(STATE_DIR, "monitor.log")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

CPU_THRESHOLD = float(os.environ.get("CPU_THRESHOLD_PCT", "80"))
MEM_THRESHOLD = float(os.environ.get("MEM_THRESHOLD_PCT", "80"))

os.makedirs(STATE_DIR, exist_ok=True)


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def notify_discord(msg):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=5)
    except Exception as e:
        log(f"Discord notify failed: {e}")


def get_gpu_usage():
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return util.gpu, 100.0 * mem.used / mem.total
    except Exception:
        return None, None


def main():
    cpu_pct = psutil.cpu_percent(interval=1)
    mem_pct = psutil.virtual_memory().percent
    gpu_pct, gpu_mem_pct = get_gpu_usage()

    reading = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu_pct": cpu_pct,
        "mem_pct": mem_pct,
        "gpu_pct": gpu_pct,
        "gpu_mem_pct": gpu_mem_pct,
    }
    log(f"reading: {json.dumps(reading)}")

    over_threshold = cpu_pct >= CPU_THRESHOLD or mem_pct >= MEM_THRESHOLD
    if gpu_pct is not None:
        over_threshold = over_threshold or gpu_pct >= CPU_THRESHOLD

    was_degraded = os.path.exists(FLAG_FILE)

    if over_threshold and not was_degraded:
        with open(FLAG_FILE, "w") as f:
            json.dump(reading, f)
        log("ENTERING degraded mode.")
        notify_discord(
            f"🟠 **Resource threshold exceeded** — CPU {cpu_pct:.0f}% / MEM {mem_pct:.0f}%"
            + (f" / GPU {gpu_pct:.0f}%" if gpu_pct is not None else "")
            + f" (threshold {CPU_THRESHOLD:.0f}%). App is now serving in degraded mode."
        )
    elif not over_threshold and was_degraded:
        os.remove(FLAG_FILE)
        log("EXITING degraded mode.")
        notify_discord("🟢 Resource usage back to normal — degraded mode cleared.")


if __name__ == "__main__":
    main()
