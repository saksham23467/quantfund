.PHONY: setup test smoke phase1-dataset phase2-demo phase3-demo phase35-pilot phase4-demo phase5-demo phase6-demo phase7-demo phase8-demo phase9-demo phase9a-demo phase9b-demo phase10-demo phase11-demo phase11-preflight phase11-connectivity phase11-paper phase11-replay phase11-report phase12-demo phase12-preflight phase12-paper phase12-replay phase12-report phase13-demo phase13-preflight phase13-paper phase13-replay phase13-drift phase13-report phase14-demo phase14-preflight phase14-shadow phase14-paper phase14-health phase14-recovery phase14-report phase15-demo phase15-preflight phase15-connectivity phase15-shadow phase15-report phase16a-demo phase16a-preflight phase16a-connectivity phase16b-demo phase16b-preflight phase16b-live-canary zerodha-connectivity-test zerodha-order-dry-run zerodha-auth-check zerodha-login zerodha-historical-test zerodha-data-quality zerodha-research zerodha-compare zerodha-demo zerodha-real-validation phase17a-data-check phase17a-backtest phase17a-walkforward phase17a-robustness phase17a-report phase17a-demo phase17b-download phase17b-quality phase17b-ca phase17b-backtest phase17b-walkforward phase17b-report phase17b-demo phase17c-calendar phase17c-ca phase17c-certify phase17c-report phase17c-demo phase18-eligibility pit-universe-coverage phase19-strategy-research realdata-paper-preflight phase18-search phase18-backtest phase18-walkforward phase18-robustness phase18-report phase18-demo phase19-preflight phase19-paper phase19-health phase19-reconcile phase19-report phase19-replay phase19-demo phase20-validate phase20-demo phase21-preflight phase21-start phase21-status phase21-report phase21-recovery phase21-stop phase21-demo environment-check ec2-preflight deploy-ec2 enable-live-trading development-data ingest-development-data yfinance-dev-backtest ca-data-demo audit-research-package validate-research-package certify-research-package certify-dataset certify-research certify-research-data research-readiness clean

setup:
	python3.12 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest

smoke:
	.venv/bin/python scripts/run_smoke_backtest.py

phase1-dataset:
	.venv/bin/python scripts/build_phase1_dev_dataset.py

phase2-demo:
	.venv/bin/python scripts/run_phase2_research_demo.py

phase3-demo:
	.venv/bin/python scripts/run_phase3_demo.py

phase35-pilot:
	.venv/bin/python scripts/build_phase35_pilot.py

phase4-demo:
	.venv/bin/python scripts/run_phase4_demo.py

phase5-demo:
	.venv/bin/python scripts/run_phase5_demo.py

phase6-demo:
	.venv/bin/python scripts/run_phase6_demo.py

phase7-demo:
	.venv/bin/python scripts/run_phase7_demo.py

phase8-demo:
	.venv/bin/python scripts/run_phase8_demo.py

phase9-demo:
	.venv/bin/python scripts/run_phase9_demo.py

phase9a-demo:
	.venv/bin/python scripts/run_phase9a_demo.py

phase9b-demo:
	.venv/bin/python scripts/run_phase9b_demo.py

research-readiness:
	.venv/bin/python scripts/research_readiness.py $${PACKAGE:-}

phase10-demo:
	.venv/bin/python scripts/run_phase10_demo.py

phase11-demo:
	.venv/bin/python scripts/run_phase11_demo.py

phase11-preflight:
	.venv/bin/python scripts/run_phase11_preflight.py

phase11-connectivity:
	.venv/bin/python scripts/run_phase11_connectivity.py

phase11-paper:
	.venv/bin/python scripts/run_phase11_paper.py

phase11-replay:
	.venv/bin/python scripts/run_phase11_replay.py

phase11-report:
	.venv/bin/python scripts/run_phase11_report.py

phase12-demo:
	.venv/bin/python scripts/run_phase12_demo.py

phase12-preflight:
	.venv/bin/python scripts/run_phase12_preflight.py

phase12-paper:
	.venv/bin/python scripts/run_phase12_paper.py

