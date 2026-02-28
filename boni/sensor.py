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


class _MouseMonitor:
    """Tracks click frequency using pynput. No coordinates recorded."""

    def __init__(self):
        self._clicks: list[float] = []
        self._lock = threading.Lock()
        self._listener = None

    def start(self):
        try:
            from pynput.mouse import Listener
            self._listener = Listener(on_click=self._on_click)
            self._listener.daemon = True
            self._listener.start()
            print("[sensor] Mouse monitor started")
        except ImportError:
            print("[sensor] pynput not available — mouse monitor disabled")
        except Exception as e:
            print(f"[sensor] Mouse monitor failed: {e}")

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_click(self, x, y, button, pressed):
        if pressed:
            with self._lock:
                self._clicks.append(time.time())

    def get_stats(self) -> dict:
        now = time.time()
        with self._lock:
            # Keep only last 60 seconds
            self._clicks = [t for t in self._clicks if now - t <= 60]
            count = len(self._clicks)
        return {"clicks_60s": count, "clicks_per_min": count}


class _KeyboardMonitor:
    """Tracks typing patterns. Never records key content — only patterns."""

    def __init__(self):
        self._keystrokes: list[float] = []
        self._backspaces: int = 0
        self._total_keys: int = 0
        self._pauses: int = 0  # gaps > 3 seconds in typing
        self._last_key_time: float = 0
        self._lock = threading.Lock()
        self._listener = None

    def start(self):
        try:
            from pynput.keyboard import Key, Listener
            self._Key = Key
            self._listener = Listener(on_press=self._on_press)
            self._listener.daemon = True
            self._listener.start()
            print("[sensor] Keyboard monitor started")
        except ImportError:
            print("[sensor] pynput not available — keyboard monitor disabled")
        except Exception as e:
            print(f"[sensor] Keyboard monitor failed: {e}")

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key):
        now = time.time()
        with self._lock:
            # Detect typing pauses (> 3s gap)
            if self._last_key_time and now - self._last_key_time > 3.0:
                self._pauses += 1
            self._last_key_time = now
            self._keystrokes.append(now)
            self._total_keys += 1
            if key == self._Key.backspace:
                self._backspaces += 1

    def get_stats(self) -> dict:
        now = time.time()
        with self._lock:
            # Keep only last 60 seconds of keystroke timestamps
            self._keystrokes = [t for t in self._keystrokes if now - t <= 60]
            speed = len(self._keystrokes)  # keys in last 60s
            ratio = round(self._backspaces / max(1, self._total_keys), 2)
            pauses = self._pauses
        return {
            "typing_speed": speed,
            "backspace_ratio": ratio,
            "typing_pauses": pauses,
        }

    def reset_counters(self):
        with self._lock:
            self._backspaces = 0
            self._total_keys = 0
            self._pauses = 0


