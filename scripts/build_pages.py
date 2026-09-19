# 코드별 정적 페이지를 만든다 — 검색엔진에 색인될 방문 유입 엔진.
#   python scripts/build_pages.py
# 출력: docs/  (류 96 + 호 1,228 + 소호 5,612 + 목차 + sitemap.xml + robots.txt)
import csv, html, json, os, shutil, sys, time
from collections import defaultdict
import duckdb

from paths import DATA, DOCS, SRC, TAR, TRD  # noqa: E402

OUT = DOCS
YMAX, YR, Y0 = 2026, 2025, 2007
BASE = 'https://pilsunchoi.github.io/KoreaTariffAtlas'   # 실제 주소가 정해지면 여기만 고친다
APP = '../atlas.html'                                    # docs/hs/*.html 에서 본 대시보드 경로
FX = 1380

ORI = [('mfn', '무협정'), ('applied_cn', '중국'), ('applied_eu', 'EU'), ('applied_us', '미국'),
       ('applied_asean', '아세안'), ('applied_vn', '베트남'), ('applied_in', '인도'),
       ('applied_ca', '캐나다'), ('applied_apta', 'APTA')]
OCOL = [c for c, _ in ORI]
NM = json.load(open(os.path.join(DATA, 'hs_names.json'), encoding='utf-8'))
E = lambda s: html.escape(str(s or ''), quote=True)

# ---------------------------------------------------------------- 자료 읽기
t0 = time.time()
con = duckdb.connect()
con.execute(f"attach '{TAR}' as t (read_only)")
con.execute(f"attach '{TRD}' as k (read_only)")
q = lambda s: con.execute(s).fetchall()

sel = ','.join(f'a.{c}' for c in OCOL)
CODES = {}
for r in q(f"""select a.hs10, coalesce(c.name_ko,''), {sel},
     a.has_W1, a.has_I, a.has_P1, a.r_P3, a.specific_won_kg, a.floor_won_kg,
     a.rate_undetermined, coalesce(a.txt_A, a.txt_W2, '')
   from t.fct_applied_rate a left join t.tariff_code c on c.hs10=a.hs10 and c.year={YMAX}
   where a.year={YMAX} order by a.hs10"""):
    CODES[r[0]] = {'leaf': r[1], 'rate': dict(zip(OCOL, r[2:2 + len(OCOL)])),
                   'trq': r[11], 'dump': r[12], 'quota': bool(r[13]) or r[14] is not None,
                   'spec': r[15], 'floor': r[16], 'undet': r[17], 'txt': r[18]}

IMP = dict(q(f"""select hs10, sum(imp_dlr) from k.fact_trade
  where yyyymm between {YR}01 and {YR}12 and imp_dlr>0 group by 1"""))
UPX = dict(q(f"""select hs10, sum(imp_dlr)/sum(imp_wgt) from k.fact_trade
  where yyyymm between {YR}01 and {YR}12 and imp_wgt>0 group by 1 having sum(imp_wgt)>0"""))

TOP6 = defaultdict(list)                       # HS6 → [(국가, 금액)] 상위 5
for h6, nm, cd, v in q(f"""select h6, name_ko_kcs, stat_cd, dlr from (
    select substr(f.hs10,1,6) h6, c.name_ko_kcs, f.stat_cd, sum(f.imp_dlr) dlr,
      row_number() over (partition by substr(f.hs10,1,6) order by sum(f.imp_dlr) desc) rn
    from k.fact_trade f left join k.dim_country c on c.stat_cd=f.stat_cd
    where f.yyyymm between {YR}01 and {YR}12 and f.imp_dlr>0 group by 1,2,3) where rn<=5"""):
    TOP6[h6].append((nm or cd, v))

HIST = defaultdict(list)                       # hs10 → [(연도, {열: 값})] 변화 시점만
prev = {}
for r in q(f"""select hs10, year, {','.join(OCOL)} from t.fct_applied_rate
  where not rate_undetermined and year between {Y0} and {YMAX} order by hs10, year"""):
    hs, y, vals = r[0], r[1], r[2:]
    if prev.get(hs) != vals:
        HIST[hs].append((y, dict(zip(OCOL, vals))))
        prev[hs] = vals

