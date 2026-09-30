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
CC_VIEW = '2306085919929012'        # 상세·체험 페이지 조회 (ViewContent + /feel)
CC_TRIAL_V2 = '1074629242220862'    # 체험 결제 v2 (TrialPurchase)
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


def first_action(lst):
    """video_*_actions 필드: [{'action_type':'video_view','value':'123'}] → 123.0"""
    for a in lst or []:
        if a.get('action_type') == 'video_view':
            return float(a.get('value') or 0)
    return 0.0


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
               fields='campaign_id,campaign_name,spend,actions,date_start,impressions,reach,inline_link_clicks,'
                      'video_play_actions,video_thruplay_watched_actions,video_avg_time_watched_actions')
    ad_rows = m.q(f'{m.act}/insights', level='ad', time_range=tr, time_increment=1, limit=500,
                  fields='ad_id,ad_name,campaign_id,spend,impressions,actions,date_start')
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
        plays = first_action(r.get('video_play_actions'))
        c['daily'][r['date_start']] = {
            'spend': round(float(r.get('spend', 0))),
            'lpv': int(a.get('landing_page_view', 0)),
            'deep_meta': int(a.get(f'offsite_conversion.custom.{CC_DEEP_V2}', 0)),
            'purchase': int(purchase),
            'purchase_src': src,
            # 상세 지표 (Meta 노출·소재 반응 / 전환 신호)
            'impr': int(r.get('impressions') or 0),
            'reach': int(r.get('reach') or 0),                  # 일별 도달 (기간 합산 시 중복 포함)
            'link_clicks': int(r.get('inline_link_clicks') or 0),
            'v3s': int(a.get('video_view', 0)),                 # 영상 3초 조회
            'thruplay': int(first_action(r.get('video_thruplay_watched_actions'))),
            'plays': int(plays),
            'watch_sec_total': round(first_action(r.get('video_avg_time_watched_actions')) * plays),
            'saves': int(a.get('onsite_conversion.post_save', 0)),
            'shares': int(a.get('post', 0)),
            'comments': int(a.get('comment', 0)),
            'cc_view': int(a.get(f'offsite_conversion.custom.{CC_VIEW}', 0)),
            'initiate_checkout': int(a.get('offsite_conversion.fb_pixel_initiate_checkout', 0)),
            'trial_purchase_meta': int(a.get(f'offsite_conversion.custom.{CC_TRIAL_V2}', 0)),
        }
    ad_names = {}
    for r in ad_rows:
        c = out.get(r['campaign_id'])
        if not c:
            continue
        a = meta_actions(r)
        ad = c.setdefault('ads', {}).setdefault(r['ad_id'], {'name': r.get('ad_name', ''), 'daily': {}})
        ad['daily'][r['date_start']] = {'spend': round(float(r.get('spend', 0))), 'impr': int(r.get('impressions') or 0),
                                        'v3s': int(a.get('video_view', 0)), 'lpv': int(a.get('landing_page_view', 0)),
                                        'deep_meta': int(a.get(f'offsite_conversion.custom.{CC_DEEP_V2}', 0))}
        ad_names[r['ad_id']] = r['campaign_id']
    log(f'  Meta: 캠페인 {len(out)}개, 일별 행 {len(rows)}, 광고 {len(ad_names)}개, 계정 지출 {acct_spend:,.0f}')
    return out


