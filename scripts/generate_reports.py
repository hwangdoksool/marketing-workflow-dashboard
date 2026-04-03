#!/usr/bin/env python3
"""
주간 리포트 생성 스크립트 (새 양식)
양식: 🔔 특이사항 → 전환 건별 → Part 1 관계 분석 → Part 2 지표 현황
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(os.path.expanduser("~/.openclaw/workspace-ex-asst/marketing-pipeline/data"))
CS_DIR = Path(os.path.expanduser("~/.openclaw/workspace/synapse-search/cs/crawled"))
OUT_DIR = Path(os.path.expanduser("~/.openclaw/workspace-ex-asst/marketing-workflow-dashboard/site"))

# Week definitions (Mon-Sun)
WEEKS = {
    "W6":  ("2026-02-02", "2026-02-08"),
    "W7":  ("2026-02-09", "2026-02-15"),
    "W8":  ("2026-02-16", "2026-02-22"),
    "W9":  ("2026-02-23", "2026-03-01"),
    "W10": ("2026-03-02", "2026-03-08"),
    "W11": ("2026-03-09", "2026-03-15"),
    "W12": ("2026-03-16", "2026-03-22"),
    "W13": ("2026-03-23", "2026-03-29"),
}

# 2개월 이력 타임라인 (2MONTH-REVIEW.md 기반)
ACTIONS_TIMELINE = {
    "W6": [],  # 02-02~08: 파이프라인 구축 이전, 특별한 마케팅 액션 없음
    "W7": [
        {"date": "02-14", "action": "블로그 초안(형은님) 팩트체크", "type": "웹 콘텐츠"},
        {"date": "02-15", "action": "마케팅 데이터 파이프라인 구축 (GA4/Meta/네이버/IG/YT 자동 수집)", "type": "인프라"},
    ],
    "W8": [
        {"date": "02-16", "action": "크리에이티브 Vision 분석 — IG 133영상 16,727프레임 추출+분석", "type": "인프라"},
        {"date": "02-17", "action": "홈페이지 CF Pages 전환 + 히어로 AI VBT 멘트 + CTA 강화", "type": "웹 구조"},
        {"date": "02-20", "action": "CTA 테스트 페이지(/cta-test) 구현", "type": "웹 구조"},
        {"date": "02-21", "action": "크리에이티브 빌더 LLM 연동 + 배포", "type": "인프라"},
    ],
    "W9": [
        {"date": "02-24", "action": "UTM 미설정 문제 발견 → 마케터 전달 (대표님 발견)", "type": "광고"},
        {"date": "02-25", "action": "운동 가이드 65개 동작 텍스트 완성", "type": "웹 콘텐츠"},
    ],
    "W10": [
        {"date": "03-01", "action": "상세페이지 프리미엄 개선 (비교표, 결제허들, 애니메이션)", "type": "웹 구조"},
        {"date": "03-03", "action": "/links 페이지 (리틀리 대체) + roomfit.kr DNS 이전", "type": "웹 구조"},
        {"date": "03-04", "action": "아임웹 주문 알림 시스템", "type": "인프라"},
        {"date": "03-05", "action": "스포엑스/프리오더/B2B 3대 시급 과제 확정", "type": "전략"},
        {"date": "03-08", "action": "체험 신청 시스템 전면 개편", "type": "퍼널"},
    ],
    "W11": [
        {"date": "03-09", "action": "주간 리포트 → 대시보드 통합 전환 결정", "type": "인프라"},
        {"date": "03-11", "action": "체험 프로세스 대규모 전환 (결제 선행)", "type": "퍼널"},
        {"date": "03-13", "action": "GA4/Meta 체험/본품 전환 분리 (Worker)", "type": "인프라"},
        {"date": "03-15", "action": "시작가이드 수정", "type": "웹 콘텐츠"},
    ],
    "W12": [
        {"date": "03-18", "action": "스포엑스 준비 대시보드 구축 (38개 카드, 8카테고리)", "type": "인프라"},
        {"date": "03-19", "action": "체험 슬롯 당일 오픈 + STT 파이프라인", "type": "퍼널/인프라"},
        {"date": "03-20", "action": "스포엑스 B2B/B2C 리플렛 제작", "type": "오프라인 소재"},
    ],
    "W13": [
        {"date": "03-23", "action": "마케팅 인텔리전스 리포트 v1~v5 작성", "type": "리포트"},
        {"date": "03-26~29", "action": "스포엑스 현장 (DP화면, 리더보드, 제안서, DP페이지)", "type": "현장"},
    ],
}


def load_ga4_full():
    with open(DATA_DIR / "ga4_full.json") as f:
        return json.load(f)


def load_meta_full():
    with open(DATA_DIR / "meta_full.json") as f:
        return json.load(f)


def load_naver_full():
    with open(DATA_DIR / "naver_full.json") as f:
        return json.load(f)


def load_weekly_json(prefix, week_num):
    """Load wXX.json file if it exists"""
    path = DATA_DIR / f"{prefix}_w{week_num}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def date_range(start_str, end_str):
    """Generate date strings in YYYYMMDD format"""
    start = datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.strptime(end_str, "%Y-%m-%d")
    dates = []
    d = start
    while d <= end:
        dates.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return dates


def date_range_dash(start_str, end_str):
    """Generate date strings in YYYY-MM-DD format"""
    start = datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.strptime(end_str, "%Y-%m-%d")
    dates = []
    d = start
    while d <= end:
        dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return dates


def extract_ga4_week(ga4_full, start, end):
    """Extract weekly GA4 data from full dataset"""
    dates = set(date_range(start, end))
    daily = [r for r in ga4_full["daily"] if r["date"] in dates]
    channels = [r for r in ga4_full["channels"] if r["date"] in dates]
    pages = [r for r in ga4_full.get("pages", []) if r.get("date") in dates]
    
    if not daily:
        return None
    
    overview = {
        "sessions": sum(r["sessions"] for r in daily),
        "total_users": sum(r["users"] for r in daily),
        "new_users": sum(r["new_users"] for r in daily),
        "page_views": sum(r["pageviews"] for r in daily),
        "bounce_rate": sum(r["bounce_rate"] * r["sessions"] for r in daily) / max(sum(r["sessions"] for r in daily), 1),
    }
    
    # Aggregate channels
    channel_agg = {}
    for c in channels:
        ch = c["channel"]
        if ch not in channel_agg:
            channel_agg[ch] = {"sessions": 0, "users": 0, "bounce_rate_weighted": 0}
        channel_agg[ch]["sessions"] += c["sessions"]
        channel_agg[ch]["users"] += c["users"]
        channel_agg[ch]["bounce_rate_weighted"] += c["bounce_rate"] * c["sessions"]
    
    traffic_sources = []
    for ch, v in sorted(channel_agg.items(), key=lambda x: -x[1]["sessions"]):
        traffic_sources.append({
            "channel": ch,
            "sessions": v["sessions"],
            "users": v["users"],
            "bounce_rate": v["bounce_rate_weighted"] / max(v["sessions"], 1),
        })
    
    return {
        "overview": overview,
        "traffic_sources": traffic_sources,
        "daily_sessions": daily,
    }


def extract_meta_week(meta_full, start, end):
    """Extract weekly Meta data from full dataset"""
    dates = set(date_range_dash(start, end))
    daily = [r for r in meta_full["daily"] if r["date"] in dates]
    campaigns = [r for r in meta_full["campaigns"] if r["date"] in dates]
    
    if not daily:
        return None
    
    summary = {
        "total_spend": sum(r["spend"] for r in daily),
        "total_impressions": sum(r["impressions"] for r in daily),
        "total_clicks": sum(r["clicks"] for r in daily),
    }
    if summary["total_impressions"] > 0:
        summary["avg_ctr"] = summary["total_clicks"] / summary["total_impressions"] * 100
    if summary["total_clicks"] > 0:
        summary["avg_cpc"] = summary["total_spend"] / summary["total_clicks"]
    
    # Aggregate campaigns
    camp_agg = {}
    for c in campaigns:
        name = c["campaign"]
        if name not in camp_agg:
            camp_agg[name] = {"impressions": 0, "clicks": 0, "spend": 0}
        camp_agg[name]["impressions"] += c["impressions"]
        camp_agg[name]["clicks"] += c["clicks"]
        camp_agg[name]["spend"] += c["spend"]
    
    return {"summary": summary, "campaigns": camp_agg, "daily": daily}


def extract_naver_week(naver_full, start, end):
    """Extract weekly Naver data from full dataset"""
    dates = set(date_range_dash(start, end))
    
    total_imp = 0
    total_clk = 0
    total_spend = 0
    
    for stat_group in naver_full["stats"]:
        for d in stat_group.get("data", []):
            if d.get("dateStart") in dates:
                total_imp += d.get("impCnt", 0)
                total_clk += d.get("clkCnt", 0)
                total_spend += d.get("salesAmt", 0)
    
    return {
        "total_impressions": total_imp,
        "total_clicks": total_clk,
        "total_spend": total_spend,
    }


def get_ga4_data(week_id, week_num, start, end, ga4_full):
    """Get GA4 data for a week - either from wXX.json or full dataset"""
    weekly = load_weekly_json("ga4", week_num)
    if weekly:
        return weekly
    return extract_ga4_week(ga4_full, start, end)


def get_meta_data(week_id, week_num, start, end, meta_full):
    """Get Meta data for a week"""
    weekly = load_weekly_json("meta", week_num)
    if weekly:
        return weekly
    return extract_meta_week(meta_full, start, end)


def get_naver_data(week_id, week_num, start, end, naver_full):
    """Get Naver data for a week"""
    weekly = load_weekly_json("naver", week_num)
    if weekly:
        return weekly
    return extract_naver_week(naver_full, start, end)


def fmt_money(v):
    if v is None:
        return "-"
    return f"₩{int(v):,}"


def fmt_num(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.1f}"
    return f"{int(v):,}"


def fmt_pct(v):
    if v is None:
        return "-"
    return f"{v:.1f}%"


def calc_wow(curr, prev):
    """Calculate week-over-week change"""
    if prev is None or prev == 0 or curr is None:
        return None
    return ((curr - prev) / abs(prev)) * 100


def build_kpi(ga4, meta, naver, prev_ga4, prev_meta, prev_naver):
    """Build KPI section"""
    # Current values
    if isinstance(ga4, dict) and "overview" in ga4:
        sessions = ga4["overview"]["sessions"]
        users = ga4["overview"]["total_users"]
        new_users = ga4["overview"]["new_users"]
    else:
        sessions = users = new_users = 0
    
    if isinstance(meta, dict) and "summary" in meta:
        meta_spend = meta["summary"]["total_spend"]
        meta_imp = meta["summary"]["total_impressions"]
        meta_clicks = meta["summary"]["total_clicks"]
        meta_ctr = meta["summary"].get("avg_ctr")
        meta_cpc = meta["summary"].get("avg_cpc")
    else:
        meta_spend = meta_imp = meta_clicks = 0
        meta_ctr = meta_cpc = None
    
    if isinstance(naver, dict):
        if "summary" in naver:
            naver_spend = naver["summary"].get("total_spend", 0)
            naver_imp = naver["summary"].get("total_impressions", 0)
            naver_clicks = naver["summary"].get("total_clicks", 0)
        else:
            naver_spend = naver.get("total_spend", 0)
            naver_imp = naver.get("total_impressions", 0)
            naver_clicks = naver.get("total_clicks", 0)
    else:
        naver_spend = naver_imp = naver_clicks = 0
    
    total_spend = meta_spend + naver_spend
    total_imp = meta_imp + naver_imp
    total_clicks = meta_clicks + naver_clicks
    
    # GA4 funnel
    funnel = ga4.get("funnel", {}) if isinstance(ga4, dict) else {}
    purchases = funnel.get("purchase", {}).get("count", 0) if isinstance(funnel.get("purchase"), dict) else funnel.get("purchase", 0)
    
    # Previous values
    prev_sessions = prev_users = prev_new_users = prev_spend = prev_purchases = 0
    if prev_ga4 and "overview" in prev_ga4:
        prev_sessions = prev_ga4["overview"]["sessions"]
        prev_users = prev_ga4["overview"]["total_users"]
        prev_new_users = prev_ga4["overview"]["new_users"]
    
    prev_meta_spend = 0
    if prev_meta and "summary" in prev_meta:
        prev_meta_spend = prev_meta["summary"]["total_spend"]
    
    prev_naver_spend = 0
    if prev_naver:
        if "summary" in prev_naver:
            prev_naver_spend = prev_naver["summary"].get("total_spend", 0)
        else:
            prev_naver_spend = prev_naver.get("total_spend", 0)
    
    prev_spend = prev_meta_spend + prev_naver_spend
    
    prev_funnel = prev_ga4.get("funnel", {}) if prev_ga4 and isinstance(prev_ga4, dict) else {}
    prev_purchases = prev_funnel.get("purchase", {}).get("count", 0) if isinstance(prev_funnel.get("purchase"), dict) else prev_funnel.get("purchase", 0)
    
    # CPC, CTR, CPA, ROAS
    cpc = total_spend / total_clicks if total_clicks > 0 else None
    ctr = total_clicks / total_imp * 100 if total_imp > 0 else None
    cpa = total_spend / purchases if purchases > 0 else None
    conv_rate = purchases / sessions * 100 if sessions > 0 else None
    
    kpi = {
        "sessions": {"value": sessions, "prev": prev_sessions or None},
        "users": {"value": users, "prev": prev_users or None},
        "newUsers": {"value": new_users, "prev": prev_new_users or None},
        "adSpend": {"value": int(total_spend), "prev": int(prev_spend) or None, "unit": "₩",
                    "note": f"Meta {fmt_money(meta_spend)} + 네이버 {fmt_money(naver_spend)}"},
        "impressions": {"value": total_imp, "prev": None, 
                       "note": f"Meta {fmt_num(meta_imp)} + 네이버 {fmt_num(naver_imp)}"},
        "clicks": {"value": total_clicks, "prev": None,
                  "note": f"Meta {fmt_num(meta_clicks)} + 네이버 {fmt_num(naver_clicks)}"},
        "purchases_ga4": {"value": purchases, "prev": prev_purchases or None, "note": "GA4 purchase 이벤트"},
    }
    
    if cpc is not None:
        kpi["cpc"] = {"value": round(cpc), "prev": None, "unit": "₩"}
    if ctr is not None:
        kpi["ctr"] = {"value": round(ctr, 2), "prev": None, "unit": "%"}
    if cpa is not None:
        kpi["cpa"] = {"value": round(cpa), "prev": None, "unit": "₩", "note": "광고비/구매건수"}
    if conv_rate is not None:
        kpi["convRate"] = {"value": round(conv_rate, 3), "prev": None, "unit": "%", "note": "구매/세션"}
    
    return kpi


def build_channel_section(ga4):
    """Build 채널별 트래픽 section"""
    sources = []
    if isinstance(ga4, dict) and "traffic_sources" in ga4:
        sources = ga4["traffic_sources"]
    
    rows = []
    for s in sources[:8]:
        bounce = f"이탈 {s['bounce_rate']*100:.0f}%" if "bounce_rate" in s else ""
        rows.append({
            "metric": s["channel"],
            "w12": s["sessions"],
            "w11": None,
            "note": f"유저 {fmt_num(s['users'])}명, {bounce}"
        })
    
    return {"title": "📊 채널별 트래픽", "type": "metrics", "content": rows}


def build_funnel_section(ga4):
    """Build 전환 퍼널 section"""
    funnel = {}
    if isinstance(ga4, dict) and "funnel" in ga4:
        raw = ga4["funnel"]
        for k, v in raw.items():
            if isinstance(v, dict):
                funnel[k] = v.get("count", 0)
            else:
                funnel[k] = v
    
    return {"title": "🎯 전환 퍼널 (GA4)", "type": "funnel", "content": funnel}


def build_meta_section(meta):
    """Build Meta 소재 성과 section"""
    if not isinstance(meta, dict):
        return {"title": "💰 Meta 광고 성과", "type": "metrics", "content": []}
    
    # Use ads if available, otherwise campaigns
    ads = meta.get("ads", [])
    if ads:
        sorted_ads = sorted(ads, key=lambda x: x.get("spend", 0), reverse=True)[:7]
        rows = []
        for a in sorted_ads:
            name = a.get("ad_name", "Unknown")
            spend = a.get("spend", 0)
            imp = a.get("impressions", 0)
            clicks = a.get("clicks", 0)
            ctr = a.get("ctr", 0)
            rows.append({
                "metric": name[:30],
                "w12": fmt_money(spend),
                "w11": f"imp {fmt_num(imp)}",
                "note": f"clicks {fmt_num(clicks)}, CTR {ctr:.1f}%"
            })
        return {"title": "💰 Meta 소재 TOP", "type": "metrics", "content": rows}
    
    # Campaign level
    campaigns = meta.get("campaigns", {})
    if isinstance(campaigns, dict):
        sorted_camps = sorted(campaigns.items(), key=lambda x: x[1].get("spend", 0), reverse=True)[:5]
        rows = []
        for name, v in sorted_camps:
            rows.append({
                "metric": name[:35],
                "w12": fmt_money(v["spend"]),
                "w11": f"imp {fmt_num(v['impressions'])}",
                "note": f"clicks {fmt_num(v['clicks'])}"
            })
        return {"title": "💰 Meta 캠페인별", "type": "metrics", "content": rows}
    
    return {"title": "💰 Meta 광고 성과", "type": "metrics", "content": []}


def build_naver_section(naver):
    """Build 네이버 광고 section"""
    if not isinstance(naver, dict):
        return {"title": "🔍 네이버 검색광고", "type": "metrics", "content": []}
    
    imp = naver.get("total_impressions", 0) if "total_impressions" in naver else naver.get("summary", {}).get("total_impressions", 0)
    clk = naver.get("total_clicks", 0) if "total_clicks" in naver else naver.get("summary", {}).get("total_clicks", 0)
    spend = naver.get("total_spend", 0) if "total_spend" in naver else naver.get("summary", {}).get("total_spend", 0)
    
    rows = [{
        "metric": "네이버 검색광고 합계",
        "w12": fmt_money(spend),
        "w11": f"imp {fmt_num(imp)}",
        "note": f"clicks {fmt_num(clk)}, CTR {clk/imp*100:.1f}%" if imp > 0 else ""
    }]
    
    return {"title": "🔍 네이버 검색광고", "type": "metrics", "content": rows}


def build_page_section(ga4):
    """Build 페이지별 트래픽"""
    pages = []
    if isinstance(ga4, dict) and "top_pages" in ga4:
        pages = ga4["top_pages"]
    
    rows = []
    for p in pages[:7]:
        views = p.get("views", 0)
        users = p.get("users", 0)
        dur = p.get("avg_duration", 0)
        rows.append({
            "metric": p.get("page", "?"),
            "w12": f"{fmt_num(views)}뷰",
            "w11": None,
            "note": f"체류 {dur:.0f}초, 유저 {fmt_num(users)}"
        })
    
    return {"title": "📄 페이지별 트래픽", "type": "metrics", "content": rows}


def build_abstract(week_id, kpi, ga4, meta, naver, actions):
    """Build 🔔 특이사항 요약"""
    sessions = kpi.get("sessions", {}).get("value", 0)
    users = kpi.get("users", {}).get("value", 0)
    spend = kpi.get("adSpend", {}).get("value", 0)
    purchases = kpi.get("purchases_ga4", {}).get("value", 0)
    
    prev_sessions = kpi.get("sessions", {}).get("prev")
    prev_purchases = kpi.get("purchases_ga4", {}).get("prev")
    
    lines = []
    lines.append(f"세션 {fmt_num(sessions)}, 유저 {fmt_num(users)}명. 총 광고비 {fmt_money(spend)}.")
    
    if purchases > 0:
        lines.append(f"GA4 구매 {purchases}건.")
    
    if prev_sessions and prev_sessions > 0:
        wow = calc_wow(sessions, prev_sessions)
        if wow is not None:
            direction = "▲" if wow > 0 else "▼"
            lines.append(f"세션 전주 대비 {direction}{abs(wow):.1f}%.")
    
    if actions:
        action_summary = ", ".join(a["action"][:20] for a in actions[:3])
        lines.append(f"주요 액션: {action_summary}")
    
    return " ".join(lines)


def build_relation_section(week_id, kpi, prev_kpi, actions):
    """Build Part 1: 관계 분석 sections"""
    sections = []
    
    # 1-1. Live 설계서 × 지표 변화
    if actions:
        items = []
        for a in actions:
            items.append(f"[{a['date']}] {a['action']} ({a['type']})")
        
        # Analyze impact
        sessions_wow = calc_wow(
            kpi.get("sessions", {}).get("value"),
            kpi.get("sessions", {}).get("prev")
        )
        if sessions_wow is not None:
            direction = "상승" if sessions_wow > 0 else "하락"
            items.append(f"→ 세션 전주 대비 {abs(sessions_wow):.1f}% {direction}")
        
        sections.append({
            "title": "📋 1-1. 이번 주 액션 × 지표 변화",
            "type": "insights",
            "content": items
        })
    else:
        sections.append({
            "title": "📋 1-1. 이번 주 액션 × 지표 변화",
            "type": "insights",
            "content": ["이번 주 기록된 마케팅 액션 없음"]
        })
    
    # 1-2. 전환 건↔액션 매칭
    purchases = kpi.get("purchases_ga4", {}).get("value", 0)
    if purchases > 0 and actions:
        matching_items = [
            f"GA4 구매 {purchases}건 발생",
            f"같은 주 액션 {len(actions)}건 — 직접 매칭 판단 필요"
        ]
        # Look for web structure changes that might affect conversion
        web_actions = [a for a in actions if a["type"] in ("웹 구조", "퍼널")]
        if web_actions:
            matching_items.append(f"⚡ 웹/퍼널 변경 {len(web_actions)}건 → 전환율 영향 가능성")
        sections.append({
            "title": "🔗 1-2. 전환 건 ↔ 액션 매칭",
            "type": "insights",
            "content": matching_items
        })
    elif purchases > 0:
        sections.append({
            "title": "🔗 1-2. 전환 건 ↔ 액션 매칭",
            "type": "insights",
            "content": [f"GA4 구매 {purchases}건 — 이번 주 별도 액션 없음 (기존 소재/구조 효과 지속)"]
        })
    else:
        sections.append({
            "title": "🔗 1-2. 전환 건 ↔ 액션 매칭",
            "type": "insights",
            "content": ["이번 주 GA4 구매 이벤트 0건"]
        })
    
    # 1-3. 매칭 안 되는 변화
    unmatch = []
    if kpi.get("sessions", {}).get("prev"):
        sessions_wow = calc_wow(kpi["sessions"]["value"], kpi["sessions"]["prev"])
        if sessions_wow and abs(sessions_wow) > 20 and not actions:
            unmatch.append(f"세션 {sessions_wow:+.1f}% 변화 — 명시적 액션 없이 발생")
    if not unmatch:
        unmatch.append("전주 대비 큰 괴리 없음 (또는 비교 데이터 부족)")
    
    sections.append({
        "title": "❓ 1-3. 매칭 안 되는 변화",
        "type": "insights",
        "content": unmatch
    })
    
    # 1-4. 시차 매칭
    sections.append({
        "title": "⏱️ 1-4. 시차 매칭 (1~2주 전 액션의 지연 효과)",
        "type": "insights",
        "content": ["소급 리포트 — 과거 데이터 기반 시차 분석은 전체 기간 종합 리뷰에서 수행"]
    })
    
    return sections


def build_conversion_section(ga4):
    """Build 전환 건별 상세 section"""
    funnel = {}
    if isinstance(ga4, dict) and "funnel" in ga4:
        raw = ga4["funnel"]
        for k, v in raw.items():
            if isinstance(v, dict):
                funnel[k] = v.get("count", 0)
            else:
                funnel[k] = v
    
    purchases = funnel.get("purchase", 0)
    checkout = funnel.get("begin_checkout", 0)
    payment = funnel.get("add_payment_info", 0)
    
    items = [
        f"📦 구매 완료: {purchases}건",
        f"🛒 결제 시작: {checkout}건",
        f"💳 결제정보 입력: {payment}건",
    ]
    
    if checkout > 0 and purchases > 0:
        items.append(f"결제시작→구매 전환율: {purchases/checkout*100:.1f}%")
    
    # Note: 실제 매출 데이터는 아임웹에서 가져와야 정확하지만 소급이라 GA4 기준
    return {
        "title": "🛒 전환 건별 상세 (GA4 기준)",
        "type": "insights",
        "content": items
    }


def generate_report(week_id, start, end, ga4, meta, naver, prev_ga4, prev_meta, prev_naver, actions):
    """Generate a single week report in new format"""
    week_num = int(week_id[1:])
    month = datetime.strptime(start, "%Y-%m-%d").month
    week_in_month = (datetime.strptime(start, "%Y-%m-%d").day - 1) // 7 + 1
    
    month_names = {2: "2월", 3: "3월"}
    month_name = month_names.get(month, f"{month}월")
    
    title = f"{week_id} · {month_name} {week_in_month}주차"
    period = f"{start[5:]} ~ {end[5:]}"
    
    # Build KPI
    kpi = build_kpi(ga4, meta, naver, prev_ga4, prev_meta, prev_naver)
    prev_kpi = build_kpi(prev_ga4, prev_meta, prev_naver, None, None, None) if prev_ga4 else None
    
    # Build abstract (🔔)
    abstract = build_abstract(week_id, kpi, ga4, meta, naver, actions)
    
    # Build sections in NEW order:
    # 1. 전환 건별 상세
    # 2. Part 1: 관계 분석 (1-1 ~ 1-4)
    # 3. Part 2: 지표 현황 (채널, 퍼널, Meta, 네이버, 페이지)
    sections = []
    
    # 전환 건별 상세
    sections.append(build_conversion_section(ga4))
    
    # Part 1 header
    sections.append({
        "title": "━━ Part 1: 관계 분석 ━━",
        "type": "text",
        "content": "이번 주 액션과 지표 변화의 관계"
    })
    
    # Relation analysis sections
    relation_sections = build_relation_section(week_id, kpi, prev_kpi, actions)
    sections.extend(relation_sections)
    
    # Part 2 header  
    sections.append({
        "title": "━━ Part 2: 지표 현황 ━━",
        "type": "text",
        "content": "상세 데이터 (참조용)"
    })
    
    # 지표 현황 sections
    sections.append(build_channel_section(ga4))
    sections.append(build_funnel_section(ga4))
    sections.append(build_meta_section(meta))
    sections.append(build_naver_section(naver))
    sections.append(build_page_section(ga4))
    
    return {
        "id": f"{week_id.lower()}-2026",
        "title": title,
        "period": period,
        "publishedAt": end,
        "kpi": kpi,
        "abstract": abstract,
        "sections": sections
    }


def main():
    print("Loading data sources...")
    ga4_full = load_ga4_full()
    meta_full = load_meta_full()
    naver_full = load_naver_full()
    
    reports = []
    prev_ga4 = prev_meta = prev_naver = None
    
    week_order = ["W6", "W7", "W8", "W9", "W10", "W11", "W12", "W13"]
    
    for week_id in week_order:
        start, end = WEEKS[week_id]
        week_num = int(week_id[1:])
        actions = ACTIONS_TIMELINE.get(week_id, [])
        
        print(f"Generating {week_id} ({start} ~ {end})...")
        
        # Get data
        ga4 = get_ga4_data(week_id, week_num, start, end, ga4_full)
        meta = get_meta_data(week_id, week_num, start, end, meta_full)
        naver = get_naver_data(week_id, week_num, start, end, naver_full)
        
        if ga4 is None:
            print(f"  ⚠️ No GA4 data for {week_id}")
            ga4 = {"overview": {"sessions": 0, "total_users": 0, "new_users": 0, "page_views": 0, "bounce_rate": 0}, "traffic_sources": [], "funnel": {}}
        
        if meta is None:
            print(f"  ⚠️ No Meta data for {week_id}")
            meta = {"summary": {"total_spend": 0, "total_impressions": 0, "total_clicks": 0}}
        
        if naver is None:
            print(f"  ⚠️ No Naver data for {week_id}")
            naver = {"total_impressions": 0, "total_clicks": 0, "total_spend": 0}
        
        report = generate_report(week_id, start, end, ga4, meta, naver, prev_ga4, prev_meta, prev_naver, actions)
        reports.append(report)
        
        # Store for prev comparison
        prev_ga4 = ga4
        prev_meta = meta
        prev_naver = naver
    
    # Reverse order (newest first)
    reports.reverse()
    
    # Write output
    out_path = OUT_DIR / "reports.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Generated {len(reports)} reports → {out_path}")
    print(f"   File size: {out_path.stat().st_size:,} bytes")
    
    # Summary
    for r in reports:
        purchases = r["kpi"].get("purchases_ga4", {}).get("value", 0)
        sessions = r["kpi"].get("sessions", {}).get("value", 0)
        spend = r["kpi"].get("adSpend", {}).get("value", 0)
        print(f"   {r['id']}: {r['title']} | 세션 {fmt_num(sessions)} | 광고비 {fmt_money(spend)} | 구매 {purchases}건")


if __name__ == "__main__":
    main()
