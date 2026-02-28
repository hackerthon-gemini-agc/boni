# boni 🦝

> Mac 메뉴바에 사는 투덜이 AI 데스크톱 컴패니언 — Gemini 기반

boni는 당신의 Mac 안에서 살아가는 너구리 룸메이트입니다. CPU가 터질 것 같으면 같이 헥헥거리고, 새벽까지 일하면 잔소리하고, 막히는 일이 있으면 먼저 도움을 제안합니다. 숫자도, 대시보드도 없이 — 오직 감정으로.

---

## 데모

![boni demo](boni/image/boni.png)

메뉴바에 기분 이모지(🦝 😮 🥵 😢 🧐 😏 😊 😴)가 표시되고, 플로팅 말풍선이 나타납니다. 평소엔 접혀 있다가 새 반응이 오면 자동으로 펼쳐지고 8초 뒤 다시 접힙니다.

---

## 핵심 기능

### 1. 실시간 감정 반응
시스템 상태를 감지해 Gemini가 한 줄짜리 캐릭터 대사를 생성합니다.

| 상태 | boni 반응 |
|------|-----------|
| CPU 80%+ | 🥵 "헥헥... 여기 왜 이렇게 더워 ㅠㅠ" |
| 배터리 15% 이하 | 😢 "으앙... 힘들어... 충전해줘...!" |
| 새벽 작업 중 | 😴 "쿨쿨... 아직 안 자? 나는 졸려..." |
| 업무 중 유튜브 | 😏 "에헤헤~ 지금 이거 보는 거야? ㅎㅎ" |

### 2. 행동 패턴 인식
boni는 단순한 시스템 지표 그 이상을 봅니다:

- **앱 전환 감지** — NSWorkspace 알림으로 즉각 반응
- **창 체류 감지** — 같은 화면을 2분 이상 보고 있으면 nudge
- **좌절 패턴** — backspace 비율 30%+ AND 마우스 클릭 30회/분 이상이면 격려
- **한숨 감지** — 마이크 오디오 진폭 패턴 분석 (키입력/내용 불녹음)
- **타이핑 급증** — 100키/분 이상이면 열정을 칭찬
- **유휴 감지** — 자리를 비우면 기다림 메시지

### 3. 화면 인식 + 선제적 도움
행동 이벤트 발생 시 활성 창 스크린샷을 찍어 Gemini Vision에 전달합니다. 쇼핑 비교, 긴 글 읽기, 폼 작성 등 막혀 보이는 상황을 감지하면 먼저 도움을 제안합니다:

```
boni: "결정장애 왔냐? 내가 골라줌"
→ 클릭하면 비교 분석 결과가 말풍선 안에 바로 펼쳐짐
```

### 4. 장기 기억 (GCP 백엔드)
매 60초마다 현재 상태와 반응을 GCP 백엔드에 저장합니다. 다음 반응 시 과거 기억을 벡터 검색으로 불러와 문맥에 맞게 참고합니다 ("아까 힘들어 했는데 이제 좀 나아?").

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    macOS (클라이언트)                     │
│                                                         │
│  SystemSensor ──→ EventAccumulator ──→ BoniBrain        │
│  (CPU/RAM/배터리    (점수 기반 이벤트      (Gemini API     │
│   앱/타이핑/클릭/   필터링 + 버퍼링)       + 화면 캡처)    │
│   한숨/유휴)                                             │
│                          │                              │
│  BoniApp (rumps)  ←──────┘                              │
│  (메뉴바 + 플로팅                                        │
│   말풍선 PyObjC)                                         │
│         │                                               │
│  BoniMemory ──→ GCP Backend (Cloud Run + Firestore)     │
│  (장기 기억        + Vertex AI Embeddings + Vector Search)│
└─────────────────────────────────────────────────────────┘
```

### 클라이언트 모듈

| 모듈 | 역할 |
|------|------|
| `sensor.py` | 시스템 지표 수집, 앱 전환/체류/유휴/행동 패턴 감지, 스크린샷 |
| `accumulator.py` | 이벤트를 점수화하여 AI 호출 빈도 제어 |
| `brain.py` | Gemini API 연동, 프롬프트 구성, 응답 파싱 |
| `mood.py` | 시스템 지표 → 8가지 감정 상태 매핑 |
| `memory.py` | GCP 백엔드 API 클라이언트 (store / recall) |
| `app.py` | rumps 메뉴바 앱 + PyObjC 플로팅 패널 |

### 백엔드 (GCP Cloud Run)

| 모듈 | 역할 |
|------|------|
| `main.py` | FastAPI 서버, `/api/v1/memories` 엔드포인트 |
| `embeddings.py` | Vertex AI text-embedding-004로 텍스트 벡터화 |
| `vector_search.py` | Firestore 벡터 유사도 검색 |
| `storage.py` | Firestore CRUD |

---

## 기술 스택

- **AI**: Google Gemini 3 Flash Preview (텍스트 + Vision)
- **임베딩**: Vertex AI text-embedding-004
- **백엔드**: Cloud Run (FastAPI) + Firestore
- **클라이언트**: Python, rumps, PyObjC, psutil, pynput, sounddevice
- **플랫폼**: macOS (네이티브 NSPanel, NSVisualEffectView)

---

## 세팅 방법

### 사전 요구사항

- macOS
- Python 3.10+
- [Google AI Studio](https://aistudio.google.com/) Gemini API 키

### 빠른 세팅 (추천)

```bash
git clone <repo-url>
cd boni
./setup.sh
```

venv 생성, 의존성 설치, API 키 입력까지 한 번에 진행됩니다.

### 실행

```bash
source .venv/bin/activate
python run.py
```

### 장기 기억 활성화 (선택)

GCP 백엔드 URL이 있다면:

```bash
export BONI_MEMORY_URL=https://your-backend-url
python run.py
```

### macOS 권한

원활한 동작을 위해 다음 권한을 허용해 주세요:
- **손쉬운 사용(Accessibility)** — 창 제목 읽기, 키보드/마우스 모니터링
- **화면 녹화(Screen Recording)** — 화면 스냅샷 (Vision 기능 사용 시)
- **마이크** — 한숨 감지 (선택)

---

## 팀

해커톤 출품작입니다.
