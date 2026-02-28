# Boni 장기 기억 시스템 — GCP 설정 가이드

## 프로젝트 정보
- GCP 프로젝트: `gemini-hackathon-488801`
- 프로젝트 번호: `164559031993`
- 리전: `asia-northeast3` (서울)

## 현재 배포 현황

### Cloud Run
| 서비스 | URL | 메모리 | 인스턴스 |
|--------|-----|--------|---------|
| `boni-memory` | https://boni-memory-164559031993.asia-northeast3.run.app | 512Mi | 0~2 (자동 스케일) |

### Vector Search (Vertex AI)
| 리소스 | ID | 비고 |
|--------|-----|------|
| 인덱스 | `3833693580845645824` | 768차원, cosine, stream update |
| 엔드포인트 | `8488871881221341184` | public endpoint |
| 배포된 인덱스 | `boni_memory_deployed` | replica 2개 |

### Cloud Storage
| 버킷 | 경로 | 용도 |
|-------|------|------|
| `gs://boni-memories` | `raw/{user_id}/{date}/{id}.json` | 메모리 원시 JSON 저장 (사용자별 분리) |

### Artifact Registry
| 리포지토리 | 형식 | 용도 |
|-----------|------|------|
| `cloud-run-source-deploy` | DOCKER | Cloud Run 빌드 이미지 |

### 활성화된 API
| API | 용도 |
|-----|------|
| Cloud Run | 백엔드 서비스 호스팅 |
| Cloud Storage | 메모리 JSON 저장 |
| Vertex AI | 임베딩 생성 + Vector Search |
| Cloud Build | 소스 → Docker 이미지 빌드 |
| Artifact Registry | Docker 이미지 저장소 |

### IAM (서비스 계정: `164559031993-compute@developer.gserviceaccount.com`)
| 역할 | 용도 |
|-------|------|
| `roles/storage.objectAdmin` | GCS 읽기/쓰기 |
| `roles/aiplatform.user` | Vertex AI 임베딩 + Vector Search |

## 1. API 활성화

```bash
gcloud config set project gemini-hackathon-488801

gcloud services enable \
  run.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com
```

## 2. Cloud Storage 버킷 생성

```bash
gsutil mb -l asia-northeast3 gs://boni-memories
```

## 3. Vertex AI Vector Search 인덱스 생성

### 3-1. 인덱스 메타데이터 파일 생성

`--dimensions` 등의 플래그가 gcloud 버전에 따라 지원 안 될 수 있으므로 metadata-file 방식 사용:

```json
// /tmp/boni-index-metadata.json
{
  "contentsDeltaUri": "",
  "config": {
    "dimensions": 768,
    "approximateNeighborsCount": 10,
    "distanceMeasureType": "COSINE_DISTANCE",
    "shardSize": "SHARD_SIZE_SMALL",
    "algorithmConfig": {
      "treeAhConfig": {
        "leafNodeEmbeddingCount": 1000,
        "leafNodesToSearchPercent": 10
      }
    }
  }
}
```

### 3-2. 인덱스 생성

```bash
gcloud ai indexes create \
  --display-name=boni-memory-index \
  --description="Boni long-term memory embeddings" \
  --region=asia-northeast3 \
  --metadata-file=/tmp/boni-index-metadata.json \
  --index-update-method=STREAM_UPDATE
```

생성된 인덱스 ID: `3833693580845645824`

### 3-3. 인덱스 엔드포인트 생성

```bash
gcloud ai index-endpoints create \
  --display-name=boni-memory-endpoint \
  --region=asia-northeast3 \
  --public-endpoint-enabled
```

생성된 엔드포인트 ID: `8488871881221341184`

### 3-4. 인덱스를 엔드포인트에 배포

```bash
gcloud ai index-endpoints deploy-index 8488871881221341184 \
  --deployed-index-id=boni_memory_deployed \
  --display-name=boni-memory-deployed \
  --index=3833693580845645824 \
  --region=asia-northeast3
```

> 배포에 15-30분 소요될 수 있음. 비동기 작업으로 진행됨.

## 4. 서비스 계정 설정

```bash
# Storage 권한
gcloud projects add-iam-policy-binding gemini-hackathon-488801 \
  --member="serviceAccount:164559031993-compute@developer.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Vertex AI 권한
gcloud projects add-iam-policy-binding gemini-hackathon-488801 \
  --member="serviceAccount:164559031993-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

## 5. Cloud Run 배포

소스에서 직접 빌드+배포 (Cloud Build + Artifact Registry 자동 사용):

```bash
gcloud run deploy boni-memory \
  --source backend/ \
  --region asia-northeast3 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT=gemini-hackathon-488801,GCP_LOCATION=asia-northeast3,GCS_BUCKET=boni-memories,VECTOR_SEARCH_ENDPOINT_ID=8488871881221341184,VECTOR_SEARCH_DEPLOYED_INDEX_ID=boni_memory_deployed" \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 2
```

## 6. 클라이언트 설정

boni 앱에서 환경변수를 설정:

```bash
export BONI_MEMORY_URL="https://boni-memory-164559031993.asia-northeast3.run.app"
```

또는 `~/.boni/config.json`에 추가하거나, 실행 스크립트에 포함.

### user_id 자동 관리

첫 실행 시 `~/.boni/config.json`에 UUID 기반 `user_id`가 자동 생성됩니다.
이 ID로 메모리 저장/검색이 사용자별로 분리됩니다.

```json
{
  "api_key": "YOUR_GEMINI_API_KEY",
  "user_id": "a1b2c3d4e5f6..."
}
```

- GCS 경로: `raw/{user_id}/{date}/{memory_id}.json`
- Vector Search ID: `{user_id}_{memory_id}`
- `user_id`가 없는 기존 데이터는 `"anonymous"`로 간주됩니다.

## 7. 검증

```bash
# 헬스체크
curl https://boni-memory-164559031993.asia-northeast3.run.app/api/v1/health

# 메모리 저장 테스트
curl -X POST https://boni-memory-164559031993.asia-northeast3.run.app/api/v1/memories \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": {"cpu_percent": 45, "ram_percent": 72, "battery_percent": 88, "is_charging": true, "active_app": "VS Code", "running_apps": 12, "hour": 14, "minute": 30},
    "reaction": {"message": "You have been staring at code for 3 hours...", "mood": "judgy"}
  }'

# 메모리 검색 테스트
curl -X POST https://boni-memory-164559031993.asia-northeast3.run.app/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d '{"query": "VS Code coding afternoon", "top_k": 3}'
```

## 비용 참고

- Cloud Run: 요청당 과금, 유휴 시 무료 (min-instances=0)
- Cloud Storage: GB당 월 ~$0.02
- Vertex AI Embedding: 1000자당 ~$0.00002
- Vector Search: 인덱스 배포 시 노드 비용 발생 (~$0.30/시간)
  - **주의**: Vector Search 노드는 배포 중 상시 과금. 테스트 후 필요 없으면 undeploy 할 것.

## 리소스 정리 (필요 시)

```bash
# Vector Search 인덱스 undeploy (과금 중지)
gcloud ai index-endpoints undeploy-index 8488871881221341184 \
  --deployed-index-id=boni_memory_deployed \
  --region=asia-northeast3

# Cloud Run 서비스 삭제
gcloud run services delete boni-memory --region=asia-northeast3

# GCS 버킷 삭제
gsutil rm -r gs://boni-memories
```