# ───────────────────────── 네이버 ─────────────────────────
def collect_naver(prev_campaigns=()):
    prev_kw = {c['id']: {d: v.get('kw') for d, v in c.get('daily', {}).items() if v.get('kw') is not None}
               for c in prev_campaigns if c.get('platform') == 'naver'}
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
        st = get('/stats', {'id': gid, 'fields': '["impCnt","clkCnt","salesAmt","avgRnk"]',
                            'timeRange': json.dumps({'since': DATA_SINCE, 'until': TODAY}), 'timeIncrement': '1'})
        daily = {}
        for d in st.get('data', []):
            if d.get('salesAmt') or d.get('clkCnt') or d.get('impCnt'):
                daily[d['dateStart']] = {'spend': round(d.get('salesAmt', 0)), 'lpv': int(d.get('clkCnt', 0)),
                                         'impr': int(d.get('impCnt', 0)),
                                         'rank_x_impr': round(float(d.get('avgRnk') or 0) * int(d.get('impCnt', 0)), 1)}
        camp = camps.get(g['nccCampaignId'], {})
        live = (g.get('status') == 'ELIGIBLE' and camp.get('status') == 'ELIGIBLE'
                and not g.get('userLock') and not camp.get('userLock'))
        if not any(v['spend'] for v in daily.values()) and not live:
            continue
        kws = get('/ncc/keywords', {'nccAdgroupId': gid}) if camp.get('campaignTp') == 'WEB_SITE' else []
        kw_names = [k.get('keyword', '') for k in kws if not k.get('userLock')]
        for k in kw_names:
            kw_map.setdefault(k.replace(' ', '').lower(), gid)
        # 키워드별 일별 성과(행 펼침 상위 5개용): ids+timeIncrement 조합은 API 미지원 → 하루씩 조회.
        # 최근 3일은 매번 다시 받고, 그 이전 날짜는 이전 json 값을 재사용한다.
        kw_text = {k['nccKeywordId']: k.get('keyword', '') for k in kws}
        pk = prev_kw.get(gid, {})
        for d in daterange(DATA_SINCE, TODAY):
            if d not in daily:
                continue
            if d < (NOW.date() - dt.timedelta(days=3)).isoformat() and d in pk:
                daily[d]['kw'] = pk[d]
                continue
            kwd = {}
            ids = list(kw_text)
            for i in range(0, len(ids), 100):
                r = get('/stats', {'ids': ','.join(ids[i:i + 100]), 'fields': '["impCnt","clkCnt","salesAmt"]',
                                   'timeRange': json.dumps({'since': d, 'until': d})})
                for x in r.get('data', []):
                    if x.get('impCnt') or x.get('clkCnt'):
                        kwd[kw_text.get(x['id'], x['id'])] = [int(x.get('impCnt', 0)), int(x.get('clkCnt', 0)), round(x.get('salesAmt', 0))]
            daily[d]['kw'] = kwd
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


BRIDGE_EVENTS = ['section_view', 'embed_scroll_depth', 'embed_engaged', 'detail_rescroll']


def classify_channel(source, medium):
    """유입 채널 분류 — 규칙은 이 함수 한 곳에만 둔다(화면 툴팁은 CHANNEL_RULES 문구)."""
    s, m = (source or '').lower().strip(), (medium or '').lower().strip()
    if m in ('paid', 'paid_social', 'cpc', 'cpm', 'ppc', 'display', 'ad', 'ads', 'paidsocial'):
        return 'ads'
    if 'instagram' in s or s == 'ig':
        return 'ig'
    if 'youtube' in s or s == 'youtu.be':
        return 'youtube'
    if 'blog.naver' in s or 'cafe.naver' in s:
        return 'naver_blog'
    if (s == 'naver' and m == 'organic') or 'search.naver' in s:
        return 'naver_search'
    if s == 'google' and m == 'organic':
        return 'google'
    if s == '(direct)' and m in ('(none)', ''):
        return 'direct'
    return 'other'


CHANNELS = [('ig', '인스타 오가닉'), ('naver_search', '네이버 자연검색'), ('naver_blog', '네이버 블로그·카페'),
            ('google', '구글 검색'), ('youtube', '유튜브'), ('direct', '직접 방문'), ('other', '기타'),
            ('ads', '유료 광고 합계')]
CHANNEL_RULES = ('GA4 sessionSource/sessionMedium 기준(봇 제외). 유료 광고 = medium이 paid·paid_social·cpc 등 '
                 '(위 캠페인 행 합계, 캠페인 미매칭 포함) · 인스타 오가닉 = source에 instagram 또는 ig(광고 제외, '
                 'roomfit.kr/link 프로필 링크 포함) · 네이버 자연검색 = naver/organic 또는 search.naver 참조 · '
                 '네이버 블로그·카페 = blog.naver·cafe.naver 참조 · 구글 검색 = google/organic · '
                 '유튜브 = source에 youtube(roomfit.kr/link-yt 포함) · 직접 방문 = (direct)/(none) · 기타 = 나머지')