SYN6 = defaultdict(list)                       # HS6 → 관용명 전부
SYN6P = defaultdict(list)                      # HS6 → 대표 관용명만(제목용)
try:
    for row in csv.DictReader(open(os.path.join(DATA, '관용명_사전.csv'), encoding='utf-8-sig')):
        words = [row['term']] + [a for a in (row['aliases'] or '').split('|') if a]
        for tg in row['target'].split('|'):
            tg = tg.strip()
            for h6 in {h[:6] for h in CODES if h.startswith(tg) or tg.startswith(h[:6])}:
                SYN6[h6].extend(words)
                if row['term'] not in SYN6P[h6]:
                    SYN6P[h6].append(row['term'])
except FileNotFoundError:
    print('관용명_사전.csv 없음 — 관용명 없이 만든다', file=sys.stderr)

H6 = defaultdict(list)
for hs in CODES:
    H6[hs[:6]].append(hs)
H4 = defaultdict(list)
for h6 in H6:
    H4[h6[:4]].append(h6)
H2 = defaultdict(list)
for h4 in H4:
    H2[h4[:2]].append(h4)
for d in (H6, H4, H2):
    for k2 in d:
        d[k2].sort()
print(f'자료 {time.time()-t0:.0f}초 · 소호 {len(H6)} 호 {len(H4)} 류 {len(H2)}', file=sys.stderr)

# ---------------------------------------------------------------- 서식
def dot(hs):
    return f'{hs[:4]}.{hs[4:6]}' + (f'.{hs[6:]}' if len(hs) > 6 else '')

def pct(v):
    if v is None:
        return '—'
    if v == int(v):
        return f'{int(v):,}%'
    return f'{v:,.1f}%' if v >= 10 else f'{v:,.2f}'.rstrip('0').rstrip('.') + '%'

def usd(v):                                    # 달러 금액을 한국어 단위로
    if not v:
        return '—'
    if v >= 1e8:
        return f'{v/1e8:,.0f}억 달러' if v >= 1e9 else f'{v/1e8:,.1f}억 달러'
    return f'{v/1e4:,.0f}만 달러'

def name6(h6):
    return NM['h6'].get(h6) or NM['h5'].get(h6[:5]) or NM['h4'].get(h6[:4]) or f'제{h6[:4]}호'

def title6(h6):
    """소호명만으로는 「건조한 것」처럼 뜻이 안 선다 — 윗단계 이름을 앞에 붙인다."""
    nm = NM['h6'].get(h6)
    up = NM['h5'].get(h6[:5]) or NM['h4'].get(h6[:4])
    if not nm:
        return up or f'제{h6[:4]}호'
    if up and up != nm:
        return f'{up} 중 {nm}'
    return nm

def cut(t, n):                                 # 자를 때는 말 끝을 알린다
    t = t or ''
    return t if len(t) <= n else t[:n - 1].rstrip('([·, ') + '…'

def short6(h6, n=52):                          # <title>·목록용 짧은 이름
    t = title6(h6)
    return cut(t, n)

def chain(h6):                                 # 계층 이름 — 중복은 접는다
    out, seen = [], set()
    for v in (NM['h2'].get(h6[:2]), NM['h4'].get(h6[:4]), NM['h5'].get(h6[:5]), NM['h6'].get(h6)):
        if v and v not in seen:
            out.append(v); seen.add(v)
    return out

