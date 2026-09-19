# NOTICE — 자료에 관한 고지

[`LICENSE`](LICENSE)(MIT)는 **이 저장소의 코드와 문서에만** 적용된다.
아래 원자료는 그 대상이 아니며 각 제공기관의 조건을 따른다.

## 원자료

| 자료 | 제공 | 조건 |
|---|---|---|
| 연도별 HSK 10단위 관세율표·주요세율보기 화면(2007~2026) | 관세청 관세법령정보포털(CLIP) | 같은 자료의 공공데이터포털 공개본 「품목번호별 관세율표」(15051179)가 공공누리 제1유형 — **출처표시 의무**. 화면 자체에는 공공누리 표시가 없다 |
| 품목·국가별 월별 수출입 실적 | 관세청 무역통계 OpenAPI | 공공누리 제1유형 — 출처표시 의무 |
| 관세법 별표 관세율표, 양허관세 규정 별표 | 국가법령정보센터 | 공공저작물 |

**공공누리 제1유형은 출처표시가 의무이고, 빠뜨리면 이용허락이 자동으로 종료된다.**
모든 화면의 아래쪽에 출처를 적어 두었으므로, 재배포할 때 그대로 유지해야 한다.

관세청이 이 사이트를 후원하거나 특수 관계에 있는 것으로 오인하게 하는 표시를 해서는 안 된다.

## 가공한 자료의 출처

이 저장소는 자료를 직접 수집하지 않는다. 두 저장소에서 읽어 온다.

- 세율 — [KCSTARIFF](https://github.com/pilsunchoi/KCSTARIFF) (`fct_applied_rate`, `tariff_code`)
- 무역액 — [KCSDB2](https://github.com/pilsunchoi/KCSDB2) (`fact_trade`, `dim_country`)

## 우리가 계산한 것과 법적 효력

화면에 보이는 **실행세율은 관세청이 공표한 값이 아니다.** KCSTARIFF가 관세법 제50조·
FTA 관세특례법 제5조·양허관세 규정 제6조를 해석해 계산한 파생값이고, 이 저장소는 그것을
원산지·연도별로 늘어놓아 보여 줄 뿐이다.

관세법령정보포털은 10단위 세율이 참고용이며 법적 효력이 없다고 밝힌다.
**세액 계산이나 수입신고에는 관세법 별표 관세율표와 해당 규정의 원문을 확인해야 하며,
인용하거나 재배포할 때는 파생값임을 함께 밝힌다.**

「명목 관세액」으로 적힌 값은 법정 실행세율에 수입액을 곱한 것이다. 감면·면세·환급·보세가
빠져 있어 실제 관세 수입보다 훨씬 크다. 「FTA로 깎인 몫」은 협정을 100% 활용했다고 가정한
상한이다 — 원산지증명을 받지 못해 MFN을 낸 물량은 자료에 드러나지 않는다.

---

This NOTICE accompanies the MIT licence in `LICENSE`, which covers the source code and
documentation only. The underlying tariff and trade data remain subject to the terms of the
Korea Customs Service; the same data as published on the Korean open data portal is released
under the Korea Open Government License Type 1, which makes attribution mandatory. The
applicable-rate figures shown here are derived from the statutory priority rules by
[KCSTARIFF](https://github.com/pilsunchoi/KCSTARIFF), not official determinations, and the
portal states that 10-digit rates are for reference only and carry no legal effect.
