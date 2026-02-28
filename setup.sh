#!/bin/bash
# boni 초기 세팅 스크립트

set -e

echo "🐾 boni 세팅을 시작합니다..."
echo ""

# 1. venv 생성
if [ ! -d ".venv" ]; then
    echo "📦 가상환경 생성 중..."
    python3 -m venv .venv
fi

# 2. 의존성 설치
echo "📦 의존성 설치 중..."
source .venv/bin/activate
pip install -q -r requirements.txt

# 3. API 키 설정
echo ""
read -p "🔑 Gemini API 키를 입력하세요 (건너뛰려면 Enter): " api_key

if [ -n "$api_key" ]; then
    mkdir -p ~/.boni
    echo "{\"api_key\": \"$api_key\"}" > ~/.boni/config.json
    echo "✅ API 키 저장 완료 (~/.boni/config.json)"
else
    echo "⏭️  건너뜀 — 나중에 메뉴바 🔑 Set API Key 에서 설정할 수 있어요."
fi

echo ""
echo "✅ 세팅 완료! 아래 명령어로 실행하세요:"
echo ""
echo "   source .venv/bin/activate"
echo "   python run.py"
echo ""
