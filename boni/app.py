"""Main application — menu bar + floating character window."""

import json
import os
import threading
import uuid
import webbrowser
from pathlib import Path

import rumps

from .brain import BoniBrain
from .memory import BoniMemory
from .mood import DEFAULT_MESSAGES, MOOD_EMOJI, Mood, determine_mood
from .sensor import SystemSensor

CONFIG_DIR = Path.home() / ".boni"
CONFIG_FILE = CONFIG_DIR / "config.json"

MEMORY_STORE_INTERVAL = 60  # seconds between memory stores

class BoniApp(rumps.App):
    """boni menu bar application."""

    def __init__(self):
        super().__init__(name="boni", title="🦝", quit_button=None)

        # State
        self.sensor = SystemSensor(dwell_minutes=2, idle_threshold_seconds=10)
        self.brain = None
        self.current_mood = Mood.CHILL
        self.current_message = "Waking up..."
        self.messages_history = []
        self.api_key = None
        self.user_id = None
        self.floating_visible = True
        self.panel = None
        self._pending_update = None
        self._update_lock = threading.Lock()
        self._last_metrics = None  # cached for memory store
        self._last_reaction = None  # cached for memory store

        # Load config (sets api_key and user_id)
        self._load_config()

        # Memory system (activated by BONI_MEMORY_URL env var)
        memory_url = os.environ.get("BONI_MEMORY_URL")
        self.memory = BoniMemory(memory_url, user_id=self.user_id) if memory_url else None
        if self.memory:
            print(f"[boni] Memory enabled: {memory_url} (user_id={self.user_id})")

        # Build menu
        self.msg_item = rumps.MenuItem(
            f"💬 {self.current_message}", callback=self._on_pet
        )
        self.pet_item = rumps.MenuItem("🐾 Pet boni", callback=self._on_pet)
        self.float_toggle = rumps.MenuItem(
            "👻 Hide boni", callback=self._on_toggle_float
        )
        self.recent_menu = rumps.MenuItem("📜 Recent")
        self.recent_menu.add(rumps.MenuItem("(no history yet)"))
        self.suggestion_item = rumps.MenuItem("🔗 ...", callback=self._on_suggestion)
        self._suggestion_url = None

        self.api_item = rumps.MenuItem("🔑 Set API Key", callback=self._on_set_api_key)
        self.quit_item = rumps.MenuItem("Quit boni", callback=self._on_quit)

        self.menu = [
            self.msg_item,
            self.suggestion_item,
            None,
            self.pet_item,
            self.float_toggle,
            None,
            self.recent_menu,
            None,
            self.api_item,
            None,
            self.quit_item,
        ]

        # Hide suggestion item initially
        self.suggestion_item.hidden = True

        # Initialize brain if API key exists
        if self.api_key:
            try:
                self.brain = BoniBrain(self.api_key)
            except Exception as e:
                print(f"[boni] Failed to init brain: {e}")

        # Quick initial mood (no API call, just metrics)
        self._quick_mood_check()

    # ── Config ──────────────────────────────────────────────────────

    def _load_config(self):
        config = {}
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    config = json.load(f)
                if not self.api_key:
                    self.api_key = config.get("api_key")
            except Exception:
                pass

        # Load or auto-generate user_id
        self.user_id = config.get("user_id")
        if not self.user_id:
            self.user_id = uuid.uuid4().hex
            print(f"[boni] Generated new user_id: {self.user_id}")
            self._save_config()

    def _save_config(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config = {}
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    config = json.load(f)
            except Exception:
                pass
        config["api_key"] = self.api_key
        config["user_id"] = self.user_id
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)

    # ── Initial mood ────────────────────────────────────────────────

    def _quick_mood_check(self):
        """Set initial mood from metrics without calling AI."""
        try:
            # Use non-blocking CPU reading for startup speed
            import psutil

            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            battery = psutil.sensors_battery()
            import datetime

            now = datetime.datetime.now()

            metrics = {
                "cpu_percent": round(cpu),
                "ram_percent": round(ram),
                "battery_percent": round(battery.percent) if battery else None,
                "is_charging": battery.power_plugged if battery else True,
                "active_app": "",
                "running_apps": 0,
                "hour": now.hour,
                "minute": now.minute,
                "is_late_night": (now.hour >= 23 or now.hour < 5),
                "is_work_hours": (9 <= now.hour <= 18),
            }
            self.current_mood = determine_mood(metrics)
            self.current_message = DEFAULT_MESSAGES.get(
                self.current_mood, "I'm here now."
            )
            self._refresh_display()
        except Exception as e:
            print(f"[boni] Quick mood check failed: {e}")

    # ── Timers ──────────────────────────────────────────────────────

    @rumps.timer(2)
    def _startup(self, timer):
        """One-shot: create floating window and trigger first AI update."""
        timer.stop()
        self._create_floating_window()
        self.sensor.start_watchers()
        if self.brain:
            self._trigger_ai_update()
        elif not self.api_key:
            self.current_message = "Set your Gemini API key to wake me up! (🔑 in menu)"
            self._refresh_display()

    @rumps.timer(0.5)
    def _consume_sensor_events(self, _):
        """Consume event-trigger candidates from sensor."""
        if not self.brain:
            return
        events = self.sensor.pop_events()
        for event in events:
            print(f"[boni] consume trigger: {event.get('reason')} / {event.get('app_name')}")
            self._trigger_ai_update(trigger_event=event)

    @rumps.timer(MEMORY_STORE_INTERVAL)
    def _memory_store_timer(self, _):
        """Store current state to long-term memory every 60 seconds."""
        if not self.memory:
            return
        if self._last_metrics is None or self._last_reaction is None:
            return

        metrics = self._last_metrics
        reaction = self._last_reaction

        def bg_store():
            self.memory.store(metrics, reaction)

        threading.Thread(target=bg_store, daemon=True).start()

    @rumps.timer(0.5)
    def _apply_pending(self, _):
        """Check for pending updates from background thread and apply."""
        if self._pending_update is not None:
            update = self._pending_update
            self._pending_update = None
            self._apply_ai_result(update)

    # ── Background AI update ────────────────────────────────────────

    def _trigger_ai_update(self, trigger_event: dict | None = None):
        """Start a background thread to collect metrics, snapshot, and call Gemini."""
        if not self._update_lock.acquire(blocking=False):
            return  # Previous update still running

        def bg():
            try:
                metrics = self.sensor.collect()
                snapshot = None
                if trigger_event is not None:
                    snapshot = self.sensor.capture_snapshot()
                    print(
                        "[boni] snapshot:",
                        snapshot.get("scope"),
                        snapshot.get("path"),
                    )

                # Recall past memories if memory system is active
                memories = None
                if self.memory:
                    memories = self.memory.recall(metrics, self.current_mood.value)

                result = self.brain.react(
                    metrics=metrics,
                    current_mood=self.current_mood.value,
                    memories=memories,
                    trigger=trigger_event,
                    snapshot=snapshot,
                )
                if trigger_event is not None:
                    print(
                        "[boni] react done:",
                        trigger_event.get("reason"),
                        "->",
                        result.get("message") or result.get("대사") or "...",
                    )
                self._pending_update = {
                    "metrics": metrics,
                    "result": result,
                    "trigger": trigger_event,
                    "snapshot": snapshot,
                }
            except Exception as e:
                print(f"[boni] BG update error: {e}")
            finally:
                self._update_lock.release()

        threading.Thread(target=bg, daemon=True).start()

    def _apply_ai_result(self, update):
        """Apply AI result to state and UI (runs on main thread via timer)."""
        metrics = update["metrics"]
        result = update["result"]

        # Cache for memory store timer
        if metrics:
            self._last_metrics = metrics
            self._last_reaction = result

        # Update mood
        mood_str = result.get("mood", "chill")
        try:
            new_mood = Mood(mood_str)
        except ValueError:
            new_mood = determine_mood(metrics)
        self.current_mood = new_mood

        # Update message + history
        new_message = result.get("message") or result.get("line") or result.get("대사") or "..."
        if new_message and new_message != self.current_message:
            if self.current_message and not self.current_message.startswith("Set your"):
                self.messages_history.append(
                    {
                        "emoji": MOOD_EMOJI.get(self.current_mood, "😌"),
                        "message": self.current_message,
                    }
                )
                self.messages_history = self.messages_history[-5:]
            self.current_message = new_message

        # Handle link suggestion
        suggest_msg = result.get("제안_메시지", "")
        suggest_url = result.get("연관링크", "")
        if suggest_msg and suggest_url:
            self._suggestion_url = suggest_url
            display_suggest = suggest_msg if len(suggest_msg) <= 40 else suggest_msg[:37] + "..."
            self.suggestion_item.title = f"🔗 {display_suggest}"
            self.suggestion_item.hidden = False
        else:
            self._suggestion_url = None
            self.suggestion_item.hidden = True

        self._refresh_display()

    # ── Display ─────────────────────────────────────────────────────

    def _refresh_display(self):
        """Update menu bar title, menu items, and floating window."""
        emoji = MOOD_EMOJI.get(self.current_mood, "😌")
        self.title = emoji

        # Update message item
        display_msg = self.current_message
        if len(display_msg) > 50:
            display_msg = display_msg[:47] + "..."
        self.msg_item.title = f"💬 {display_msg}"

        # Update recent submenu
        self.recent_menu.clear()
        if self.messages_history:
            for item in reversed(self.messages_history):
                msg = item["message"]
                if len(msg) > 45:
                    msg = msg[:42] + "..."
                self.recent_menu.add(
                    rumps.MenuItem(f"{item['emoji']} {msg}")
                )
        else:
            self.recent_menu.add(rumps.MenuItem("(no history yet)"))

        # Update floating window
        self._update_floating_window()

    def _update_floating_window(self):
        """Update the floating character bubble content."""
        if self.panel is None:
            return
        if not self.floating_visible:
            return

        try:
            emoji = MOOD_EMOJI.get(self.current_mood, "😌")
            self._emoji_field.setStringValue_(emoji)
            self._message_field.setStringValue_(f"\u201c{self.current_message}\u201d")
            self.panel.orderFront_(None)
        except Exception as e:
            print(f"[boni] Float update error: {e}")

    # ── Floating window (PyObjC) ────────────────────────────────────

    def _create_floating_window(self):
        """Create a native macOS floating panel with vibrancy."""
        try:
            from AppKit import (
                NSBackingStoreBuffered,
                NSColor,
                NSFont,
                NSMakeRect,
                NSPanel,
                NSScreen,
                NSTextField,
                NSVisualEffectView,
                NSWindowStyleMaskBorderless,
                NSFloatingWindowLevel,
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorStationary,
                NSLineBreakByWordWrapping,
            )

            # Dimensions
            width, height = 320, 110

            # Position: top-right corner, below menu bar
            screen = NSScreen.mainScreen().frame()
            x = screen.size.width - width - 20
            y = screen.size.height - height - 45
            frame = NSMakeRect(x, y, width, height)

            # Borderless floating panel
            panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                frame,
                NSWindowStyleMaskBorderless,
                NSBackingStoreBuffered,
                False,
            )
            panel.setLevel_(NSFloatingWindowLevel)
            panel.setOpaque_(False)
            panel.setBackgroundColor_(NSColor.clearColor())
            panel.setHasShadow_(True)
            panel.setMovableByWindowBackground_(True)
            panel.setFloatingPanel_(True)
            panel.setBecomesKeyOnlyIfNeeded_(True)
            panel.setHidesOnDeactivate_(False)
            panel.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorStationary
            )
            panel.setAlphaValue_(0.95)

            # Visual effect view — blurred translucent background
            content_frame = NSMakeRect(0, 0, width, height)
            effect = NSVisualEffectView.alloc().initWithFrame_(content_frame)
            effect.setMaterial_(12)  # NSVisualEffectMaterialPopover
            effect.setBlendingMode_(0)  # BehindWindow
            effect.setState_(1)  # Active
            effect.setWantsLayer_(True)
            effect.layer().setCornerRadius_(16)
            effect.layer().setMasksToBounds_(True)

            # Large emoji
            self._emoji_field = NSTextField.alloc().initWithFrame_(
                NSMakeRect(15, 25, 70, 65)
            )
            emoji = MOOD_EMOJI.get(self.current_mood, "😌")
            self._emoji_field.setStringValue_(emoji)
            self._emoji_field.setFont_(NSFont.systemFontOfSize_(48))
            self._emoji_field.setBezeled_(False)
            self._emoji_field.setDrawsBackground_(False)
            self._emoji_field.setEditable_(False)
            self._emoji_field.setSelectable_(False)

            # Speech bubble message
            self._message_field = NSTextField.alloc().initWithFrame_(
                NSMakeRect(90, 30, 210, 60)
            )
            self._message_field.setStringValue_(
                f"\u201c{self.current_message}\u201d"
            )
            self._message_field.setFont_(NSFont.systemFontOfSize_(13))
            self._message_field.setBezeled_(False)
            self._message_field.setDrawsBackground_(False)
            self._message_field.setEditable_(False)
            self._message_field.setSelectable_(False)
            self._message_field.setTextColor_(NSColor.labelColor())
            self._message_field.cell().setWraps_(True)
            self._message_field.cell().setLineBreakMode_(
                NSLineBreakByWordWrapping
            )

            # "— boni" attribution
            boni_label = NSTextField.alloc().initWithFrame_(
                NSMakeRect(235, 8, 70, 18)
            )
            boni_label.setStringValue_("— boni")
            boni_label.setFont_(NSFont.systemFontOfSize_(10))
            boni_label.setBezeled_(False)
            boni_label.setDrawsBackground_(False)
            boni_label.setEditable_(False)
            boni_label.setSelectable_(False)
            boni_label.setTextColor_(NSColor.secondaryLabelColor())

            # Assemble
            effect.addSubview_(self._emoji_field)
            effect.addSubview_(self._message_field)
            effect.addSubview_(boni_label)
            panel.setContentView_(effect)

            if self.floating_visible:
                panel.orderFront_(None)

            self.panel = panel
            print("[boni] Floating window created")

        except Exception as e:
            print(f"[boni] Could not create floating window: {e}")
            import traceback
            traceback.print_exc()
            self.panel = None

    # ── Menu callbacks ──────────────────────────────────────────────

    def _on_pet(self, sender):
        """Pet boni — trigger a special reaction."""
        if not self.brain:
            rumps.alert("boni is sleeping 😴", "Set your Gemini API key first!\n(🔑 in the menu bar)")
            return

        def bg():
            try:
                result = self.brain.pet_react(self.current_mood.value)
                message = result.get("message", "헤헤~ 또 만져줘!")
                self.current_message = message
                # Schedule UI update — pass full result for suggestion handling
                result.setdefault("message", message)
                result.setdefault("mood", self.current_mood.value)
                self._pending_update = {
                    "metrics": {},
                    "result": result,
                }
            except Exception as e:
                print(f"[boni] Pet error: {e}")

        threading.Thread(target=bg, daemon=True).start()

    def _on_suggestion(self, sender):
        """Open the suggested URL in the default browser."""
        if self._suggestion_url:
            webbrowser.open(self._suggestion_url)
            self._suggestion_url = None
            self.suggestion_item.hidden = True

    def _on_toggle_float(self, sender):
        """Show/hide the floating character window."""
        self.floating_visible = not self.floating_visible
        sender.title = "👻 Hide boni" if self.floating_visible else "👻 Show boni"

        if self.panel:
            if self.floating_visible:
                self.panel.orderFront_(None)
            else:
                self.panel.orderOut_(None)

    def _on_set_api_key(self, sender):
        """Prompt the user to enter their Gemini API key."""
        window = rumps.Window(
            message="Enter your Gemini API key\n(from Google AI Studio or Cloud Console):",
            title="boni Setup",
            default_text=self.api_key or "",
            ok="Save",
            cancel="Cancel",
            dimensions=(340, 24),
        )
        response = window.run()
        if response.clicked:
            key = response.text.strip()
            if key:
                self.api_key = key
                self._save_config()
                try:
                    self.brain = BoniBrain(self.api_key)
                    self._trigger_ai_update()
                    rumps.notification(
                        "boni", "I'm awake!", "Let's see what you're up to..."
                    )
                except Exception as e:
                    rumps.alert("Error", f"Failed to initialize: {e}")

    def _on_quit(self, sender):
        """Quit boni."""
        self.sensor.stop_watchers()
        if self.panel:
            self.panel.orderOut_(None)
        rumps.quit_application()
