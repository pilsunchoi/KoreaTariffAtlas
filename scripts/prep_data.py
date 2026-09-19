# Korea Tariff Atlas 프로토타입 데이터 추출
import duckdb, json, os, sys

from paths import DATA, DOCS, TAR, TRD  # noqa: E402

NM = json.load(open(os.path.join(DATA, 'hs_names.json'), encoding='utf-8'))

YMIN, YMAX, YR = 2007, 2026, 2025          # YR = 무역 결합 기준연도(마지막 완전연도)
con = duckdb.connect()
con.execute(f"attach '{TAR}' as t (read_only)")
con.execute(f"attach '{TRD}' as k (read_only)")

# ---- 원산지군 → 실행세율 열 대응 -------------------------------------------
REG = {'FCN1': ('applied_cn', '중국'), 'FEU1': ('applied_eu', 'EU'), 'FUS1': ('applied_us', '미국'),
       'FAS1': ('applied_asean', '아세안'), 'FIN1': ('applied_in', '인도'), 'FVN1': ('applied_vn', '베트남'),
       'FCA1': ('applied_ca', '캐나다'), 'E1': ('applied_apta', 'APTA'), 'E2': ('applied_apta_bd', 'APTA(방글라)'),
       'E3': ('applied_apta_la', 'APTA(라오스)')}

# 국가×연도가 속한 원산지군 목록 → 그중 최저 세율이 그 나라의 실행세율
best = "least(a.mfn," + ",".join(
    f"coalesce(case when list_contains(r.rs,'{rg}') then a.{col} end,999)" for rg, (col, _) in REG.items()) + ")"

con.execute("""create view reg as
  select stat_cd, year, list(regime) rs from (
    select d.stat_cd, y.year, d.regime from t.dim_origin_regime d
    join (select distinct year from t.fct_applied_rate) y
      on y.year between d.from_year and d.to_year) group by 1,2""")
con.execute("""create view imp as
  select yyyymm//100 as "year", stat_cd, hs10, sum(imp_dlr) dlr, sum(imp_wgt) wgt
  from k.fact_trade where imp_dlr>0 and yyyymm//100 between 2007 and 2025 group by 1,2,3""")
con.execute(f"""create view j as
  select i.year, i.stat_cd, i.hs10, i.dlr, a.mfn, {best} best
  from imp i join t.fct_applied_rate a on a.hs10=i.hs10 and a.year=i.year
  left join reg r on r.stat_cd=i.stat_cd and r.year=i.year
  where not a.rate_undetermined and a.mfn is not null""")

out = {}
q = lambda s: con.execute(s).fetchall()

# ---- 1. 헤드라인 -----------------------------------------------------------
h = q(f"""select round(sum(dlr)/1e9,1), round(sum(dlr*best)/sum(dlr),2), round(sum(dlr*mfn)/sum(dlr),2),
  round(sum(dlr*best)/100/1e9,1), round(sum(dlr*(mfn-best))/100/1e9,1) from j where year={YR}""")[0]
out['head'] = {'year': YR, 'imports_bn': h[0], 'applied': h[1], 'mfn': h[2], 'duty_bn': h[3], 'saving_bn': h[4]}

# ---- 2. 연도별 시계열 ------------------------------------------------------
ser = q("""select year, round(sum(dlr)/1e9,1), round(sum(dlr*best)/sum(dlr),3), round(sum(dlr*mfn)/sum(dlr),3)
  from j group by 1 order by 1""")
simple = dict(q("select year, round(avg(mfn),3) from t.fct_applied_rate where not rate_undetermined group by 1"))
out['series'] = [[y, bn, ap, mf, simple.get(y)] for y, bn, ap, mf in ser]

# ---- 3. HS 2단위 (트리맵) --------------------------------------------------
hs2 = q(f"""select substr(hs10,1,2) h2, round(sum(dlr)/1e9,2), round(sum(dlr*best)/sum(dlr),2),
  round(sum(dlr*mfn)/sum(dlr),2) from j where year={YR} group by 1 order by 2 desc""")
out['hs2'] = [[h2, NM['h2'].get(h2, h2 + '류'), bn, ap, mf] for h2, bn, ap, mf in hs2]

