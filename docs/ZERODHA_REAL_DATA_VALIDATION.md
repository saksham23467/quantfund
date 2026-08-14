# Zerodha Real Data Validation

## Prominence

Historical-data validation only. No broker order submission occurred.

- Provider: `ZERODHA`
- Data: `REAL HISTORICAL API`
- Result: `PASS`
- Date range: `2024-01-01` → `2024-06-28`
- Interval: `1DAY`
- Price policy: `unknown` (RAW as returned; adjusted not invented)

## Security verification

- orders_submitted: `0`
- place_order_called: `0`
- broker_write_attempts: `0`
- live_trading: `DISABLED`
- kill_switch: `ARMED`
- paper_trading: `NOT_STARTED`
- broker_write_capability: `DISABLED`

## Aggregate

| symbol | bars | missing sessions | quality errors | warnings | CA coverage | eligibility |
|---|---:|---:|---:|---:|---|---|
| RELIANCE | 123 | 2 | 5 | 0 | PARTIAL | DEVELOPMENT_ONLY |
| TCS | 123 | 2 | 5 | 0 | PARTIAL | DEVELOPMENT_ONLY |
| INFY | 123 | 2 | 5 | 0 | PARTIAL | DEVELOPMENT_ONLY |
| HDFCBANK | 123 | 2 | 5 | 0 | PARTIAL | DEVELOPMENT_ONLY |
| ICICIBANK | 123 | 2 | 5 | 0 | PARTIAL | DEVELOPMENT_ONLY |
| SBIN | 123 | 2 | 5 | 0 | PARTIAL | DEVELOPMENT_ONLY |
| ITC | 123 | 2 | 5 | 0 | PARTIAL | DEVELOPMENT_ONLY |
| LT | 123 | 2 | 5 | 0 | PARTIAL | DEVELOPMENT_ONLY |

## Per-symbol baseline (summary)

### RELIANCE
- Bars: `123` (2024-01-01 → 2024-06-28)
- Instrument token: `738561`
- Dataset hash: `sha256:5012dac0bfae34bcc8ddaae48f8264037233c3ca17f18a1130e59fd7ff9a532f`
- Calendar coverage: `0.983607` (missing=2, unexpected=3)
- Quality errors/warnings: `5` / `0`
- CA: count=`23` coverage=`PARTIAL`
- Eligibility: `DEVELOPMENT_ONLY`
- Leakage: `PASS`
- Reproducibility: `PASS`
- Next-bar-open: `PASS`
- buy_and_hold: return=`0.10319104878530361` trades=`1` sharpe=`1.604547011453751` dd=`-0.03982237269100574`
- ma_cross: return=`-0.01926483115473354` trades=`25` sharpe=`-0.1529229559986144` dd=`-0.12297991856327938`
- momentum: return=`-0.12976685375502262` trades=`41` sharpe=`-1.7834044480032343` dd=`-0.18269188005029724`
- mean_reversion: return=`0.06374376618482813` trades=`20` sharpe=`0.9605614123111729` dd=`-0.06686633396033477`
- vol_breakout: return=`-0.12360097266378767` trades=`48` sharpe=`-1.8312668063047437` dd=`-0.19094924116088643`
- research_runner_buy_and_hold: status=`exploratory_only` hash=`sha256:685f44277f7f621cebab506bf1f3362dfff7ccf8493fbea51c16028945ce6541`

### TCS
- Bars: `123` (2024-01-01 → 2024-06-28)
- Instrument token: `2953217`
- Dataset hash: `sha256:30b130ac452651dcc34083872c53771fc39c345bfc5b7b6a388b60209cf3fb34`
- Calendar coverage: `0.983607` (missing=2, unexpected=3)
- Quality errors/warnings: `5` / `0`
- CA: count=`77` coverage=`PARTIAL`
- Eligibility: `DEVELOPMENT_ONLY`
- Leakage: `PASS`
- Reproducibility: `PASS`
- Next-bar-open: `PASS`
- buy_and_hold: return=`0.011581082708616908` trades=`1` sharpe=`0.2837252007174547` dd=`-0.06772067903946666`
- ma_cross: return=`0.0417604736776358` trades=`27` sharpe=`0.7225329071247555` dd=`-0.07013929955941899`
- momentum: return=`-0.024122646826267413` trades=`31` sharpe=`-0.27218477340481245` dd=`-0.12567993976881922`
- mean_reversion: return=`-0.013490609186168179` trades=`20` sharpe=`-0.2795995164855956` dd=`-0.06093512112658668`
- vol_breakout: return=`-0.145327625942415` trades=`39` sharpe=`-3.632850518185632` dd=`-0.14532762594241502`
- research_runner_buy_and_hold: status=`exploratory_only` hash=`sha256:0baf1735acf21531fe2dada0fb3c549993c4d44ae5fd4a8e86eb80f810fab994`

