"""SQLite experiment registry with per-experiment artifact directories."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from quantfund.research.experiment import ExperimentConfig, ExperimentResult


class ExperimentRegistry:
    """Query store for experiments; artifacts live beside the DB."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "registry.sqlite"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    config_hash TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    dataset_version TEXT NOT NULL,
                    family_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    research_eligibility TEXT NOT NULL,
                    score_total REAL,
                    rejection_reasons TEXT,
                    created_at TEXT NOT NULL,
                    artifacts_path TEXT,
                    config_json TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trial_counts (
                    family_id TEXT PRIMARY KEY,
                    n_experiments INTEGER NOT NULL,
                    n_param_combinations INTEGER NOT NULL,
                    n_strategies INTEGER NOT NULL
                )
                """
            )
            # Phase 6 — campaign records + append-only event log
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS campaigns (
                    campaign_id TEXT PRIMARY KEY,
                    config_hash TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    state TEXT NOT NULL,
                    sealed INTEGER NOT NULL DEFAULT 0,
                    config_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS campaign_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS campaign_trial_counts (
                    campaign_id TEXT PRIMARY KEY,
                    n_candidates INTEGER NOT NULL,
                    n_experiments INTEGER NOT NULL,
                    n_validation_trials INTEGER NOT NULL,
                    n_test_evaluations INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def artifact_dir(self, experiment_id: str) -> Path:
        path = self.root / experiment_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def already_run(self, config_hash: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT experiment_id FROM experiments WHERE config_hash = ? LIMIT 1",
                (config_hash,),
            ).fetchone()
        return row["experiment_id"] if row else None

    def count_trials(self, family_id: str) -> dict[str, int]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trial_counts WHERE family_id = ?",
                (family_id,),
            ).fetchone()
        if not row:
            return {
                "n_experiments": 0,
                "n_param_combinations": 0,
                "n_strategies": 0,
            }
        return {
            "n_experiments": int(row["n_experiments"]),
            "n_param_combinations": int(row["n_param_combinations"]),
            "n_strategies": int(row["n_strategies"]),
        }

    def _bump_trials(self, conn: sqlite3.Connection, config: ExperimentConfig) -> int:
        row = conn.execute(
            "SELECT * FROM trial_counts WHERE family_id = ?",
            (config.family_id,),
        ).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO trial_counts(family_id, n_experiments, n_param_combinations, n_strategies)
                VALUES (?, 1, 1, 1)
                """,
                (config.family_id,),
            )
            return 1
        n_exp = int(row["n_experiments"]) + 1
        # Approximate unique params/strategies via cumulative counts
        n_param = int(row["n_param_combinations"]) + 1
        n_strat = int(row["n_strategies"]) + 1
        conn.execute(
            """
            UPDATE trial_counts
            SET n_experiments = ?, n_param_combinations = ?, n_strategies = ?
            WHERE family_id = ?
            """,
            (n_exp, n_param, n_strat, config.family_id),
        )
        return n_exp

    def put(
        self,
        config: ExperimentConfig,
        result: ExperimentResult,
        *,
        equity_curve: list[dict[str, Any]] | None = None,
    ) -> Path:
        art = self.artifact_dir(config.experiment_id)
        (art / "config.json").write_text(
            json.dumps(config.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )
        (art / "result.json").write_text(
            json.dumps(result.to_json_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        if equity_curve is not None:
            pd.DataFrame(equity_curve).to_parquet(art / "equity.parquet", index=False)

        score_total = None
        if result.score and "total" in result.score:
            score_total = float(result.score["total"])

        with self._connect() as conn:
            n_trials = self._bump_trials(conn, config)
            conn.execute(
                """
                INSERT OR REPLACE INTO experiments(
                    experiment_id, config_hash, strategy_id, strategy_version,
                    dataset_id, dataset_version, family_id, status, purpose,
                    research_eligibility, score_total, rejection_reasons,
                    created_at, artifacts_path, config_json, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config.experiment_id,
                    result.config_hash,
                    config.strategy_id,
                    config.strategy_version,
                    config.dataset_id,
                    config.dataset_version,
                    config.family_id,
                    result.status,
                    config.purpose,
                    config.research_eligibility,
                    score_total,
                    json.dumps(result.rejection_reasons),
                    result.created_at,
                    str(art),
                    json.dumps(config.model_dump(mode="json"), default=str),
                    json.dumps(result.to_json_dict(), default=str),
                ),
            )
            conn.commit()
        # Persist trial count onto result file for audit (update n_trials)
        updated = result.model_copy(update={"n_trials_in_family": n_trials, "artifacts_path": str(art)})
        (art / "result.json").write_text(
            json.dumps(updated.to_json_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return art

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def find(
        self,
        *,
        strategy_id: str | None = None,
        dataset_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if strategy_id:
            clauses.append("strategy_id = ?")
            params.append(strategy_id)
        if dataset_id:
            clauses.append("dataset_id = ?")
            params.append(dataset_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM experiments{where} ORDER BY created_at",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Phase 6 campaign APIs ---

    def create_campaign(
        self,
        *,
        campaign_id: str,
        config_hash: str,
        purpose: str,
        state: str,
        config_json: dict[str, Any],
        created_at: str,
    ) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT campaign_id FROM campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if existing:
                raise FileExistsError(f"campaign already exists: {campaign_id}")
            conn.execute(
                """
                INSERT INTO campaigns(
                    campaign_id, config_hash, purpose, state, sealed,
                    config_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    campaign_id,
                    config_hash,
                    purpose,
                    state,
                    json.dumps(config_json, default=str),
                    created_at,
                    created_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO campaign_trial_counts(
                    campaign_id, n_candidates, n_experiments,
                    n_validation_trials, n_test_evaluations
                ) VALUES (?, 0, 0, 0, 0)
                """,
                (campaign_id,),
            )
            conn.commit()
        self.append_campaign_event(
            campaign_id=campaign_id,
            event_type="campaign_created",
            payload={
                "config_hash": config_hash,
                "purpose": purpose,
                "state": state,
            },
            created_at=created_at,
        )

    def append_campaign_event(
        self,
        *,
        campaign_id: str,
        event_type: str,
        payload: dict[str, Any],
        created_at: str | None = None,
    ) -> int:
        """Append-only — never UPDATE/REPLACE prior events."""
        from datetime import datetime, timezone

        ts = created_at or datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO campaign_events(
                    campaign_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (campaign_id, event_type, json.dumps(payload, default=str), ts),
            )
            conn.execute(
                "UPDATE campaigns SET updated_at = ? WHERE campaign_id = ?",
                (ts, campaign_id),
            )
            conn.commit()
            return int(cur.lastrowid)

    def set_campaign_state(
        self, campaign_id: str, state: str, *, sealed: bool | None = None
    ) -> None:
        with self._connect() as conn:
            if sealed is None:
                conn.execute(
                    "UPDATE campaigns SET state = ? WHERE campaign_id = ?",
                    (state, campaign_id),
                )
            else:
                conn.execute(
                    "UPDATE campaigns SET state = ?, sealed = ? WHERE campaign_id = ?",
                    (state, 1 if sealed else 0, campaign_id),
                )
            conn.commit()
        self.append_campaign_event(
            campaign_id=campaign_id,
            event_type="state_transition",
            payload={"state": state, "sealed": sealed},
        )

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_campaign_events(self, campaign_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, campaign_id, event_type, payload_json, created_at
                FROM campaign_events
                WHERE campaign_id = ?
                ORDER BY event_id ASC
                """,
                (campaign_id,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d.pop("payload_json"))
            out.append(d)
        return out

    def count_campaign_trials(self, campaign_id: str) -> dict[str, int]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM campaign_trial_counts WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
        if not row:
            return {
                "n_candidates": 0,
                "n_experiments": 0,
                "n_validation_trials": 0,
                "n_test_evaluations": 0,
            }
        return {
            "n_candidates": int(row["n_candidates"]),
            "n_experiments": int(row["n_experiments"]),
            "n_validation_trials": int(row["n_validation_trials"]),
            "n_test_evaluations": int(row["n_test_evaluations"]),
        }

    def bump_campaign_trials(
        self,
        campaign_id: str,
        *,
        candidates: int = 0,
        experiments: int = 0,
        validation_trials: int = 0,
        test_evaluations: int = 0,
    ) -> dict[str, int]:
        """Monotonic increment only — never decreases."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM campaign_trial_counts WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if not row:
                conn.execute(
                    """
                    INSERT INTO campaign_trial_counts(
                        campaign_id, n_candidates, n_experiments,
                        n_validation_trials, n_test_evaluations
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        campaign_id,
                        max(0, candidates),
                        max(0, experiments),
                        max(0, validation_trials),
                        max(0, test_evaluations),
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE campaign_trial_counts SET
                        n_candidates = n_candidates + ?,
                        n_experiments = n_experiments + ?,
                        n_validation_trials = n_validation_trials + ?,
                        n_test_evaluations = n_test_evaluations + ?
                    WHERE campaign_id = ?
                    """,
                    (
                        max(0, candidates),
                        max(0, experiments),
                        max(0, validation_trials),
                        max(0, test_evaluations),
                        campaign_id,
                    ),
                )
            conn.commit()
        return self.count_campaign_trials(campaign_id)

    def is_campaign_sealed(self, campaign_id: str) -> bool:
        camp = self.get_campaign(campaign_id)
        if not camp:
            return False
        return bool(camp["sealed"])

