---
title: 캠페인 비교 탭 (라이브) 기획
date: 2026-09-30
domain: 마케팅
status: confirmed
tags: [dashboard, campaign-compare, meta, naver, ga4, clarity]
---

# 캠페인 비교 탭 — 기획 (대표님 2026-09-30 20:14 지시, 20:17 지표 정정)

## 목적
대표님이 지금 도는 캠페인을 한 화면에서 비교하고, 어느 캠페인을 늘리고 줄일지 판단한다. 기준은 **판매에 가까운 행동 1건당 비용**이다.
기준선 화면: `marketing-pipeline/reports/campaign-compare/2026-09-30_campaign-compare.html`(이미지 https://wspn-images.wespion.workers.dev/reports/campaign-compare.png). 모양은 이걸 따르고, 지표는 아래와 같이 바꾼다.

## 절대 금지 지표
- **"구매 버튼 클릭"(GA4 `cta_click`)은 넣지 않는다.** 메인 팝업의 "구매하기"는 제품 페이지로 넘어가는 단순 이동이라 판단 지표가 아니다(대표님 강한 지적).
- 링크 클릭, CTR, 참여(좋아요 등)도 판단 열로 두지 않는다.

## 위치·배포
- 레포: `marketing-workflow-dashboard`. Pages 프로젝트: `rf-marketing-dashboard`. 배포는 `./scripts/deploy_pages.sh`만 쓴다(DEPLOYMENT.md 참조).
- `site/index.html`의 분석/리포트(`#analysis`) 아래에 서브탭 **"캠페인 비교"**를 추가한다. 해시는 `#analysis/compare`.
- 기존 탭·데이터 파일은 건드리지 않는다. 새 데이터 파일은 `site/campaign_compare.json` 하나만 쓴다.

## 화면
1. 상단
   - 기간 선택: 오늘 / 어제 / 최근 3일 / 7일 / 14일 / 30일 / 직접 지정(시작·끝 날짜).
   - 요약 KPI: 전체 지출, 깊은 관심 합계와 1건당 비용, 체험 신청 수, 아임웹 실판매 대수(기간 내).
   - "마지막 갱신 시각"을 표시한다.
2. 표: 한 행에 캠페인 하나.
   - 설정 열: 캠페인(코드·짧은 이름·상태 배지), 매체(Meta/네이버), 소재(종류·개수), 타겟 요약, 학습 기준(최적화 이벤트를 한국어로), 하루 예산, 시작일.
   - 판단 열(강조 색 = 브랜드 #5252FA 계열):
     1. **깊은 관심 1건당 비용**과 건수. 건수 옆에 종류별 내역을 작게 적는다(체험 페이지·결제 시작·상세 90초·커뮤니티·재방문).
     2. 체험 신청 수(1건당 비용)
     3. 구매(Meta 귀속 본체 구매, 1건당 비용)
   - 참고 열(회색): 지출, 방문 1회당 비용(랜딩 페이지 조회), 실제 체류(Clarity 활성 시간, 초).
   - 기간 안에 지출이 없는 캠페인은 "꺼짐 캠페인 보기" 토글을 켰을 때만 표시한다.
3. 정렬·필터: 열 제목 클릭 정렬, 상태(켜짐/꺼짐), 매체 필터. 필수 정보는 앞 열에 둔다(공통 규칙).
4. 행 클릭: 그 캠페인의 날짜별 추이(지출, 깊은 관심, 1건당 비용)를 작은 표나 막대로 펼친다.
5. 데이터 주의 표시
   - GA4 당일분은 처리 전이라 "참고"로 회색 표시한다. 전날까지가 확정이다.
   - 깊은 관심은 2026-09-30부터만 존재한다. 그 이전 기간을 고르면 "측정 전"으로 표시한다(0으로 표시하지 않는다).
   - Clarity는 날짜별로 쌓인 값만 있다. 없으면 "-"로 표시한다.
6. 모바일(텔레그램 인앱 브라우저)에서도 읽히게 한다. 표는 가로 스크롤을 허용하고, 첫 열은 고정한다.

## 상세 지표 (대표님 20:18 추가 지시: "상세한 지표들 전부 선택적으로 볼 수 있게 잘 꾸며봐, 클래리티든 뭐든")
- 기본 표는 위의 판단 열·참고 열만 보여 준다. 나머지는 "상세 지표" 패널에서 켜고 끈다.
  - 패널은 체크박스 그룹이다. 켜면 그 열이 표에 추가된다. 선택은 localStorage에 저장한다.
- 그룹과 항목(각 항목은 기간 합계 또는 가중 평균, 가능한 것은 1건당 비용도):
  - **Meta 노출·소재 반응**
    - 노출, 도달, 빈도, CPM
    - 영상 3초 조회율(훅), ThruPlay율, 평균 재생 시간
    - 링크 클릭률
    - 참여(저장·공유·댓글)
  - **사이트 도착 품질**
    - 랜딩 도착률(랜딩/링크 클릭)
    - GA4 세션, 참여 세션율, 세션당 참여 시간, 페이지/세션
    - 이탈 세션
  - **Clarity 행동**
    - 활성 시간, 평균 스크롤 깊이
    - 데드 클릭%, 레이지 클릭%, 빠른 이탈(quickback)%
    - 캠페인별 URL 분포(구매 페이지·체험·커뮤니티)
  - **사이트 안 깊이 (GA4 브리지 이벤트)**
    - section_view(섹션 도달), embed_scroll_depth, embed_engaged, detail_rescroll(되돌려 보기)
    - 깊은 관심 종류별 건수와 1건당 비용(체험·결제 시작·상세 90초·커뮤니티·재방문)
  - **Meta 전환 신호**
    - 최적화 이벤트 건수와 1건당 비용(상세·체험 조회 CC 2306085919929012, 깊은 관심 v2)
    - 결제 시작(InitiateCheckout)
    - 체험 결제(TrialPurchase v2 1074629242220862)
  - **네이버**
    - 노출, 클릭, CPC, 평균 순위
    - 광고그룹·키워드별 상위 5개(행 펼침 안)
- 행을 펼치면 이 상세 지표의 날짜별 추이도 같이 보인다. 광고(소재) 단위 내역도 볼 수 있게 한다(Meta 광고별 지출·깊은 관심·훅률).
- `cta_click`은 상세 패널에도 넣지 않는다.
- 데이터가 없는 항목(수집 전 기간, API가 안 주는 값)은 0이 아니라 "-"로 표시한다. 마우스를 올리거나 탭하면 이유를 보여 준다.

## 데이터 (날짜별로 저장하고, 기간 합산은 화면에서 한다)
`site/campaign_compare.json` 구조(예시):
```json
{"updated_at":"...","deep_interest_since":"2026-09-30",
 "campaigns":[{"key":"CMP-014","platform":"meta","id":"1202584...","name":"...","status":"ACTIVE",
   "settings":{"creative":"기존 릴스 3편","target":"넓게 (29~55세 제안)","optimization":"깊은 관심","daily_budget":15000,"start":"2026-09-30"},
   "daily":{"2026-09-30":{"spend":0,"lpv":0,"deep":{"total":0,"feel":0,"checkout":0,"detail_90s":0,"community":0,"revisit":0},"deep_meta":0,"trial":0,"purchase":0,"clarity_active_sec":null,"ga4_final":false}}}],
 "account_daily":{"2026-09-30":{"imweb_body_sales":0,"trial_bookings":0}}}
```
- **Meta**: `act_...` 캠페인·광고 세트 설정과 일별 인사이트(`time_increment=1`)를 받는다. 토큰은 키체인 `openclaw_meta_ads_token`, 계정은 `openclaw_meta_ads_account`.
  - 지출, `landing_page_view`
  - `offsite_conversion.custom.1712444449859619`(깊은 관심 v2): Meta 쪽 깊은 관심 수(`deep_meta`)
  - 본체 구매: `offsite_conversion.custom.3523132157864226`(구매 ≥100만). 없으면 `purchase`를 쓰고 "대조 필요" 표시.
  - 대상: 2026-09-01 이후 지출이 있는 캠페인 전부.
- **GA4**: 기존 `marketing-pipeline/ga4_bot_filter.py`를 쓰고 봇 필터를 적용한다(서비스 계정 `/Users/hsw/.openclaw/credentials/ga4_service_account.json`, property 419577751). python은 `/usr/local/bin/python3`(google-analytics-data 설치됨).
  - `rf_deep_interest` 이벤트를 `sessionCampaignName`(= Meta 캠페인 id, utm_campaign={{campaign.id}}) × `customEvent:kind`로 일별 집계해 `deep` 필드에 넣는다. 파라미터 차원명이 없으면 GA4 메타데이터 API로 확인한다.
  - 네이버는 `sessionSource=naver`·`sessionMedium=cpc` 기준으로 같은 이벤트를 집계한다.
- **체험 신청**: `marketing-pipeline/collect_feel_bookings.py`의 소스(Supabase `feel_bookings`)에서 utm_campaign이 있는 신청을 캠페인에 붙인다. utm이 없는 건은 `account_daily.trial_bookings`에만 넣는다.
- **네이버**: `marketing-pipeline/collect_naver.py` 방식으로 캠페인·광고그룹 일별 지출·클릭을 받는다. 행은 "네이버 · 광고그룹명" 단위로 한다. 비브랜드 확장 그룹은 CMP-011로 표시한다.
- **Clarity**: `marketing-pipeline/collect_clarity.py`로 최근 1일 캠페인별 활성 시간을 받는다. 수집 시점 날짜로 `clarity_active_sec`에 누적 저장한다(과거 값은 덮어쓰지 않는다). 9/28~9/30 값은 `state/evidence/2026-09-3*-ad-quality-*/clarity_*.json`에 있으면 백필한다.
- **아임웹 실판매**: `marketing-pipeline/data/imweb_body_sales.json`과 `imweb-order-notify` 알림 기록 중 최신 정본 규칙(MEMORY: 아임웹 정본)을 따른다. 1,000원 이하 테스트와 예약금(≤3만)은 제외한다.
- 캠페인 설정 문구(소재·타겟 요약)는 API 값으로 자동 생성한다. 타겟: 어드밴티지+이면 "넓게 (나이 제안 a~b세)"로 쓰고, 제외 오디언스가 있으면 "구매자 제외" 등을 덧붙인다.

## 갱신
- 수집 스크립트: `marketing-workflow-dashboard/scripts/build_campaign_compare.py`. 한 번 실행하면 json 갱신 → 배포까지 한다.
- 매시 정각(05분) launchd로 돌린다. `shared/scripts/create_launchd_job.sh` 헬퍼를 쓴다. 이름은 `com.openclaw.campaign-compare-hourly`.
- 실패하면 기존 json을 유지하고 로그를 남긴다. API 레이트 리밋은 재시도한다(Meta는 빈 배열로 위장하는 경우가 있으니 빈 결과를 성공으로 보지 않는다).

## 완료 조건
1. https://rf-marketing-dashboard.pages.dev/#analysis/compare 에서 기간을 바꾸면 숫자가 바뀐다.
2. 2026-09-27~09-29 기간의 CMP-007·009·010 지출·방문 1회당이 기준선 이미지(87,392/91원, 35,515/41원, 42,338/45원)와 일치한다.
3. 오늘 기간에 CMP-014·015가 보인다(켜지기 전이면 지출 0·상태 PAUSED).
4. 구매 버튼 클릭(cta_click) 열이 없다.
5. launchd 첫 실행이 성공했고, json의 updated_at이 갱신된 것을 확인한다.
6. 다른 PC(시크릿 창)에서 URL이 열린다.
