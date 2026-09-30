#!/usr/local/bin/python3
"""캠페인 비교 탭 자동 검증 (기획서 '품질 관리' (a)~(h))

사용: /usr/local/bin/python3 scripts/verify_campaign_compare.py [json 경로=site/campaign_compare.json]
- 매시 갱신(build_campaign_compare.py)이 배포 전에 후보 json으로 실행한다. 하나라도 실패하면 exit 1 → 배포 안 함.
- (c)(d)(e)는 index.html의 실제 화면 집계 함수(ccAggregate)를 node로 돌려 파이썬 일별 합계와 대조한다.
- (f)는 Meta 계정 인사이트(읽기 전용)와 대조한다. 키는 키체인에서만 읽는다.
"""
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = dt.timezone(dt.timedelta(hours=9))
path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'site' / 'campaign_compare.json'
D = json.loads(path.read_text())
HTML = (ROOT / 'site' / 'index.html').read_text()
results = []


def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))


def add_days(d, n):
    return (dt.date.fromisoformat(d) + dt.timedelta(days=n)).isoformat()


# (h) json 스키마 ──────────────────────────────────────────
def schema():
    errs = []
    for k, t in (('updated_at', str), ('today', str), ('deep_interest_since', str), ('campaigns', list), ('channels', list),
                 ('account_daily', dict), ('sources', dict), ('ga4_total_sessions', dict), ('organic', dict)):
        if not isinstance(D.get(k), t):
            errs.append(f'{k} 없음/형식 오류')
    for c in D.get('campaigns', []):
        for k in ('key', 'platform', 'id', 'name', 'status', 'settings', 'daily'):
            if k not in c:
                errs.append(f"{c.get('key')}: {k} 없음")
        if c.get('platform') not in ('meta', 'naver'):
            errs.append(f"{c.get('key')}: platform {c.get('platform')}")
        for d, v in c.get('daily', {}).items():
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', d):
                errs.append(f"{c['key']}: 날짜 {d}")
            for f in ('spend', 'lpv', 'trial'):
                if not isinstance(v.get(f), (int, float)):
                    errs.append(f"{c['key']} {d}: {f} 숫자 아님")
            if 'ga4_final' not in v:
                errs.append(f"{c['key']} {d}: ga4_final 없음")
    for d, v in D.get('account_daily', {}).items():
        if not all(isinstance(v.get(f), int) for f in ('imweb_body_sales', 'trial_bookings')):
            errs.append(f'account_daily {d}')
    age = dt.datetime.now(KST) - dt.datetime.fromisoformat(D['updated_at'])
    if age > dt.timedelta(hours=3):
        errs.append(f'updated_at이 {age} 전')
    return errs


e = schema()
check('(h) json 스키마', not e, '; '.join(e[:5]))

# (a) 기준선 숫자 (9/27~9/29, 지출 / 방문 1회당) ──────────────────
BASE = {'CMP-007': (87392, 91), 'CMP-009': (35515, 41), 'CMP-010': (42338, 45)}
by_key = {c['key']: c for c in D['campaigns']}
bad = []
for k, (sp, cpv) in BASE.items():
    c = by_key.get(k)
    if not c:
        bad.append(f'{k} 없음')
        continue
    s = sum(v['spend'] for d, v in c['daily'].items() if '2026-09-27' <= d <= '2026-09-29')
    l = sum(v['lpv'] for d, v in c['daily'].items() if '2026-09-27' <= d <= '2026-09-29')
    got = (round(s), round(s / l) if l else None)
    if got != (sp, cpv):
        bad.append(f'{k} {got} ≠ {(sp, cpv)}')
check('(a) 기준선 숫자 일치 (CMP-007·009·010, 9/27~9/29)', not bad, '; '.join(bad) or '87,392/91 · 35,515/41 · 42,338/45')

# (b) cta_click·링크 클릭이 판단 열에 없음 ─────────────────────
m = re.search(r'<script>\n/\* ═+\n   ⚖️ 캠페인 비교[\s\S]*?</script>', HTML)
block = m.group(0) if m else ''
judg = re.findall(r"th\('(\w+)', '([^']+)', 'g n'", block)
allowed = {'deepCost', 'trial', 'purchase', 'p100d', 'p100t'}
bad = []
if not block:
    bad.append('캠페인 비교 스크립트 블록 없음')
