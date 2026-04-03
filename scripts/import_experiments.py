#!/usr/bin/env python3
"""
기존 광고/블로그/유튜브/인스타 콘텐츠를 워크플로우 실험(Brief)으로 등록.
크리에이티브 태거 데이터 + 블로그/유튜브 크리에이티브 데이터 활용.
"""

import json
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.path.expanduser("~/.openclaw/workspace-ex-asst/marketing-pipeline/data"))
SUPA_URL = "https://ssidizurrvnfmqbvfsqr.supabase.co"

def get_supa_key():
    return subprocess.check_output(
        ["security", "find-generic-password", "-s", "openclaw_supabase_service_role_wspn", "-w"],
        text=True
    ).strip()

def load_existing_briefs(key):
    """Supabase에서 기존 briefs 로드"""
    import urllib.request
    url = f"{SUPA_URL}/rest/v1/mktg_briefs?select=id,title&limit=500"
    req = urllib.request.Request(url, headers={
        "apikey": key,
        "Authorization": f"Bearer {key}"
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def upsert_brief(key, brief):
    """Supabase에 brief upsert"""
    import urllib.request
    url = f"{SUPA_URL}/rest/v1/mktg_briefs"
    data = json.dumps(brief).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def main():
    key = get_supa_key()
    existing = load_existing_briefs(key)
    existing_titles = {b["title"] for b in existing}
    print(f"기존 briefs: {len(existing)}개")
    
    briefs = []
    now = datetime.now().isoformat()
    
    # 1) Meta 광고 소재 (retagged_creatives_v2.json)
    print("\n=== Meta 광고 소재 ===")
    with open(DATA_DIR / "retagged_creatives_v2.json") as f:
        ads = json.load(f)
    
    for ad in ads:
        name = ad.get("name", "")[:60]
        title = f"[Meta] {name}"
        if title in existing_titles:
            continue
        
        vp = ad.get("vp", [])
        problem = ad.get("problem", [])
        usp = ad.get("usp", [])
        jtbd = ad.get("jtbd", [])
        hurdle = ad.get("hurdle", [])
        
        # 메인1 + 서브1 제한
        main_vp = vp[0] if vp else ""
        sub_vp = vp[1] if len(vp) > 1 else ""
        
        spend = ad.get("spend", 0)
        imp = ad.get("impressions", 0)
        clicks = ad.get("link_clicks", 0)
        ctr = ad.get("link_ctr", 0)
        
        briefs.append({
            "id": f"exp-meta-{hash(name) % 100000:05d}",
            "title": title,
            "status": "complete",
            "signal": f"Meta 광고 ({ad.get('type', '이미지')})",
            "signal_type": "기회",
            "source": "meta_ads",
            "source_detail": f"지출 ₩{spend:,.0f}, 노출 {imp:,}, CTR {ctr:.2f}%",
            "hypothesis": f"VP:{main_vp} → 클릭 유도" if main_vp else "가설 미설정",
            "criteria": "CTR > 1%",
            "target_vp": main_vp,
            "target_problem": problem[0] if problem else None,
            "content_type": ad.get("type", "이미지"),
            "hook_type": None,
            "channel": "meta",
            "learning_result": f"CTR {ctr:.2f}%, 클릭 {clicks:,}건" if clicks > 0 else None,
            "verdict": None,
        })
    
    print(f"  신규 Meta 소재: {len([b for b in briefs if b['channel']=='meta'])}개")
    
    # 2) 블로그
    print("\n=== 블로그 ===")
    with open(DATA_DIR / "blog_creatives.json") as f:
        blog_data = json.load(f)
    
    for post in blog_data.get("posts", []):
        raw_text = post.get("text") or post.get("description") or ""
        text = str(raw_text)[:60]
        title = f"[블로그] {text}" if text else f"[블로그] {post.get('id','?')}"
        if title in existing_titles:
            continue
        
        published = post.get("published_at", "")
        
        briefs.append({
            "id": f"exp-blog-{hash(post.get('id','')) % 100000:05d}",
            "title": title,
            "status": "complete",
            "signal": "블로그 콘텐츠",
            "signal_type": "기회",
            "source": "naver_blog",
            "source_detail": f"게시일: {published[:10] if published else '미상'}",
            "hypothesis": "오가닉 트래픽 유도",
            "criteria": "조회수 확인 필요",
            "content_type": "블로그",
            "channel": "blog",
            "verdict": None,
        })
    
    print(f"  신규 블로그: {len([b for b in briefs if b['channel']=='blog'])}개")
    
    # 3) 유튜브
    print("\n=== 유튜브 ===")
    with open(DATA_DIR / "youtube_creatives.json") as f:
        yt_data = json.load(f)
    
    vids = yt_data if isinstance(yt_data, list) else yt_data.get("videos", [])
    for v in vids:
        raw_text = v.get("text") or v.get("description") or ""
        text = str(raw_text)[:60]
        title = f"[유튜브] {text}" if text else f"[유튜브] {v.get('id','?')}"
        if title in existing_titles:
            continue
        
        metrics = v.get("metrics", {})
        views = metrics.get("views", 0)
        likes = metrics.get("likes", 0)
        published = v.get("published_at", "")
        vid_type = v.get("type", "영상")
        
        briefs.append({
            "id": f"exp-yt-{hash(v.get('id','')) % 100000:05d}",
            "title": title,
            "status": "complete",
            "signal": f"유튜브 ({vid_type})",
            "signal_type": "기회",
            "source": "youtube",
            "source_detail": f"조회 {views:,}, 좋아요 {likes:,}",
            "hypothesis": "유튜브 조회 → 인지도",
            "criteria": "조회수 1,000+",
            "content_type": vid_type,
            "channel": "youtube",
            "learning_result": f"조회 {views:,}" if views > 0 else None,
            "verdict": None,
        })
    
    print(f"  신규 유튜브: {len([b for b in briefs if b['channel']=='youtube'])}개")
    
    # 요약
    print(f"\n총 {len(briefs)}개 실험 등록 예정")
    
    if not briefs:
        print("등록할 신규 실험 없음")
        return
    
    # Supabase에 batch insert (10개씩)
    success = 0
    for i in range(0, len(briefs), 10):
        batch = briefs[i:i+10]
        import urllib.request
        url = f"{SUPA_URL}/rest/v1/mktg_briefs"
        data = json.dumps(batch).encode()
        req = urllib.request.Request(url, data=data, method="POST", headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        })
        try:
            with urllib.request.urlopen(req) as resp:
                success += len(batch)
        except Exception as e:
            print(f"  Batch {i} error: {e}")
    
    print(f"\n✅ {success}/{len(briefs)}개 등록 완료")

if __name__ == "__main__":
    main()
