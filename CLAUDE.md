# Boni

## Git 워크플로우

- 4명이 **main 브랜치 하나**에서 직접 작업한다
- 브랜치 만들지 않는다. commit → pull → push를 빠르게 반복한다
- 커밋은 작고 자주 한다. 큰 변경을 한 번에 올리지 않는다

### 커밋/푸시 순서

1. `git add` — 변경된 파일만 개별 지정
2. `git commit` — 간결한 메시지
3. `git pull --rebase` — 원격 변경사항을 rebase로 가져온다
4. conflict 발생 시 AI agent가 자동 해결한다. 해결 후 `git rebase --continue`
5. `git push`

### Conflict 해결 원칙

- 양쪽 변경사항을 최대한 살린다 (둘 다 유지)
- 의미가 충돌하면 최신(remote) 로직을 우선한다
- 해결 후 앱이 깨지지 않는지 확인한다
