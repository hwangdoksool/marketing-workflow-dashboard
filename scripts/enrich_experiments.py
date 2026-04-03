#!/usr/bin/env python3
"""
실험(Brief) 가설/스키마 구체화 스크립트.
retagged_creatives_v2.json의 태깅 데이터를 기반으로 Supabase briefs 업데이트.
"""

import json
import os
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

DATA_DIR = Path(os.path.expanduser("~/.openclaw/workspace-ex-asst/marketing-pipeline/data"))
SUPA_URL = "https://ssidizurrvnfmqbvfsqr.supabase.co"

VP_LABELS = {
    "VP1": "체형 변화/근육 성장",
    "VP2": "안전한 홈트레이닝",
    "VP3": "시간 효율/편의성",
    "VP4": "경제성 (헬스장 대비)",
    "VP5": "전문적 운동 품질",
    "VP6": "공간 효율",
    "VP7": "가족/커플 운동",
    "VP8": "스마트 기술/데이터",
}

PROBLEM_LABELS = {
    "P1": "헬스장 갈 시간 없음",
    "P2": "홈트 효과 의심",
    "P3": "운동 지루/포기",
    "P4": "부상 걱정",
    "P5": "장비 공간 부족",
    "P6": "비용 부담",
}

def get_supa_key():
    return subprocess.check_output(
        ["security", "find-generic-password", "-s", "openclaw_supabase_service_role_wspn", "-w"],
        text=True
    ).strip()

def load_tagged_creatives():
    with open(DATA_DIR / "retagged_creatives_v2.json") as f:
        return json.load(f)

def load_briefs(key):
    url = f"{SUPA_URL}/rest/v1/mktg_briefs?select=*&source=eq.meta_ads&limit=500"
    req = urllib.request.Request(url, headers={
        "apikey": key,
        "Authorization": f"Bearer {key}"
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def update_brief(key, brief_id, updates):
    url = f"{SUPA_URL}/rest/v1/mktg_briefs?id=eq.{brief_id}"
    data = json.dumps(updates).encode()
    req = urllib.request.Request(url, data=data, method="PATCH", headers={
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return True
    except urllib.error.HTTPError as e:
        print(f"  PATCH error for {brief_id}: {e.read().decode()[:100]}")
        return False

def build_hypothesis(ad):
    """크리에이티브 태깅 기반 구체적 가설 생성"""
    vps = ad.get("vp", [])
    problems = ad.get("problem", [])
    usps = ad.get("usp", [])
    jtbds = ad.get("jtbd", [])
    hurdles = ad.get("hurdle", [])
    ad_type = ad.get("type", "이미지")
    ctr = ad.get("link_ctr", 0)
    
    # 메인 VP
    main_vp = vps[0] if vps else None
    vp_desc = VP_LABELS.get(main_vp, main_vp) if main_vp else "미지정"
    
    # 메인 Problem
    main_prob = problems[0] if problems else None
    prob_desc = PROBLEM_LABELS.get(main_prob, main_prob) if main_prob else None
    
    # 가설 구성
    parts = []
    if main_vp:
        parts.append(f"'{vp_desc}' 가치를")
    if ad_type == "영상":
        parts.append("영상으로 시연하면")
    else:
        parts.append("이미지로 전달하면")
    if main_prob:
        parts.append(f"'{prob_desc}' 문제를 가진 타겟이")
    parts.append("클릭할 것이다")
    
    hypothesis = " ".join(parts)
    
    # 판정 기준
    criteria = f"CTR ≥ 1.5% (현재: {ctr:.2f}%)"
    
    # 관찰 상세
    spend = ad.get("spend", 0)
    imp = ad.get("impressions", 0)
    clicks = ad.get("link_clicks", 0)
    observation = f"지출 ₩{spend:,.0f} | 노출 {imp:,} | 클릭 {clicks:,} | CTR {ctr:.2f}%"
    
    return {
        "hypothesis": hypothesis,
        "criteria": criteria,
        "source_detail": observation,
        "target_vp": main_vp,
        "target_problem": main_prob,
        "content_type": ad_type,
    }


def main():
    key = get_supa_key()
    
    # 태깅 데이터 로드
    creatives = load_tagged_creatives()
    creative_map = {}
    for c in creatives:
        name = c.get("name", "")
        creative_map[name] = c
    
    print(f"태깅 데이터: {len(creatives)}개")
    
    # Supabase briefs 로드
    briefs = load_briefs(key)
    print(f"Meta briefs: {len(briefs)}개")
    
    updated = 0
    for b in briefs:
        title = b.get("title", "")
        # [Meta] prefix 제거해서 원본 이름 매칭
        ad_name = title.replace("[Meta] ", "")
        
        # 태깅 데이터에서 이름으로 매칭
        matched = None
        for name, creative in creative_map.items():
            if name[:25] == ad_name[:25]:  # 이름이 잘렸을 수 있으므로 앞 25자로 매칭
                matched = creative
                break
        
        if not matched:
            continue
        
        updates = build_hypothesis(matched)
        
        if update_brief(key, b["id"], updates):
            updated += 1
    
    print(f"\n✅ {updated}/{len(briefs)}개 가설 구체화 완료")


if __name__ == "__main__":
    main()