# ---------------------------------------------------------------- 조각
def sparkline(hs, w=300, h=64):
    """무협정 세율과 가장 낮은 협정세율의 20년 계단선. JS 없이 그린다."""
    hist = HIST.get(hs) or []
    if not hist:
        return ''
    def step(col):
        pts, cur = [], None
        for y, d in hist:
            v = d.get(col)
            if v is None:
                continue
            if cur is not None:
                pts.append((y, cur))
            pts.append((y, v)); cur = v
        if cur is not None:
            pts.append((YMAX, cur))
        return pts
    base = step('mfn')
    if not base:
        return ''
    # 가장 많이 내려간 협정 하나만 겹쳐 그린다
    best, bestpts = None, None
    for c, lb in ORI[1:]:
        p = step(c)
        if p and p[-1][1] is not None and base[-1][1] is not None and p[-1][1] < base[-1][1]:
            if best is None or p[-1][1] < bestpts[-1][1]:
                best, bestpts = lb, p
    allv = [v for _, v in base] + ([v for _, v in bestpts] if bestpts else [])
    mx = max(allv + [1]) * 1.12
    X = lambda y: 4 + (y - Y0) / (YMAX - Y0) * (w - 52)
    Y = lambda v: h - 14 - v / mx * (h - 22)
    def path(p):
        return ' '.join(('M' if i == 0 else 'L') + f'{X(y):.1f} {Y(v):.1f}' for i, (y, v) in enumerate(p))
    s = [f'<svg class="spark" viewBox="0 0 {w} {h}" role="img" '
         f'aria-label="{Y0}년부터 {YMAX}년까지 세율 변화">']
    s.append(f'<line x1="4" y1="{h-14:.0f}" x2="{w-48}" y2="{h-14:.0f}" style="stroke:var(--line)"/>')
    if bestpts:
        s.append(f'<path d="{path(bestpts)}" fill="none" stroke-width="2" style="stroke:var(--series-3)"/>')
        s.append(f'<text x="{w-44}" y="{Y(bestpts[-1][1])+4:.0f}" font-size="10" style="fill:var(--series-3)">{E(best)}</text>')
    s.append(f'<path d="{path(base)}" fill="none" stroke-width="2" style="stroke:var(--series-1)"/>')
    s.append(f'<text x="{w-44}" y="{Y(base[-1][1])+4:.0f}" font-size="10" style="fill:var(--series-1)">무협정</text>')
    s.append(f'<text x="4" y="{h-3:.0f}" font-size="9" style="fill:var(--muted)">{Y0}</text>')
    s.append(f'<text x="{w-52}" y="{h-3:.0f}" font-size="9" text-anchor="end" style="fill:var(--muted)">{YMAX}</text>')
    s.append('</svg>')
    return ''.join(s)

def badges(hs10s):
    b, c = [], [CODES[h] for h in hs10s]
    if any(x['trq'] for x in c):
        b.append(('warn', '양허관세 추천 필요(TRQ)'))
    if any(x['dump'] for x in c):
        b.append(('fail', '덤핑방지관세 있음'))
    if any(x['quota'] for x in c):
        b.append(('ok', '할당관세 지정'))
    if any(x['spec'] is not None for x in c):
        b.append(('info', '종량세'))
    if any(x['floor'] is not None for x in c):
        b.append(('info', '종량 하한(선택세율)'))
    if any(x['undet'] for x in c):
        b.append(('fail', '세율 미확정'))
    return ''.join(f'<span class="pill {k}">{v}</span>' for k, v in b)

def rate_table(hs10s):
    head = ''.join(f'<th class="r">{lb}</th>' for _, lb in ORI)
    rows = []
    for hs in hs10s:
        c = CODES[hs]
        vals = [c['rate'][col] for col, _ in ORI]
        good = [v for v in vals if v is not None]
        lo = min(good) if good else None
        tds = ''.join(f'<td class="r{" lo" if (v is not None and lo is not None and v==lo and max(good)>lo) else ""}">{pct(v)}</td>'
                      for v in vals)
        rows.append(f'<tr><th scope="row"><code>{dot(hs)}</code><span>{E(c["leaf"])}</span></th>'
                    f'{tds}<td class="r">{usd(IMP.get(hs,0))}</td></tr>')
    return ('<div class="tw"><table class="rates"><caption>' + str(YMAX) +
            '년 원산지별 실행세율과 ' + str(YR) + '년 수입액</caption>'
            '<thead><tr><th scope="col">HSK 10단위</th>' + head +
            f'<th class="r">{YR} 수입</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')