if 'cta_click' in block or 'cta_click' in json.dumps(D, ensure_ascii=False):
    bad.append('cta_click 등장')
if {k for k, _ in judg} != allowed:
    bad.append(f'판단 열 {[k for k, _ in judg]}')
if any(re.search('클릭|CTR|참여', label) for _, label in judg):
    bad.append('판단 열에 클릭/CTR/참여')
if '구매버튼' in block or '구매 버튼' in block:
    bad.append('구매 버튼 문구 등장')
check('(b) cta_click·링크 클릭 판단 열 없음', not bad, '; '.join(bad) or f'판단 열 = {[l for _, l in judg]}')

# (c)(d)(e) 화면 집계 함수(ccAggregate)로 기간 합산 대조 ───────────────
today = D['today']
since = D['deep_interest_since']
periods = [(today, today), (add_days(today, -1), add_days(today, -1)), (add_days(today, -3), add_days(today, -1)),
           (add_days(today, -7), add_days(today, -1)), (add_days(today, -30), add_days(today, -1)),
           ('2026-09-27', '2026-09-29'), (add_days(since, -2), today)]
js = block.replace('<script>', '').replace('</script>', '')
harness = js + '''
const D = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
const P = JSON.parse(process.argv[3]);
const out = [];
for (const c of D.campaigns.concat(D.channels)) for (const [a, b] of P) {
  const g = ccAggregate(c, a, b, D.deep_interest_since, D.today);
  out.push({ key: c.key, a, b, spend: g.spend, lpv: g.lpv, deep: g.deep, deepSpend: g.deepSpend, trial: g.trial,
             sessions: g.sessions, sessDeep: g.sessDeep, deepCost: g.deepCost, trialCost: g.trialCost, cpv: g.cpv,
             per100Deep: g.per100Deep, per100Trial: g.per100Trial, measured: g.measured, clarity: g.clarity });
}
console.log(JSON.stringify(out));
'''
Path('/tmp/cc_verify_harness.js').write_text('global.localStorage={getItem:()=>null,setItem:()=>{}};\n' + harness)
np = subprocess.run(['node', '/tmp/cc_verify_harness.js', str(path), json.dumps(periods)], capture_output=True, text=True)
if np.returncode != 0:
    check('(c) 기간 합산 = 일별 합계', False, 'node 실행 실패: ' + np.stderr[-300:])
    check('(d) 분자·분모 기간 일치', False, 'node 실행 실패')
    check('(e) "-"와 0 구분', False, 'node 실행 실패')