def collect_ga4():
    """GA4(봇 필터) 조회 묶음. 요청당 차원 9개 한도(봇 필터 차원 country·screenResolution·sessionSource·
    sessionSourceMedium 포함) 때문에 Meta용(캠페인명)과 네이버용(utm_content·검색어)으로 나눠 조회한다."""
    sys.path.insert(0, str(PIPE))
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(Path.home() / '.openclaw/credentials/ga4_service_account.json')
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (DateRange, Dimension, Filter, FilterExpression, Metric,
                                                    RunReportRequest)
    from ga4_bot_filter import bot_excluded_filter, combine_filters
    c = BetaAnalyticsDataClient()
    ev = FilterExpression(filter=Filter(field_name='eventName', string_filter=Filter.StringFilter(value='rf_deep_interest')))
    bridge = FilterExpression(filter=Filter(field_name='eventName', in_list_filter=Filter.InListFilter(values=BRIDGE_EVENTS)))
    naver_cpc = FilterExpression(filter=Filter(field_name='sessionSourceMedium',
                                               string_filter=Filter.StringFilter(value='naver / cpc')))

    def run(dims, mets, flt, since=DEEP_SINCE, what='GA4'):
        req = RunReportRequest(property='properties/419577751', date_ranges=[DateRange(start_date=since, end_date=TODAY)],
                               dimensions=[Dimension(name=d) for d in dims], metrics=[Metric(name=m) for m in mets],
                               dimension_filter=flt, limit=250000)
        r = retry(lambda: c.run_report(req), what)
        if r.row_count > len(r.rows):
            raise RuntimeError(f'{what}: 행 잘림 {len(r.rows)}/{r.row_count}')
        return [([d.value for d in x.dimension_values], [float(m.value) for m in x.metric_values]) for x in r.rows]

    def ymd(d):
        return f'{d[:4]}-{d[4:6]}-{d[6:]}'

    def sm(v):
        src, _, med = v.partition(' / ')
        return src, med

    bot = bot_excluded_filter()
    out = {'deep': [], 'sessions': [], 'bridge': [], 'ad_deep': [], 'total': {}}
    # 1) 깊은 관심 — Meta·채널용(네이버 광고 제외) / 네이버 광고용
    for v, m in run(['date', 'sessionSourceMedium', 'sessionCampaignName', 'pagePath'], ['eventCount'],
                    combine_filters(ev, bot), what='GA4 깊은 관심'):
        src, med = sm(v[1])
        if (src, med) == ('naver', 'cpc'):
            continue
        out['deep'].append({'date': ymd(v[0]), 'source': src, 'medium': med, 'campaign': v[2], 'content': '', 'term': '',
                            'kind': page_kind(v[3]), 'n': int(m[0])})
    for v, m in run(['date', 'sessionSourceMedium', 'sessionManualAdContent', 'sessionManualTerm', 'pagePath'], ['eventCount'],
                    combine_filters(ev, naver_cpc, bot), what='GA4 깊은 관심(네이버)'):
        out['deep'].append({'date': ymd(v[0]), 'source': 'naver', 'medium': 'cpc', 'campaign': '', 'content': v[2],
                            'term': v[3], 'kind': page_kind(v[4]), 'n': int(m[0])})
    # 2) 세션 품질 — 9/1부터 (채널 행·100명당·도착 품질)
    smets = ['sessions', 'engagedSessions', 'userEngagementDuration', 'screenPageViews']
    for v, m in run(['date', 'sessionSourceMedium', 'sessionCampaignName'], smets, bot, since=DATA_SINCE, what='GA4 세션'):
        src, med = sm(v[1])
        out['sessions'].append({'date': ymd(v[0]), 'source': src, 'medium': med, 'campaign': v[2], 'content': '', 'term': '',
                                'naver_split': False, 'm': m})
    for v, m in run(['date', 'sessionSourceMedium', 'sessionManualAdContent', 'sessionManualTerm'], smets,
                    combine_filters(naver_cpc, bot), since=DATA_SINCE, what='GA4 세션(네이버)'):
        out['sessions'].append({'date': ymd(v[0]), 'source': 'naver', 'medium': 'cpc', 'campaign': '', 'content': v[2],
                                'term': v[3], 'naver_split': True, 'm': m})
    # 3) 사이트 안 깊이 — 브리지 이벤트
    for v, m in run(['date', 'sessionSourceMedium', 'sessionCampaignName', 'eventName'], ['eventCount'],
                    combine_filters(bridge, bot), since=DATA_SINCE, what='GA4 브리지 이벤트'):
        src, med = sm(v[1])
        if (src, med) == ('naver', 'cpc'):
            continue
        out['bridge'].append({'date': ymd(v[0]), 'source': src, 'medium': med, 'campaign': v[2], 'content': '', 'term': '',
                              'event': v[3], 'n': int(m[0])})
    for v, m in run(['date', 'sessionSourceMedium', 'sessionManualAdContent', 'sessionManualTerm', 'eventName'], ['eventCount'],
                    combine_filters(bridge, naver_cpc, bot), since=DATA_SINCE, what='GA4 브리지 이벤트(네이버)'):
        out['bridge'].append({'date': ymd(v[0]), 'source': 'naver', 'medium': 'cpc', 'campaign': '', 'content': v[2],
                              'term': v[3], 'event': v[4], 'n': int(m[0])})
    # 4) 광고(소재)별 깊은 관심 — utm_content = Meta 광고 id
    for v, m in run(['date', 'sessionCampaignName', 'sessionManualAdContent'], ['eventCount'], combine_filters(ev, bot),
                    what='GA4 광고별 깊은 관심'):
        out['ad_deep'].append({'date': ymd(v[0]), 'campaign': v[1], 'ad': v[2], 'n': int(m[0])})
    # 5) 전체 세션(검증용: 채널 행 합계 대조)
    for v, m in run(['date'], ['sessions'], bot, since=DATA_SINCE, what='GA4 전체 세션'):
        out['total'][ymd(v[0])] = int(m[0])
    log(f"  GA4: 깊은 관심 {sum(x['n'] for x in out['deep'])}건, 세션 행 {len(out['sessions'])}, "
        f"브리지 {sum(x['n'] for x in out['bridge'])}건, 전체 세션 {sum(out['total'].values())}")
    return out


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
def clarity_url_class(url):
    p = urllib.parse.urlparse(url or '').path.lower()
    if re.match(r'^/(shop_view|funding|shop_payment|buy)', p):
        return 'buy'
    if p.startswith('/feel'):
        return 'feel'
    if p.startswith('/community'):
        return 'community'
    if p in ('', '/', '/main', '/index'):
        return 'main'
    return 'other'