phase12-replay:
	.venv/bin/python scripts/run_phase12_replay.py

phase12-report:
	.venv/bin/python scripts/run_phase12_report.py

phase13-demo:
	.venv/bin/python scripts/run_phase13_demo.py

phase13-preflight:
	.venv/bin/python scripts/run_phase13_preflight.py

phase13-paper:
	.venv/bin/python scripts/run_phase13_paper.py

phase13-replay:
	.venv/bin/python scripts/run_phase13_replay.py

phase13-drift:
	.venv/bin/python scripts/run_phase13_drift.py

phase13-report:
	.venv/bin/python scripts/run_phase13_report.py

phase14-demo:
	.venv/bin/python scripts/run_phase14_demo.py

phase14-preflight:
	.venv/bin/python scripts/run_phase14_preflight.py

phase14-shadow:
	.venv/bin/python scripts/run_phase14_shadow.py

phase14-paper:
	.venv/bin/python scripts/run_phase14_paper.py

phase14-health:
	.venv/bin/python scripts/run_phase14_health.py

phase14-recovery:
	.venv/bin/python scripts/run_phase14_recovery.py

phase14-report:
	.venv/bin/python scripts/run_phase14_report.py

phase15-demo:
	.venv/bin/python scripts/run_phase15_demo.py

phase15-preflight:
	.venv/bin/python scripts/run_phase15_preflight.py

phase15-connectivity:
	.venv/bin/python scripts/run_phase15_connectivity.py

phase15-shadow:
	.venv/bin/python scripts/run_phase15_shadow.py

phase15-report:
	.venv/bin/python scripts/run_phase15_report.py

phase16a-demo:
	.venv/bin/python scripts/run_phase16a_demo.py

phase16a-preflight:
	.venv/bin/python scripts/run_phase16a_preflight.py

phase16a-connectivity:
	.venv/bin/python scripts/run_phase16a_connectivity.py

phase16b-demo:
	.venv/bin/python scripts/run_phase16b_demo.py

phase16b-preflight:
	.venv/bin/python scripts/run_phase16b_preflight.py

phase16b-live-canary:
	@echo "DANGEROUS TARGET — real canary requires LIVE_TRADING=true + confirmation."
	@echo "This Makefile target will refuse unless env/args satisfy all gates."
	.venv/bin/python scripts/run_phase16b_live_canary.py --confirm "$${CONFIRM_PHRASE:-INVALID}" || true
	@echo "Note: default invocation does not place orders (fail-closed)."

zerodha-connectivity-test:
	.venv/bin/python scripts/zerodha_connectivity_test.py

zerodha-order-dry-run:
	.venv/bin/python scripts/zerodha_order_dry_run.py

zerodha-auth-check:
	@echo "=== ZERODHA AUTH CHECK (credentials presence only; secrets never printed) ==="
	.venv/bin/python scripts/run_zerodha_auth_check.py

zerodha-login:
	@echo "=== ZERODHA LOGIN (local callback → access_token in .env; no orders) ==="
	.venv/bin/python scripts/zerodha_login.py

zerodha-historical-test:
	@echo "=== ZERODHA HISTORICAL TEST (SIMULATED unless QUANTFUND_ALLOW_ZERODHA_HISTORICAL=1) ==="
	.venv/bin/python scripts/test_zerodha_historical.py --force-mock

zerodha-data-quality:
	@echo "=== ZERODHA DATA QUALITY (SIMULATED unless opted into REAL) ==="
	.venv/bin/python scripts/run_zerodha_data_quality.py --force-mock

zerodha-research:
	@echo "=== ZERODHA RESEARCH DEMO (existing ResearchRunner; no optimization; no orders) ==="
	.venv/bin/python scripts/run_zerodha_research_demo.py

zerodha-compare:
	@echo "=== ZERODHA vs YFINANCE DIAGNOSTIC (eligibility unchanged) ==="
	.venv/bin/python scripts/compare_zerodha_yfinance.py --force-mock

zerodha-demo:
	@echo "=== QUANTFUND ZERODHA HISTORICAL VALIDATION DEMO ==="
	.venv/bin/python scripts/run_zerodha_demo.py

