# boni — UX Design Plan

## Context

RunCat proved that people engage with system metrics when presented as emotion rather than data. boni takes this further: instead of just animation speed, an AI-driven creature **empathizes and communicates** about your Mac's state. The core value is turning digital frustration into companionship — a tiny creature that suffers alongside you, making you smile instead of curse.

**Language**: Python (cross-platform — macOS first, Windows expansion planned)

---

## Design Principles

| Principle | In Practice |
|---|---|
| **Glanceability** | boni communicates in under 1 second of looking |
| **Emotion over information** | The user never sees a number. Everything is boni's mood. |
| **Tiny footprint, large personality** | Minimal screen space, disproportionately memorable presence |
| **Surprise sustains attachment** | Gemini generates fresh reactions — boni is never predictable |
| **Respect the host** | boni never nags, never interrupts, never degrades system health |

---

## User Journey

### Day 0: "Who is this?" (First 5 minutes)
- No splash screen, no tutorial. boni simply **appears** in the menu bar, already reacting to the current system state.
- First message is contextual to the exact moment — not a canned welcome.
- The user clicks the menu bar icon out of curiosity and sees boni with a speech bubble. A single line at the bottom: *"This is boni. It lives in your Mac now."* That's the entire onboarding.

### Days 1–3: "Oh, it notices things"
- The user passively catches boni's reactions — puffed cheeks when RAM is full, sweating when CPU is hot, sleepy eyes at 2am.
- Zero notifications, zero badges. boni earns attention by being interesting, not demanding it.
- **UX goal**: The user thinks "Ha!" at least once a day.

### Weeks 1–3: "It knows me"
- boni starts referencing patterns: "Third late night this week, huh?" / "You always open Spotify before a big coding session."
- The shift from "reacts to now" to "remembers before" is the biggest driver of attachment.
- **UX goal**: The user thinks "How does it know that?" at least once a week.

### Month 1+: "It's mine"
- boni has shared history with the user. Rare special moments appear:
  - Anniversary: "It's been one month. I've survived 847 Chrome tabs."
  - Milestones: First all-nighter, first CPU 100%, etc.
- The user feels reluctance at the idea of uninstalling — that's the sign of success.

---

## Personality: "The Grumpy Roommate"

boni is not a servant or assistant. It's a tiny creature that **lives in your Mac and did not ask to be here**.

- **Grumpy but affectionate**: Complains constantly but clearly cares. Tsundere energy. Closes tabs → "...thanks. Not that I needed you to."
- **Dramatic**: Treats minor system events as existential crises. Fan spins up? "THIS IS THE END."
- **Observant and slightly judgy**: Notices everything, makes snarky observations. "YouTube again? I respect the consistency."
- **Vulnerable when things get serious**: When the system truly struggles, boni drops the snark and becomes genuinely pathetic. This tonal shift from comedy to pathos creates emotional investment.

### Dialogue Rules for Gemini
1. Never use technical language. Not "CPU at 92%" → "I can't breathe."
2. First person always. Not "Your RAM is full" → "I ate too much and now I feel sick."
3. Maximum one sentence. Brevity is personality.
4. Vary the register — same situation, different reaction each time.
5. Tone: internet-native and witty, not childish.

---

## Emotional State Model

| Mood | Triggers | Visual | Tone |
|---|---|---|---|
| **Chill** | Low CPU, plenty of RAM, battery >50% | Lounging, slow idle | Relaxed idle commentary |
| **Stuffed** | High RAM, many apps open | Puffy cheeks, waddling | Food metaphors, complaining |
| **Overheated** | High CPU, fan activity | Sweating, sunglasses | Sauna jokes, dramatic |
| **Dying** | Battery <15%, extreme stress | Blanket, eyes closing | Desperate, guilt-inducing |
| **Suspicious** | Camera/mic active | Narrowed eyes, looking around | Paranoid, "who's watching?" |
| **Judgy** | Entertainment apps during work hours | Arms crossed, eyebrow raised | Snarky rhetorical questions |
| **Pleased** | User frees resources, plugs charger | Slight smile, brief glow | Grudging thanks, tsundere |
| **Nocturnal** | After midnight | Sleepy, yawning, nightcap | Sleep-deprived humor |