def collect_clarity():
    """collect_clarity.py(am/pm, 하루 10회 한도)가 쌓은 파일에서 캠페인별 행동 지표를 읽는다.
    API를 여기서 추가 호출하지 않는다. 수집 시점 날짜로 기록(최근 1일 = 수집 시각 기준 24시간)."""
    files = sorted(glob.glob(str(PIPE / 'data' / 'clarity' / '2026-*_*.json')) +
                   glob.glob(str(WS / 'state' / 'evidence' / '2026-09-3*-ad-quality-*' / 'clarity_*.json')))
    best, best_url = {}, {}
    for f in files:
        try:
            d = json.loads(Path(f).read_text())
        except Exception:  # noqa: BLE001
            continue
        if str(d.get('numOfDays', '1')) != '1':
            continue
        at = d.get('collected_at', '')
        date = at[:10]
        res = (d.get('results') or {}).get('campaign')
        if date and isinstance(res, list) and (date not in best or at > best[date][0]):
            best[date] = (at, res)
        ures = (d.get('results') or {}).get('campaign_url')
        if date and isinstance(ures, list) and (date not in best_url or at > best_url[date][0]):
            best_url[date] = (at, ures)
    out = {}
    for date, (at, res) in best.items():
        by = {m.get('metricName'): m.get('information', []) for m in res}
        sess = {}
        for x in by.get('Traffic', []):
            if x.get('Campaign'):
                sess[(x.get('Source'), x.get('Medium'), x['Campaign'])] = int(x.get('totalSessionCount') or 0)
        agg = {}

        def acc(camp, field, val, w):
            a = agg.setdefault(camp, {})
            s_, w_ = a.get(field, (0.0, 0))
            a[field] = (s_ + float(val or 0) * w, w_ + w)
        for x in by.get('EngagementTime', []):
            if x.get('Campaign'):
                acc(x['Campaign'], 'sec', x.get('activeTime'), max(sess.get((x.get('Source'), x.get('Medium'), x['Campaign']), 0), 1))
        for x in by.get('ScrollDepth', []):
            if x.get('Campaign'):
                acc(x['Campaign'], 'scroll', x.get('averageScrollDepth'), max(sess.get((x.get('Source'), x.get('Medium'), x['Campaign']), 0), 1))
        for metric, field in (('DeadClickCount', 'dead_pct'), ('RageClickCount', 'rage_pct'), ('QuickbackClick', 'quickback_pct')):
            for x in by.get(metric, []):
                if x.get('Campaign'):
                    acc(x['Campaign'], field, x.get('sessionsWithMetricPercentage'), max(int(x.get('sessionsCount') or 0), 1))
        day = {}
        for camp, a in agg.items():
            n = sum(v for k, v in sess.items() if k[2] == camp)
            rec = {'sessions': n, 'collected_at': at}
            for field, (s_, w_) in a.items():
                rec[field] = round(s_ / w_, 1) if w_ else None
            if rec.get('sec') is not None:
                rec['sec'] = round(rec['sec'])
            day[camp] = rec
        if date in best_url:
            ub = {m.get('metricName'): m.get('information', []) for m in best_url[date][1]}
            for x in ub.get('Traffic', []):
                camp = x.get('Campaign')
                if camp and camp in day:
                    u = day[camp].setdefault('url', {})
                    k = clarity_url_class(x.get('Url'))
                    u[k] = u.get(k, 0) + int(x.get('totalSessionCount') or 0)
        out[date] = day
    log(f'  Clarity: 날짜 {sorted(out)}')
    return out