zerodha-real-validation:
	@echo "=== QUANTFUND ZERODHA REAL HISTORICAL VALIDATION (READ-ONLY) ==="
	@echo "Requires QUANTFUND_ALLOW_ZERODHA_HISTORICAL=1 and ZERODHA_* env (or gitignored .env)."
	@echo "Never submits orders. Never prints credentials."
	.venv/bin/python scripts/run_zerodha_real_validation.py

phase17a-data-check:
	@echo "=== PHASE 17A DATA CHECK (REAL ZERODHA PACKAGES + CA; NO ORDERS) ==="
	.venv/bin/python scripts/run_phase17a_data_check.py

phase17a-backtest:
	@echo "=== PHASE 17A BACKTEST (EXISTING ResearchRunner; NO ORDERS) ==="
	.venv/bin/python scripts/run_phase17a_backtest.py

phase17a-walkforward:
	@echo "=== PHASE 17A WALK-FORWARD (EXISTING machinery; NO ORDERS) ==="
	.venv/bin/python scripts/run_phase17a_walkforward.py

phase17a-robustness:
	@echo "=== PHASE 17A ROBUSTNESS (EXISTING suite; NO ORDERS) ==="
	.venv/bin/python scripts/run_phase17a_robustness.py

phase17a-report:
	@echo "=== PHASE 17A REPORT ==="
	.venv/bin/python scripts/run_phase17a_report.py

phase17a-demo:
	@echo "=== PHASE 17A FULL DEMO (HISTORICAL ONLY; NO LIVE / NO ORDERS) ==="
	.venv/bin/python scripts/run_phase17a_demo.py

phase17b-download:
	@echo "=== PHASE 17B DOWNLOAD (REAL ZERODHA MULTI-YEAR; NO ORDERS) ==="
	.venv/bin/python scripts/run_phase17b_download.py

phase17b-quality:
	@echo "=== PHASE 17B QUALITY ==="
	.venv/bin/python scripts/run_phase17b_quality.py

phase17b-ca:
	@echo "=== PHASE 17B CORPORATE ACTIONS ==="
	.venv/bin/python scripts/run_phase17b_ca.py

phase17b-backtest:
	@echo "=== PHASE 17B BACKTEST REVALIDATION ==="
	.venv/bin/python scripts/run_phase17b_backtest.py

phase17b-walkforward:
	@echo "=== PHASE 17B WALK-FORWARD ==="
	.venv/bin/python scripts/run_phase17b_walkforward.py

phase17b-report:
	@echo "=== PHASE 17B REPORT ==="
	.venv/bin/python scripts/run_phase17b_report.py

phase17b-demo:
	@echo "=== PHASE 17B FULL DEMO (DOWNLOAD + REVALIDATE; NO LIVE / NO ORDERS) ==="
	.venv/bin/python scripts/run_phase17b_demo.py

phase17c-calendar:
	@echo "=== PHASE 17C CALENDAR COVERAGE ==="
	.venv/bin/python scripts/run_phase17c_calendar.py

phase17c-ca:
	@echo "=== PHASE 17C CORPORATE ACTIONS ==="
	.venv/bin/python scripts/run_phase17c_ca.py

phase17c-certify:
	@echo "=== PHASE 17C CERTIFY (NO BASELINE; NO ORDERS) ==="
	.venv/bin/python scripts/run_phase17c_certify.py

phase17c-report:
	@echo "=== PHASE 17C REPORT + BASELINE REGRESSION ==="
	.venv/bin/python scripts/run_phase17c_report.py

phase17c-demo:
	@echo "=== PHASE 17C FULL DEMO (CERTIFY + BASELINE; NO LIVE / NO ORDERS) ==="
	.venv/bin/python scripts/run_phase17c_demo.py

phase18-eligibility:
	@echo "=== PHASE 18 RESEARCH DATASET ELIGIBILITY (NO STRATEGY SEARCH / NO ORDERS) ==="
	.venv/bin/python scripts/run_phase18_dataset_eligibility.py