class _AudioMonitor:
    """Detects sighs via amplitude patterns. Never records or saves audio."""

    def __init__(self):
        self._ambient_level: float = 0.0
        self._calibrated = False
        self._sighs: int = 0
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def start(self):
        try:
            import sounddevice  # noqa: F401
            import numpy  # noqa: F401
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            print("[sensor] Audio monitor started")
        except ImportError:
            print("[sensor] sounddevice/numpy not available — audio monitor disabled")
        except Exception as e:
            print(f"[sensor] Audio monitor failed: {e}")

    def stop(self):
        self._running = False

    def _run(self):
        import sounddevice as sd
        import numpy as np

        sample_rate = 16000
        chunk_duration = 0.5  # seconds per chunk

        # Calibrate: 3 seconds of ambient noise
        try:
            print("[sensor] Audio calibrating (3s)...")
            cal_data = sd.rec(int(3 * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
            sd.wait()
            self._ambient_level = float(np.mean(np.abs(cal_data))) or 0.001
            self._calibrated = True
            print(f"[sensor] Audio ambient level: {self._ambient_level:.6f}")
        except Exception as e:
            print(f"[sensor] Audio calibration failed: {e}")
            return

        # Main monitoring loop
        elevated_chunks = 0
        while self._running:
            try:
                chunk = sd.rec(int(chunk_duration * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
                sd.wait()
                amplitude = float(np.mean(np.abs(chunk)))
                ratio = amplitude / max(self._ambient_level, 0.0001)

                # Sigh detection: amplitude 2~8x ambient for 0.5~2s
                if 2.0 <= ratio <= 8.0:
                    elevated_chunks += 1
                    # 1-4 consecutive chunks (0.5s each) = 0.5~2s
                    if elevated_chunks in (1, 2, 3, 4):
                        pass  # accumulating
                    if elevated_chunks == 2:
                        with self._lock:
                            self._sighs += 1
                        print(f"[sensor] Sigh detected (ratio={ratio:.1f})")
                else:
                    elevated_chunks = 0

            except Exception:
                time.sleep(1)

    def get_stats(self) -> dict:
        with self._lock:
            sighs = self._sighs
        return {"sighs": sighs, "calibrated": self._calibrated}

    def reset_counters(self):
        with self._lock:
            self._sighs = 0


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

        # Input monitors
        self._mouse_monitor = _MouseMonitor()
        self._keyboard_monitor = _KeyboardMonitor()
        self._audio_monitor = _AudioMonitor()
        self._last_behavior_check = time.time()

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
        """Start event watchers for app switch, dwell, idle, and input monitors."""
        if self._running:
            return
        self._running = True

        try:
            self._workspace_observer = _WorkspaceObserver(self._on_workspace_activate)
            self._workspace_observer.start()
        except Exception as e:
            print(f"[sensor] Workspace observer disabled: {e}")
            self._workspace_observer = None

        # Start input monitors
        self._mouse_monitor.start()
        self._keyboard_monitor.start()
        self._audio_monitor.start()

        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True
        )
        self._monitor_thread.start()

    def stop_watchers(self):
        self._running = False
        if self._workspace_observer:
            self._workspace_observer.stop()
            self._workspace_observer = None
        self._mouse_monitor.stop()
        self._keyboard_monitor.stop()
        self._audio_monitor.stop()

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

                # Behavioral events: check every 10 seconds
                if now - self._last_behavior_check >= 10:
                    self._last_behavior_check = now
                    self._check_behavior_patterns(context)

            except Exception as e:
                print(f"[sensor] monitor loop error: {e}")

            # Keep this light; main trigger is event-based notification.
            time.sleep(1.0)

    def _check_behavior_patterns(self, context: dict):
        """Check input monitors for behavioral patterns and emit events."""
        mouse = self._mouse_monitor.get_stats()
        keyboard = self._keyboard_monitor.get_stats()
        audio = self._audio_monitor.get_stats()

        app_name = context["app_name"]
        window_title = context["window_title"]

        # Frustration pattern: backspace ratio > 30% AND clicks > 30/min
        if keyboard["backspace_ratio"] > 0.30 and mouse["clicks_per_min"] > 30:
            self._push_event(
                reason="frustration_pattern",
                app_name=app_name,
                window_title=window_title,
                idle_seconds=context["idle_seconds"],
                dwell_seconds=context["dwell_seconds"],
                extra={
                    "clicks_per_min": mouse["clicks_per_min"],
                    "typing_speed": keyboard["typing_speed"],
                    "backspace_ratio": keyboard["backspace_ratio"],
                },
            )
            self._keyboard_monitor.reset_counters()

        # Sigh detected
        if audio.get("sighs", 0) > 0:
            self._push_event(
                reason="sigh_detected",
                app_name=app_name,
                window_title=window_title,
                idle_seconds=context["idle_seconds"],
                dwell_seconds=context["dwell_seconds"],
                extra={"sighs": audio["sighs"]},
            )
            self._audio_monitor.reset_counters()

        # High typing burst: > 100 keys/min
        if keyboard["typing_speed"] > 100:
            self._push_event(
                reason="high_typing_burst",
                app_name=app_name,
                window_title=window_title,
                idle_seconds=context["idle_seconds"],
                dwell_seconds=context["dwell_seconds"],
                extra={
                    "typing_speed": keyboard["typing_speed"],
                    "backspace_ratio": keyboard["backspace_ratio"],
                },
            )

    def _push_event(
        self, reason: str, app_name: str, window_title: str, idle_seconds: int, dwell_seconds: int,
        extra: dict | None = None,
    ):
        ev = TriggerEvent(
            reason=reason,
            ts=time.time(),
            app_name=app_name or "Unknown",
            window_title=window_title or "",
            idle_seconds=int(idle_seconds),
            dwell_seconds=int(dwell_seconds),
        )
        ev_dict = ev.to_dict()
        if extra:
            ev_dict.update(extra)
        with self._lock:
            self._events.append(ev_dict)
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