def lede(h6, hs10s):
    rep = max(hs10s, key=lambda h: IMP.get(h, 0))
    c = CODES[rep]
    mfn, parts = c['rate']['mfn'], []
    if mfn is not None:
        parts.append(f'협정이 없는 나라에서 들여오면 <b>{pct(mfn)}</b>')
    free = [lb for col, lb in ORI[1:] if c['rate'].get(col) == 0]
    if free and mfn:
        parts.append(f'{"·".join(free[:5])}산은 <b>0%</b>')
    elif not free:
        low = [(v, lb) for col, lb in ORI[1:] if (v := c['rate'].get(col)) is not None and mfn is not None and v < mfn]
        if low:
            v, lb = min(low)
            parts.append(f'가장 낮은 협정세율은 {lb} <b>{pct(v)}</b>')
    s = (', '.join(parts) + '이다. ') if parts else ''
    v = sum(IMP.get(h, 0) for h in hs10s)
    if v:
        tops = TOP6.get(h6, [])
        s += f'{YR}년 수입액은 <b>{usd(v)}</b>'
        if tops:
            s += f'로 {E(tops[0][0])}({usd(tops[0][1])})에서 가장 많이 들어왔다'
        s += '. '
    if c['spec'] is not None and c['floor'] is not None:
        s += (f'신고단가가 kg당 {c["floor"]:,.0f}원 밑으로 내려가면 종가세 대신 '
              f'kg당 {c["spec"]:,.0f}원의 종량세가 적용된다. ')
    syn = sorted(set(SYN6.get(h6, [])))[:6]
    if syn:
        s += f'흔히 {E("·".join(syn))}라고 부르는 물품이 여기에 들어간다. '
    if len(hs10s) > 1:
        s += f'아래 10단위 코드 {len(hs10s)}개로 나뉜다.'
    return s

def shell(path, title, desc, body, canon, crumbs, kw=''):
    up = '../' * (path.count('/'))
    # 'INDEX'는 목차로 가는 자리표시 — 페이지 깊이에 맞춰 바꾼다
    crumb = ' › '.join(
        f'<a href="{up}index.html">{E(t)}</a>' if u == 'INDEX'
        else (f'<a href="{u}">{E(t)}</a>' if u else f'<span>{E(t)}</span>')
        for t, u in crumbs)
    doc = f"""<!DOCTYPE html>
<html lang="ko" data-surface="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
{f'<meta name="keywords" content="{E(kw)}">' if kw else ''}
<link rel="canonical" href="{BASE}/{canon}">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<meta property="og:type" content="article"><meta property="og:url" content="{BASE}/{canon}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Instrument+Sans:wght@400;500;600&family=IBM+Plex+Sans+KR:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="{up}assets/atlas-base.css">
<link rel="stylesheet" href="{up}assets/page.css">
</head><body>
<header class="atlas-top compact"><div class="wrap"><a class="home" href="{up}index.html">한국 관세 아틀라스 <i>Korea Tariff Atlas</i></a>
{f'<nav class="crumb" aria-label="계층">{crumb}</nav>' if crumbs else ''}</div></header>
<main class="wrap">{body}</main>
<footer><div class="wrap">
<p>세율 <a href="https://github.com/pilsunchoi/KCSTARIFF">KCSTARIFF</a> ·
무역통계 <a href="https://pilsunchoi.github.io/KCSDB2/">KCSDB2</a> ·
원자료 관세청 관세법령정보포털(공공누리 제1유형)</p>
<p><b>이 화면의 세율은 참고용이며 법적 효력이 없다.</b> 실행세율은 관세법 제50조를 해석해 만든 파생값이다.
세액 계산이나 수입신고에는 관세법 별표 관세율표와 해당 규정의 원문을 확인해야 한다.</p>
</div></footer></body></html>"""
    p = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(doc)
    return len(doc)

# ---------------------------------------------------------------- 페이지
# docs/ 를 통째로 지우지 않는다 — atlas-data.js·synonyms.js는 앞 단계가 만든 것이고
# .nojekyll 은 Pages가 밑줄로 시작하는 이름을 삼키지 않게 하는 표시다.
# 이 스크립트가 만드는 것(코드 페이지)만 비운다.
if os.path.isdir(os.path.join(OUT, 'hs')):
    shutil.rmtree(os.path.join(OUT, 'hs'))
