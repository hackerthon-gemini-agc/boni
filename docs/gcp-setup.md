# Boni 장기 기억 시스템 — GCP 설정 가이드

## 프로젝트 정보
- GCP 프로젝트: `gemini-hackathon-488801`
- 리전: `asia-northeast3` (서울)

## 1. API 활성화

```bash
gcloud config set project gemini-hackathon-488801

gcloud services enable \
  run.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com
```

## 2. Cloud Storage 버킷 생성

```bash
gsutil mb -l asia-northeast3 gs://boni-memories
```

## 3. Vertex AI Vector Search 인덱스 생성

### 3-1. 빈 인덱스 생성

```bash
gcloud ai indexes create \
  --display-name=boni-memory-index \
  --description="Boni long-term memory embeddings" \
  --metadata-schema-uri="" \
  --region=asia-northeast3 \
  --dimensions=768 \
  --approximate-neighbors-count=10 \
  --distance-measure-type=COSINE_DISTANCE \
  --shard-size=SHARD_SIZE_SMALL \
  --index-update-method=STREAM_UPDATE
```

인덱스 ID를 메모해둔다 (예: `1234567890`).

### 3-2. 인덱스 엔드포인트 생성

```bash
gcloud ai index-endpoints create \
  --display-name=boni-memory-endpoint \
  --region=asia-northeast3 \
  --public-endpoint-enabled
```

엔드포인트 ID를 메모해둔다.

### 3-3. 인덱스를 엔드포인트에 배포

```bash
gcloud ai index-endpoints deploy-index ENDPOINT_ID \
  --deployed-index-id=boni_memory_deployed \
  --display-name=boni-memory-deployed \
  --index=INDEX_ID \
  --region=asia-northeast3
```

> 배포에 15-30분 소요될 수 있음.

## 4. 서비스 계정 설정

```bash
# Cloud Run용 서비스 계정 (자동 생성됨, 필요시 권한 추가)
PROJECT_NUMBER=$(gcloud projects describe gemini-hackathon-488801 --format="value(projectNumber)")

# Storage 권한
gcloud projects add-iam-policy-binding gemini-hackathon-488801 \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Vertex AI 권한
gcloud projects add-iam-policy-binding gemini-hackathon-488801 \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

## 5. Cloud Run 배포

### 5-1. Docker 이미지 빌드 & 푸시

```bash
cd /path/to/boni

# Cloud Build로 빌드 (로컬 Docker 불필요)
gcloud builds submit --tag gcr.io/gemini-hackathon-488801/boni-memory backend/
```

### 5-2. Cloud Run 서비스 생성

```bash
gcloud run deploy boni-memory \
  --image gcr.io/gemini-hackathon-488801/boni-memory \
  --region asia-northeast3 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT=gemini-hackathon-488801,GCP_LOCATION=asia-northeast3,GCS_BUCKET=boni-memories,VECTOR_SEARCH_ENDPOINT_ID=YOUR_ENDPOINT_ID,VECTOR_SEARCH_DEPLOYED_INDEX_ID=boni_memory_deployed" \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 2
```

배포 후 출력되는 URL을 메모 (예: `https://boni-memory-xxxxx-an.a.run.app`).

## 6. 클라이언트 설정

boni 앱에서 환경변수를 설정:

```bash
export BONI_MEMORY_URL="https://boni-memory-xxxxx-an.a.run.app"
```

또는 `~/.boni/config.json`에 추가하거나, 실행 스크립트에 포함.

## 7. 검증

```bash
# 헬스체크
curl https://boni-memory-xxxxx-an.a.run.app/api/v1/health

# 메모리 저장 테스트
curl -X POST https://boni-memory-xxxxx-an.a.run.app/api/v1/memories \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": {"cpu_percent": 45, "ram_percent": 72, "battery_percent": 88, "is_charging": true, "active_app": "VS Code", "running_apps": 12, "hour": 14, "minute": 30},
    "reaction": {"message": "You have been staring at code for 3 hours...", "mood": "judgy"}
  }'

# 메모리 검색 테스트
curl -X POST https://boni-memory-xxxxx-an.a.run.app/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d '{"query": "VS Code coding afternoon", "top_k": 3}'
```

## 비용 참고

- Cloud Run: 요청당 과금, 유휴 시 무료 (min-instances=0)
- Cloud Storage: GB당 월 ~$0.02
- Vertex AI Embedding: 1000자당 ~$0.00002
- Vector Search: 인덱스 배포 시 노드 비용 발생 (~$0.30/시간)
  - **주의**: Vector Search 노드는 배포 중 상시 과금. 테스트 후 필요 없으면 undeploy 할 것.
