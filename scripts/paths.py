# 저장소 안의 자리와 바깥 자료의 위치. 네 스크립트가 함께 쓴다.
#
#   scripts/  이 파일들          data/  손으로 쓰는 사전과 생성된 명칭·보고서
#   src/      화면 원본          docs/  GitHub Pages가 서빙하는 산출물(전부 생성물)
#
# 세율·무역통계 DB는 이 저장소에 없다. KCSTARIFF와 KCSDB2에서 읽어 오며,
# 다른 자리에 두었으면 환경변수로 알려 준다.
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
DOCS = os.path.join(ROOT, 'docs')
SRC = os.path.join(ROOT, 'src')

TAR = os.environ.get(
    'KCSTARIFF_DB', r'C:\Work\Projects\KCSTARIFF\data\processed\kcstariff.duckdb')
TRD = os.environ.get(
    'KCSDB2_DB', r'C:\Work\Projects\KCSDB2\data\processed\kcsdb.duckdb')
HWP = os.environ.get(
    'TARIFF_SCHEDULE_HWP',
    os.path.join(r'C:\Work\Projects\KCSTARIFF\research\data\external',
                 '관세법_별표_관세율표',
                 '관세율표_개정2022-12-31_시행2025-01-01_lsiSeq17031935.hwp'))