### INFY
- Bars: `123` (2024-01-01 → 2024-06-28)
- Instrument token: `408065`
- Dataset hash: `sha256:5391deab185fb6c576660b51513e1ac30d47f06b4cb6741a8c7b6ad5e267a09e`
- Calendar coverage: `0.983607` (missing=2, unexpected=3)
- Quality errors/warnings: `5` / `0`
- CA: count=`40` coverage=`PARTIAL`
- Eligibility: `DEVELOPMENT_ONLY`
- Leakage: `PASS`
- Reproducibility: `PASS`
- Next-bar-open: `PASS`
- buy_and_hold: return=`0.005992220723965991` trades=`1` sharpe=`0.16578983676740067` dd=`-0.0995178308185451`
- ma_cross: return=`-0.11037397271391647` trades=`31` sharpe=`-1.6184109177614132` dd=`-0.17609536296769954`
- momentum: return=`-0.11272740257418579` trades=`35` sharpe=`-1.967103271716057` dd=`-0.17369710477401926`
- mean_reversion: return=`-0.04538020925312669` trades=`8` sharpe=`-0.5593932341081322` dd=`-0.16233752873376522`
- vol_breakout: return=`-0.08448131721477636` trades=`41` sharpe=`-1.759618916926526` dd=`-0.150515484194952`
- research_runner_buy_and_hold: status=`exploratory_only` hash=`sha256:14c3231995aba3e959ba1f9f93bada942150012a3fea06151beff8e367dd736a`

### HDFCBANK
- Bars: `123` (2024-01-01 → 2024-06-28)
- Instrument token: `341249`
- Dataset hash: `sha256:11ad54fa2d2a00de95c41ea9dadb81bfc82f1c5659e9c8cd0a7a6c6e246432cd`
- Calendar coverage: `0.983607` (missing=2, unexpected=3)
- Quality errors/warnings: `5` / `0`
- CA: count=`22` coverage=`PARTIAL`
- Eligibility: `DEVELOPMENT_ONLY`
- Leakage: `PASS`
- Reproducibility: `PASS`
- Next-bar-open: `PASS`
- buy_and_hold: return=`-0.004862513769362975` trades=`1` sharpe=`-0.027700312656635456` dd=`-0.0918045137693631`
- ma_cross: return=`-0.040248268721089886` trades=`23` sharpe=`-0.33804191955956453` dd=`-0.14123920581458047`
- momentum: return=`-0.1868170486263787` trades=`31` sharpe=`-2.145634941892073` dd=`-0.2451150917289427`
- mean_reversion: return=`0.14333583368756653` trades=`19` sharpe=`2.0926228714599766` dd=`-0.05893527472776604`
- vol_breakout: return=`-0.15563461448522065` trades=`48` sharpe=`-2.213230795036827` dd=`-0.1823339867780362`
- research_runner_buy_and_hold: status=`exploratory_only` hash=`sha256:3a7e9d9d0a0d7729b248fb7d0e4bf5261a3b595466c818b15802598824e3fa66`

### ICICIBANK
- Bars: `123` (2024-01-01 → 2024-06-28)
- Instrument token: `1270529`
- Dataset hash: `sha256:e8ca7ac7f9743ebc64842a26cf73eeda04a98749da49afc2bed808ad668104a1`
- Calendar coverage: `0.983607` (missing=2, unexpected=3)
- Quality errors/warnings: `5` / `0`
- CA: count=`17` coverage=`PARTIAL`
- Eligibility: `DEVELOPMENT_ONLY`
- Leakage: `PASS`
- Reproducibility: `PASS`
- Next-bar-open: `PASS`
- buy_and_hold: return=`0.10078140246253442` trades=`1` sharpe=`1.7335307637530784` dd=`-0.041024686500145076`
- ma_cross: return=`-0.0617508770562436` trades=`29` sharpe=`-0.6324183349911564` dd=`-0.1222848620859743`
- momentum: return=`-0.06723028857966595` trades=`35` sharpe=`-0.734809150348909` dd=`-0.13293534059388531`
- mean_reversion: return=`0.17347143589644176` trades=`7` sharpe=`1.7486991207034688` dd=`-0.07256530459348377`
- vol_breakout: return=`-0.045678314336679016` trades=`40` sharpe=`-0.6043443647603592` dd=`-0.11808313100109648`
- research_runner_buy_and_hold: status=`exploratory_only` hash=`sha256:6bdd0ed2db8b85dd694270fce239a01cad50c9e8e03fec94faae132c5b97ac4b`