# ---- 4. 원산지군 × 연도 (히트맵) ------------------------------------------
rows = []
for rg, (col, label) in REG.items():
    if rg in ('E2', 'E3'):
        continue
    r = dict((y, v) for y, v in q(f"""select i.year, round(sum(i.dlr*a.{col})/sum(i.dlr),2)
      from imp i join t.fct_applied_rate a on a.hs10=i.hs10 and a.year=i.year
      join t.dim_origin_regime d on d.stat_cd=i.stat_cd and i.year between d.from_year and d.to_year
      where d.regime='{rg}' and not a.rate_undetermined and a.mfn is not null group by 1 order by 1"""))
    rows.append([rg, label, [r.get(y) for y in range(YMIN, YR + 1)]])
# 무협정(어느 군에도 없는 나라)
r = dict(q(f"""select year, round(sum(dlr*mfn)/sum(dlr),2) from j
  where best>=mfn and stat_cd not in (select stat_cd from t.dim_origin_regime) group by 1 order by 1"""))
rows.append(['NONE', '무협정(MFN)', [r.get(y) for y in range(YMIN, YR + 1)]])
out['regime'] = {'years': list(range(YMIN, YR + 1)), 'rows': rows}

# ---- 5. FTA 시계: 상대별 무관세 코드 비율 / 무관세 수입 비율 ---------------
fta = []
for rg, (col, label) in REG.items():
    if rg in ('E2', 'E3'):
        continue
    zc = dict(q(f"""select year, round(100.0*count(*) filter(where {col}=0)/count(*),1)
      from t.fct_applied_rate where not rate_undetermined and {col} is not null group by 1 order by 1"""))
    val = dict(q(f"""select i.year, round(100.0*sum(case when a.{col}=0 then i.dlr else 0 end)/sum(i.dlr),1)
      from imp i join t.fct_applied_rate a on a.hs10=i.hs10 and a.year=i.year
      join t.dim_origin_regime d on d.stat_cd=i.stat_cd and i.year between d.from_year and d.to_year
      where d.regime='{rg}' and not a.rate_undetermined group by 1 order by 1"""))
    fta.append([rg, label, [zc.get(y) for y in range(YMIN, YMAX + 1)],
                [val.get(y) for y in range(YMIN, YR + 1)]])
out['fta'] = {'years': list(range(YMIN, YMAX + 1)), 'rows': fta}

# ---- 6. 올해 무엇이 바뀌었나 (2026 vs 2025 MFN 실행세율) ------------------
ch = q(f"""select a.hs10, round(b.mfn,2) as r_old, round(a.mfn,2) as r_new, coalesce(round(v.dlr/1e6,1),0) imp
  from t.fct_applied_rate a join t.fct_applied_rate b on b.hs10=a.hs10 and b.year={YMAX-1}
  left join (select hs10, sum(dlr) dlr from imp where year={YR} group by 1) v on v.hs10=a.hs10
  where a.year={YMAX} and a.mfn is not null and b.mfn is not null and abs(a.mfn-b.mfn)>1e-9
  order by imp desc""")
out['changes'] = {'from': YMAX - 1, 'to': YMAX,
                  'up': sum(1 for r in ch if r[2] > r[1]), 'down': sum(1 for r in ch if r[2] < r[1]),
                  'rows': [[c, o, n, i] for c, o, n, i in ch[:40]]}

# ---- 7. 코드 검색 색인 (2026년 전 코드) ------------------------------------
cols = ['mfn', 'applied_cn', 'applied_eu', 'applied_us', 'applied_asean', 'applied_in',
        'applied_vn', 'applied_ca', 'applied_apta']
sel = ",".join(f"round(a.{c},2)" for c in cols)
codes = q(f"""select a.hs10, c.name_ko, {sel},
   (case when a.has_W1 then 1 else 0 end)+(case when a.has_I then 2 else 0 end)
  +(case when a.specific_won_kg is not null then 4 else 0 end)
  +(case when a.floor_won_kg is not null then 8 else 0 end)
  +(case when a.rate_undetermined then 16 else 0 end)
  +(case when a.has_P1 or a.r_P3 is not null then 32 else 0 end) fl,
   a.specific_won_kg, a.floor_won_kg, a.txt_A, a.txt_W2
  from t.fct_applied_rate a join t.tariff_code c on c.hs10=a.hs10 and c.year={YMAX}
  where a.year={YMAX} order by a.hs10""")

