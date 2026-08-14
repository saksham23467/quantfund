"""Central ResearchEligibilityChecker — research runner must not override."""

from __future__ import annotations

from dataclasses import dataclass, field

from quantfund.data.policy import (
    DEFAULT_ELIGIBILITY_POLICY,
    DEFAULT_QUALITY_POLICY,
    DatasetCertificationFacts,
    DatasetEligibilityPolicy,
    DataQualityPolicy,
    EligibilityLevel,
)


@dataclass
class EligibilityDecision:
    level: EligibilityLevel
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def is_research_eligible(self) -> bool:
        return self.level in {
            EligibilityLevel.RESEARCH_ELIGIBLE,
            EligibilityLevel.PRODUCTION_CANDIDATE,
        }


class ResearchEligibilityChecker:
    """Evaluate dataset facts against quality + eligibility policies.

    Does not look at backtest returns. Metrics cannot promote eligibility.
    """

    def __init__(
        self,
        eligibility_policy: DatasetEligibilityPolicy | None = None,
        quality_policy: DataQualityPolicy | None = None,
    ) -> None:
        self.eligibility_policy = eligibility_policy or DEFAULT_ELIGIBILITY_POLICY
        self.quality_policy = quality_policy or DEFAULT_QUALITY_POLICY

    def evaluate(self, facts: DatasetCertificationFacts) -> EligibilityDecision:
        blockers: list[str] = []
        notes: list[str] = []

        # Ignore forged eligibility claims in extras / lineage
        if facts.extras.get("research_eligible") is True or facts.extras.get(
            "research_eligibility"
        ) in {"research_eligible", "production_candidate"}:
            notes.append(
                "Ignored package/manifest eligibility assertion; "
                "eligibility is derived only from certified facts."
            )

        # --- Hard DEVELOPMENT_DATA lock (engineering only; quality cannot promote) ---
        data_class = (facts.data_class or facts.extras.get("data_class") or "").strip()
        if data_class.upper() == "DEVELOPMENT_DATA":
            blockers.append(
                "data_class=DEVELOPMENT_DATA cannot be research_eligible "
                "(development pipeline is permanently DEVELOPMENT_ONLY)"
            )
        if facts.source_grade in {"development", "development_free_nse"}:
            blockers.append(
                f"source_grade={facts.source_grade} is development-only "
                "(not exchange/paid research grade)"
            )

        # --- Hard development blockers ---
        if facts.source_grade in {"non_exchange", "synthetic"}:
            blockers.append(
                f"source_grade={facts.source_grade} is not exchange/paid research grade"
            )
        if (
            self.eligibility_policy.require_capability_source_bar
            and not facts.capability_source_bar_ok
        ):
            blockers.append(
                "capability_source_bar_ok=false "
                "(provider cannot satisfy research source bar)"
            )
        if self.eligibility_policy.require_calendar_verified and not facts.calendar_verified:
            blockers.append("calendar_verified=false")
        if facts.universe_completeness == "current_snapshot_only":
            blockers.append(
                "universe_completeness=current_snapshot_only "
                "(today's constituents must not stand in for history)"
            )
        if facts.universe_completeness not in self.eligibility_policy.min_universe_completeness:
            if facts.universe_completeness != "current_snapshot_only":
                blockers.append(
                    f"universe_completeness={facts.universe_completeness} "
                    f"below required {self.eligibility_policy.min_universe_completeness}"
                )
        if facts.corporate_action_coverage not in (
            self.eligibility_policy.min_corporate_action_coverage
        ):
            blockers.append(
                f"corporate_action_coverage={facts.corporate_action_coverage} insufficient"
            )
        if facts.error_count > 0:
            blockers.append(
                f"quality ERROR count={facts.error_count} codes={facts.quality_error_codes}"
            )
        if (
            not self.eligibility_policy.allow_unknown_membership_periods_for_research
            and facts.unknown_membership_session_count > 0
        ):
            blockers.append(
                f"unknown_membership_session_count={facts.unknown_membership_session_count}"
            )

        ratio = facts.membership_coverage_ratio
        if ratio is None:
            ratio = 0.0 if facts.unknown_membership_session_count > 0 else 1.0
        if ratio < self.eligibility_policy.min_membership_coverage_ratio:
            blockers.append(
                f"membership_coverage_ratio={ratio} "
                f"< required {self.eligibility_policy.min_membership_coverage_ratio}"
            )

        # full_pit claim incompatible with remaining unknowns
        if (
            facts.universe_completeness == "full_pit"
            and facts.unknown_membership_session_count > 0
        ):
            blockers.append(
                "full_pit claim rejected while unknown_membership_session_count > 0"
            )

        if facts.delisted_coverage not in (
            self.eligibility_policy.min_delisted_coverage_for_research
        ):
            blockers.append(
                f"delisted_coverage={facts.delisted_coverage} insufficient for research "
                f"(need {self.eligibility_policy.min_delisted_coverage_for_research})"
            )

        if facts.instrument_identity_issues > 0:
            blockers.append(
                f"instrument_identity_issues={facts.instrument_identity_issues}"
            )
        if facts.duplicate_bars > 0 and self.quality_policy.fail_on_duplicate_bars:
            blockers.append(f"duplicate_bars={facts.duplicate_bars}")
        if facts.missing_bars > 0 and self.quality_policy.fail_on_missing_open_session:
            blockers.append(f"missing_bars_on_open_sessions={facts.missing_bars}")
        if facts.invalid_ohlc > 0 and self.quality_policy.fail_on_invalid_ohlc:
            blockers.append(f"invalid_ohlc={facts.invalid_ohlc}")

        if (
            self.eligibility_policy.require_provenance_complete
            and not facts.provenance_complete
        ):
            blockers.append("provenance_complete=false")

        if self.eligibility_policy.require_license_not_prohibited:
            if facts.license_status == "prohibited":
                blockers.append("license_status=prohibited")
            elif facts.license_status == "expired":
                blockers.append("license_status=expired")
            elif (
                not self.eligibility_policy.allow_unknown_license_for_research
                and facts.license_status == "unknown"
            ):
                blockers.append("license_status=unknown (research requires known license)")

        # Explicit synthetic flag (Phase 7) — never research eligible
        if facts.extras.get("synthetic") is True:
            blockers.append("synthetic=true cannot be research_eligible")

        if blockers:
            return EligibilityDecision(
                level=EligibilityLevel.DEVELOPMENT_ONLY,
                reasons=[
                    "Dataset fails research-grade requirements; "
                    "marked development_only."
                ],
                blockers=blockers,
                notes=notes,
            )

        # --- Production candidate (stricter) ---
        prod_blockers: list[str] = []
        if self.eligibility_policy.production_requires_full_pit and (
            facts.universe_completeness != "full_pit"
        ):
            prod_blockers.append("production requires universe_completeness=full_pit")
        if self.eligibility_policy.production_requires_full_verified_ca and (
            facts.corporate_action_coverage != "full_verified"
        ):
            prod_blockers.append(
                "production requires corporate_action_coverage=full_verified"
            )
        if facts.delisted_coverage not in (
            self.eligibility_policy.production_requires_delisted_coverage
        ):
            prod_blockers.append(
                f"production requires delisted_coverage in "
                f"{self.eligibility_policy.production_requires_delisted_coverage}, "
                f"got {facts.delisted_coverage}"
            )
        if (
            self.eligibility_policy.production_requires_zero_quality_warnings
            and facts.warning_count > 0
        ):
            prod_blockers.append(f"production forbids warnings; got {facts.warning_count}")

        if not prod_blockers:
            return EligibilityDecision(
                level=EligibilityLevel.PRODUCTION_CANDIDATE,
                reasons=[
                    "Calendar verified, source grade acceptable, PIT universe, "
                    "corporate actions verified, quality errors absent, "
                    "delisted coverage complete."
                ],
                blockers=[],
                notes=notes,
            )

        notes.extend(prod_blockers)
        return EligibilityDecision(
            level=EligibilityLevel.RESEARCH_ELIGIBLE,
            reasons=[
                "Meets research-eligible bar (verified calendar, acceptable source, "
                "PIT universe, sufficient CA coverage, no mandatory ERRORs)."
            ],
            blockers=[],
            notes=notes
            + ["Not production_candidate due to stricter remaining requirements."],
        )