else:
    agg = json.loads(np.stdout)
    rows = {c['key']: c for c in D['campaigns'] + D['channels']}
    c_bad, d_bad, e_bad = [], [], []

    def close(x, y):
        if x is None or y is None:
            return x is None and y is None
        return abs(x - y) <= 1e-6 * max(1, abs(y))
    for r in agg:
        c = rows[r['key']]
        days = {d: v for d, v in c['daily'].items() if r['a'] <= d <= r['b']}
        ddays = {d: v for d, v in days.items() if d >= since}
        exp = {f: sum(v.get(f) or 0 for v in days.values()) for f in ('spend', 'lpv', 'trial', 'sessions')}
        exp['deep'] = sum((v.get('deep') or {}).get('total', 0) for v in ddays.values())
        exp['deepSpend'] = sum(v.get('spend') or 0 for v in ddays.values())
        exp['sessDeep'] = sum(v.get('sessions') or 0 for v in ddays.values())
        for f, x in exp.items():
            if not close(r[f], x):
                c_bad.append(f"{r['key']} {r['a']}~{r['b']} {f} {r[f]}≠{x}")
        measured = r['b'] >= since
        exp_d = {
            'deepCost': exp['deepSpend'] / exp['deep'] if measured and exp['deep'] else None,
            'trialCost': exp['spend'] / exp['trial'] if exp['trial'] else None,
            'cpv': exp['spend'] / exp['lpv'] if exp['lpv'] else None,
            'per100Deep': exp['deep'] / exp['sessDeep'] * 100 if measured and exp['sessDeep'] else None,
            'per100Trial': exp['trial'] / exp['sessions'] * 100 if exp['sessions'] else None,
        }
        for f, x in exp_d.items():
            if not close(r[f], x):
                d_bad.append(f"{r['key']} {r['a']}~{r['b']} {f} {r[f]}≠{x}")
        if r['measured'] != measured:
            e_bad.append(f"{r['key']} {r['a']}~{r['b']} measured {r['measured']}")
        if not measured and r['deepCost'] is not None:
            e_bad.append(f"{r['key']} 측정 전 기간에 deepCost 값")
        if r['clarity'] is None and any((v.get('clarity') or {}).get('sec') is not None for v in days.values()):
            e_bad.append(f"{r['key']} Clarity 값 있는데 None")
    for c in D['campaigns'] + D['channels']:
        for d, v in c['daily'].items():
            if d < since and v.get('deep') is not None:
                e_bad.append(f"{c['key']} {d}: 측정 전 날짜에 deep={v['deep']}")
            if v.get('clarity_active_sec') == 0 and not v.get('clarity'):
                e_bad.append(f"{c['key']} {d}: Clarity 없음을 0으로 저장")
    check('(c) 기간 합산 = 일별 합계', not c_bad, '; '.join(c_bad[:4]) or f'{len(agg)}개 (행×기간) 대조')
    check('(d) 분자·분모 기간 일치', not d_bad, '; '.join(d_bad[:4]) or '1건당·방문당·100명당 모두 같은 기간 분자/분모')
    check('(e) "-"와 0 구분', not e_bad, '; '.join(e_bad[:4]) or f'측정 전({since} 이전) deep=null, Clarity 없음=null')

# (f) Meta 지출 합계 = 계정 인사이트 합계(±1%) ─────────────────────
try:
    def k(s):
        return subprocess.check_output(['security', 'find-generic-password', '-s', s, '-w']).decode().strip()
    tok = k('openclaw_meta_ads_token')
    act = k('openclaw_meta_ads_account')
    act = act if act.startswith('act_') else 'act_' + act
    q = urllib.parse.urlencode({'access_token': tok, 'level': 'account', 'fields': 'spend',
                                'time_range': json.dumps({'since': D['data_since'], 'until': today})})
    acct = json.load(urllib.request.urlopen(f'https://graph.facebook.com/v24.0/{act}/insights?{q}', timeout=60))
    a_sp = sum(float(x['spend']) for x in acct.get('data', []))
    j_sp = sum(v['spend'] for c in D['campaigns'] if c['platform'] == 'meta' for v in c['daily'].values())
    ok = a_sp > 0 and abs(a_sp - j_sp) <= a_sp * 0.01
    check('(f) Meta 지출 합계 = 계정 인사이트(±1%)', ok, f'json {j_sp:,.0f} vs 계정 {a_sp:,.0f} ({D["data_since"]}~{today})')
except Exception as ex:  # noqa: BLE001
    check('(f) Meta 지출 합계 = 계정 인사이트(±1%)', False, f'조회 실패: {type(ex).__name__}')

# (g) GA4 채널 행 세션 합계 = GA4 전체 세션(±2%) ─────────────────────
tot = D.get('ga4_total_sessions') or {}
days = [d for d in tot if d < today]
ch_sum = sum(v.get('sessions', 0) for c in D['channels'] for d, v in c['daily'].items() if d in days)
t_sum = sum(tot[d] for d in days)
check('(g) GA4 채널 행 세션 합계 = 전체 세션(±2%)', t_sum > 0 and abs(ch_sum - t_sum) <= t_sum * 0.02,
      f'채널 합 {ch_sum:,} vs 전체 {t_sum:,} ({min(days) if days else "-"}~{max(days) if days else "-"}, 당일 제외)')

fail = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'} {name} — {detail}")
print(f'결과: {len(results) - len(fail)}/{len(results)} 통과')
sys.exit(1 if fail else 0)