os.makedirs(os.path.join(OUT, 'assets'), exist_ok=True)
urls, total = [], 0

def crumbs_of(h, upto):
    c = [('한국 관세 아틀라스', 'INDEX')]
    if upto >= 2:
        c.append((f'제{int(h[:2])}류 {NM["h2"].get(h[:2],"")}'[:34], f'ch{h[:2]}.html'))
    if upto >= 4:
        c.append((f'제{h[:4]}호', f'{h[:4]}.html'))
    if upto >= 6:
        c.append((f'HS {dot(h[:6])}', ''))
    return c

# --- 소호(HS6) ---
for h6, hs10s in sorted(H6.items()):
    nm = title6(h6)
    syn = sorted(set(SYN6.get(h6, [])))
    v = sum(IMP.get(h, 0) for h in hs10s)
    rep = max(hs10s, key=lambda h: IMP.get(h, 0))
    mfn = CODES[rep]['rate']['mfn']
    free = [lb for col, lb in ORI[1:] if CODES[rep]['rate'].get(col) == 0]
    desc = (f'HS {dot(h6)} {short6(h6, 40)}의 {YMAX}년 관세율. 무협정 {pct(mfn)}'
            + (f', {"·".join(free[:3])} 0%' if free else '')
            + (f'. {YR}년 수입 {usd(v)}' if v else '')
            + (f'. {"·".join(syn[:5])}.' if syn else '.')
            + f' {Y0}년부터의 세율 이력과 원산지별 비교.')
    sibs = [x for x in H4[h6[:4]] if x != h6]
    body = [(f'<p class="kicker">{E("·".join(SYN6P.get(h6, [])[:4]))}</p>' if SYN6P.get(h6) else '')
            + f'<h1>{E(nm)} <span class="hs">HS {dot(h6)}</span></h1>',
            f'<p class="lede">{lede(h6, hs10s)}</p>']
    bg = badges(hs10s)
    if bg:
        body.append(f'<p class="badges">{bg}</p>')
    body.append(rate_table(hs10s))
    sp = sparkline(rep)
    if sp:
        body.append(f'<section><h2>세율 이력</h2><p class="cap">{Y0}~{YMAX}년, '
                    f'{"수입액이 가장 큰 " if len(hs10s)>1 else ""}<code>{dot(rep)}</code> 기준.</p>{sp}</section>')
    tops = TOP6.get(h6, [])
    if tops:
        body.append('<section><h2>' + str(YR) + '년 주요 수입 상대</h2><ol class="tops">' + ''.join(
            f'<li><span>{E(n)}</span><i style="width:{max(3,100*x/tops[0][1]):.0f}%"></i>'
            f'<b>{usd(x)}</b></li>' for n, x in tops) + '</ol></section>')
    if UPX.get(rep):
        body.append(f'<p class="cap">{YR}년 평균 수입단가 약 {UPX[rep]*FX:,.0f}원/kg '
                    f'({UPX[rep]:,.2f}달러/kg, 환율 {FX:,}원 가정).</p>')
    if syn:
        body.append('<section><h2>이렇게도 부른다</h2><p class="syn">' +
                    ' · '.join(E(s) for s in syn) + '</p></section>')
    if sibs:
        body.append(f'<section><h2>같은 호(제{h6[:4]}호)의 다른 소호</h2><ul class="sibs">' + ''.join(
            f'<li><a href="{s}.html"><code>{dot(s)}</code> {E(short6(s, 44))}</a></li>'
            for s in sibs[:30]) + '</ul>'
            + (f'<p class="cap"><a href="{h6[:4]}.html">제{h6[:4]}호 전체 보기</a></p>'
               if len(sibs) > 30 else '') + '</section>')
    body.append(f'<section class="more"><h2>더 보기</h2><ul>'
                f'<li><a href="{APP}#hs={hs10s[0]}">대화형 대시보드에서 이 코드 열기</a></li>'
                f'<li><a href="https://unipass.customs.go.kr/clip/">관세법령정보포털(CLIP) 원문 확인</a></li>'
                f'<li><a href="ch{h6[:2]}.html">제{int(h6[:2])}류 전체</a></li></ul></section>')
    lead = '·'.join(SYN6P.get(h6, [])[:2])
    ttl = (f'{lead} 관세율 — {short6(h6, 34)} (HS {dot(h6)}) | 한국 관세 아틀라스' if lead
           else f'{short6(h6, 42)} 관세율 — HS {dot(h6)} | 한국 관세 아틀라스')
    total += shell(f'hs/{h6}.html', ttl,
                   desc, '\n'.join(body), f'hs/{h6}.html', crumbs_of(h6, 6),
                   ' '.join(syn + [nm, f'HS{dot(h6)}', '관세율']))
    urls.append((f'hs/{h6}.html', v))

