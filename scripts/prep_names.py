# 관세법 별표 관세율표 HWP에서 류·호·소호그룹·소호 명칭 계층을 뽑는다.
#   python scripts/prep_names.py
# 출력: hs_names.json {h2,h4,h5,h6}
#
# 표의 구조가 두 가지라 그대로 읽으면 호 이름이 빈다.
#   (가) 소호가 여럿인 호 — 호 이름 행이 따로 있고 소호 칸이 비어 있다.
#           8535 | 　  | 전기회로의 개폐용·보호용…    |
#   (나) 소호가 '00' 하나뿐인 호 — 호 행과 소호 행이 한 줄로 합쳐져 호 이름 행이 없다.
#           2709 | 00 | 석유와 역청유(원유로 한정한다) |
# (나)를 놓쳐 1,228개 중 957개만 잡혔었다. 이제 소호에서 호 이름을 올려 채운다.
# 류 이름도 「주:」 앞까지 여러 줄에 걸쳐 있어 첫 줄만 읽으면 잘린다.
import json, os, re, struct, sys, zlib
import olefile

from paths import DATA, TAR, HWP  # noqa: E402

OUT = os.path.join(DATA, 'hs_names.json')
YEAR = 2026

# ---------------------------------------------------------------- HWP 본문
def cells_of(path):
    f = olefile.OleFileIO(path)
    out = []
    for n in sorted('/'.join(s) for s in f.listdir() if s[0] == 'BodyText'):
        d = f.openstream(n).read()
        try:
            d = zlib.decompress(d, -15)
        except Exception:
            pass
        i = 0
        while i < len(d) - 4:
            hdr = struct.unpack('<I', d[i:i + 4])[0]
            tag, sz = hdr & 0x3ff, (hdr >> 20) & 0xfff
            if sz == 0xfff:
                sz = struct.unpack('<I', d[i + 4:i + 8])[0]; i += 4
            i += 4
            if tag == 67:                                    # PARA_TEXT
                s = d[i:i + sz].decode('utf-16le', 'ignore')
                out.append(''.join(c for c in s if ord(c) > 31).strip())
            i += sz
    return out

cells = cells_of(HWP)
print(f'본문 조각 {len(cells):,}개', file=sys.stderr)

# ---------------------------------------------------------------- 류 이름
BLANK = '\u3000'
h2 = {}
for i, line in enumerate(cells):
    m = re.fullmatch(r'제(\d+)류', line)
    if not m:
        continue
    key = '%02d' % int(m.group(1))
    if key in h2:
        continue
    parts = []
    for nxt in cells[i + 1:i + 6]:                           # 「주:」 앞까지가 류 이름
        nxt = nxt.strip()
        if nxt.startswith('주') or not nxt or nxt == BLANK:
            break
        parts.append(nxt)
    if parts:
        s = parts[0]
        for p in parts[1:]:                                  # 「…검사기기·」 + 「정밀기기…」
            s = s + p if s.endswith(('·', '‧', '-')) else s + ' ' + p
        h2[key] = re.sub(r'\s+', ' ', s).strip(' ,')

# ---------------------------------------------------------------- 호·소호
# 한 행의 칸 수가 일정하지 않다. 소호그룹 행은 세율 칸이 없어 3칸뿐이고
#   8109 | 2 | 지르코늄의 괴(塊), 가루          ← 3칸
#   8109 | 21| 하프늄 함유량이…            | 3  ← 4칸
# 4칸씩 건너뛰면 어긋나 행 하나를 통째로 잃는다(8109.21이 그랬다).
# 그래서 보폭을 고정하지 않고 「행 머리」를 먼저 찾아 그 사이를 한 행으로 본다.
def is_head(i):
    if not re.fullmatch(r'\d{4}', cells[i]) or i + 1 >= len(cells):
        return False
    nxt = cells[i + 1].strip(BLANK + ' ')
    return nxt == '' or (nxt.isdigit() and len(nxt) <= 2)

heads = [i for i in range(len(cells)) if is_head(i)]
h4, h5, h6, seen4 = {}, {}, {}, set()
for k, i in enumerate(heads):
    end = heads[k + 1] if k + 1 < len(heads) else len(cells)
    rec = cells[i + 1:end]
    c0 = cells[i]
    seen4.add(c0)
    sub = rec[0].strip(BLANK + ' ') if rec else ''
    nm = rec[1].strip(BLANK + ' ') if len(rec) > 1 else ''
    if not nm:
        continue
    if sub == '':
        h4.setdefault(c0, nm)                                # (가) 호 이름 행
    elif len(sub) == 1:
        h5.setdefault(c0 + sub, nm)
    else:
        h6.setdefault(c0 + sub, nm)

# (나) 호 이름 행이 없는 호는 소호에서 올려 채운다
filled = 0
for c4 in sorted(seen4):
    if c4 in h4:
        continue
    subs = sorted(k for k in h6 if k[:4] == c4)
    src = (c4 + '00') if (c4 + '00') in h6 else (subs[0] if subs else None)
    if src:
        h4[c4] = h6[src]
        filled += 1

print(f'류 {len(h2)} · 호 {len(h4)}(소호에서 올린 것 {filled}) · 소호그룹 {len(h5)} · 소호 {len(h6)}',
      file=sys.stderr)

# ---------------------------------------------------------------- 대조
try:
    import duckdb
    con = duckdb.connect(TAR, read_only=True)
    db4 = {r[0] for r in con.execute(
        f'select distinct substr(hs10,1,4) from fct_applied_rate where year={YEAR}').fetchall()}
    db6 = {r[0] for r in con.execute(
        f'select distinct substr(hs10,1,6) from fct_applied_rate where year={YEAR}').fetchall()}
    m4, m6 = sorted(db4 - set(h4)), sorted(db6 - set(h6))
    print(f'DB 대조({YEAR}년) — 호 {len(db4)-len(m4)}/{len(db4)} 빈 곳 {len(m4)}'
          f' · 소호 {len(db6)-len(m6)}/{len(db6)} 빈 곳 {len(m6)}', file=sys.stderr)
    for k in m4[:15]:
        print('   호 없음', k, file=sys.stderr)
    for k in m6[:15]:
        print('   소호 없음', k, file=sys.stderr)
except Exception as e:
    print(f'DB 대조 건너뜀: {e}', file=sys.stderr)

json.dump({'h2': h2, 'h4': h4, 'h5': h5, 'h6': h6},
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print(f'저장 {OUT} ({os.path.getsize(OUT)//1024}KB)', file=sys.stderr)