# ───────────────────────── 오가닉 콘텐츠 ─────────────────────────
IG_HOURS = (6, 12, 18, 23)   # 인스타 API 호출은 하루 4회로 제한
IG_REELS_METRICS = 'views,reach,saved,shares,comments,likes,total_interactions,ig_reels_avg_watch_time'
IG_FEED_METRICS = 'views,reach,saved,shares,comments,likes,total_interactions,profile_visits,follows'
IG_MIN_METRICS = 'views,reach,saved,shares,comments,likes'


def collect_ig(prev_ig, force=False):
    """인스타 게시물·릴스 스냅샷(누적값)을 수집 날짜별로 쌓는다. 06·12·18·23시(또는 첫 실행)에만 API 호출."""
    media = dict((prev_ig or {}).get('media', {}))
    if not force and NOW.hour not in IG_HOURS and media:
        return {'media': media, 'collected_at': (prev_ig or {}).get('collected_at'), 'skipped': True}
    tok = keychain('openclaw_meta_ig_token')
    igid = keychain('openclaw_meta_ig_account_id')

    def g(path, **p):
        p['access_token'] = tok
        url = f'https://graph.facebook.com/v24.0/{path}?' + urllib.parse.urlencode(p)
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'IG HTTP {e.code} {path.split("/")[-1]}: {e.read().decode(errors="replace")[:200]}') from None

    cutoff = (NOW - dt.timedelta(days=90)).astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    fields = 'id,caption,media_type,media_product_type,thumbnail_url,media_url,timestamp,permalink'
    items, url_path, params = [], f'{igid}/media', {'fields': fields, 'limit': 50}
    for _ in range(5):
        r = retry(lambda: g(url_path, **params), 'IG media')
        items += r.get('data', [])
        after = r.get('paging', {}).get('cursors', {}).get('after')
        if not after or not r.get('data') or r['data'][-1]['timestamp'][:19] < cutoff:
            break
        params = {'fields': fields, 'limit': 50, 'after': after}
    if not items:
        raise RuntimeError('IG 게시물 0개 — 빈 결과를 성공으로 보지 않음')
    now_utc = dt.datetime.now(dt.timezone.utc)
    for m in items:
        if m['timestamp'][:19] < cutoff:
            continue
        ts = dt.datetime.strptime(m['timestamp'][:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=dt.timezone.utc)
        reels = m.get('media_product_type') == 'REELS'
        vals = None
        for metrics in ((IG_REELS_METRICS if reels else IG_FEED_METRICS), IG_MIN_METRICS):
            try:
                r = retry(lambda mt=metrics: g(f"{m['id']}/insights", metric=mt), 'IG insights', tries=2)
                vals = {x['name']: (x.get('values') or [{}])[0].get('value') for x in r.get('data', [])}
                break
            except Exception as e:  # noqa: BLE001
                log(f"  IG insights {m['id']} ({metrics.split(',')[-1]}): {scrub(e)[:120]}")
        rec = media.setdefault(m['id'], {'daily': {}})
        rec.update({
            'ts': ts.astimezone(KST).isoformat(timespec='minutes'), 'date': ts.astimezone(KST).date().isoformat(),
            'type': '릴스' if reels else {'CAROUSEL_ALBUM': '캐러셀', 'IMAGE': '이미지', 'VIDEO': '영상'}.get(m.get('media_type'), m.get('media_type')),
            'thumb': m.get('thumbnail_url') or m.get('media_url'), 'permalink': m.get('permalink'),
            'caption': (m.get('caption') or '').replace('\n', ' ')[:80],
        })
        if vals is None:
            continue
        snap = {'views': vals.get('views'), 'reach': vals.get('reach'), 'saved': vals.get('saved'), 'shares': vals.get('shares'),
                'comments': vals.get('comments'), 'likes': vals.get('likes'), 'profile_visits': vals.get('profile_visits'),
                'follows': vals.get('follows'), 'avg_watch_ms': vals.get('ig_reels_avg_watch_time'),
                'at': NOW.isoformat(timespec='minutes')}
        rec['daily'][TODAY] = snap
        age_h = (now_utc - ts).total_seconds() / 3600
        if 'h24' not in rec and 24 <= age_h <= 31:   # 게시 후 24시간 판정용: 24~31시간 사이 첫 수집값
            rec['h24'] = {'views': snap['views'], 'reach': snap['reach'], 'age_h': round(age_h, 1)}
    log(f'  IG: 게시물 {len(items)}개 조회, 최근 90일 {sum(1 for m in media.values() if m.get("date", "") >= cutoff[:10])}개 스냅샷')
    return {'media': media, 'collected_at': NOW.isoformat(timespec='seconds'), 'skipped': False}


def collect_organic_files(prev_org):
    """팔로워(ig_follower_history.json)·유튜브(youtube_full.json)·블로그(blog_*.json) — 기존 수집 파일만 읽는다."""
    data = PIPE / 'data'
    out = {}
    fh = json.loads((data / 'ig_follower_history.json').read_text())
    out['followers'] = [{'date': r['date'], 'followers': r.get('followers'), 'delta': r.get('delta')}
                        for r in fh if r.get('date', '') >= '2026-08-01']
    yt_file = data / 'youtube_full.json'
    yt_prev = (prev_org or {}).get('youtube', {}).get('videos', {})
    snap_date = dt.datetime.fromtimestamp(yt_file.stat().st_mtime, KST).date().isoformat()
    vids = {}
    for v in json.loads(yt_file.read_text()):
        rec = dict(yt_prev.get(v['video_id'], {'daily': {}}))
        rec['daily'] = dict(rec.get('daily', {}))
        rec.update({'title': v.get('title'), 'published': (v.get('published') or '')[:10]})
        rec['daily'][snap_date] = {'views': v.get('views'), 'likes': v.get('likes'), 'comments': v.get('comments')}
        vids[v['video_id']] = rec
    out['youtube'] = {'videos': vids, 'snapshot_date': snap_date}
    blogs = sorted(glob.glob(str(data / 'blog_2026-*.json')))
    posts = []
    if blogs:
        b = json.loads(Path(blogs[-1]).read_text())
        posts = [{'title': p.get('title'), 'date': (p.get('parsed_date') or p.get('date') or '')[:10], 'url': p.get('url')}
                 for p in b.get('all_posts', [])]
    out['blog'] = {'posts': posts, 'source': Path(blogs[-1]).name if blogs else None}
    return out


# ───────────────────────── 조립 ─────────────────────────
EMPTY_DEEP = lambda: {'total': 0, 'feel': 0, 'checkout': 0, 'detail_90s': 0, 'community': 0,  # noqa: E731
                      'revisit': 0, 'detail_or_revisit': 0, 'other': 0}
GA_DAY_FIELDS = ('deep', 'sessions', 'engaged', 'eng_time', 'pv', 'bridge')
CANDIDATE = Path('/tmp/campaign_compare.candidate.json')


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

    (naver, kw_map), naver_ok = attempt('naver', lambda: collect_naver(prev.get('campaigns', [])), ({}, {}))
    ga, ga_ok = attempt('ga4', collect_ga4, {})
    trials, tr_ok = attempt('trials', collect_trials, [])
    (sales, sales_meta), sales_ok = attempt('imweb', collect_sales, ({}, {}))
    clarity, cl_ok = attempt('clarity', collect_clarity, {})
    prev_org = prev.get('organic', {})
    ig, ig_ok = attempt('instagram', lambda: collect_ig(prev_org.get('ig'), force='--ig' in sys.argv), prev_org.get('ig', {}))
    org_files, of_ok = attempt('organic_files', lambda: collect_organic_files(prev_org), {})

    camps = list(meta.values())
    if naver_ok:
        camps += list(naver.values())
    else:  # 네이버 실패 → 이전 네이버 행 그대로
        camps += [c for c in prev.get('campaigns', []) if c['platform'] == 'naver' and c['key'] != 'NV-UNMAPPED']
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

    channels = {k: {'key': 'CH-' + k, 'platform': 'channel', 'id': k, 'name': n, 'short': n, 'status': 'ACTIVE', 'daily': {}}
                for k, n in CHANNELS}
    unmatched_deep = 0
    if ga_ok:
        for r in ga['deep']:
            ch = channels[classify_channel(r['source'], r['medium'])]
            cd = ch['daily'].setdefault(r['date'], {}).setdefault('deep', EMPTY_DEEP())
            cd['total'] += r['n']
            cd[r['kind']] += r['n']
            c = resolve(r['source'], r['medium'], r['campaign'], r['content'], r['term'])
            if not c:
                unmatched_deep += r['n']
                continue
            dd = day(c, r['date']).setdefault('deep', EMPTY_DEEP())
            dd['total'] += r['n']
            dd[r['kind']] += r['n']
        for r in ga['sessions']:
            sess, eng, dur, pv = (int(r['m'][0]), int(r['m'][1]), round(r['m'][2]), int(r['m'][3]))
            targets = []
            if not r['naver_split']:
                ch = channels[classify_channel(r['source'], r['medium'])]
                targets.append(ch['daily'].setdefault(r['date'], {}))
                if (r['source'], r['medium']) != ('naver', 'cpc'):
                    c = resolve(r['source'], r['medium'], r['campaign'], '', '')
                    if c and c['platform'] == 'meta':
                        targets.append(day(c, r['date']))
            else:
                targets.append(day(resolve('naver', 'cpc', '', r['content'], r['term']), r['date']))
            for t in targets:
                t['sessions'] = t.get('sessions', 0) + sess
                t['engaged'] = t.get('engaged', 0) + eng
                t['eng_time'] = t.get('eng_time', 0) + dur
                t['pv'] = t.get('pv', 0) + pv
        for r in ga['bridge']:
            c = resolve(r['source'], r['medium'], r['campaign'], r['content'], r['term'])
            if c:
                b = day(c, r['date']).setdefault('bridge', {})
                b[r['event']] = b.get(r['event'], 0) + r['n']
        for r in ga['ad_deep']:
            c = by_meta_id.get(r['campaign']) or (by_key.get(r['campaign']) if re.fullmatch(r'CMP-\d+', r['campaign']) else None)
            if c and c['platform'] == 'meta' and re.fullmatch(r'\d{10,}', r['ad']):
                ad = c.setdefault('ads', {}).setdefault(r['ad'], {'name': r['ad'], 'daily': {}})
                v = ad['daily'].setdefault(r['date'], {'spend': 0, 'impr': 0, 'v3s': 0, 'lpv': 0, 'deep_meta': 0})
                v['deep'] = v.get('deep', 0) + r['n']
    # 체험 신청
    account = {d: {'imweb_body_sales': 0, 'trial_bookings': 0} for d in daterange(DATA_SINCE, TODAY)}
    trial_utm = 0
    if tr_ok:
        for t in trials:
            account.setdefault(t['date'], {'imweb_body_sales': 0, 'trial_bookings': 0})['trial_bookings'] += 1
            if t.get('utm_campaign'):
                trial_utm += 1
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

    if naver_unknown['daily']:
        camps.append(naver_unknown)

    # 날짜별 정리 + 이전 값 유지 규칙
    for c in camps:
        pc = prev_c.get(c['key'] + '|' + c['id'], {})
        pdaily = pc.get('daily', {})
        for d in sorted(set(c['daily']) | set(pdaily)):
            v = c['daily'].setdefault(d, {'spend': 0, 'lpv': 0})
            pv = pdaily.get(d, {})
            if not ga_ok:  # GA4 실패 → GA4 필드는 이전 값
                for f in GA_DAY_FIELDS:
                    if f in pv:
                        v[f] = pv[f]
            if d >= DEEP_SINCE:
                v.setdefault('deep', EMPTY_DEEP() if ga_ok else None)
            else:
                v['deep'] = None  # 측정 전
            if not tr_ok:
                v['trial'] = pv.get('trial', 0)
            v.setdefault('trial', 0)
            # Clarity: 과거 값은 덮어쓰지 않는다(오늘 값만 최신 수집으로 갱신)
            old = pv.get('clarity')
            new = None
            if c['platform'] == 'meta':
                cd = clarity.get(d, {})
                new = cd.get(c['id']) or cd.get(c['key'])
            rec = old if (old and d < TODAY) else (new or old)
            v['clarity'] = rec
            v['clarity_active_sec'] = rec.get('sec') if rec else None
            v['clarity_sessions'] = rec.get('sessions') if rec else None
            v['ga4_final'] = d < TODAY
        c['daily'] = dict(sorted(c['daily'].items()))
        if c.get('ads'):
            if not ga_ok:
                pads = pc.get('ads', {})
                for aid, ad in c['ads'].items():
                    for d, v in ad['daily'].items():
                        pdv = pads.get(aid, {}).get('daily', {}).get(d, {})
                        if 'deep' in pdv:
                            v['deep'] = pdv['deep']
            for ad in c['ads'].values():
                ad['daily'] = dict(sorted(ad['daily'].items()))

    ch_list = list(channels.values())
    if not ga_ok:
        ch_list = prev.get('channels', ch_list)
    for ch in ch_list:
        for d in list(ch['daily']):
            v = ch['daily'][d]
            if d < DEEP_SINCE:
                v['deep'] = None
            elif 'deep' not in v:
                v['deep'] = EMPTY_DEEP()
            v['ga4_final'] = d < TODAY
        ch['daily'] = dict(sorted(ch['daily'].items()))

    organic = {'ig': ig if ig_ok else prev_org.get('ig', {})}
    organic.update(org_files if of_ok else {k: prev_org.get(k) for k in ('followers', 'youtube', 'blog')})

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
            'clarity': 'Clarity 최근 1일(수집 시각 기준 24시간) 캠페인별 값. am/pm 수집 파일 중 그날 마지막 값.',
            'sales': '아임웹 정본(imweb_orders.json + 주문 알림 캐시). 취소·반품·환불·3만 원 이하 제외.',
            'sales_meta': sales_meta if sales_ok else prev.get('notes', {}).get('sales_meta'),
            'trial': 'Supabase feel_bookings. 취소·중복 제외. utm_campaign이 있는 건만 캠페인에 붙임.',
            'trial_with_utm': trial_utm,
            'channel_rule': CHANNEL_RULES,
            'section_view': 'GA4에 section_view 이벤트가 수집되지 않음(2026-07 이후 0건)',
        },
        'campaigns': [c for c in camps if c['daily'] or c['status'] == 'ACTIVE' or total_spend(c) > 0 or c['platform'] == 'meta'],
        'channels': ch_list,
        'ga4_total_sessions': ga.get('total') if ga_ok else prev.get('ga4_total_sessions', {}),
        'account_daily': dict(sorted(account.items())),
        'organic': organic,
    }
    for c in out['campaigns']:
        c.pop('nonbrand', None)
    CANDIDATE.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')))
    src_state = ', '.join(k + (':ok' if v['ok'] else ':FAIL') for k, v in sources.items())
    log(f"후보 json: 캠페인 {len(out['campaigns'])}개, 채널 {len(ch_list)}개, 소스 {{{src_state}}}")

    # 검증 → 통과해야 교체·배포 (실패 시 이전 json 유지)
    vp = subprocess.run(['/usr/local/bin/python3', str(ROOT / 'scripts' / 'verify_campaign_compare.py'), str(CANDIDATE)],
                        cwd=str(ROOT), capture_output=True, text=True)
    for line in (vp.stdout + vp.stderr).strip().splitlines()[-20:]:
        if 'Warning' not in line and 'warnings.warn' not in line:
            log('  [verify] ' + scrub(line))
    if vp.returncode != 0:
        log('❌ 검증 실패 → 배포하지 않고 이전 json 유지')
        return 4
    os.replace(CANDIDATE, OUT)
    log(f"✅ json 갱신: updated_at {out['updated_at']}")

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