# --- 호(HS4) ---
for h4, h6s in sorted(H4.items()):
    nm = NM['h4'].get(h4) or f'제{h4}호'
    v = sum(IMP.get(h, 0) for h6 in h6s for h in H6[h6])
    rows = ''.join(
        f'<tr><th scope="row"><a href="{h6}.html"><code>{dot(h6)}</code> {E(short6(h6, 60))}</a></th>'
        f'<td class="r">{pct(CODES[max(H6[h6], key=lambda h: IMP.get(h,0))]["rate"]["mfn"])}</td>'
        f'<td class="r">{len(H6[h6])}</td>'
        f'<td class="r">{usd(sum(IMP.get(h,0) for h in H6[h6]))}</td></tr>' for h6 in h6s)
    body = [f'<h1>제{h4}호 <span class="hs">{E(cut(nm, 70))}</span></h1>',
            f'<p class="lede">제{h4}호는 소호 {len(h6s)}개, HSK 10단위 코드 '
            f'{sum(len(H6[x]) for x in h6s)}개로 나뉜다.'
            + (f' {YR}년 수입액은 {usd(v)}다.' if v else '') + '</p>',
            '<div class="tw"><table class="rates"><caption>소호 목록</caption><thead><tr>'
            f'<th scope="col">소호</th><th class="r">무협정 세율</th><th class="r">코드</th>'
            f'<th class="r">{YR} 수입</th></tr></thead><tbody>' + rows + '</tbody></table></div>',
            f'<section class="more"><h2>더 보기</h2><ul>'
            f'<li><a href="ch{h4[:2]}.html">제{int(h4[:2])}류 전체</a></li>'
            f'<li><a href="{APP}">대화형 대시보드</a></li></ul></section>']
    total += shell(f'hs/{h4}.html', f'제{h4}호 {cut(nm, 40)} 관세율 — 한국 관세 아틀라스',
                   f'제{h4}호({cut(nm, 60)})의 소호별 {YMAX}년 관세율과 {YR}년 수입액.',
                   '\n'.join(body), f'hs/{h4}.html', crumbs_of(h4, 4)[:-1] + [(f'제{h4}호', '')])
    urls.append((f'hs/{h4}.html', v))