### SBIN
- Bars: `123` (2024-01-01 → 2024-06-28)
- Instrument token: `779521`
- Dataset hash: `sha256:ba1271a2ef33772dd43bdf8df025f6e8b81ac1a8723ebb7dd962368f978e68ce`
- Calendar coverage: `0.983607` (missing=2, unexpected=3)
- Quality errors/warnings: `5` / `0`
- CA: count=`19` coverage=`PARTIAL`
- Eligibility: `DEVELOPMENT_ONLY`
- Leakage: `PASS`
- Reproducibility: `PASS`
- Next-bar-open: `PASS`
- buy_and_hold: return=`0.15933825085535958` trades=`1` sharpe=`1.7257220033814589` dd=`-0.08349686578966004`
- ma_cross: return=`0.29875838505956764` trades=`5` sharpe=`1.8724313392330687` dd=`-0.13874573139028198`
- momentum: return=`0.24358105956449894` trades=`7` sharpe=`1.5670507019522133` dd=`-0.13897287531669167`
- mean_reversion: return=`0.17723703647647948` trades=`9` sharpe=`1.3262232172153723` dd=`-0.13850538614823243`
- vol_breakout: return=`-0.12759846044114387` trades=`40` sharpe=`-1.2271238337918424` dd=`-0.1791578526120822`
- research_runner_buy_and_hold: status=`exploratory_only` hash=`sha256:44ceafd6a3673a70ec11907535bb76d8362c3f617225001683052742839cc5b1`

### ITC
- Bars: `123` (2024-01-01 → 2024-06-28)
- Instrument token: `424961`
- Dataset hash: `sha256:94fa51aff703ddd7255f6aa087e292bd33e1df7faa5954eec55f0c96adfe6ead`
- Calendar coverage: `0.983607` (missing=2, unexpected=3)
- Quality errors/warnings: `5` / `0`
- CA: count=`27` coverage=`PARTIAL`
- Eligibility: `DEVELOPMENT_ONLY`
- Leakage: `PASS`
- Reproducibility: `PASS`
- Next-bar-open: `PASS`
- buy_and_hold: return=`-0.0485081621727641` trades=`1` sharpe=`-1.03355588538554` dd=`-0.07806190570035847`
- ma_cross: return=`-0.06829688083138152` trades=`31` sharpe=`-1.130660577707487` dd=`-0.08762868023108995`
- momentum: return=`-0.128077059103754` trades=`33` sharpe=`-1.795177291256699` dd=`-0.13047653198592932`
- mean_reversion: return=`-0.06094779124974159` trades=`24` sharpe=`-1.0724900813537794` dd=`-0.1166108588650485`
- vol_breakout: return=`-0.13335694173651913` trades=`42` sharpe=`-3.7659538627790967` dd=`-0.13335694173651907`
- research_runner_buy_and_hold: status=`exploratory_only` hash=`sha256:bef3af9516b6ad8c274f61d8c86b19fc77a24b2ce91186ca9e84f7c9f5e7e1e6`

### LT
- Bars: `123` (2024-01-01 → 2024-06-28)
- Instrument token: `2939649`
- Dataset hash: `sha256:7695b5a4b68ec5a52eba29b31e037284ad16976d2eae8738770e1f5a43e4a832`
- Calendar coverage: `0.983607` (missing=2, unexpected=3)
- Quality errors/warnings: `5` / `0`
- CA: count=`25` coverage=`PARTIAL`
- Eligibility: `DEVELOPMENT_ONLY`
- Leakage: `PASS`
- Reproducibility: `PASS`
- Next-bar-open: `PASS`
- buy_and_hold: return=`0.0027625967604372192` trades=`1` sharpe=`0.11649765304010289` dd=`-0.07602514200742368`
- ma_cross: return=`-0.11618568342447366` trades=`29` sharpe=`-1.0058267867722785` dd=`-0.1381173260239907`
- momentum: return=`-0.12659519752732984` trades=`33` sharpe=`-1.0197180234853023` dd=`-0.15340177195226926`
- mean_reversion: return=`0.0848247720847457` trades=`17` sharpe=`1.138218327747794` dd=`-0.05758341766604858`
- vol_breakout: return=`-0.17360619444345615` trades=`48` sharpe=`-1.7535286504178615` dd=`-0.1822555801062075`
- research_runner_buy_and_hold: status=`exploratory_only` hash=`sha256:610d93dad9247b5fccd9f9cc68d5b5b8c477497a53e1dec5673810224cb37f15`

## Zerodha vs yfinance (diagnostic)

```json
{
  "symbol": "RELIANCE",
  "date_range": {
    "start": "2024-01-01",
    "end": "2024-06-28"
  },
  "zerodha_rows": 123,
  "yfinance_rows": 119,
  "common_rows": 90,
  "zerodha_only_rows": 33,
  "yfinance_only_rows": 29,
  "ohlc_differences": 90,
  "volume_differences": 90,
  "warnings": [
    "Do not declare either source correct solely because values differ.",
    "Eligibility unchanged."
  ],
  "note": "Diagnostic only \u2014 does not change eligibility."
}
```

## Remaining blockers

- Zerodha historical remains `non_exchange` / DEVELOPMENT_ONLY under existing gates
- `price_policy=unknown` until adjustment semantics are independently proven
- Calendar/PIT/delisted/CA completeness still required for RESEARCH_ELIGIBLE
- No eligibility shortcut for provider==zerodha

## Explicit statement

> Historical-data validation only. No broker order submission occurred.

