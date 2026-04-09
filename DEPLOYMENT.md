# DEPLOYMENT.md

## Single Source of Truth

이 프로젝트의 코드/배포 기준은 아래 한 줄로 고정한다.

- **Repo:** `marketing-workflow-dashboard`
- **Pages project:** `rf-marketing-dashboard`
- **Deploy command:** `./scripts/deploy_pages.sh`

## Why this file exists

이전에는 repo 이름과 실제 Pages 프로젝트 이름이 달라서,
수정은 한 프로젝트에서 하고 확인은 다른 배포본에서 보는 혼선이 발생했다.

앞으로는 아래 원칙을 지킨다.

1. `site/index.html` 헤더의 배지(`repo: ...`, `pages: ...`)가 맞는지 먼저 확인
2. 배포는 직접 `wrangler` 명령을 치지 말고 **반드시** `./scripts/deploy_pages.sh` 사용
3. README / DEPLOYMENT.md / 화면 헤더의 repo/pages 표기가 서로 달라지면 즉시 수정

## Pre-deploy checklist

- [ ] 수정한 파일이 `marketing-workflow-dashboard/` 안에 있다
- [ ] 화면 헤더 배지에 `repo: marketing-workflow-dashboard` 표시가 있다
- [ ] 화면 헤더 배지에 `pages: rf-marketing-dashboard` 표시가 있다
- [ ] 배포는 `./scripts/deploy_pages.sh` 로 실행한다
- [ ] 배포 후 실제 URL에서 변경 요소를 바로 확인한다
