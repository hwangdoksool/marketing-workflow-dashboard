#!/usr/bin/env python3
"""
Signal Analyzer — OpenClaw 에이전트 호출 (시냅스서치 + 크리에이티브 스키마 기반)
workflow-api.wespion.com에서 pending 분석 요청을 가져와 처리합니다.

Usage:
  python3 signal-analyzer.py [--once]  # --once: 1회 실행 후 종료
  python3 signal-analyzer.py           # 30초 간격 폴링
"""

import json, os, sys, time, subprocess, urllib.request, urllib.error
from pathlib import Path

API_BASE = "https://workflow-api.wespion.com/api"
API_KEY = subprocess.run(
    ["security", "find-generic-password", "-s", "openclaw_wspn_api_key", "-w"],
    capture_output=True, text=True
).stdout.strip()

OPENAI_KEY = subprocess.run(
    ["security", "find-generic-password", "-s", "openclaw_openai", "-w"],
    capture_output=True, text=True
).stdout.strip()

# Paths
WORKSPACE = Path.home() / ".openclaw" / "workspace-ex-asst"
PIPELINE = WORKSPACE / "marketing-pipeline"
SYNAPSE = Path.home() / ".openclaw" / "workspace" / "synapse-search"
SCHEMA_FILE = PIPELINE / "CREATIVE_SCHEMA_v1.md"

# Load creative schema
def load_schema():
    if SCHEMA_FILE.exists():
        return SCHEMA_FILE.read_text()[:3000]
    return "크리에이티브 스키마를 찾을 수 없습니다."

# Load latest report summary
def load_latest_report():
    reports_file = WORKSPACE / "marketing-workflow-dashboard" / "site" / "reports.json"
    if reports_file.exists():
        reports = json.loads(reports_file.read_text())
        if reports:
            latest = reports[0]  # newest first
            return json.dumps({
                "title": latest.get("title"),
                "abstract": latest.get("abstract"),
                "kpi": latest.get("kpi")
            }, ensure_ascii=False, indent=2)[:2000]
    return "최신 리포트 없음"

# Synapse search
def synapse_search(query, collections=None, limit=5):
    """Run synapse search and return results."""
    search_script = SYNAPSE / "search_engine" / "pass1_explorer.py"
    if not search_script.exists():
        return "시냅스서치 스크립트 없음"
    
    cmd = [sys.executable, str(search_script), "--query", query, "--limit", str(limit)]
    if collections:
        cmd.extend(["--collections", ",".join(collections)])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=str(SYNAPSE))
        return result.stdout[:3000] if result.stdout else f"검색 결과 없음 (stderr: {result.stderr[:200]})"
    except Exception as e:
        return f"검색 오류: {e}"

# API helpers
UA = "signal-analyzer/1.0"

def api_get(path):
    req = urllib.request.Request(f"{API_BASE}{path}", headers={"User-Agent": UA, "X-API-Key": API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  API GET error: {e}")
        return None

def api_put(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{API_BASE}{path}", data=body, method="PUT",
                                headers={"Content-Type": "application/json", "X-API-Key": API_KEY, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  API PUT error: {e}")
        return None

def analyze_with_openai(user_text, context):
    """Full analysis with OpenAI using rich context."""
    SOURCES = ['주간리포트','Meta Ads','GA4','네이버SA','아임웹주문',
               'CS카카오','CS아임웹','CS커뮤니티','인스타그램',
               '현장','외부시장','내부논의','이전실험','기타']
    TYPES = ['위협','기회','외부','루프','현장']
    
    system_prompt = f"""You are a senior marketing analyst for Roomfit (스마트 웨이트 머신, ₩3,480,000).
You analyze marketing signals based on real data.

## Creative Schema (9요소)
{context['schema'][:1500]}

## Latest Weekly Report
{context['report'][:1500]}

## Relevant Search Results
{context['search_results'][:2000]}

## Available Sources: {', '.join(SOURCES)}
## Available Signal Types: {', '.join(TYPES)}

Based on the user's observation AND the real data above, provide a thorough analysis.

Respond ONLY with JSON (no markdown):
{{
  "title": "concise signal title in Korean (max 50 chars)",
  "signal": "detailed analysis in Korean — reference actual data. 3-5 sentences. What the data shows, why it matters, what's unusual.",
  "source": "one of the available sources",
  "sourceDetail": "specific reference (e.g. W13 report, specific campaign name, CS case)",
  "signalType": "one of the available types",
  "suggestedAction": "recommended next step in Korean — what experiment or action to consider",
  "relatedSchema": {{
    "vp": "relevant VP from schema (e.g. VP2 안심/안전)",
    "problem": "relevant Problem (e.g. P7 공간부족)",
    "hook": "relevant Hook type if applicable"
  }},
  "confidence": "high/medium/low",
  "dataEvidence": "specific numbers/facts from the data that support this signal"
}}"""

    body = json.dumps({
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.3,
        "max_tokens": 800
    }).encode()
    
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions",
                                data=body, method="POST",
                                headers={"Content-Type": "application/json",
                                         "Authorization": f"Bearer {OPENAI_KEY}",
                                         "User-Agent": UA})
    
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    
    content = data["choices"][0]["message"]["content"]
    return json.loads(content.replace("```json", "").replace("```", "").strip())

def process_request(item):
    """Process a single analysis request."""
    text = item["text"]
    req_id = item["id"]
    print(f"  Processing {req_id}: {text[:60]}...")
    
    # 1. Load context
    schema = load_schema()
    report = load_latest_report()
    
    # 2. Synapse search based on user text
    search_results = synapse_search(text, limit=5)
    
    # 3. Analyze with full context
    context = {
        "schema": schema,
        "report": report,
        "search_results": search_results
    }
    
    result = analyze_with_openai(text, context)
    
    # 4. Save result
    api_put(f"/analyze-signal/{req_id}", result)
    print(f"  ✅ Done: {result.get('title', 'unknown')}")
    return result

def main():
    once = "--once" in sys.argv
    
    while True:
        print(f"[{time.strftime('%H:%M:%S')}] Checking for pending analysis requests...")
        pending = api_get("/analyze-pending")
        
        if pending:
            print(f"  Found {len(pending)} pending requests")
            for item in pending:
                try:
                    process_request(item)
                except Exception as e:
                    print(f"  ❌ Error processing {item.get('id')}: {e}")
                    # Save error result
                    api_put(f"/analyze-signal/{item['id']}", {
                        "error": str(e),
                        "title": "분석 실패",
                        "signal": f"원문: {item['text']}\n\n오류: {e}",
                        "source": "기타",
                        "signalType": "기타",
                        "confidence": "low"
                    })
        else:
            print("  No pending requests")
        
        if once:
            break
        
        time.sleep(10)

if __name__ == "__main__":
    main()
