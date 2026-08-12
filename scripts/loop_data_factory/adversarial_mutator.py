"""Script wrapper for deterministic adversarial loop-case mutations."""

from __future__ import annotations

import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from xagent.loop_data_factory.adversarial_mutator import (  # noqa: E402,F401
    LOOP_MUTATIONS,
    MUTATION_VERSION,
    build_mutation_plan_from_coverage,
    mutate_case,
    mutate_cases,
)