pit-universe-coverage:
	@echo "=== PIT HISTORICAL UNIVERSE COVERAGE (NO STRATEGY SEARCH / NO ORDERS) ==="
	.venv/bin/python scripts/run_pit_universe_coverage.py

phase19-strategy-research:
	@echo "=== PHASE 19 CONTROLLED STRATEGY RESEARCH (GATED / NO ORDERS / NO PROMOTION) ==="
	.venv/bin/python scripts/run_phase19_strategy_research.py

realdata-paper-preflight:
	@echo "=== REAL-MARKET-DATA PAPER PREFLIGHT (NOT LIVE / NO ORDERS / STOP BEFORE SESSION) ==="
	.venv/bin/python scripts/run_realdata_paper_preflight.py

phase18-search:
	@echo "=== PHASE 18 CONTROLLED STRATEGY SEARCH (NO LIVE / NO ORDERS) ==="
	QUANTFUND_PHASE18_MODE=$${QUANTFUND_PHASE18_MODE:-full} .venv/bin/python scripts/run_phase18_search.py

phase18-backtest:
	@echo "=== PHASE 18 BACKTEST / SCREENING ==="
	QUANTFUND_PHASE18_MODE=$${QUANTFUND_PHASE18_MODE:-demo} .venv/bin/python scripts/run_phase18_backtest.py

phase18-walkforward:
	@echo "=== PHASE 18 WALK-FORWARD (FINALISTS) ==="
	QUANTFUND_PHASE18_MODE=$${QUANTFUND_PHASE18_MODE:-demo} .venv/bin/python scripts/run_phase18_walkforward.py

phase18-robustness:
	@echo "=== PHASE 18 ROBUSTNESS (FINALISTS) ==="
	QUANTFUND_PHASE18_MODE=$${QUANTFUND_PHASE18_MODE:-demo} .venv/bin/python scripts/run_phase18_robustness.py

phase18-report:
	@echo "=== PHASE 18 REPORT ==="
	QUANTFUND_PHASE18_MODE=$${QUANTFUND_PHASE18_MODE:-demo} .venv/bin/python scripts/run_phase18_report.py

phase18-demo:
	@echo "=== PHASE 18 FULL DEMO (CONTROLLED SEARCH; NO LIVE / NO ORDERS) ==="
	QUANTFUND_PHASE18_MODE=$${QUANTFUND_PHASE18_MODE:-demo} .venv/bin/python scripts/run_phase18_demo.py

phase19-preflight:
	@echo "=== PHASE 19 PREFLIGHT (PAPER ONLY; NO LIVE / NO ORDERS) ==="
	.venv/bin/python scripts/run_phase19_preflight.py

phase19-paper:
	@echo "=== PHASE 19 CONTROLLED PAPER SESSION ==="
	QUANTFUND_PHASE19_DURATION=$${QUANTFUND_PHASE19_DURATION:-1d} .venv/bin/python scripts/run_phase19_paper.py

phase19-health:
	@echo "=== PHASE 19 HEALTH ==="
	.venv/bin/python scripts/run_phase19_health.py

phase19-reconcile:
	@echo "=== PHASE 19 RECONCILE ==="
	.venv/bin/python scripts/run_phase19_reconcile.py

phase19-report:
	@echo "=== PHASE 19 REPORT ==="
	.venv/bin/python scripts/run_phase19_report.py

phase19-replay:
	@echo "=== PHASE 19 REPLAY ==="
	.venv/bin/python scripts/run_phase19_replay.py

phase19-demo:
	@echo "=== PHASE 19 FULL DEMO (PAPER ONLY; ZERO REAL ORDERS) ==="
	QUANTFUND_PHASE19_DURATION=$${QUANTFUND_PHASE19_DURATION:-1d} .venv/bin/python scripts/run_phase19_demo.py

phase20-validate:
	@echo "=== PHASE 20 LONG-DURATION PAPER VALIDATION (NO LIVE / NO ORDERS) ==="
	QUANTFUND_PHASE20_DAYS=$${QUANTFUND_PHASE20_DAYS:-20} .venv/bin/python scripts/run_phase20_validate.py

