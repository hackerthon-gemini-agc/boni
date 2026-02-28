# boni

Mac 메뉴바에 사는 투덜이 AI 데스크톱 컴패니언. Gemini 기반.

boni는 시스템 상태(CPU, RAM, 배터리, 실행 중인 앱, 시간대)를 모니터링하고 츤데레 "투덜대는 룸메이트" 성격으로 위트 있는 한 줄 반응을 합니다. 숫자도, 대시보드도 없이 — 오직 감정으로.

## 세팅 방법

### 1. 사전 요구사항

- macOS
- Python 3.10+

### 2. 클론 및 설치

```bash
git clone <repo-url>
cd boni
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Gemini API 키 설정

[Google AI Studio](https://aistudio.google.com/apikey)에서 API 키를 발급받으세요.

**방법 A** — 메뉴바에서 설정 (추천):

boni를 먼저 실행한 뒤, 😌 클릭 → 🔑 Set API Key 에 키를 붙여넣기 하세요.

**방법 B** — 환경변수:

```bash
export GEMINI_API_KEY="your-api-key-here"
```

**방법 C** — 설정 파일:

```bash
mkdir -p ~/.boni
echo '{"api_key": "your-api-key-here"}' > ~/.boni/config.json
```

### 4. 실행

```bash
source .venv/bin/activate
python run.py
```

메뉴바에 기분 이모지(😌, 🥵, 💀 등)와 함께 플로팅 말풍선이 나타납니다.

## 참고 자료

- 기술적 사례: https://gemini.google.com/share/44b05dd09bc4
