"""Script wrapper for local seed-material extraction."""

from __future__ import annotations

import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from xagent.loop_data_factory.local_sample_extractor import (  # noqa: E402,F401
    LOCAL_SEED_MANIFEST,
    LOCAL_SEED_OUTPUT_DIR,
    SUPPORTED_TEXT_SUFFIXES,
    anonymize_seed_text,
    build_profile_summary,
    extract_claims,
    extract_local_seed_dir,
    infer_risk_hypotheses,
    write_local_seed_manifest,
)
