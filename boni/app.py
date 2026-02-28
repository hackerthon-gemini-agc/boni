"""Main application — menu bar + floating character window."""

import json
import os
import threading
import uuid
from pathlib import Path

import rumps

from .accumulator import EventAccumulator
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
        self.accumulator = EventAccumulator()
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

        # Collapsible UI state
        self._collapsed = True  # start collapsed
        self._collapse_timer = None
        self._pending_collapse = False
        self._COLLAPSED_SIZE = (96, 96)
        self._EXPANDED_SIZE = (640, 220)
        self._AUTO_COLLAPSE_SECONDS = 8
        self._bubble_left = False  # True = bubble appears left of image
        self._showing_answer = False  # True = answer panel is expanded
        self._ANSWER_EXPANDED_SIZE = (640, 500)

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
        self.suggestion_item = rumps.MenuItem("💡 ...", callback=self._on_suggestion)
        self._current_answer = ""

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
        """Consume event-trigger candidates from sensor via accumulator."""
        if not self.brain:
            return
        events = self.sensor.pop_events()
        should_trigger = False
        for event in events:
            print(f"[boni] accumulate: {event.get('reason')} / {event.get('app_name')}")
            if self.accumulator.add_event(event):
                should_trigger = True
        if should_trigger:
            accumulated = self.accumulator.consume()
            print(f"[boni] trigger AI — score={accumulated['total_score']}, events={accumulated['event_count']}")
            self._trigger_ai_update(accumulated_context=accumulated)

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
        if self._pending_collapse:
            self._pending_collapse = False
            self._collapse_panel()

    # ── Background AI update ────────────────────────────────────────

    def _trigger_ai_update(self, accumulated_context: dict | None = None):
        """Start a background thread to collect metrics, snapshot, and call Gemini."""
        if not self._update_lock.acquire(blocking=False):
            return  # Previous update still running

        def bg():
            try:
                metrics = self.sensor.collect()
                snapshot = None
                if accumulated_context is not None:
                    snapshot = self.sensor.capture_snapshot(delay_seconds=0.0)
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
                    accumulated_context=accumulated_context,
                    snapshot=snapshot,
                )
                if accumulated_context is not None:
                    print(
                        "[boni] react done:",
                        accumulated_context.get("dominant_pattern"),
                        "->",
                        result.get("message") or result.get("대사") or "...",
                    )
                self._pending_update = {
                    "metrics": metrics,
                    "result": result,
                    "accumulated_context": accumulated_context,
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

        # Handle proactive answer suggestion — show in bubble, not menu bar
        suggest_msg = result.get("제안_메시지", "")
        answer_content = result.get("정답_내용", "")
        if suggest_msg and answer_content:
            self._current_answer = answer_content
            display_suggest = suggest_msg if len(suggest_msg) <= 35 else suggest_msg[:32] + "..."
            if hasattr(self, '_suggestion_field'):
                self._suggestion_field.setStringValue_(f"💡 {display_suggest}")
        else:
            self._current_answer = ""
            if hasattr(self, '_suggestion_field'):
                self._suggestion_field.setStringValue_("")
        self.suggestion_item.hidden = True  # always hide menu bar suggestion

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
        """Update the floating character bubble content and expand."""
        if self.panel is None:
            return
        if not self.floating_visible:
            return
        if self._showing_answer:
            return  # Don't interrupt answer view

        try:
            self._message_field.setStringValue_(f"\u201c{self.current_message}\u201d")
            self._expand_panel()
        except Exception as e:
            print(f"[boni] Float update error: {e}")

    def _expand_panel(self):
        """Animate panel from collapsed to expanded state."""
        if self.panel is None:
            return

        # Cancel any pending collapse
        if self._collapse_timer:
            self._collapse_timer.cancel()
            self._collapse_timer = None

        try:
            from AppKit import NSAnimationContext, NSMakeRect, NSScreen

            w, h = self._EXPANDED_SIZE
            cur = self.panel.frame()

            # Determine bubble direction based on screen position
            screen = NSScreen.mainScreen().frame()
            panel_center_x = cur.origin.x + cur.size.width / 2
            screen_center_x = screen.size.width / 2
            bubble_left = panel_center_x > screen_center_x
            self._bubble_left = bubble_left

            if bubble_left:
                # Boni on right half → anchor right edge, bubble goes left
                x = cur.origin.x + cur.size.width - w
            else:
                # Boni on left half → anchor left edge, bubble goes right
                x = cur.origin.x
            y = cur.origin.y + cur.size.height - h
            target_frame = NSMakeRect(x, y, w, h)

            # Resize container + drag view + subviews
            self._container_view.setFrame_(NSMakeRect(0, 0, w, h))
            self._drag_view.setFrame_(NSMakeRect(0, 0, w, h))

            if bubble_left:
                # Image on right, bubble on left
                self._image_view.setFrame_(NSMakeRect(w - 160, 30, 140, 160))
                self._effect_view.setFrame_(NSMakeRect(10, 10, w - 170, h - 20))
            else:
                # Image on left, bubble on right
                self._image_view.setFrame_(NSMakeRect(20, 30, 140, 160))
                self._effect_view.setFrame_(NSMakeRect(160, 10, w - 170, h - 20))
            self._effect_view.layer().setCornerRadius_(20)

            # Message and label (relative to effect view, same for both directions)
            ev_w = int(self._effect_view.frame().size.width)
            ev_h = int(self._effect_view.frame().size.height)
            self._message_field.setFrame_(NSMakeRect(20, 50, ev_w - 60, 120))
            self._boni_label.setFrame_(NSMakeRect(ev_w - 160, 10, 140, 36))
            self._suggestion_field.setFrame_(NSMakeRect(20, 10, ev_w - 60, 36))
            self._close_label.setFrame_(NSMakeRect(ev_w - 35, ev_h - 35, 30, 30))

            NSAnimationContext.beginGrouping()
            NSAnimationContext.currentContext().setDuration_(0.3)
            self.panel.animator().setFrame_display_(target_frame, True)
            self._effect_view.animator().setAlphaValue_(0.95)
            self._message_field.animator().setAlphaValue_(1.0)
            self._close_label.animator().setAlphaValue_(1.0)

            # Show suggestion link or boni label
            if self._current_answer:
                self._suggestion_field.animator().setAlphaValue_(1.0)
                self._boni_label.animator().setAlphaValue_(0.0)
            else:
                self._suggestion_field.animator().setAlphaValue_(0.0)
                self._boni_label.animator().setAlphaValue_(1.0)
            NSAnimationContext.endGrouping()

            self._collapsed = False
            self.panel.orderFront_(None)

            # Schedule auto-collapse
            self._collapse_timer = threading.Timer(
                self._AUTO_COLLAPSE_SECONDS, self._schedule_collapse
            )
            self._collapse_timer.daemon = True
            self._collapse_timer.start()

        except Exception as e:
            print(f"[boni] Expand error: {e}")

    def _expand_answer_panel(self):
        """Expand the bubble downward to show the answer content inline."""
        if self.panel is None:
            return

        # Cancel any pending collapse
        if self._collapse_timer:
            self._collapse_timer.cancel()
            self._collapse_timer = None

        try:
            from AppKit import NSAnimationContext, NSMakeRect, NSScreen

            w, h = self._ANSWER_EXPANDED_SIZE
            cur = self.panel.frame()

            if self._bubble_left:
                x = cur.origin.x + cur.size.width - w
            else:
                x = cur.origin.x
            # Anchor top edge
            y = cur.origin.y + cur.size.height - h
            target_frame = NSMakeRect(x, y, w, h)

            self._container_view.setFrame_(NSMakeRect(0, 0, w, h))
            self._drag_view.setFrame_(NSMakeRect(0, 0, w, h))

            # Image stays at top
            img_y = h - 190
            if self._bubble_left:
                self._image_view.setFrame_(NSMakeRect(w - 160, img_y, 140, 160))
                self._effect_view.setFrame_(NSMakeRect(10, 10, w - 170, h - 20))
            else:
                self._image_view.setFrame_(NSMakeRect(20, img_y, 140, 160))
                self._effect_view.setFrame_(NSMakeRect(160, 10, w - 170, h - 20))
            self._effect_view.layer().setCornerRadius_(20)

            ev_w = int(self._effect_view.frame().size.width)
            ev_h = h - 20  # effect view height
            # Message at top of effect view
            self._message_field.setFrame_(NSMakeRect(20, ev_h - 150, ev_w - 60, 120))
            # Divider area — suggestion link
            self._suggestion_field.setFrame_(NSMakeRect(20, ev_h - 180, ev_w - 60, 30))
            # Answer content fills remaining space
            self._answer_field.setStringValue_(self._current_answer)
            self._answer_field.setFrame_(NSMakeRect(20, 40, ev_w - 40, ev_h - 230))
            # Close button at top-right
            self._close_label.setFrame_(NSMakeRect(ev_w - 35, ev_h - 35, 30, 30))
            # Boni label at bottom
            self._boni_label.setFrame_(NSMakeRect(ev_w - 160, 10, 140, 36))

            NSAnimationContext.beginGrouping()
            NSAnimationContext.currentContext().setDuration_(0.3)
            self.panel.animator().setFrame_display_(target_frame, True)
            self._effect_view.animator().setAlphaValue_(0.95)
            self._message_field.animator().setAlphaValue_(1.0)
            self._suggestion_field.animator().setAlphaValue_(1.0)
            self._answer_field.animator().setAlphaValue_(1.0)
            self._close_label.animator().setAlphaValue_(1.0)
            self._boni_label.animator().setAlphaValue_(1.0)
            NSAnimationContext.endGrouping()

            self._collapsed = False
            self._showing_answer = True
            self.panel.orderFront_(None)
            # No auto-collapse when showing answer

        except Exception as e:
            print(f"[boni] Answer expand error: {e}")

    def _schedule_collapse(self):
        """Set flag for main thread to collapse (called from timer thread)."""
        self._pending_collapse = True

    def _collapse_panel(self):
        """Animate panel from expanded to collapsed state."""
        if self.panel is None or self._collapsed:
            return

        try:
            from AppKit import NSAnimationContext, NSMakeRect

            w, h = self._COLLAPSED_SIZE
            cur = self.panel.frame()

            if self._bubble_left:
                # Anchor right edge (boni image is on the right)
                x = cur.origin.x + cur.size.width - w
            else:
                # Anchor left edge (boni image is on the left)
                x = cur.origin.x
            y = cur.origin.y + cur.size.height - h
            target_frame = NSMakeRect(x, y, w, h)

            # Shrink to just the image
            self._container_view.setFrame_(NSMakeRect(0, 0, w, h))
            self._image_view.setFrame_(NSMakeRect(0, 0, w, h))

            NSAnimationContext.beginGrouping()
            NSAnimationContext.currentContext().setDuration_(0.3)
            self.panel.animator().setFrame_display_(target_frame, True)
            self._effect_view.animator().setAlphaValue_(0.0)
            self._message_field.animator().setAlphaValue_(0.0)
            self._boni_label.animator().setAlphaValue_(0.0)
            self._suggestion_field.animator().setAlphaValue_(0.0)
            self._answer_field.animator().setAlphaValue_(0.0)
            self._close_label.animator().setAlphaValue_(0.0)
            NSAnimationContext.endGrouping()

            self._collapsed = True
            self._showing_answer = False

        except Exception as e:
            print(f"[boni] Collapse error: {e}")

    # ── Floating window (PyObjC) ────────────────────────────────────

    def _create_floating_window(self):
        """Create a native macOS floating panel — starts collapsed (48x48)."""
        try:
            import objc
            from AppKit import (
                NSBackingStoreBuffered,
                NSColor,
                NSFont,
                NSImage,
                NSImageScaleProportionallyUpOrDown,
                NSImageView,
                NSMakeRect,
                NSPanel,
                NSScreen,
                NSTextField,
                NSView,
                NSVisualEffectView,
                NSWindowStyleMaskBorderless,
                NSFloatingWindowLevel,
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorStationary,
                NSLineBreakByWordWrapping,
            )

            # Store NSFont for use in expand/collapse
            self._NSFont = NSFont

            # Load boni image
            image_path = str(Path(__file__).parent / "image" / "boni.png")
            boni_image = NSImage.alloc().initWithContentsOfFile_(image_path)

            # Start collapsed
            cw, ch = self._COLLAPSED_SIZE

            # Position: top-right corner, below menu bar
            screen = NSScreen.mainScreen().frame()
            x = screen.size.width - cw - 20
            y = screen.size.height - ch - 45
            frame = NSMakeRect(x, y, cw, ch)

            # Borderless floating panel — fully transparent, no shadow
            panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                frame,
                NSWindowStyleMaskBorderless,
                NSBackingStoreBuffered,
                False,
            )
            panel.setLevel_(NSFloatingWindowLevel)
            panel.setOpaque_(False)
            panel.setBackgroundColor_(NSColor.clearColor())
            panel.setHasShadow_(False)
            panel.setMovableByWindowBackground_(True)
            panel.setFloatingPanel_(True)
            panel.setBecomesKeyOnlyIfNeeded_(True)
            panel.setHidesOnDeactivate_(False)
            panel.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorStationary
            )

            # Expanded content with vibrancy — hidden initially
            ew, eh = self._EXPANDED_SIZE
            effect = NSVisualEffectView.alloc().initWithFrame_(
                NSMakeRect(0, 0, cw, ch)
            )
            effect.setMaterial_(12)  # NSVisualEffectMaterialPopover
            effect.setBlendingMode_(0)  # BehindWindow
            effect.setState_(1)  # Active
            effect.setWantsLayer_(True)
            effect.layer().setCornerRadius_(16)
            effect.layer().setMasksToBounds_(True)
            effect.setAlphaValue_(0.0)  # hidden when collapsed
            self._effect_view = effect

            # Boni image view — centered in collapsed state
            self._image_view = NSImageView.alloc().initWithFrame_(
                NSMakeRect(0, 0, cw, ch)
            )
            if boni_image:
                self._image_view.setImage_(boni_image)
            self._image_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)

            # Speech bubble message — hidden initially (alpha=0)
            self._message_field = NSTextField.alloc().initWithFrame_(
                NSMakeRect(10, 25, 210, 60)
            )
            self._message_field.setStringValue_(
                f"\u201c{self.current_message}\u201d"
            )
            self._message_field.setFont_(NSFont.systemFontOfSize_(18))
            self._message_field.setBezeled_(False)
            self._message_field.setDrawsBackground_(False)
            self._message_field.setEditable_(False)
            self._message_field.setSelectable_(False)
            self._message_field.setTextColor_(NSColor.labelColor())
            self._message_field.cell().setWraps_(True)
            self._message_field.cell().setLineBreakMode_(
                NSLineBreakByWordWrapping
            )
            self._message_field.setAlphaValue_(0.0)

            # "— boni" attribution — hidden initially
            self._boni_label = NSTextField.alloc().initWithFrame_(
                NSMakeRect(155, 5, 70, 18)
            )
            self._boni_label.setStringValue_("— boni")
            self._boni_label.setFont_(NSFont.systemFontOfSize_(14))
            self._boni_label.setBezeled_(False)
            self._boni_label.setDrawsBackground_(False)
            self._boni_label.setEditable_(False)
            self._boni_label.setSelectable_(False)
            self._boni_label.setTextColor_(NSColor.secondaryLabelColor())
            self._boni_label.setAlphaValue_(0.0)

            # Suggestion link — hidden initially, shown inside bubble
            self._suggestion_field = NSTextField.alloc().initWithFrame_(
                NSMakeRect(10, 5, 200, 18)
            )
            self._suggestion_field.setStringValue_("")
            self._suggestion_field.setFont_(NSFont.systemFontOfSize_(15))
            self._suggestion_field.setBezeled_(False)
            self._suggestion_field.setDrawsBackground_(False)
            self._suggestion_field.setEditable_(False)
            self._suggestion_field.setSelectable_(False)
            self._suggestion_field.setTextColor_(NSColor.systemBlueColor())
            self._suggestion_field.setAlphaValue_(0.0)

            # Answer content field — hidden initially, shown when suggestion clicked
            self._answer_field = NSTextField.alloc().initWithFrame_(
                NSMakeRect(20, 40, 420, 260)
            )
            self._answer_field.setStringValue_("")
            self._answer_field.setFont_(NSFont.systemFontOfSize_(14))
            self._answer_field.setBezeled_(False)
            self._answer_field.setDrawsBackground_(False)
            self._answer_field.setEditable_(False)
            self._answer_field.setSelectable_(True)
            self._answer_field.setTextColor_(NSColor.labelColor())
            self._answer_field.cell().setWraps_(True)
            self._answer_field.cell().setLineBreakMode_(
                NSLineBreakByWordWrapping
            )
            self._answer_field.setAlphaValue_(0.0)

            # Close (collapse) button — "✕" at top-right of effect view
            self._close_label = NSTextField.alloc().initWithFrame_(
                NSMakeRect(0, 0, 30, 30)
            )
            self._close_label.setStringValue_("✕")
            self._close_label.setFont_(NSFont.systemFontOfSize_(18))
            self._close_label.setBezeled_(False)
            self._close_label.setDrawsBackground_(False)
            self._close_label.setEditable_(False)
            self._close_label.setSelectable_(False)
            self._close_label.setTextColor_(NSColor.secondaryLabelColor())
            self._close_label.setAlignment_(1)  # NSTextAlignmentCenter
            self._close_label.setAlphaValue_(0.0)

            # Drag + click handler using objc.super
            app_ref = self

            class _DragClickView(NSView):
                def initWithFrame_(self, frame):
                    self = objc.super(_DragClickView, self).initWithFrame_(frame)
                    if self is None:
                        return None
                    self._dragged = False
                    self._mouse_down_origin = None
                    return self

                def mouseDown_(self, event):
                    self._dragged = False
                    self._mouse_down_origin = event.locationInWindow()

                def mouseDragged_(self, event):
                    self._dragged = True
                    origin = self._mouse_down_origin
                    current = event.locationInWindow()
                    win = self.window()
                    if win and origin:
                        frame = win.frame()
                        dx = current.x - origin.x
                        dy = current.y - origin.y
                        frame.origin.x += dx
                        frame.origin.y += dy
                        win.setFrameOrigin_(frame.origin)

                def mouseUp_(self, event):
                    if not self._dragged:
                        if app_ref._collapsed:
                            app_ref._expand_panel()
                            return
                        # Check close button hit — convert click to effect view coords
                        loc = event.locationInWindow()
                        try:
                            ev = app_ref._effect_view
                            pt = ev.convertPoint_fromView_(loc, None)
                            cf = app_ref._close_label.frame()
                            # Generous 40x40 hit area centered on the button
                            pad = 5
                            if (cf.origin.x - pad <= pt.x <= cf.origin.x + cf.size.width + pad
                                    and cf.origin.y - pad <= pt.y <= cf.origin.y + cf.size.height + pad):
                                app_ref._collapse_panel()
                                return
                        except Exception:
                            pass
                        if app_ref._showing_answer:
                            pass  # click elsewhere on answer — do nothing
                        elif app_ref._current_answer:
                            app_ref._on_suggestion(None)

            drag_view = _DragClickView.alloc().initWithFrame_(
                NSMakeRect(0, 0, ew, eh)
            )
            self._drag_view = drag_view

            # Container: transparent NSView holding image + effect bubble
            container = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, cw, ch))
            container.setWantsLayer_(True)
            container.addSubview_(self._image_view)
            container.addSubview_(effect)
            effect.addSubview_(self._message_field)
            effect.addSubview_(self._boni_label)
            effect.addSubview_(self._suggestion_field)
            effect.addSubview_(self._answer_field)
            effect.addSubview_(self._close_label)
            container.addSubview_(drag_view)
            self._container_view = container
            panel.setContentView_(container)

            if self.floating_visible:
                panel.orderFront_(None)

            self.panel = panel
            self._collapsed = True
            print("[boni] Floating window created (collapsed)")

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
        """Show the AI answer inline by expanding the bubble downward."""
        if not self._current_answer:
            return
        self._expand_answer_panel()

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