# --- 류(HS2) ---
for h2, h4s in sorted(H2.items()):
    nm = NM['h2'].get(h2, '')
    v = sum(IMP.get(h, 0) for h4 in h4s for h6 in H4[h4] for h in H6[h6])
    rows = ''.join(
        f'<tr><th scope="row"><a href="{h4}.html">제{h4}호 {E((NM["h4"].get(h4) or "")[:54])}</a></th>'
        f'<td class="r">{len(H4[h4])}</td>'
        f'<td class="r">{usd(sum(IMP.get(h,0) for h6 in H4[h4] for h in H6[h6]))}</td></tr>'
        for h4 in h4s)
    body = [f'<h1>제{int(h2)}류 <span class="hs">{E(nm)}</span></h1>',
            f'<p class="lede">제{int(h2)}류는 호 {len(h4s)}개로 나뉜다.'
            + (f' {YR}년 수입액은 {usd(v)}다.' if v else '') + '</p>',
            '<div class="tw"><table class="rates"><caption>호 목록</caption><thead><tr>'
            f'<th scope="col">호</th><th class="r">소호</th><th class="r">{YR} 수입</th>'
            '</tr></thead><tbody>' + rows + '</tbody></table></div>']
    total += shell(f'hs/ch{h2}.html', f'제{int(h2)}류 {cut(nm, 40)} 관세율 — 한국 관세 아틀라스',
                   f'제{int(h2)}류({cut(nm, 60)})에 속한 호별 {YMAX}년 관세율과 {YR}년 수입액.',
                   '\n'.join(body), f'hs/ch{h2}.html',
                   [('한국 관세 아틀라스', 'INDEX'), (f'제{int(h2)}류', '')])
    urls.append((f'hs/ch{h2}.html', v))

# --- 목차 ---
cards = ''.join(
    f'<a class="chcard" href="hs/ch{h2}.html"><b>제{int(h2)}류</b><span>{E(NM["h2"].get(h2,""))}</span>'
    f'<i>{usd(sum(IMP.get(h,0) for h4 in H2[h2] for h6 in H4[h4] for h in H6[h6]))}</i></a>'
    for h2 in sorted(H2))
body = [f'<h1>한국 관세 아틀라스</h1>',
        f'<p class="lede">HSK 10단위 코드마다 <b>어느 나라에서 들여오면 관세가 얼마인지</b>, '
        f'그 세율이 <b>{YMAX-Y0+1}년 동안 어떻게 바뀌었는지</b>, '
        f'<b>실제로 얼마가 그 세율을 만났는지</b>를 함께 보여 준다. '
        f'소호 {len(H6):,}개 · 호 {len(H4):,}개 · 류 {len(H2)}개의 페이지가 있다.</p>',
        f'<p class="btnrow"><a class="btn primary" href="atlas.html">대화형 대시보드에서 검색</a></p>',
        '<h2>류로 찾기</h2><div class="chgrid">' + cards + '</div>']
total += shell('index.html', '한국 관세 아틀라스 — HSK 10단위 관세율',
               f'한국의 HSK 10단위 관세율을 코드·원산지·연도별로. 소호 {len(H6):,}개 페이지.',
               '\n'.join(body), 'index.html', [])
urls.append(('index.html', 1e18))