Mood is **holistic** — not a 1:1 mapping to a single metric. Gemini reads the full bundle of signals and produces a coherent emotional interpretation.

---

## Signature UX Moments

### The Charger Moment
Plugging in the charger while boni is "Dying" → immediate visible relief. "You came back for me..." This **rewards a physical action with an emotional response** — bridges physical and digital.

### The Late Night Check-In
After midnight, boni gets sleepier and more sympathetic. "Still going, huh? I'll stay up with you." Makes the user feel accompanied during solo late-night work.

### The Tab Guilt Trip
30+ Chrome tabs → boni visibly stuffed and uncomfortable. "I have 47 tabs inside me and I can feel each one." User closes tabs → boni deflates with relief. "Oh thank god. I can see my feet again."

### The App-Aware Quip
- Opening Figma after coding: "Switching to the pretty side, I see."
- Spotify opens: "Ooh, what's the vibe today?"
- Zoom opens: "Meeting time? I'll judge silently."
- YouTube for 30 min: "Stop watching YouTube and get to work!"

### The Callback
After a week+, boni references past events: "Last time your CPU was this hot, you were exporting that video for three hours." Creates the illusion of shared history.

### The Click/Pet
Click boni → mood-dependent reaction:
- Chill: "Hmm? Oh, hi."
- Stuffed: "Don't poke me, I'll pop."
- Dying: "...is this goodbye?"
- Judgy: "Yes? Can I help you? Oh wait, I don't work here."

---

## Where boni Lives (Information Architecture)

### Menu Bar Icon (Primary — Always Visible)
- Small animated icon (18x18pt) showing boni's current mood
- Communicates through posture and animation speed (RunCat's proven model)
- **Never shows numbers or percentages**

### Menu Bar Dropdown (On Click)
- Larger boni view (~80x80pt) with animation
- Speech bubble with current one-liner
- Last 2–3 past messages, lightly grayed
- Click/pet interaction zone
- Minimal controls: gear icon → Settings, "..." → About/Quit

### Floating Mode (Optional, OFF by default)
- boni sits on the edge of the active window (Magnetic Bounding Box from existing design doc)
- Hops to new window when active window changes
- Click-through for everything except boni itself — never interferes with work
- Power-user feature for people who want boni more present

### Notifications: Almost None
- Only exception: battery <5% — one notification. "I'm about to pass out. Charger. Now. Please."
- Everything else is ambient. boni waits to be noticed.

---

## Settings (Keep It Minimal)

| Category | Setting | Details |
|---|---|---|
| **Appearance** | Character style | 2–3 variants (fairy, cat creature, tiny monster) — same personality, different visuals |
| | Floating mode | ON/OFF (default OFF) |
| **Behavior** | Chattiness | 3 levels: Quiet / Normal / Chatty |
| | Language | English, Korean, Japanese |
| **Privacy** | Screen awareness | ON/OFF — when OFF, boni only reacts to system metrics, not app names |
| | Context memory | ON/OFF — when OFF, every session is fresh |
| | Clear memory | Wipe all accumulated context. boni says: "Wait, no—" |
| **System** | Gemini API key | Text field |
| | Launch at login | Toggle |

That's it. No themes, no color pickers, no advanced metrics. Simplicity is the feature.

---

## Why This Survives the AI Explosion

1. **Generative variety**: Gemini produces each reaction fresh — boni never becomes predictable like rule-based alternatives
2. **Context accumulation**: boni gets more valuable over time — uninstalling means losing your "relationship"
3. **Emotional, not informational**: boni never competes with Activity Monitor or iStat Menus — it competes with the feeling of having a pet

---

## Verification

- Walk through each user journey phase and verify the UX moments are achievable
- Test personality prompts with Gemini to ensure dialogue quality matches the tone guidelines
- Validate that the emotional state model covers the most common real-world scenarios
- Prototype the menu bar interaction flow to confirm glanceability
- Test floating mode to ensure it never obstructs user work
