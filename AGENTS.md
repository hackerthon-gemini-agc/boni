# 프로젝트명: Agentic AI Companion (Hackathon MVP)
**목표:** 모든 것을 감지하지 않는다. "AI가 나를 지켜본다"는 착각을 주는 이벤트 기반 반응 엔진을 구현한다.

## 0. MVP Operating Rules (필수)

- 폴링 기반 상시 분석 금지. 이벤트 기반 트리거를 우선한다.
- 트리거 발생 직후 즉시 분석하지 않고 `1~2초 지연 후` 화면 캡처를 수행한다.
- AI 출력은 반드시 JSON 단일 객체여야 하며 파싱 실패를 허용하지 않는다.
- 현재 MVP의 데이터 수집 트리거는 아래 3개만 지원한다.

### 트리거 정의

1. `active_window_changed` / `active_window_title_changed`  
   활성 창의 프로세스 또는 타이틀이 변경될 때.
2. `window_dwell_timeout`  
   특정 창에 N분 이상 머무를 때(기본 2분).
3. `system_idle_threshold`  
   시스템 유휴 상태가 10초 이상일 때.

### 트리거 페이로드 규격 (Role 3 -> Role 2)

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

### AI 응답 규격 (Role 2 -> UI)

```json
{
  "대사": "또 딴짓하다 들켰지.",
  "표정": "비웃음",
  "위치": "활성창_오른쪽",
  "mood": "judgy"
}
```

허용 값:
- `표정`: `무표정|비웃음|노려봄|한심|소름|졸림`
- `위치`: `활성창_오른쪽|활성창_중앙|메뉴바_근처`

## 1. Core Architecture (클라우드 두뇌 - 로컬 수족 분리 모델)

시스템의 무거운 연산(인지, 기억, 판단)은 GCP로 오프로딩하고, 로컬(맥북)은 깃털처럼 가벼운 실행기(Executor)와 감각 기관(Sensor) 역할만 수행한다.

* **해마 (Long-term Memory):** GCP Cloud Storage + Vertex AI Vector Search
    * 과거 에러 로그, 검색 기록, 스마트폰에서 본 문서 등의 파편화된 데이터를 벡터화하여 중앙 집중식으로 저장 및 검색 (Stateful Agent).
* **대뇌 (Long-Context Reasoning):** Vertex AI (Gemini 1.5 Pro)
    * 1M+ 토큰 윈도우를 활용. 과거의 벡터화된 문맥과 현재 로컬의 화면(멀티모달)을 동시에 인지하여 행동 판단.
* **척수 (Middleware & Security):** GCP Cloud Run
    * 로컬과 AI 사이의 게이트웨이. API Key를 은닉하고, 에이전트가 생성한 위험한 시스템 명령어(`rm -rf` 등)를 1차 필터링하여 안전한 커맨드만 로컬로 하강.
* **수족 및 감각 (Local Node):** Python OS Hook + Gemini CLI + PyQt/Electron
    * 자석 윈도우로 화면을 추적 및 캡처(Sensor)하고, Cloud Run에서 내려온 안전한 CLI 명령어를 `subprocess`로 실행(Executor).

---

## 2. Team Roles & Responsibilities (수직적 4인 분업)

각 파트는 서로의 코드를 알 필요가 없다. 오직 사전에 합의된 **JSON 규격**으로만 통신한다.

### 👤 Role 1: GCP & RAG Architect (클라우드 뇌 신경망)
* **미션:** 파편화된 활동 데이터를 에이전트의 '기억'으로 구축.
* **Task:**
    * 로컬에서 올라오는 이미지/텍스트 데이터를 Cloud Storage에 적재.
    * 데이터를 임베딩하여 Vertex AI Vector Search 파이프라인 구축.
    * 현재 화면과 유사한 과거의 '실수'나 '맥락'을 초고속으로 검색해 Role 2에게 제공.

### 👤 Role 2: Prompt & Agentic Logic (성격과 지능)
* **미션:** 트리거+스냅샷 기반으로 캐릭터성 강한 대사를 생성하고, UI가 파싱 가능한 엄격 JSON만 반환.
* **Task:**
    * Vertex AI Gemini API 프롬프트 엔지니어링 전담.
    * Role 3이 준 트리거 메타데이터 + 1~2초 지연 캡처 이미지를 결합 분석.
    * **출력 규격:** `{"대사": "...", "표정": "...", "위치": "...", "mood": "..."}` JSON 단일 객체 강제.

### 👤 Role 3: Local Node & CLI Executor (로컬 신경계 및 실행기)
* **미션:** 이벤트 기반 트리거를 감지해 최소 비용으로 "감시당하는 느낌"의 입력 데이터를 Role 2에 제공.
* **Task:**
    * 활성 창 변경 이벤트(NSWorkspace) + 유휴/체류 시간 감지 루프 운영.
    * 트리거 발생 시 1~2초 지연 후 활성 창 우선 캡처(실패 시 전체 화면 폴백).
    * 트리거 페이로드 + 스냅샷을 Role 2 입력으로 전달.

### 👤 Role 4: UI & Integration PM (시각화 및 데모 디렉터)
* **미션:** '자석 윈도우' 구현 및 3분 데모 시나리오의 완벽한 통합.
* **Task:**
    * PyQt/Electron 기반 배경 투명 오버레이 및 캐릭터 애니메이션 구현.
    * 활성 창(Active Window) 우측 상단 좌표를 추적해 캐릭터를 붙이는 로직 개발.
    * **통합 및 테스트:** 4개의 모듈이 비동기적으로 맞물릴 때 발생하는 Latency와 파싱 에러 방어. 데모 시연 시나리오 총괄.

---

## 3. The 3-Minute Killer Demo Scenario

해커톤 심사위원을 타격할 단 하나의 시나리오. 이 흐름이 막힘없이 돌아가는 것이 MVP의 유일한 목표다.

1.  **(과거 문맥 축적):** 사용자가 스마트폰으로 특정 논문이나 스택오버플로우를 보는 척한다. (데이터는 이미 GCP에 벡터로 저장됨)
2.  **(에러 발생 및 캡처):** 맥북 IDE에서 관련 코드를 짜다가 의도적으로 치명적인 에러를 발생시킨다. 자석처럼 붙어있던 캐릭터가 활성 창의 텍스트 타이핑 정지를 감지하고 화면을 캡처해 GCP로 전송한다.
3.  **(클라우드 추론):** Cloud Run + Vertex AI가 과거의 스마트폰 검색 기록(RAG)과 현재 에러 화면을 대조한다.
4.  **(자동 수정 및 조롱):** 캐릭터가 화면 중앙으로 날아오며 말한다. *"아까 폰으로 본 논문 수식 제대로 안 읽었죠? 차원(Dimension)이 안 맞잖아요. 제가 수정해서 돌려볼까요?"*
5.  **(CLI 실행):** 사용자가 승인하면, 백그라운드에서 Gemini CLI가 코드를 직접 덮어쓰고 테스트 런을 실행하여 초록색 성공 로그를 띄운다.
