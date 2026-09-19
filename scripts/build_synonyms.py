# 관용명_사전.csv를 검증하고 검색용 synonyms.js를 만든다.
#   python scripts/build_synonyms.py
# 출력: synonyms.js (window.SYN), 관용명_사전_검증.csv (행마다 판정)
import csv, json, os, sys, unicodedata
import duckdb

from paths import DATA, DOCS, TAR, TRD  # noqa: E402

YMAX, YR = 2026, 2025
NM = json.load(open(os.path.join(DATA, 'hs_names.json'), encoding='utf-8'))

con = duckdb.connect()
con.execute(f"attach '{TAR}' as t (read_only)")
con.execute(f"attach '{TRD}' as k (read_only)")
codes = con.execute(f"""select a.hs10, coalesce(c.name_ko,'')
  from t.fct_applied_rate a left join t.tariff_code c on c.hs10=a.hs10 and c.year={YMAX}
  where a.year={YMAX} order by 1""").fetchall()
imp = dict(con.execute(f"""select hs10, sum(imp_dlr) from k.fact_trade
  where yyyymm between {YR}01 and {YR}12 and imp_dlr>0 group by 1""").fetchall())
TOTAL = sum(v for h, v in imp.items() if h in {c for c, _ in codes})

# 지금 검색이 훑는 글자 — 여기에 이미 있는 말은 사전이 없어도 찾아진다
def key_of(hs, leaf):
    parts = [hs, leaf, NM['h4'].get(hs[:4], ''), NM['h5'].get(hs[:5], ''),
             NM['h6'].get(hs[:6], ''), NM['h2'].get(hs[:2], '')]
    return ' '.join(parts).lower()

KEY = {hs: key_of(hs, leaf) for hs, leaf in codes}
ALLC = list(KEY)

def under(pfx):
    return [h for h in ALLC if h.startswith(pfx)]

def name_of(pfx):
    for d, tb in ((6, 'h6'), (5, 'h5'), (4, 'h4'), (2, 'h2')):
        if len(pfx) >= d and NM[tb].get(pfx[:d]):
            return NM[tb][pfx[:d]]
    return ''

rows, seen, problems = [], {}, 0
syn, covered = [], set()
with open(os.path.join(DATA, '관용명_사전.csv'), encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        term = r['term'].strip()
        if not term:
            continue
        words = [term] + [a.strip() for a in (r['aliases'] or '').split('|') if a.strip()]
        targets = [t.strip() for t in r['target'].split('|') if t.strip()]
        hits, bad = [], []
        for t in targets:
            u = under(t)
            (hits.extend(u) if u else bad.append(t))
        hits = sorted(set(hits))
        covered.update(hits)
        val = sum(imp.get(h, 0) for h in hits)
        # 이미 찾아지는 말인지 — 대표 관용명이 대상 코드의 글자에 들어 있나
        already = sum(1 for h in hits if term.lower() in KEY[h])
        dup = [w for w in words if w in seen]
        for w in words:
            seen.setdefault(w, term)
        verdict = []
        if bad:
            verdict.append('대상없음:' + ','.join(bad))
        if not hits:
            verdict.append('코드0')
        if dup:
            verdict.append('중복:' + ','.join(dup))
        if hits and already == len(hits):
            verdict.append('이미검색됨')
        if hits and val == 0:
            verdict.append('수입0')
        if any(v.startswith(('대상없음', '코드0', '중복')) for v in verdict):
            problems += 1
        rows.append([term, '|'.join(words[1:]), '|'.join(targets), len(hits),
                     round(val / 1e6, 1), round(100 * val / TOTAL, 3),
                     f'{already}/{len(hits)}' if hits else '0/0',
                     '; '.join(verdict) or 'OK',
                     ' / '.join(name_of(t)[:60] for t in targets)])
        if hits:
            syn.append([words, targets])

out = os.path.join(DATA, '관용명_사전_검증.csv')
with open(out, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['term', 'aliases', 'target', '코드수', '수입액_백만달러', '수입몫_%',
                '이미검색됨', '판정', '대상_법정명칭'])
    w.writerows(rows)

with open(os.path.join(DOCS, 'synonyms.js'), 'w', encoding='utf-8') as f:
    f.write('window.SYN=')
    json.dump(syn, f, ensure_ascii=False, separators=(',', ':'))
    f.write(';')

# 아직 사전이 없는 호를 수입액 순으로 — 사전을 넓힐 때의 작업 목록
gap = {}
for h in ALLC:
    if h in covered:
        continue
    gap.setdefault(h[:4], [0, 0])
    gap[h[:4]][0] += imp.get(h, 0)
    gap[h[:4]][1] += 1
with open(os.path.join(DATA, '관용명_사전_빈칸.csv'), 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['hs4', '수입액_백만달러', '미등록_코드수', '류', '호_법정명칭'])
    for h4, (v, n) in sorted(gap.items(), key=lambda x: -x[1][0])[:150]:
        w.writerow([h4, round(v / 1e6, 1), n, NM['h2'].get(h4[:2], ''), NM['h4'].get(h4, '')[:90]])

cv = sum(imp.get(h, 0) for h in covered)
nw = sum(len(w) for w, _ in syn)
print(f'항목 {len(rows)}개 · 검색어 {nw}개 · 문제 {problems}건', file=sys.stderr)
print(f'덮은 코드 {len(covered):,}개 / {len(ALLC):,}개  ({100*len(covered)/len(ALLC):.1f}%)', file=sys.stderr)
print(f'덮은 수입액 {cv/1e9:.1f}십억 달러 / {TOTAL/1e9:.1f}  ({100*cv/TOTAL:.1f}%)', file=sys.stderr)
for r in rows:
    if r[7] != 'OK' and not r[7].startswith('이미검색됨'):
        print('  !', r[0], '→', r[2], '|', r[7], file=sys.stderr)
