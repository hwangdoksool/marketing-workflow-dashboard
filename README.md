# 마케팅 워크플로우 대시보드

> 가설 → 실험 → 학습 사이클을 대시보드로 구현

| 항목 | 값 |
|------|---|
| **URL** | https://rf-marketing-dashboard.pages.dev |
| **Cloudflare Pages 프로젝트명** | `rf-marketing-dashboard` |
| **GitHub / 소스 정본** | `hwangdoksool/marketing-workflow-dashboard` |
| **시작일** | 2026-04-01 |

## 🔴 배포 단일 기준

이번 혼선 방지용으로 아래를 **정본**으로 고정합니다.

- **수정할 레포:** `marketing-workflow-dashboard`
- **배포할 Pages 프로젝트:** `rf-marketing-dashboard`
- **배포 명령:** `./scripts/deploy_pages.sh`
- 다른 폴더/과거 대시보드는 **참조용 또는 아카이브**로 보고, 여기서만 수정/배포합니다.

## 구조

```
docs/           ← PRD, 설계 문서
site/           ← 프론트엔드 (HTML/CSS/JS)
  index.html    ← 메인 대시보드
  tasks.json    ← 태스크 데이터 (기존 계승)
  reports.json  ← 주간 리포트 데이터
workers/        ← Cloudflare Workers (API)
scripts/        ← 데이터 수집 스크립트
```

## 탭 구조

1. **📊 주간 리뷰** — 구매자 역추적 / 채널별 성과 / 가설 검증 / 계획
2. **📋 Brief 관리** — Creative Brief 등록 / 가설 보드 / 학습 아카이브
3. **🎯 태스크** — 칸반/리스트 (기존 계승)
4. **📈 트렌드** — 시계열 지표 시각화

## 참조

- [PRD](docs/PRD.md)
- [운영 가이드 (노션)](https://www.notion.so/335478cb1fa581cba068c65b9977f55d)
- [진단 보고서 (노션)](https://www.notion.so/335478cb1fa581c19cb4c655e77a6025)
- 기존 대시보드: [rf-marketing-dashboard.pages.dev](https://rf-marketing-dashboard.pages.dev)
