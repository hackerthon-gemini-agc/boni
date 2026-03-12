# boni 🦝

> Event-driven AI desktop companion for hackathons.

**boni** is a lightweight macOS agent that creates the feeling of being "watched" without constant polling.
It reacts only to key OS events, captures context with a short delay, sends it to an AI brain, and returns a strict JSON response for the UI.

---

## Why this project

Most productivity companions over-monitor everything. boni does the opposite:

- **Event-first, not always-on analysis**
- **Fast MVP architecture** for a live demo
- **Character-driven feedback** with strict machine-parseable output

---

## MVP Rules (must-have)

- No continuous polling-based analysis.
- On trigger, wait **1–2 seconds** before screenshot capture.
- AI output must be **one valid JSON object** (no parsing failures allowed).
- Only these 3 trigger families are supported in MVP.

### Supported triggers

1. `active_window_changed` / `active_window_title_changed`
2. `window_dwell_timeout` (default: 2 minutes)
3. `system_idle_threshold` (idle for 10+ seconds)

### Trigger payload (Role 3 → Role 2)

```json
{
  "reason": "active_window_changed|active_window_title_changed|window_dwell_timeout|system_idle_threshold",
  "ts": 1735689600.0,
  "app_name": "Visual Studio Code",
  "window_title": "main.py",
  "idle_seconds": 0,
  "dwell_seconds": 12
}
```

### AI response schema (Role 2 → UI)

```json
{
  "대사": "또 딴짓하다 들켰지.",
  "표정": "비웃음",
  "위치": "활성창_오른쪽",
  "mood": "judgy"
}
```

Allowed values:

- `표정`: `무표정 | 비웃음 | 노려봄 | 한심 | 소름 | 졸림`
- `위치`: `활성창_오른쪽 | 활성창_중앙 | 메뉴바_근처`

---

## Architecture (Cloud Brain + Local Executor)

### Cloud (heavy reasoning)

- **Long-term memory**: Cloud Storage + Vertex AI Vector Search
- **Reasoning**: Vertex AI Gemini (long-context, multimodal)
- **Gateway/security**: Cloud Run middleware to hide keys and filter dangerous commands

### Local macOS node (lightweight)

- **Sensor**: OS hooks for trigger detection + delayed screenshot capture
- **Executor**: safe CLI command execution via subprocess
- **UI**: floating companion window (PyQt/Electron)

---

## Team roles (4-way split)

- **Role 1 — GCP & RAG Architect**: storage, embeddings, retrieval pipeline
- **Role 2 — Prompt & Agent Logic**: trigger+snapshot reasoning, strict JSON output
- **Role 3 — Local Node & CLI Executor**: trigger loop, delayed capture, payload delivery
- **Role 4 — UI & Integration PM**: magnetic overlay, async integration, demo direction

---

## 3-minute hackathon demo

1. User previously viewed relevant content (already embedded in cloud memory).
2. User triggers an error in IDE; local node captures context after delay.
3. Cloud reasoning compares current screen with past memory (RAG).
4. Companion responds with a mocking/helpful line and suggests a fix.
5. On approval, safe CLI flow runs patch/test and shows success logs.

---

## Quick start

### Requirements

- macOS
- Python 3.10+
- Gemini API key

### Setup

```bash
git clone <repo-url>
cd boni
./setup.sh
```

### Run

```bash
source .venv/bin/activate
python run.py
```

### Optional: memory backend

```bash
export BONI_MEMORY_URL=https://your-backend-url
python run.py
```

---

## macOS permissions

Grant these for full functionality:

- Accessibility
- Screen Recording
- Microphone (optional)

---

## Hackathon note

Built as a demo-first MVP: strict interfaces, strong personality, and reliable live flow.
