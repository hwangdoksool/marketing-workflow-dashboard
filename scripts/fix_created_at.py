#!/usr/bin/env python3
"""
Supabase mktg_briefs의 created_at을 원본 업로드 날짜로 수정.
- 인스타: timestamp 필드
- 유튜브: published_at 필드
- Meta: Meta Ads API에서 ad created_time 조회
"""
import json, subprocess, hashlib, urllib.request, urllib.parse, sys

SUPABASE_URL = "https://ssidizurrvnfmqbvfsqr.supabase.co"
KEY = subprocess.check_output(["security", "find-generic-password", "-s", "openclaw_supabase_service_role_wspn", "-w"]).decode().strip()
HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}

DATA_DIR = "/Users/hsw/.openclaw/workspace-ex-asst/marketing-pipeline/data"

def patch(brief_id, created_at):
    url = f"{SUPABASE_URL}/rest/v1/mktg_briefs?id=eq.{brief_id}"
    data = json.dumps({"created_at": created_at}).encode()
    req = urllib.request.Request(url, data=data, headers=HEADERS, method="PATCH")
    try:
        urllib.request.urlopen(req)
        return True
    except Exception as e:
        print(f"  ❌ {brief_id}: {e}")
        return False

# --- Instagram ---
print("=== Instagram ===")
with open(f"{DATA_DIR}/instagram_creatives.json") as f:
    ig_data = json.load(f)

ig_ok = 0
for c in ig_data:
    cid = c.get("id", "")
    ts = c.get("timestamp")
    if not ts:
        continue
    brief_id = f"exp-ig-{hashlib.md5(cid.encode()).hexdigest()[:5]}"
    if patch(brief_id, ts):
        ig_ok += 1
print(f"✅ Instagram: {ig_ok}/{len(ig_data)}")

# --- YouTube ---
print("\n=== YouTube ===")
with open(f"{DATA_DIR}/youtube_creatives.json") as f:
    yt_data = json.load(f)

yt_ok = 0
for c in yt_data:
    vid = c.get("id", "")
    pub = c.get("published_at")
    if not pub:
        continue
    brief_id = f"exp-yt-{hashlib.md5(vid.encode()).hexdigest()[:5]}"
    if patch(brief_id, pub):
        yt_ok += 1
print(f"✅ YouTube: {yt_ok}/{len(yt_data)}")

# --- Meta Ads: API에서 ad created_time 가져오기 ---
print("\n=== Meta Ads ===")
META_TOKEN = subprocess.check_output(["security", "find-generic-password", "-s", "openclaw_meta_ads_token", "-w"]).decode().strip()
META_ACCOUNT = subprocess.check_output(["security", "find-generic-password", "-s", "openclaw_meta_ads_account", "-w"]).decode().strip()
META_ACCOUNT = META_ACCOUNT.replace("act_", "")

# 태깅 데이터에서 이름 목록
with open(f"{DATA_DIR}/retagged_creatives_v2.json") as f:
    meta_creatives = json.load(f)

# Meta Ads API: 모든 광고의 name + created_time 가져오기
print("  Fetching ad created_time from Meta Ads API...")
ads_dates = {}
url = f"https://graph.facebook.com/v22.0/act_{META_ACCOUNT}/ads?fields=name,created_time&limit=500&access_token={META_TOKEN}"
while url:
    req = urllib.request.Request(url, headers={"User-Agent": "signal-analyzer/1.0"})
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    for ad in result.get("data", []):
        ads_dates[ad["name"]] = ad["created_time"]
    url = result.get("paging", {}).get("next")

print(f"  Fetched {len(ads_dates)} ads from Meta API")

meta_ok = 0
meta_skip = 0
for c in meta_creatives:
    name = c.get("name", "")
    brief_id = f"exp-meta-{hashlib.md5(name.encode()).hexdigest()[:5]}"
    
    # 정확 매칭 시도
    created = ads_dates.get(name)
    if not created:
        # 부분 매칭 (태깅 이름이 그룹명일 수 있음)
        for ad_name, ad_date in ads_dates.items():
            if name in ad_name or ad_name in name:
                created = ad_date
                break
    
    if created:
        if patch(brief_id, created):
            meta_ok += 1
    else:
        meta_skip += 1

print(f"✅ Meta: {meta_ok}/{len(meta_creatives)} (skip: {meta_skip})")
print(f"\n총 업데이트: {ig_ok + yt_ok + meta_ok}개")
