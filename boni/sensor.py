"""System metrics collector for macOS."""

import datetime
import subprocess
import psutil


class SystemSensor:
    """Collects system metrics: CPU, RAM, battery, active app, time."""

    def __init__(self):
        # Prime the CPU percent counter (first call always returns 0)
        psutil.cpu_percent(interval=None)

    def collect(self) -> dict:
        """Collect all system metrics. Blocks ~1s for accurate CPU reading."""
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent

        battery = psutil.sensors_battery()
        battery_pct = round(battery.percent) if battery else None
        is_charging = battery.power_plugged if battery else True

        active_app = self._get_active_app()
        running_apps = self._get_running_app_count()

        now = datetime.datetime.now()
        hour = now.hour
        minute = now.minute

        return {
            "cpu_percent": round(cpu),
            "ram_percent": round(ram),
            "battery_percent": battery_pct,
            "is_charging": is_charging,
            "active_app": active_app,
            "running_apps": running_apps,
            "hour": hour,
            "minute": minute,
            "is_late_night": (hour >= 23 or hour < 5),
            "is_work_hours": (9 <= hour <= 18),
        }

    def _get_active_app(self) -> str:
        """Get the name of the frontmost application."""
        try:
            from AppKit import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            return app.localizedName() if app else "Unknown"
        except Exception:
            try:
                script = (
                    'tell application "System Events" to get name of '
                    'first application process whose frontmost is true'
                )
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True, text=True, timeout=5,
                )
                return result.stdout.strip() or "Unknown"
            except Exception:
                return "Unknown"

    def _get_running_app_count(self) -> int:
        """Get approximate count of running user applications."""
        try:
            from AppKit import NSWorkspace
            apps = NSWorkspace.sharedWorkspace().runningApplications()
            # Filter to regular apps (activation policy 0 = regular)
            return sum(1 for a in apps if a.activationPolicy() == 0)
        except Exception:
            return 0
