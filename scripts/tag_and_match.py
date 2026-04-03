#!/usr/bin/env python3
"""
1. 인스타↔유튜브 날짜 기반 매칭 (같은 날 → 같은 콘텐츠)
2. 인스타 140개 + 블로그 20개 임시 태깅 (캡션/제목 기반 키워드 매칭)
3. 유튜브 119개에 인스타 태깅 복사
4. Supabase 업데이트
"""
import json, subprocess, hashlib, urllib.request, urllib.parse, re
from collections import defaultdict

SUPABASE_URL = "https://ssidizurrvnfmqbvfsqr.supabase.co"
KEY = subprocess.check_output(["security", "find-generic-password", "-s", "openclaw_supabase_service_role_wspn", "-w"]).decode().strip()
HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
DATA_DIR = "/Users/hsw/.openclaw/workspace-ex-asst/marketing-pipeline/data"

def patch(brief_id, fields):
    url = f"{SUPABASE_URL}/rest/v1/mktg_briefs?id=eq.{urllib.parse.quote(brief_id)}"
    data = json.dumps(fields).encode()
    req = urllib.request.Request(url, data=data, headers=HEADERS, method="PATCH")
    urllib.request.urlopen(req)

def fetch_briefs(source):
    url = f"{SUPABASE_URL}/rest/v1/mktg_briefs?select=id,title,created_at,target_vp,target_problem,content_type,hook_type,hypothesis&source=eq.{source}&limit=500"
    req = urllib.request.Request(url, headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"})
    return json.loads(urllib.request.urlopen(req).read())

# === VP/Problem 키워드 매핑 ===
VP_KEYWORDS = {
    "VP1": ["자유", "해방", "공간", "시간", "눈치", "소음", "층간", "이사", "어디서든", "언제든", "자유롭"],
    "VP2": ["안전", "안심", "부상", "보호", "세이프티", "국내", "A/S", "안전장치"],
    "VP3": ["성장", "성취", "기록", "한계", "돌파", "득근", "변화", "근성장", "벌크", "폭발"],
    "VP4": ["경제", "절약", "비용", "가성비", "헬스장비", "PT비", "절감"],
    "VP5": ["라이프", "습관", "일상", "루틴", "가정", "인테리어", "홈짐", "홈트"],
    "VP6": ["프리미엄", "내 전용", "소유", "고급", "럭셔리"],
    "VP7": ["AI", "코칭", "재활", "B2B", "PT샵", "센터", "트레이너", "전문"],
    "VP8": ["스마트", "기술", "터치", "음성", "모터", "신기", "혁신", "테슬라", "신개념"],
}

PROBLEM_KEYWORDS = {
    "P1": ["시간", "바쁜", "퇴근", "야근", "출퇴근", "왕복"],
    "P2": ["헬스장 비용", "월회비", "등록비"],
    "P4": ["부상", "깔림", "안전", "위험", "혼자"],
    "P5": ["자세", "피드백", "폼"],
    "P7": ["공간", "좁은", "0.5평", "반평", "풋프린트", "컴팩트", "소형"],
    "P8": ["소음", "층간", "진동", "아파트"],
    "P9": ["이사", "처분", "이동"],
    "P10": ["한계", "무게", "중량", "원판", "덤벨", "밴드", "종류"],
    "P13": ["아이", "아기", "육아", "돌봄"],
    "P22": ["꾸준", "습관", "포기", "작심삼일"],
}

HOOK_KEYWORDS = {
    "질문형": ["?", "어떻게", "왜", "뭐", "무엇", "할까", "되나", "가능"],
    "숫자": ["0.5평", "120kg", "200+", "1시간", "3배", "50%", "1RM"],
    "호기심": ["비법", "방법", "몰랐", "알려드", "치트키", "신기"],
    "도발": ["버려", "포기", "필요없", "가지않", "하지마"],
    "시연데모": ["시연", "데모", "직접", "실제로", "보여"],
}

CONTENT_TYPE_MAP = {
    "IMAGE": "이미지",
    "VIDEO": "영상(숏폼)",
    "CAROUSEL_ALBUM": "카루셀",
}

def auto_tag(text, media_type=None, is_blog=False):
    """텍스트 기반 자동 태깅"""
    text_lower = text.lower()
    
    # VP
    vps = []
    for vp, keywords in VP_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                vps.append(vp)
                break
    if not vps:
        vps = ["VP5"]  # 기본: 라이프스타일
    
    # Problem
    problems = []
    for p, keywords in PROBLEM_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                problems.append(p)
                break
    if not problems:
        problems = ["P10"]  # 기본: 장비 한계
    
    # Hook
    hook = None
    for h, keywords in HOOK_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                hook = h
                break
        if hook:
            break
    if not hook:
        hook = "호기심"
    
    # Content type
    if is_blog:
        content_type = "블로그"
    elif media_type:
        content_type = CONTENT_TYPE_MAP.get(media_type, "영상(숏폼)")
    else:
        content_type = "영상(숏폼)"
    
    return {
        "target_vp": ", ".join(sorted(set(vps))),
        "target_problem": ", ".join(sorted(set(problems))),
        "hook_type": hook,
        "content_type": content_type,
    }


# === 1. 인스타 태깅 ===
print("=== 1. 인스타 140개 태깅 ===")
with open(f"{DATA_DIR}/instagram_creatives.json") as f:
    ig_data = json.load(f)

ig_briefs = fetch_briefs("instagram")
ig_by_date = {}
ig_tags = {}  # date → tags (유튜브 복사용)

for brief in ig_briefs:
    # 해당 원본 찾기
    date = brief["created_at"][:10]
    orig = None
    for c in ig_data:
        if c.get("timestamp", "")[:10] == date:
            orig = c
            break
    
    if not orig:
        # fallback: title로 매칭
        for c in ig_data:
            cap = (c.get("caption") or "")[:20]
            if cap and cap in brief["title"]:
                orig = c
                date = c.get("timestamp", "")[:10]
                break
    
    if orig and not brief.get("target_vp"):
        caption = orig.get("caption") or ""
        media_type = orig.get("media_type", "VIDEO")
        tags = auto_tag(caption, media_type)
        
        # 가설도 구체화
        vp_text = tags["target_vp"]
        prob_text = tags["target_problem"]
        title_short = brief["title"].replace("[인스타] ", "")[:30]
        tags["hypothesis"] = f"{vp_text} 가치를 {prob_text} 문제 맥락에서 전달하면 인스타 오가닉 도달이 증가하는가 (소재: {title_short})"
        
        patch(brief["id"], tags)
        ig_tags[date] = tags
        
print(f"✅ 인스타 태깅: {len(ig_tags)}개")


# === 2. 인스타↔유튜브 매칭 + 태깅 복사 ===
print("\n=== 2. 유튜브 119개 태깅 (인스타에서 복사) ===")
with open(f"{DATA_DIR}/youtube_creatives.json") as f:
    yt_data = json.load(f)

yt_briefs = fetch_briefs("youtube")

# 인스타 date → tags 완성 (이미 태깅된 것 포함)
for brief in ig_briefs:
    date = brief["created_at"][:10]
    if date not in ig_tags and brief.get("target_vp"):
        ig_tags[date] = {
            "target_vp": brief["target_vp"],
            "target_problem": brief["target_problem"],
            "hook_type": brief["hook_type"],
            "content_type": brief["content_type"],
        }

yt_matched = 0
yt_auto = 0
for brief in yt_briefs:
    if brief.get("target_vp"):
        continue  # 이미 태깅됨
    
    date = brief["created_at"][:10]
    
    # 인스타 매칭
    if date in ig_tags:
        tags = dict(ig_tags[date])
        tags["content_type"] = "영상(숏폼)"  # 유튜브는 영상
        title_short = brief["title"].replace("[유튜브] ", "")[:30]
        tags["hypothesis"] = f"{tags['target_vp']} 가치를 {tags['target_problem']} 문제 맥락에서 전달하면 유튜브 조회/좋아요가 증가하는가 (소재: {title_short})"
        patch(brief["id"], tags)
        yt_matched += 1
    else:
        # 매칭 안 되면 유튜브 텍스트로 자동 태깅
        orig = None
        for c in yt_data:
            if c.get("published_at", "")[:10] == date:
                orig = c
                break
        if orig:
            text = orig.get("text") or orig.get("description") or ""
            tags = auto_tag(text)
            tags["content_type"] = "영상(숏폼)"
            title_short = brief["title"].replace("[유튜브] ", "")[:30]
            tags["hypothesis"] = f"{tags['target_vp']} 가치를 {tags['target_problem']} 문제 맥락에서 전달하면 유튜브 조회/좋아요가 증가하는가 (소재: {title_short})"
            patch(brief["id"], tags)
            yt_auto += 1

print(f"✅ 유튜브: 인스타 복사 {yt_matched} + 자동 {yt_auto} = {yt_matched + yt_auto}개")


# === 3. 블로그 20개 태깅 ===
print("\n=== 3. 블로그 20개 태깅 ===")
blog_briefs = fetch_briefs("naver_blog")

with open(f"{DATA_DIR}/blog_creatives.json") as f:
    blog_posts = json.load(f)["posts"]

blog_ok = 0
for brief in blog_briefs:
    if brief.get("target_vp"):
        continue
    
    # 원본 텍스트 찾기
    title_clean = brief["title"].replace("[블로그] ", "")
    text = title_clean
    for p in blog_posts:
        ptitle = p["text"]["title"] if isinstance(p.get("text"), dict) else ""
        if ptitle and ptitle[:15] in title_clean:
            body = p["text"].get("body", "") if isinstance(p.get("text"), dict) else ""
            text = ptitle + " " + body[:200]
            break
    
    tags = auto_tag(text, is_blog=True)
    tags["hypothesis"] = f"{tags['target_vp']} 가치를 블로그 SEO 콘텐츠로 전달하면 네이버 오가닉 유입이 증가하는가 (소재: {title_clean[:30]})"
    patch(brief["id"], tags)
    blog_ok += 1

print(f"✅ 블로그: {blog_ok}개")

print(f"\n=== 완료 ===")
print(f"인스타: {len(ig_tags)}개, 유튜브: {yt_matched + yt_auto}개, 블로그: {blog_ok}개")
print(f"총: {len(ig_tags) + yt_matched + yt_auto + blog_ok}개")
