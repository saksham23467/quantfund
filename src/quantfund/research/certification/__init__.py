"""Research dataset certification engine.

Each sub-module certifies one dimension of a :class:`ResearchDatasetPackage`.
:func:`certify_dataset` aggregates them into ``DatasetCertificationFacts`` and
evaluates those facts through the EXISTING, UNMODIFIED
``ResearchEligibilityChecker`` — the engine composes the authoritative gate, it
never re-implements or relaxes it. Verdict is RESEARCH_ELIGIBLE or
DEVELOPMENT_ONLY, failing closed on any missing/unknown fact.
"""

from quantfund.research.certification.calendar_certification import certify_calendar
from quantfund.research.certification.corporate_action_certification import (
    certify_corporate_actions,
)
from quantfund.research.certification.dataset_certification import (
    DatasetCertification,
    certify_dataset,
)
from quantfund.research.certification.delisting_certification import certify_delisting
from quantfund.research.certification.identity_certification import certify_identity
from quantfund.research.certification.immutability import (
    verify_immutable,
    write_certified_package,
)
from quantfund.research.certification.results import CertResult
from quantfund.research.certification.source_certification import certify_source
from quantfund.research.certification.universe_certification import certify_universe

__all__ = [
    "CertResult",
    "DatasetCertification",
    "certify_calendar",
    "certify_corporate_actions",
    "certify_dataset",
    "certify_delisting",
    "certify_identity",
    "certify_source",
    "certify_universe",
    "verify_immutable",
    "write_certified_package",
]
