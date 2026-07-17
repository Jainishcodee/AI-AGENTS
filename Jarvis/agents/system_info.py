"""System info agent — CPU, RAM, disk, uptime."""
import shutil
import time
from datetime import timedelta

import psutil

from .base import Agent


class SystemInfoAgent(Agent):
    name = "System"
    description = "Reports CPU, memory, disk and uptime."

    def start(self, args: str = "") -> str:
        self._set_status("running")
        try:
            cpu = psutil.cpu_percent(interval=0.4)
            mem = psutil.virtual_memory()
            try:
                disk = shutil.disk_usage("C:\\" if hasattr(shutil, "disk_usage") else "/")
            except Exception:  # noqa: BLE001
                disk = shutil.disk_usage("/")
            uptime = timedelta(seconds=int(time.time() - psutil.boot_time()))
            return (
                f"CPU is at {cpu:.0f} percent. "
                f"Memory at {mem.percent:.0f} percent, with {mem.available / 1e9:.1f} gigabytes free. "
                f"Disk has {disk.free / 1e9:.0f} gigabytes free out of {disk.total / 1e9:.0f}. "
                f"Up for {str(uptime).split('.')[0]}."
            )
        finally:
            self._set_status("idle")