# --- sitemap / robots ---
urls.sort(key=lambda x: -x[1])
with open(os.path.join(OUT, 'sitemap.xml'), 'w', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
    for u, v in urls:
        pr = '1.0' if u == 'index.html' else '0.8' if v > 1e8 else '0.6' if v > 1e6 else '0.4'
        f.write(f'<url><loc>{BASE}/{u}</loc><changefreq>yearly</changefreq>'
                f'<priority>{pr}</priority></url>\n')
    f.write('</urlset>\n')
open(os.path.join(OUT, 'robots.txt'), 'w', encoding='utf-8').write(
    f'User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n')

CSS = """/* 코드 페이지 전용. 토큰과 공용 골격은 atlas-base.css에 있다(light 변종). */
.wrap{max-width:880px}
.atlas-top.compact{padding:12px 0}
.home{font-weight:700;color:var(--ink);font-size:1.02rem}
.home:hover{text-decoration:none;color:var(--accent)}
.home i{font-family:var(--serif);font-style:normal;color:var(--accent);font-weight:400;margin-left:6px}
.crumb{font-size:.82rem;color:var(--muted);margin-top:4px}
.crumb a{color:var(--muted)}
.crumb span{color:var(--ink);font-weight:600}

.kicker{color:var(--accent);font-weight:700;font-size:.86rem;margin:0 0 2px}
h1{font-size:1.58rem;margin:0 0 6px;letter-spacing:-.01em}
h1 .hs{display:block;font-family:var(--mono);font-size:.9rem;font-weight:500;color:var(--muted);margin-top:5px}
.lede{font-size:1.02rem;margin:10px 0 16px;color:var(--ink)}
section:first-of-type h2{border-top:none;padding-top:0}
h2{border-top:1px solid var(--line);padding-top:20px}

table.rates{min-width:760px}
.rates tbody th{min-width:170px;font-weight:400}
.rates thead th:first-child{min-width:170px}
.rates tbody th code{display:block;font-weight:500;color:var(--accent)}
.rates tbody th span{color:var(--muted);font-size:.86em}

.spark{width:100%;max-width:340px;margin:4px 0}
.tops{list-style:none;padding:0;margin:10px 0}
.tops li{display:grid;grid-template-columns:110px 1fr auto;gap:10px;align-items:center;margin:4px 0;font-size:.9rem}
.tops i{display:block;height:14px;border-radius:4px;background:var(--seq-500)}
.tops b{font-variant-numeric:tabular-nums}
.syn{background:var(--accent-soft);border-radius:10px;padding:10px 14px;font-size:.92rem;color:var(--ink)}
.sibs{list-style:none;padding:0;margin:8px 0;columns:2;column-gap:24px}
.sibs li{break-inside:avoid;margin:3px 0;font-size:.9rem}
.sibs code{color:var(--muted)}
.more ul{margin:8px 0;padding-left:20px}

.chgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin:14px 0}
.chcard{display:block;background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:12px 14px;color:var(--ink);box-shadow:var(--shadow)}
.chcard:hover{border-color:var(--accent);background:var(--accent-soft);text-decoration:none}
.chcard b{display:block;color:var(--accent)}
.chcard span{display:block;font-size:.86rem;color:var(--muted);margin:2px 0}
.chcard i{font-style:normal;font-size:.8rem;color:var(--muted);font-variant-numeric:tabular-nums}

@media(max-width:560px){.sibs{columns:1}h1{font-size:1.32rem}
.tops li{grid-template-columns:80px 1fr auto}}
"""
open(os.path.join(OUT, 'assets', 'page.css'), 'w', encoding='utf-8').write(CSS)

# 원본(src/)에서 화면과 공용 토큰을 내린다
shutil.copy2(os.path.join(SRC, 'assets', 'atlas-base.css'),
             os.path.join(OUT, 'assets', 'atlas-base.css'))
shutil.copy2(os.path.join(SRC, 'atlas.html'), os.path.join(OUT, 'atlas.html'))
open(os.path.join(OUT, '.nojekyll'), 'a', encoding='utf-8').close()

# 앞 단계가 만들어 둬야 하는 것 — 없으면 대시보드가 빈 화면이 된다
for f in ('atlas-data.js', 'synonyms.js'):
    if not os.path.exists(os.path.join(OUT, f)):
        print(f'docs/{f} 없음 — prep_data.py·build_synonyms.py를 먼저 돌려야 한다',
              file=sys.stderr)

# 내부 링크 검사 — 자리표시자나 오타가 그대로 나가는 것을 막는다
import re as _re
_pat = _re.compile(r'href="([^"#?]+)')
bad, nlink = [], 0
for root, _, fs in os.walk(OUT):
    for f in fs:
        if not f.endswith('.html'):
            continue
        fp = os.path.join(root, f)
        for h in _pat.findall(open(fp, encoding='utf-8').read()):
            # atlas.html 의 `hs/${...}.html` 처럼 실행할 때 만들어지는 주소는 셀 수 없다
            if h.startswith(('http://', 'https://', 'mailto:')) or '${' in h:
                continue
            nlink += 1
            if not os.path.exists(os.path.normpath(os.path.join(root, h))):
                bad.append((os.path.relpath(fp, OUT), h))

n = len(urls)
sz = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs)
print(f'페이지 {n:,}개 · {sz/1e6:.1f}MB · 평균 {total/n/1024:.1f}KB · {time.time()-t0:.0f}초', file=sys.stderr)
print(f'내부 링크 {nlink:,}개 · 깨진 링크 {len(bad)}개', file=sys.stderr)
for b_ in bad[:10]:
    print('  !', b_[0], '→', b_[1], file=sys.stderr)
if bad:
    sys.exit(1)
