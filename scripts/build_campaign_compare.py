#!/usr/local/bin/python3
"""캠페인 비교 탭 데이터 수집 → site/campaign_compare.json → 배포

기획: docs/2026-09-30_campaign-compare-tab-spec.md (대표님 2026-09-30 지시)
- 날짜별로 저장하고, 기간 합산은 화면(index.html #analysis/compare)에서 한다.
- 소스: Meta(설정+일별 인사이트) / GA4 rf_deep_interest(봇 필터) / Supabase feel_bookings
        / 네이버 광고그룹 일별 / Clarity(am·pm 수집 파일) / 아임웹 실판매
- Meta 실패 → 기존 json 유지하고 종료(exit 1). 그 외 소스 실패 → 해당 필드는 기존 값 유지, sources에 오류 기록.
- 매시 05분 launchd(com.openclaw.campaign-compare-hourly)에서 실행.

사용: /usr/local/bin/python3 scripts/build_campaign_compare.py [--no-deploy]
Meta는 읽기(GET)만 한다. 키는 macOS 키체인에서만 읽는다.
"""
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'site' / 'campaign_compare.json'
WS = Path.home() / '.openclaw' / 'workspace-ex-asst'
PIPE = WS / 'marketing-pipeline'
KST = dt.timezone(dt.timedelta(hours=9))

DATA_SINCE = '2026-09-01'
DEEP_SINCE = '2026-09-30'          # rf_deep_interest 이벤트 시작일
CC_DEEP_V2 = '1712444449859619'     # 깊은 관심 v2 (RfDeepInterest)
CC_BODY_PURCHASE = '3523132157864226'  # 본체 구매 (Purchase ≥100만)
NAVER_NONBRAND_CONTENT = 'nonbrand_0927'  # 비브랜드 확장 그룹 utm_content → CMP-011

NOW = dt.datetime.now(KST)
TODAY = NOW.date().isoformat()

SECRETS = []