phase20-demo:
	@echo "=== PHASE 20 PAPER VALIDATION DEMO (NO LIVE / NO ORDERS) ==="
	QUANTFUND_PHASE20_DAYS=$${QUANTFUND_PHASE20_DAYS:-20} .venv/bin/python scripts/run_phase20_demo.py

phase21-preflight:
	@echo "=== PHASE 21 PREFLIGHT (PAPER ONLY; NO LIVE / NO ORDERS) ==="
	.venv/bin/python scripts/run_phase21_preflight.py

phase21-start:
	@echo "=== PHASE 21 AUTONOMOUS REAL-TIME PAPER (ZERODHA MD; NO LIVE ORDERS) ==="
	@echo "LIVE_TRADING = DISABLED"
	@echo "BROKER_WRITE = DISABLED"
	@echo "PAPER_TRADING = ENABLED"
	@echo "KILL_SWITCH = ARMED"
	QUANTFUND_PHASE21_DAYS=$${QUANTFUND_PHASE21_DAYS:-20} .venv/bin/python scripts/run_phase21_start.py

phase21-status:
	@echo "=== PHASE 21 STATUS ==="
	.venv/bin/python scripts/run_phase21_status.py

phase21-report:
	@echo "=== PHASE 21 REPORT ==="
	.venv/bin/python scripts/run_phase21_report.py

phase21-recovery:
	@echo "=== PHASE 21 RECOVERY ==="
	.venv/bin/python scripts/run_phase21_recovery.py

phase21-stop:
	@echo "=== PHASE 21 STOP ==="
	.venv/bin/python scripts/run_phase21_stop.py

phase21-demo:
	@echo "=== PHASE 21 DEMO (MOCK ZERODHA TRANSPORT; PAPER ONLY) ==="
	QUANTFUND_PHASE21_ALLOW_MOCK=1 QUANTFUND_PHASE21_FORCE_MOCK=1 QUANTFUND_PHASE21_DAYS=$${QUANTFUND_PHASE21_DAYS:-20} .venv/bin/python scripts/run_phase21_demo.py

environment-check:
	@echo "=== EXECUTION ENVIRONMENT CHECK (NO SECRETS / NO ORDERS) ==="
	.venv/bin/python scripts/run_environment_check.py

ec2-preflight:
	@echo "=== EC2 PREFLIGHT (NO SECRETS / NO ORDERS) ==="
	.venv/bin/python scripts/run_ec2_preflight.py

deploy-ec2:
	@echo "=== DEPLOY QuantFund Mac → EC2 (NO LIVE / NO ORDERS) ==="
	chmod +x scripts/deploy_to_ec2.sh
	./scripts/deploy_to_ec2.sh

enable-live-trading:
	@echo "Refusing blind enable. Pass explicit args, e.g.:"
	@echo "  .venv/bin/python scripts/enable_live_trading.py --actor YOU --confirm I_CONFIRM_CONTROLLED_LIVE_ACTIVATION ..."
	@echo "This target does not place orders."
	@exit 1

development-data ingest-development-data:
	FILE="$(FILE)" .venv/bin/python scripts/ingest_development_data.py

yfinance-dev-backtest:
	.venv/bin/python scripts/run_yfinance_dev_backtest.py

ca-data-demo:
	.venv/bin/python scripts/run_ca_data_demo.py

validate-research-package:
	.venv/bin/python scripts/validate_research_package.py $${PACKAGE:-tests/fixtures/phase35/pilot_package}

audit-research-package:
	.venv/bin/python scripts/audit_research_package.py

certify-research-package:
	.venv/bin/python scripts/certify_research_package.py

certify-dataset:
	.venv/bin/python scripts/certify_dataset.py

certify-research:
	@.venv/bin/python scripts/certify_research_dataset.py --dataset-id india_eq_pilot_phase35 --dataset-version v1_synthetic --write; \
	code=$$?; if [ $$code -eq 0 ] || [ $$code -eq 3 ]; then exit 0; else exit $$code; fi

certify-research-data:
	.venv/bin/python scripts/run_research_data_certification.py

clean:
	rm -rf build dist *.egg-info .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
