"""System metrics + event-triggered context collector for macOS."""

import datetime
import random
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import psutil


@dataclass
class TriggerEvent:
    """Event payload used for AI trigger decisions."""

    reason: str
    ts: float
    app_name: str
    window_title: str
    idle_seconds: int
    dwell_seconds: int

    def to_dict(self) -> dict:
        return asdict(self)


class _WorkspaceObserver:
    """Bridges NSWorkspace activation events to Python callbacks."""

    def __init__(self, callback):
        from Foundation import NSObject

        self._callback = callback

        class _Observer(NSObject):
            def initWithCallback_(inner_self, cb):
                inner_self = inner_self.init()
                if inner_self is None:
                    return None
                inner_self._cb = cb
                return inner_self

            def handleAppActivated_(inner_self, notification):
                inner_self._cb()

        self._observer_class = _Observer
        self._observer = None
        self._center = None

    def start(self):
        from AppKit import NSWorkspace

        workspace = NSWorkspace.sharedWorkspace()
        self._center = workspace.notificationCenter()
        self._observer = self._observer_class.alloc().initWithCallback_(self._callback)
        self._center.addObserver_selector_name_object_(
            self._observer,
            "handleAppActivated:",
            "NSWorkspaceDidActivateApplicationNotification",
            None,
        )

    def stop(self):
        if self._center is not None and self._observer is not None:
            self._center.removeObserver_(self._observer)
        self._center = None
        self._observer = None