def log(msg):
    print(f"[{dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def keychain(name):
    v = subprocess.check_output(['security', 'find-generic-password', '-s', name, '-w']).decode().strip()
    SECRETS.append(v)
    return v


def scrub(s):
    s = str(s)
    for v in SECRETS:
        if v:
            s = s.replace(v, '***')
    return s


def daterange(a, b):
    d, e = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    while d <= e:
        yield d.isoformat()
        d += dt.timedelta(days=1)


def retry(fn, what, tries=4, base=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            wait = base * (2 ** i)
            log(f'  {what} 재시도 {i + 1}/{tries - 1} ({scrub(e)[:200]}) {wait}s 후')
            time.sleep(wait)


# ───────────────────────── Meta ─────────────────────────
class Meta:
    V = 'v24.0'

    def __init__(self):
        self.token = keychain('openclaw_meta_ads_token')
        a = keychain('openclaw_meta_ads_account')
        self.act = a if a.startswith('act_') else 'act_' + a

    def _get(self, url):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors='replace')
            raise RuntimeError(f'Meta HTTP {e.code}: {body[:400]}') from None

    def q(self, path, **p):
        p['access_token'] = self.token
        url = f'https://graph.facebook.com/{self.V}/{path}?' + urllib.parse.urlencode(p)
        out = []
        while url:
            r = retry(lambda u=url: self._get(u), f'Meta {path}')
            if 'error' in r:
                raise RuntimeError(f"Meta error: {r['error']}")
            out += r.get('data', [])
            url = r.get('paging', {}).get('next')
        return out


def meta_actions(row):
    return {a['action_type']: float(a['value']) for a in row.get('actions', []) or []}


OPT_EVENT = {'PURCHASE': '구매', 'COMPLETE_REGISTRATION': '가입 완료', 'LEAD': '리드', 'CONTENT_VIEW': '콘텐츠 조회',
             'INITIATED_CHECKOUT': '결제 시작', 'ADD_TO_CART': '장바구니', 'START_TRIAL': '체험 시작'}
OPT_GOAL = {'LANDING_PAGE_VIEWS': '방문(랜딩 조회)', 'LINK_CLICKS': '링크 클릭', 'REACH': '도달', 'IMPRESSIONS': '노출',
            'THRUPLAY': '영상 재생', 'POST_ENGAGEMENT': '참여', 'VALUE': '구매 금액'}
CC_LABEL = {CC_DEEP_V2: '깊은 관심', '1630203808629814': '깊은 관심(v1)', '2306085919929012': '상세·체험 조회',
            CC_BODY_PURCHASE: '본체 구매', '1074629242220862': '체험 결제', '2149955095774462': '체험 결제',
            '1881050985909109': '모든 결제', '2066858340772428': '체험 신청 완료'}


def opt_label(adset, cc_names):
    po = adset.get('promoted_object') or {}
    cc = po.get('custom_conversion_id')
    if cc:
        return CC_LABEL.get(cc) or re.sub(r'\s*\(.*\)$', '', cc_names.get(cc, f'맞춤 전환 {cc}'))
    if po.get('custom_event_type'):
        return OPT_EVENT.get(po['custom_event_type'], po['custom_event_type'])
    return OPT_GOAL.get(adset.get('optimization_goal'), adset.get('optimization_goal') or '-')


def target_label(t):
    t = t or {}
    ar = t.get('age_range')
    adv = (t.get('targeting_automation') or {}).get('advantage_audience') == 1
    if adv:
        s = f'넓게 (나이 제안 {ar[0]}~{ar[1]}세)' if ar else '넓게'
    else:
        s = f"나이 {t.get('age_min', 18)}~{t.get('age_max', 65)}세"
        if t.get('genders') == [1]:
            s += ' 남성'
        elif t.get('genders') == [2]:
            s += ' 여성'
    if t.get('custom_audiences'):
        s += ' · 지정 오디언스'
    ex = []
    for a in t.get('excluded_custom_audiences') or []:
        n = a.get('name', '')
        lab = ('구매자' if '구매' in n else '사이트 방문자' if '방문' in n
               else '이미 본 사람' if re.search('참여|관심|시청|팔로우', n) else '기타 오디언스')
        if lab not in ex:
            ex.append(lab)
    if ex:
        s += ' · ' + '·'.join(ex) + ' 제외'
    return s


def creative_label(ads):
    vid = img = 0
    for a in ads:
        c = a.get('creative') or {}
        afs = c.get('asset_feed_spec') or {}
        if c.get('object_type') == 'VIDEO' or c.get('video_id') or afs.get('videos'):
            vid += 1
        else:
            img += 1
    parts = []
    if vid:
        parts.append(f'영상 {vid}편')
    if img:
        parts.append(f'이미지 {img}장')
    return ' · '.join(parts) or '-', vid + img


def short_name(name, key):
    s = name.replace(key, '', 1).strip()
    s = re.sub(r'^\[[^\]]*\]\s*', '', s)
    s = re.sub(r'\s*·\s*(\d{4}|\d{1,2}/\d{1,2}까지)$', '', s)
    return s.strip(' ·') or name


def collect_meta():
    m = Meta()
    tr = json.dumps({'since': DATA_SINCE, 'until': TODAY})
    rows = m.q(f'{m.act}/insights', level='campaign', time_range=tr, time_increment=1, limit=500,
               fields='campaign_id,campaign_name,spend,actions,date_start')
    acct = m.q(f'{m.act}/insights', level='account', time_range=tr, fields='spend')
    acct_spend = sum(float(x.get('spend', 0)) for x in acct)
    row_spend = sum(float(x.get('spend', 0)) for x in rows)
    # 레이트 리밋 시 빈 배열로 위장하는 경우 → 계정 합계와 대조해 빈 결과를 성공으로 보지 않는다
    if acct_spend > 0 and (not rows or abs(acct_spend - row_spend) > max(100, acct_spend * 0.01)):
        raise RuntimeError(f'Meta 캠페인 인사이트 불일치: 계정 {acct_spend:.0f} vs 캠페인 합 {row_spend:.0f} (행 {len(rows)})')
    since_ts = int(dt.datetime.fromisoformat(DATA_SINCE + 'T00:00:00+09:00').timestamp())
    recent = m.q(f'{m.act}/campaigns', fields='id', limit=200,
                 filtering=json.dumps([{'field': 'created_time', 'operator': 'GREATER_THAN', 'value': since_ts}]))
    ids = sorted({r['campaign_id'] for r in rows} | {c['id'] for c in recent})
    if not ids:
        raise RuntimeError('Meta 대상 캠페인 0개 — 빈 결과를 성공으로 보지 않음')
    flt = json.dumps([{'field': 'campaign.id', 'operator': 'IN', 'value': ids}])
    camps = m.q(f'{m.act}/campaigns', fields='id,name,status,effective_status,daily_budget,lifetime_budget,start_time,stop_time',
                limit=200, filtering=json.dumps([{'field': 'id', 'operator': 'IN', 'value': ids}]))
    adsets = m.q(f'{m.act}/adsets', limit=300, filtering=flt,
                 fields='name,status,effective_status,campaign_id,optimization_goal,promoted_object,daily_budget,'
                        'daily_spend_cap,targeting{age_range,age_min,age_max,genders,targeting_automation,'
                        'excluded_custom_audiences{name},custom_audiences{name}}')
    ads = m.q(f'{m.act}/ads', limit=500, filtering=flt,
              fields='name,status,effective_status,campaign_id,adset_id,creative{object_type,video_id,image_hash,asset_feed_spec{videos,images}}')
    ccs = {c['id']: c['name'] for c in m.q(f'{m.act}/customconversions', fields='id,name', limit=200)}
    if len(camps) != len(ids):
        raise RuntimeError(f'Meta 캠페인 설정 조회 누락: {len(camps)}/{len(ids)}')

    out = {}
    for c in camps:
        name = c['name']
        km = re.search(r'CMP-\d+', name)
        key = km.group(0) if km else 'META-' + c['id'][-6:]
        sets = [s for s in adsets if s['campaign_id'] == c['id'] and s.get('status') not in ('DELETED', 'ARCHIVED')]
        live_sets = [s for s in sets if s.get('status') == 'ACTIVE'] or sets
        sids = {s['id'] for s in live_sets}
        cads = [a for a in ads if a['adset_id'] in sids and a.get('status') not in ('DELETED', 'ARCHIVED')]
        cads = [a for a in cads if a.get('status') == 'ACTIVE'] or cads
        creative, n_ads = creative_label(cads)
        if c.get('daily_budget'):
            budget = int(c['daily_budget'])
        else:
            budget = sum(int(s.get('daily_budget') or 0) for s in live_sets) or None
        caps = [int(s['daily_spend_cap']) for s in live_sets if s.get('daily_spend_cap')]
        note = ''
        if caps and len(caps) == len(live_sets) and len(set(caps)) == 1:
            note = f"{caps[0] / 1000:g}천×{len(caps)}"
        uniq = lambda xs: list(dict.fromkeys(xs))  # noqa: E731
        out[c['id']] = {
            'key': key, 'platform': 'meta', 'id': c['id'], 'name': name, 'short': short_name(name, key),
            'status': c.get('effective_status') or c.get('status'),
            'settings': {
                'creative': creative, 'n_ads': n_ads,
                'target': ' / '.join(uniq(target_label(s.get('targeting')) for s in live_sets)) or '-',
                'optimization': ' / '.join(uniq(opt_label(s, ccs) for s in live_sets)) or '-',
                'daily_budget': budget, 'budget_note': note,
                'start': (c.get('start_time') or '')[:10] or None,
                'stop': (c.get('stop_time') or '')[:10] or None,
            },
            'daily': {},
        }
    for r in rows:
        c = out.get(r['campaign_id'])
        if not c:
            continue
        a = meta_actions(r)
        cc_key = f'offsite_conversion.custom.{CC_BODY_PURCHASE}'
        if cc_key in a:
            purchase, src = a[cc_key], 'body_cc'
        elif a.get('purchase'):
            purchase, src = a['purchase'], 'purchase'   # 본체 구매 CC 없음 → purchase 사용, 대조 필요
        else:
            purchase, src = 0, 'body_cc'
        c['daily'][r['date_start']] = {
            'spend': round(float(r.get('spend', 0))),
            'lpv': int(a.get('landing_page_view', 0)),
            'deep_meta': int(a.get(f'offsite_conversion.custom.{CC_DEEP_V2}', 0)),
            'purchase': int(purchase),
            'purchase_src': src,
        }
    log(f'  Meta: 캠페인 {len(out)}개, 일별 행 {len(rows)}, 계정 지출 {acct_spend:,.0f}')
    return out


# ───────────────────────── 네이버 ─────────────────────────
def collect_naver():
    sys.path.insert(0, str(PIPE))
    import collect_naver as nv  # noqa: E402  (서명·키체인 방식 재사용)
    lk, sec, cid = nv.get_credentials()
    SECRETS.extend([lk, sec])

    def get(path, params=None):
        def once():
            ts = str(int(time.time() * 1000))
            h = {'X-Timestamp': ts, 'X-API-KEY': lk, 'X-Customer': cid,
                 'X-Signature': nv.make_signature(sec, ts, 'GET', path)}
            url = nv.API_BASE + path + ('?' + urllib.parse.urlencode(params) if params else '')
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                raise RuntimeError(f'Naver HTTP {e.code} {path}: {e.read().decode(errors="replace")[:200]}') from None
        return retry(once, f'Naver {path}')

    camps = {c['nccCampaignId']: c for c in get('/ncc/campaigns')}
    if not camps:
        raise RuntimeError('네이버 캠페인 0개')
    groups = []
    for cid_ in camps:
        groups += get('/ncc/adgroups', {'nccCampaignId': cid_})
    out, kw_map = {}, {}
    for g in groups:
        gid = g['nccAdgroupId']
        st = get('/stats', {'id': gid, 'fields': '["impCnt","clkCnt","salesAmt"]',
                            'timeRange': json.dumps({'since': DATA_SINCE, 'until': TODAY}), 'timeIncrement': '1'})
        daily = {}
        for d in st.get('data', []):
            if d.get('salesAmt') or d.get('clkCnt'):
                daily[d['dateStart']] = {'spend': round(d.get('salesAmt', 0)), 'lpv': int(d.get('clkCnt', 0))}
        camp = camps.get(g['nccCampaignId'], {})
        live = (g.get('status') == 'ELIGIBLE' and camp.get('status') == 'ELIGIBLE'
                and not g.get('userLock') and not camp.get('userLock'))
        if not daily and not live:
            continue
        kws = get('/ncc/keywords', {'nccAdgroupId': gid}) if camp.get('campaignTp') == 'WEB_SITE' else []
        kw_names = [k.get('keyword', '') for k in kws if not k.get('userLock')]
        for k in kw_names:
            kw_map.setdefault(k.replace(' ', '').lower(), gid)
        nonbrand = '비브랜드' in g.get('name', '')
        key = 'CMP-011' if nonbrand else 'NV-' + gid[-6:]
        budget = g.get('dailyBudget') if g.get('useDailyBudget') else camp.get('dailyBudget')
        reg = g.get('regTm')
        start = (dt.datetime.fromisoformat(reg.replace('Z', '+00:00')).astimezone(KST).date().isoformat() if reg else None)
        shopping = camp.get('campaignTp') == 'SHOPPING'
        out[gid] = {
            'key': key, 'platform': 'naver', 'id': gid, 'campaign_id': g['nccCampaignId'],
            'name': f"{camp.get('name', '')} · {g.get('name', '')}", 'short': f"네이버 · {g.get('name', '')}",
            'status': 'ACTIVE' if live else 'PAUSED',
            'settings': {
                'creative': '쇼핑 상품' if shopping else '검색 문구', 'n_ads': None,
                'target': (f"검색어 {len(kw_names)}개 ({', '.join(kw_names[:3])}{'…' if len(kw_names) > 3 else ''})"
                           if kw_names else ('쇼핑 검색' if shopping else '검색어')),
                'optimization': '클릭 (검색 광고)', 'daily_budget': budget or None, 'budget_note': '',
                'start': start, 'stop': None,
            },
            'daily': daily,
            'nonbrand': nonbrand,
        }
    log(f"  네이버: 광고그룹 {len(out)}개, 키워드 {len(kw_map)}개")
    return out, kw_map


# ───────────────────────── GA4 ─────────────────────────
def page_kind(path):
    p = (path or '').split('?')[0]
    if re.match(r'^/feel/?$', p):
        return 'feel'
    if p.startswith('/community'):
        return 'community'
    if p.startswith('/shop_payment'):
        return 'checkout'
    if p.startswith('/shop_view'):
        return 'detail_90s'
    if p.startswith('/funding'):
        return 'detail_or_revisit'   # GA4에 kind 파라미터 차원이 없어 /funding의 상세90초·재방문은 구분 불가
    return 'other'


def collect_ga4():
    sys.path.insert(0, str(PIPE))
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(Path.home() / '.openclaw/credentials/ga4_service_account.json')
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (DateRange, Dimension, Filter, FilterExpression, Metric,
                                                    RunReportRequest)
    from ga4_bot_filter import bot_excluded_filter, combine_filters
    c = BetaAnalyticsDataClient()
    ev = FilterExpression(filter=Filter(field_name='eventName', string_filter=Filter.StringFilter(value='rf_deep_interest')))
    naver_cpc = FilterExpression(filter=Filter(field_name='sessionSourceMedium',
                                               string_filter=Filter.StringFilter(value='naver / cpc')))

    # GA4 한도: 요청당 차원 9개(봇 필터 차원 country·screenResolution·sessionSource·sessionSourceMedium·eventName 포함)
    # → Meta용(캠페인명)과 네이버용(utm_content·검색어) 두 번에 나눠 조회
    def run(dims, flt):
        req = RunReportRequest(property='properties/419577751', date_ranges=[DateRange(start_date=DEEP_SINCE, end_date=TODAY)],
                               dimensions=[Dimension(name=d) for d in dims], metrics=[Metric(name='eventCount')],
                               dimension_filter=flt, limit=100000)
        r = retry(lambda: c.run_report(req), 'GA4 rf_deep_interest')
        return [([d.value for d in x.dimension_values], int(x.metric_values[0].value)) for x in r.rows]

    def ymd(d):
        return f'{d[:4]}-{d[4:6]}-{d[6:]}'

    rows = []
    for v, n in run(['date', 'sessionSourceMedium', 'sessionCampaignName', 'pagePath'],
                    combine_filters(ev, bot_excluded_filter())):
        src, _, med = v[1].partition(' / ')
        if (src, med) == ('naver', 'cpc'):
            continue  # 네이버는 아래 전용 조회로
        rows.append({'date': ymd(v[0]), 'source': src, 'medium': med, 'campaign': v[2],
                     'content': '', 'term': '', 'kind': page_kind(v[3]), 'n': n})
    for v, n in run(['date', 'sessionSourceMedium', 'sessionManualAdContent', 'sessionManualTerm', 'pagePath'],
                    combine_filters(ev, naver_cpc, bot_excluded_filter())):
        rows.append({'date': ymd(v[0]), 'source': 'naver', 'medium': 'cpc', 'campaign': '',
                     'content': v[2], 'term': v[3], 'kind': page_kind(v[4]), 'n': n})
    log(f'  GA4: rf_deep_interest 행 {len(rows)}, 합계 {sum(x["n"] for x in rows)}')
    return rows


# ───────────────────────── 체험 신청 ─────────────────────────
def collect_trials():
    key = keychain('openclaw_supabase_anon_wspn')
    since = (dt.datetime.fromisoformat(DATA_SINCE + 'T00:00:00+09:00')).astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    url = ('https://ssidizurrvnfmqbvfsqr.supabase.co/rest/v1/feel_bookings?select=created_at,status,cancel_reason,'
           f'utm_source,utm_medium,utm_campaign,utm_content,utm_term&created_at=gte.{since}&order=created_at.asc&limit=5000')
    req = urllib.request.Request(url, headers={'apikey': key, 'Authorization': 'Bearer ' + key})
    rows = retry(lambda: json.load(urllib.request.urlopen(req, timeout=60)), 'Supabase feel_bookings')
    out = []
    for b in rows:
        # 취소·중복은 신청으로 세지 않는다
        if b.get('status') == 'cancelled' or b.get('cancel_reason') == 'duplicate':
            continue
        d = dt.datetime.fromisoformat(b['created_at'].replace('Z', '+00:00')).astimezone(KST).date().isoformat()
        out.append({'date': d, **{k: b.get(k) for k in ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term')}})
    log(f'  체험 신청: {len(out)}건 (취소·중복 제외, {DATA_SINCE}~)')
    return out


# ───────────────────────── 아임웹 실판매 ─────────────────────────
def is_cancel(status):
    return any(w in (status or '') for w in ('취소', '반품', '환불'))


def body_units_from_items(items):
    n = 0
    for i in items or []:
        nm = i.get('name', '')
        if '룸핏' in nm and ('웨이트 머신' in nm or (i.get('price') or 0) >= 1_000_000):
            n += int(i.get('qty') or 1)
    return n


def collect_sales():
    """아임웹 정본: imweb_body_sales.json(~2026-03) + imweb_orders.json(2026-04~, 매일 03:30 갱신)
    + 주문 알림 크롤링 캐시(orders_cache.json, 당일 신규). 1,000원 이하 테스트·예약금(≤3만)·취소/반품/환불 제외."""
    sales = {}
    seen = set()

    def add(date, n, order_no):
        if order_no:
            if order_no in seen:
                return
            seen.add(order_no)
        if date >= DATA_SINCE and n > 0:
            sales[date] = sales.get(date, 0) + n

    bs = json.loads((PIPE / 'data' / 'imweb_body_sales.json').read_text())
    for o in bs['body_sales'].get('completed', []):
        if not o.get('internal') and (o.get('total_paid') or 0) > 30000:
            add(o['date'], 1, o.get('order_no'))
    io = json.loads((PIPE / 'data' / 'imweb_orders.json').read_text())
    for o in io.get('orders', []):
        if is_cancel(o.get('status')) or (o.get('payment') or {}).get('total', 0) <= 30000:
            continue
        add(o['order_date'][:10], int((o.get('classification') or {}).get('body_units') or 0), o['order_no'])
    cache = Path.home() / '.openclaw/workspace/synapse-search/finance/data/orders_cache.json'
    cache_note = 'none'
    if cache.exists():
        cj = json.loads(cache.read_text())
        cache_note = cj.get('crawled_at', '')
        for o in cj.get('orders', []):
            if is_cancel(o.get('status')) or (o.get('payment') or {}).get('total', 0) <= 30000:
                continue
            add(o['order_date'][:10], body_units_from_items(o.get('items')), o['order_no'])
    log(f'  아임웹 실판매: {sum(sales.values())}대 ({DATA_SINCE}~), orders.json {io.get("updated_at", "")[:16]}, 캐시 {cache_note[:16]}')
    return sales, {'imweb_orders_updated': io.get('updated_at'), 'orders_cache_crawled': cache_note}


# ───────────────────────── Clarity ─────────────────────────
def collect_clarity():
    """collect_clarity.py(am/pm, 하루 10회 한도)가 쌓은 파일에서 캠페인별 활성 시간을 읽는다.
    API를 여기서 추가 호출하지 않는다. 수집 시점 날짜로 기록(최근 1일 = 수집 시각 기준 24시간)."""
    files = sorted(glob.glob(str(PIPE / 'data' / 'clarity' / '2026-*_*.json')) +
                   glob.glob(str(WS / 'state' / 'evidence' / '2026-09-3*-ad-quality-*' / 'clarity_*.json')))
    best = {}
    for f in files:
        try:
            d = json.loads(Path(f).read_text())
        except Exception:  # noqa: BLE001
            continue
        res = (d.get('results') or {}).get('campaign')
        if not isinstance(res, list) or str(d.get('numOfDays', '1')) != '1':
            continue
        at = d.get('collected_at', '')
        date = at[:10]
        if date and (date not in best or at > best[date][0]):
            best[date] = (at, res)
    out = {}
    for date, (at, res) in best.items():
        by = {m.get('metricName'): m.get('information', []) for m in res}
        sess = {}
        for x in by.get('Traffic', []):
            sess[(x.get('Source'), x.get('Medium'), x.get('Campaign'))] = int(x.get('totalSessionCount') or 0)
        agg = {}
        for x in by.get('EngagementTime', []):
            camp = x.get('Campaign')
            if not camp:
                continue
            n = sess.get((x.get('Source'), x.get('Medium'), camp), 0) or 0
            a = agg.setdefault(camp, [0.0, 0])
            a[0] += float(x.get('activeTime') or 0) * max(n, 1)
            a[1] += max(n, 1)
        out[date] = {camp: {'sec': round(t / n), 'sessions': n, 'collected_at': at} for camp, (t, n) in agg.items() if n}
    log(f'  Clarity: 날짜 {sorted(out)}')
    return out


# ───────────────────────── 조립 ─────────────────────────
EMPTY_DEEP = lambda: {'total': 0, 'feel': 0, 'checkout': 0, 'detail_90s': 0, 'community': 0,  # noqa: E731
                      'revisit': 0, 'detail_or_revisit': 0, 'other': 0}


def main():
    deploy = '--no-deploy' not in sys.argv
    log(f'캠페인 비교 빌드 시작 (오늘 {TODAY})')
    prev = json.loads(OUT.read_text()) if OUT.exists() else {}
    prev_c = {c['key'] + '|' + c['id']: c for c in prev.get('campaigns', [])}
    sources = {}

    try:
        meta = collect_meta()
        sources['meta'] = {'ok': True}
    except Exception as e:  # noqa: BLE001
        log('❌ Meta 수집 실패 → 기존 json 유지, 종료: ' + scrub(e))
        log(scrub(traceback.format_exc())[-1500:])
        return 1

    def attempt(name, fn, default):
        try:
            v = fn()
            sources[name] = {'ok': True}
            return v, True
        except Exception as e:  # noqa: BLE001
            log(f'⚠️ {name} 수집 실패 → 기존 값 유지: {scrub(e)[:300]}')
            sources[name] = {'ok': False, 'error': scrub(e)[:300], 'at': NOW.isoformat(timespec='seconds')}
            return default, False

    (naver, kw_map), naver_ok = attempt('naver', collect_naver, ({}, {}))
    ga_rows, ga_ok = attempt('ga4', collect_ga4, [])
    trials, tr_ok = attempt('trials', collect_trials, [])
    (sales, sales_meta), sales_ok = attempt('imweb', collect_sales, ({}, {}))
    clarity, cl_ok = attempt('clarity', collect_clarity, {})

    camps = list(meta.values())
    if naver_ok:
        camps += list(naver.values())
    else:  # 네이버 실패 → 이전 네이버 행 그대로
        camps += [c for c in prev.get('campaigns', []) if c['platform'] == 'naver']
    by_meta_id = {c['id']: c for c in camps if c['platform'] == 'meta'}
    by_key = {c['key']: c for c in camps}
    naver_rows = [c for c in camps if c['platform'] == 'naver']
    naver_nonbrand = next((c for c in naver_rows if c['key'] == 'CMP-011'), None)
    naver_unknown = {'key': 'NV-UNMAPPED', 'platform': 'naver', 'id': 'naver-unmapped', 'name': '네이버 검색광고 · 광고그룹 미확인',
                     'short': '네이버 · 광고그룹 미확인', 'status': 'ACTIVE',
                     'settings': {'creative': '검색 문구', 'n_ads': None, 'target': '검색어 (키워드 매칭 실패분)',
                                  'optimization': '클릭 (검색 광고)', 'daily_budget': None, 'budget_note': '', 'start': None, 'stop': None},
                     'daily': {}}
    naver_by_gid = {c['id']: c for c in naver_rows}
    naver_campaign_ids = {c.get('campaign_id') for c in naver_rows}

    def resolve(source, medium, campaign, content, term):
        source, medium = (source or '').lower(), (medium or '').lower()
        campaign = campaign or ''
        if campaign in by_meta_id:
            return by_meta_id[campaign]
        km = re.fullmatch(r'CMP-\d+', campaign.strip())
        if km and km.group(0) in by_key and by_key[km.group(0)]['platform'] == 'meta':
            return by_key[km.group(0)]
        if (source == 'naver' and medium == 'cpc') or campaign in naver_campaign_ids:
            if content == NAVER_NONBRAND_CONTENT and naver_nonbrand:
                return naver_nonbrand
            gid = kw_map.get((term or '').replace(' ', '').lower())
            if gid and gid in naver_by_gid:
                return naver_by_gid[gid]
            return naver_unknown
        return None

    def day(c, d):
        return c['daily'].setdefault(d, {'spend': 0, 'lpv': 0})

    # GA4 깊은 관심
    unmatched_deep = 0
    if ga_ok:
        for r in ga_rows:
            c = resolve(r['source'], r['medium'], r['campaign'], r['content'], r['term'])
            if not c:
                unmatched_deep += r['n']
                continue
            dd = day(c, r['date']).setdefault('deep', EMPTY_DEEP())
            dd['total'] += r['n']
            dd[r['kind']] += r['n']
    # 체험 신청
    account = {}
    for d in daterange(DATA_SINCE, TODAY):
        account[d] = {'imweb_body_sales': 0, 'trial_bookings': 0}
    if tr_ok:
        for t in trials:
            account.setdefault(t['date'], {'imweb_body_sales': 0, 'trial_bookings': 0})['trial_bookings'] += 1
            if t.get('utm_campaign'):
                c = resolve(t.get('utm_source'), t.get('utm_medium'), t['utm_campaign'], t.get('utm_content'), t.get('utm_term'))
                if c:
                    day(c, t['date'])['trial'] = day(c, t['date']).get('trial', 0) + 1
    if sales_ok:
        for d, n in sales.items():
            account.setdefault(d, {'imweb_body_sales': 0, 'trial_bookings': 0})['imweb_body_sales'] = n
    prev_acc = prev.get('account_daily', {})
    if not tr_ok or not sales_ok:
        for d, v in account.items():
            p = prev_acc.get(d, {})
            if not tr_ok:
                v['trial_bookings'] = p.get('trial_bookings', 0)
            if not sales_ok:
                v['imweb_body_sales'] = p.get('imweb_body_sales', 0)

    if any(d.get('deep') for d in naver_unknown['daily'].values()) or naver_unknown['daily']:
        camps.append(naver_unknown)

    # 날짜별 정리 + 이전 값 유지 규칙
    for c in camps:
        pc = prev_c.get(c['key'] + '|' + c['id'], {})
        pdaily = pc.get('daily', {})
        dates = set(c['daily']) | {d for d in pdaily}
        for d in sorted(dates):
            v = c['daily'].setdefault(d, {'spend': 0, 'lpv': 0})
            pv = pdaily.get(d, {})
            v.setdefault('spend', 0)
            v.setdefault('lpv', 0)
            if c['platform'] == 'meta':
                v.setdefault('deep_meta', 0)
                v.setdefault('purchase', 0)
            if d >= DEEP_SINCE:
                if not ga_ok:
                    v['deep'] = pv.get('deep')
                else:
                    v.setdefault('deep', EMPTY_DEEP())
            else:
                v['deep'] = None  # 측정 전
            if not tr_ok:
                v['trial'] = pv.get('trial', 0)
            v.setdefault('trial', 0)
            # Clarity: 과거 값은 덮어쓰지 않는다(오늘 값만 최신 수집으로 갱신)
            old = pv.get('clarity_active_sec')
            new = None
            if c['platform'] == 'meta':
                cd = clarity.get(d, {})
                hit = cd.get(c['id']) or cd.get(c['key'])
                if hit:
                    new = hit
            if old is not None and d < TODAY:
                v['clarity_active_sec'] = old
                v['clarity_sessions'] = pv.get('clarity_sessions')
            elif new:
                v['clarity_active_sec'] = new['sec']
                v['clarity_sessions'] = new['sessions']
            else:
                v['clarity_active_sec'] = old
                v['clarity_sessions'] = pv.get('clarity_sessions')
            v['ga4_final'] = d < TODAY
        c['daily'] = dict(sorted(c['daily'].items()))

    def total_spend(c):
        return sum(v.get('spend', 0) for v in c['daily'].values())
    camps.sort(key=lambda c: (c['platform'] != 'meta', c['key']))
    out = {
        'updated_at': dt.datetime.now(KST).isoformat(timespec='seconds'),
        'today': TODAY,
        'data_since': DATA_SINCE,
        'deep_interest_since': DEEP_SINCE,
        'sources': sources,
        'notes': {
            'deep': 'GA4 rf_deep_interest(봇 필터 적용). 종류는 이벤트 발생 페이지로 구분 — GA4에 kind 파라미터 맞춤 차원이 없어 '
                    '/funding의 상세 90초·재방문은 합쳐서 표시.',
            'deep_unmatched_events': unmatched_deep,
            'visit': 'Meta = 랜딩 페이지 조회, 네이버 = 클릭',
            'clarity': 'Clarity 최근 1일(수집 시각 기준 24시간) 캠페인별 평균 활성 시간. am/pm 수집 파일 중 그날 마지막 값.',
            'sales': '아임웹 정본(imweb_orders.json + 주문 알림 캐시). 취소·반품·환불·3만 원 이하 제외.',
            'sales_meta': sales_meta if sales_ok else prev.get('notes', {}).get('sales_meta'),
            'trial': 'Supabase feel_bookings. 취소·중복 제외. utm_campaign이 있는 건만 캠페인에 붙임.',
        },
        'campaigns': [c for c in camps if c['daily'] or c['status'] == 'ACTIVE' or total_spend(c) > 0 or c['platform'] == 'meta'],
        'account_daily': dict(sorted(account.items())),
    }
    for c in out['campaigns']:
        c.pop('nonbrand', None)
    tmp = OUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')))
    os.replace(tmp, OUT)
    log(f"✅ json 갱신: 캠페인 {len(out['campaigns'])}개, updated_at {out['updated_at']}, 소스 {{{', '.join(f'{k}:{"ok" if v["ok"] else "FAIL"}' for k, v in sources.items())}}}")

    if deploy:
        log('배포: scripts/deploy_pages.sh')
        p = subprocess.run([str(ROOT / 'scripts' / 'deploy_pages.sh')], cwd=str(ROOT), capture_output=True, text=True)
        tail = scrub((p.stdout + p.stderr)[-800:])
        if p.returncode != 0:
            log(f'❌ 배포 실패 (exit {p.returncode}): {tail}')
            return 2
        m = re.search(r'https://\S+\.pages\.dev', p.stdout)
        log(f"✅ 배포 완료 {m.group(0) if m else ''}")
    return 0 if all(v['ok'] for v in sources.values()) else 3


if __name__ == '__main__':
    sys.exit(main())