impv = dict(q(f"select hs10, sum(dlr) from imp where year={YR} group by 1"))
upx = dict(q(f"select hs10, round(sum(dlr)/sum(wgt),4) from imp where year={YR} and wgt>0 group by 1 having sum(wgt)>0"))
top = {}
for hs, cd, nm, d in q(f"""select hs10, stat_cd, name_ko_kcs, dlr from (
    select i.hs10, i.stat_cd, c.name_ko_kcs, i.dlr,
      row_number() over (partition by i.hs10 order by i.dlr desc) rn
    from imp i left join k.dim_country c on c.stat_cd=i.stat_cd where i.year={YR}) where rn<=3"""):
    top.setdefault(hs, []).append([nm or cd, round(d / 1e6, 2)])

# MFN 이력: 변화 시점만 (연도 끝 2자리:값)
hist = {}
for hs, y, v in q("""select hs10, year, round(mfn,2) from t.fct_applied_rate
  where mfn is not null and not rate_undetermined order by hs10, year"""):
    a = hist.setdefault(hs, [])
    if not a or a[-1][1] != v:
        a.append([y, v])

rowsC = []
ctry, cidx = [], {}
def ci(n):
    if n not in cidx:
        cidx[n] = len(ctry); ctry.append(n)
    return cidx[n]

# 원산지별 세율 이력. 전 코드에 담되 변화 시점만 남기고,
# 원산지 사이에 차이가 한 번도 없었고 시점별로도 안 움직인 코드는 뺀다(파일 크기).
live = set(r[0] for r in codes)
ohist = {}
for hs, y, *vs in q("""select hs10, year, round(applied_cn,2), round(applied_eu,2), round(applied_us,2),
    round(applied_asean,2), round(applied_vn,2), round(applied_in,2), round(applied_ca,2)
  from t.fct_applied_rate where not rate_undetermined order by hs10, year"""):
    if hs not in live: continue
    a = ohist.setdefault(hs, [])
    if not a or a[-1][1] != vs:
        a.append([y, vs])
ohist = {h: v for h, v in ohist.items()
         if len(v) > 1 or any(len(set(x for x in vs if x is not None)) > 1 for _, vs in v)}

def rle(h):
    return ''.join(f"{y%100:02d}:{v:g};" for y, v in h)

for hs, nm, *rest in codes:
    rates = rest[:9]; fl = rest[9]; spec, floor, txtA, txtW2 = rest[10], rest[11], rest[12], rest[13]
    oh = ''
    if hs in ohist:
        oh = '|'.join(f"{y%100:02d}:" + ','.join('' if v is None else f"{v:g}" for v in vs)
                      for y, vs in ohist[hs])
    rowsC.append([hs, nm or '', fl, round(impv.get(hs, 0) / 1e6, 2),
                  [[ci(n), m] for n, m in top.get(hs, [])],
                  rle(hist.get(hs, [])), oh, spec, floor, txtA or txtW2 or '', upx.get(hs), *rates])

out['names'] = {'h2': NM['h2'], 'h4': NM['h4'], 'h5': NM['h5'], 'h6': NM['h6']}
out['countries'] = ctry
out['codes'] = {'cols': ['hs10', 'leaf', 'flags', 'imp_musd', 'top3', 'hist', 'ohist', 'spec', 'floor',
                         'txt', 'usdkg', 'mfn', 'cn', 'eu', 'us', 'asean', 'in', 'vn', 'ca', 'apta'],
                'rows': rowsC}
out['meta'] = {'year': YMAX, 'trade_year': YR, 'n_codes': len(rowsC),
               'trade_last': q("select max(yyyymm) from k.fact_trade")[0][0]}

out['shares'] = q(f"""select coalesce(d.regime,'NONE') rg, round(sum(i.dlr)/1e9,1)
  from imp i left join (select stat_cd, min(regime) regime from t.dim_origin_regime
    where regime like 'F%' and {YR} between from_year and to_year group by 1) d on d.stat_cd=i.stat_cd
  where i.year={YR} group by 1 order by 2 desc""")

p = os.path.join(DOCS, 'atlas-data.js')
with open(p, 'w', encoding='utf-8') as fp:
    fp.write('window.ATLAS=')
    json.dump(out, fp, ensure_ascii=False, separators=(',', ':'))
    fp.write(';')
print('wrote', p, os.path.getsize(p) // 1024, 'KB', file=sys.stderr)
print(json.dumps(out['head'], ensure_ascii=False), file=sys.stderr)
print(out['series'][-3:], file=sys.stderr)
print(out['hs2'][:3], file=sys.stderr)
print(out['changes']['up'], out['changes']['down'], out['changes']['rows'][:3], file=sys.stderr)
print([r for r in rowsC if r[0] in ('0904210000','2711110000')], file=sys.stderr)