class SystemSensor:
    """Collects system metrics and emits event-driven trigger candidates."""

    def __init__(self, dwell_minutes: int = 2, idle_threshold_seconds: int = 10):
        # Prime the CPU percent counter (first call always returns 0)
        psutil.cpu_percent(interval=None)

        self.dwell_seconds_threshold = max(1, dwell_minutes) * 60
        self.idle_threshold_seconds = max(1, idle_threshold_seconds)

        self._lock = threading.Lock()
        self._events = []
        self._running = False
        self._monitor_thread = None
        self._workspace_observer = None

        self._last_context_key = ""
        self._last_app_name = ""
        self._last_title = ""
        self._context_started_at = time.time()
        self._dwell_fired_for_key = set()
        self._idle_triggered = False

    def collect(self) -> dict:
        """Collect all system metrics."""
        cpu = psutil.cpu_percent(interval=None)
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

    def start_watchers(self):
        """Start event watchers for app switch, dwell, and idle."""
        if self._running:
            return
        self._running = True

        try:
            self._workspace_observer = _WorkspaceObserver(self._on_workspace_activate)
            self._workspace_observer.start()
        except Exception as e:
            print(f"[sensor] Workspace observer disabled: {e}")
            self._workspace_observer = None

        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True
        )
        self._monitor_thread.start()

    def stop_watchers(self):
        self._running = False
        if self._workspace_observer:
            self._workspace_observer.stop()
            self._workspace_observer = None

    def pop_events(self) -> list[dict]:
        """Pop all currently queued trigger events."""
        with self._lock:
            events = self._events
            self._events = []
        return events

    def capture_snapshot(self, delay_seconds: float | None = None) -> dict:
        """Capture active window screenshot with full-screen fallback."""
        if delay_seconds is None:
            delay_seconds = random.uniform(1.0, 2.0)
        time.sleep(delay_seconds)

        tmp_dir = Path(tempfile.gettempdir())
        ts = int(time.time() * 1000)
        target = tmp_dir / f"boni_snapshot_{ts}.jpg"

        window_id = self._get_front_window_id()
        cmd = ["screencapture", "-x", "-t", "jpg"]
        capture_scope = "full_screen"
        if window_id:
            cmd.extend(["-l", str(window_id)])
            capture_scope = "active_window"
        cmd.append(str(target))

        try:
            subprocess.run(cmd, check=True, timeout=5)
        except Exception:
            # Fallback: full screen capture
            capture_scope = "full_screen_fallback"
            subprocess.run(
                ["screencapture", "-x", "-t", "jpg", str(target)],
                check=True,
                timeout=5,
            )

        return {"path": str(target), "scope": capture_scope, "delay_seconds": delay_seconds}

    def collect_trigger_context(self) -> dict:
        """Collect active context fields used in trigger and AI prompts."""
        app_name = self._get_active_app()
        title = self._get_active_window_title()
        key = f"{app_name}::{title}"
        dwell_seconds = int(max(0, time.time() - self._context_started_at))
        idle_seconds = int(self._get_idle_seconds())
        return {
            "app_name": app_name,
            "window_title": title,
            "context_key": key,
            "dwell_seconds": dwell_seconds,
            "idle_seconds": idle_seconds,
        }

    def _on_workspace_activate(self):
        context = self.collect_trigger_context()
        now = time.time()
        if context["context_key"] != self._last_context_key:
            self._last_context_key = context["context_key"]
            self._last_app_name = context["app_name"]
            self._last_title = context["window_title"]
            self._context_started_at = now
            self._push_event(
                reason="active_window_changed",
                app_name=context["app_name"],
                window_title=context["window_title"],
                idle_seconds=context["idle_seconds"],
                dwell_seconds=0,
            )

    def _monitor_loop(self):
        while self._running:
            try:
                context = self.collect_trigger_context()
                now = time.time()

                # Safety net: observer miss fallback for app switch.
                if (
                    self._last_app_name
                    and context["app_name"]
                    and context["app_name"] != self._last_app_name
                ):
                    self._last_context_key = context["context_key"]
                    self._last_app_name = context["app_name"]
                    self._last_title = context["window_title"]
                    self._context_started_at = now
                    self._push_event(
                        reason="active_window_changed",
                        app_name=context["app_name"],
                        window_title=context["window_title"],
                        idle_seconds=context["idle_seconds"],
                        dwell_seconds=0,
                    )

                # Event 1 (supplement): title changed inside same app.
                if (
                    self._last_context_key
                    and context["app_name"] == self._last_app_name
                    and context["window_title"]
                    and context["window_title"] != self._last_title
                ):
                    self._last_title = context["window_title"]
                    self._last_context_key = context["context_key"]
                    self._context_started_at = now
                    self._push_event(
                        reason="active_window_title_changed",
                        app_name=context["app_name"],
                        window_title=context["window_title"],
                        idle_seconds=context["idle_seconds"],
                        dwell_seconds=0,
                    )

                if not self._last_context_key:
                    self._last_context_key = context["context_key"]
                    self._last_app_name = context["app_name"]
                    self._last_title = context["window_title"]
                    self._context_started_at = now

                # Event 2: dwell timeout.
                key = context["context_key"]
                dwell_seconds = int(now - self._context_started_at)
                if (
                    key
                    and dwell_seconds >= self.dwell_seconds_threshold
                    and key not in self._dwell_fired_for_key
                ):
                    self._dwell_fired_for_key.add(key)
                    self._push_event(
                        reason="window_dwell_timeout",
                        app_name=context["app_name"],
                        window_title=context["window_title"],
                        idle_seconds=context["idle_seconds"],
                        dwell_seconds=dwell_seconds,
                    )

                # Event 3: idle >= threshold (fire once per idle period).
                idle_seconds = context["idle_seconds"]
                if idle_seconds >= self.idle_threshold_seconds and not self._idle_triggered:
                    self._idle_triggered = True
                    self._push_event(
                        reason="system_idle_threshold",
                        app_name=context["app_name"],
                        window_title=context["window_title"],
                        idle_seconds=idle_seconds,
                        dwell_seconds=dwell_seconds,
                    )
                elif idle_seconds < 2:
                    self._idle_triggered = False

            except Exception as e:
                print(f"[sensor] monitor loop error: {e}")

            # Keep this light; main trigger is event-based notification.
            time.sleep(1.0)

    def _push_event(
        self, reason: str, app_name: str, window_title: str, idle_seconds: int, dwell_seconds: int
    ):
        ev = TriggerEvent(
            reason=reason,
            ts=time.time(),
            app_name=app_name or "Unknown",
            window_title=window_title or "",
            idle_seconds=int(idle_seconds),
            dwell_seconds=int(dwell_seconds),
        )
        with self._lock:
            self._events.append(ev.to_dict())
        print(
            "[sensor] trigger:",
            reason,
            "| app=",
            ev.app_name,
            "| title=",
            ev.window_title[:60],
        )

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

    def _get_active_window_title(self) -> str:
        """Get title of active window (may need Accessibility permission)."""
        script = (
            'tell application "System Events" to tell '
            '(first application process whose frontmost is true) '
            "to get name of front window"
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            title = result.stdout.strip()
            if title:
                return title
        except Exception:
            pass

        # Fallback: Quartz window title can still work even when AppleScript is blocked.
        try:
            from Quartz import (
                CGWindowListCopyWindowInfo,
                kCGNullWindowID,
                kCGWindowListExcludeDesktopElements,
                kCGWindowListOptionOnScreenOnly,
            )

            front_app = self._get_active_app()
            infos = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                kCGNullWindowID,
            )
            for info in infos:
                owner = info.get("kCGWindowOwnerName", "")
                layer = int(info.get("kCGWindowLayer", 1))
                name = (info.get("kCGWindowName") or "").strip()
                if owner == front_app and layer == 0 and name:
                    return name
        except Exception:
            pass
        return ""

    def _get_idle_seconds(self) -> float:
        """Get seconds since user input event."""
        try:
            from Quartz import (
                CGEventSourceSecondsSinceLastEventType,
                kCGAnyInputEventType,
                kCGEventSourceStateHIDSystemState,
            )

            return float(
                CGEventSourceSecondsSinceLastEventType(
                    kCGEventSourceStateHIDSystemState, kCGAnyInputEventType
                )
            )
        except Exception:
            return 0.0

    def _get_front_window_id(self) -> int | None:
        """Try to resolve current front window id for targeted capture."""
        try:
            from Quartz import (
                CGWindowListCopyWindowInfo,
                kCGNullWindowID,
                kCGWindowListExcludeDesktopElements,
                kCGWindowListOptionOnScreenOnly,
            )

            front_app = self._get_active_app()
            infos = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                kCGNullWindowID,
            )
            for info in infos:
                owner = info.get("kCGWindowOwnerName", "")
                layer = int(info.get("kCGWindowLayer", 1))
                if owner == front_app and layer == 0:
                    return int(info.get("kCGWindowNumber"))
        except Exception:
            return None
        return None

    def _get_running_app_count(self) -> int:
        """Get approximate count of running user applications."""
        try:
            from AppKit import NSWorkspace

            apps = NSWorkspace.sharedWorkspace().runningApplications()
            # Filter to regular apps (activation policy 0 = regular)
            return sum(1 for a in apps if a.activationPolicy() == 0)
        except Exception:
            return 0
