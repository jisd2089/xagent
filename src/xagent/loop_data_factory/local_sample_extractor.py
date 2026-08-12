"""Local seed-material extraction and anonymization for loop data generation."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SUPPORTED_TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".json"}
LOCAL_SEED_OUTPUT_DIR = "local_seed_extracts"
LOCAL_SEED_MANIFEST = "anonymized_seed_manifest.json"

PHONE_RE = re.compile(r"(?<!\d)(?:1[3-9]\d{9})(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
QQ_RE = re.compile(r"(?i)\bqq[:\s]*\d{5,12}\b")
WECHAT_RE = re.compile(r"(?i)\b(?:wechat|weixin|wx)[:\s]*[a-z][\w-]{5,19}\b")
NAME_FIELD_RE = re.compile(
    r"(?im)^(\s*(?:name|candidate_name|\u59d3\u540d|\u5019\u9009\u4eba)"
    r"\s*[:=]\s*)([^\n,;|]+)"
)
COMPANY_FIELD_RE = re.compile(
    r"(?im)^(\s*(?:company|employer|\u516c\u53f8|\u5355\u4f4d)\s*[:=]\s*)([^\n,;|]+)"
)
SCHOOL_FIELD_RE = re.compile(
    r"(?im)^(\s*(?:school|university|\u5b66\u6821|\u9662\u6821)"
    r"\s*[:=]\s*)([^\n,;|]+)"
)
CLAIM_HINT_RE = re.compile(
    r"(?i)(\bI\b|\bwe\b|\u6211|\u6211\u4eec|\u4e3b\u5bfc|\u8d1f\u8d23|"
    r"\u63a8\u52a8|\u4f18\u5316|\u642d\u5efa|\u89e3\u51b3|\u63d0\u5347|"
    r"\u964d\u4f4e|%|\d+\s*(?:percent|pct))"
)
METRIC_RE = re.compile(r"(?:\d+(?:\.\d+)?\s*%|\d+\s*(?:percent|pct))", re.I)


def extract_local_seed_dir(seed_dir: Path) -> dict[str, Any]:
    """Extract anonymized seed summaries from a local directory.

    The extractor is intentionally conservative and stdlib-only. It supports
    text-like files now and records binary/unsupported documents as skipped so
    later PDF/DOCX parsing can extend the same manifest contract.
    """

    root = seed_dir.resolve()
    if not root.exists():
        raise FileNotFoundError(f"seed_dir does not exist: {seed_dir}")
    if not root.is_dir():
        raise NotADirectoryError(f"seed_dir is not a directory: {seed_dir}")

    seeds: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    pii_totals = {"phone": 0, "email": 0, "id_card": 0, "qq": 0, "wechat": 0}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel_path = path.relative_to(root).as_posix()
        if path.suffix.lower() not in SUPPORTED_TEXT_SUFFIXES:
            skipped.append(
                {
                    "path": rel_path,
                    "reason": f"unsupported_suffix:{path.suffix.lower() or '<none>'}",
                }
            )
            continue

        try:
            raw_text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            skipped.append({"path": rel_path, "reason": "decode_error:utf-8"})
            continue

        anonymized_text, pii_counts = anonymize_seed_text(raw_text)
        for key, count in pii_counts.items():
            pii_totals[key] += count
        seeds.append(
            {
                "candidate_seed_id": f"candidate_{len(seeds) + 1:03d}_anonymized",
                "source_files": [
                    {
                        "path": rel_path,
                        "sha256": _sha256(path),
                        "bytes": path.stat().st_size,
                    }
                ],
                "profile_summary": build_profile_summary(anonymized_text),
                "claims": extract_claims(anonymized_text),
                "risk_hypotheses": infer_risk_hypotheses(anonymized_text),
                "pii_removed": pii_counts,
                "usable_as_global_kb": False,
            }
        )

    return {
        "seed_dir": str(root),
        "supported_suffixes": sorted(SUPPORTED_TEXT_SUFFIXES),
        "seed_count": len(seeds),
        "skipped_count": len(skipped),
        "pii_removed": pii_totals,
        "seeds": seeds,
        "skipped_files": skipped,
    }


def write_local_seed_manifest(seed_dir: Path, output_dir: Path) -> dict[str, Any]:
    manifest = extract_local_seed_dir(seed_dir)
    manifest_path = output_dir / LOCAL_SEED_OUTPUT_DIR / LOCAL_SEED_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def anonymize_seed_text(text: str) -> tuple[str, dict[str, int]]:
    counts = {
        "phone": len(PHONE_RE.findall(text)),
        "email": len(EMAIL_RE.findall(text)),
        "id_card": len(ID_CARD_RE.findall(text)),
        "qq": len(QQ_RE.findall(text)),
        "wechat": len(WECHAT_RE.findall(text)),
    }
    anonymized = PHONE_RE.sub("[PHONE_REDACTED]", text)
    anonymized = EMAIL_RE.sub("[EMAIL_REDACTED]", anonymized)
    anonymized = ID_CARD_RE.sub("[ID_CARD_REDACTED]", anonymized)
    anonymized = QQ_RE.sub("QQ:[QQ_REDACTED]", anonymized)
    anonymized = WECHAT_RE.sub("WECHAT:[WECHAT_REDACTED]", anonymized)
    anonymized = NAME_FIELD_RE.sub(r"\1Candidate A", anonymized)
    anonymized = COMPANY_FIELD_RE.sub(r"\1[INDUSTRY_LEVEL_COMPANY]", anonymized)
    anonymized = SCHOOL_FIELD_RE.sub(r"\1[EDUCATION_LEVEL_SCHOOL]", anonymized)
    return anonymized, counts


def build_profile_summary(text: str) -> dict[str, Any]:
    lines = _meaningful_lines(text)
    return {
        "summary": " ".join(lines[:3])[:500],
        "evidence_line_count": len(lines),
        "experience_band": _extract_field(text, ["experience_band", "\u7ecf\u9a8c"])
        or "unknown",
        "target_role": _extract_field(text, ["target_role", "role", "\u5c97\u4f4d"])
        or "unknown",
    }


def extract_claims(text: str, *, limit: int = 8) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    for line in _meaningful_lines(text):
        if not CLAIM_HINT_RE.search(line):
            continue
        claims.append(
            {
                "claim_id": f"claim_{len(claims) + 1:03d}",
                "claim_text": line[:500],
                "risk_type": _claim_risk(line),
            }
        )
        if len(claims) >= limit:
            break
    return claims


def infer_risk_hypotheses(text: str) -> list[str]:
    risks = {_claim_risk(line) for line in _meaningful_lines(text) if CLAIM_HINT_RE.search(line)}
    risks.discard("low_risk_control")
    if PHONE_RE.search(text) or EMAIL_RE.search(text) or ID_CARD_RE.search(text):
        risks.add("pii_present_before_redaction")
    return sorted(risks)


def _claim_risk(line: str) -> str:
    lowered = line.lower()
    has_metric = bool(METRIC_RE.search(line))
    has_baseline = any(
        token in lowered
        for token in ("baseline", "denominator", "period", "\u57fa\u7ebf", "\u53e3\u5f84", "\u5468\u671f")
    )
    if has_metric and not has_baseline:
        return "metric_inflation"
    if "\u4e3b\u5bfc" in line or "led " in lowered or "owner" in lowered:
        return "role_exaggeration"
    if "\u6211\u4eec" in line or " we " in f" {lowered} ":
        return "distancing"
    return "low_risk_control"


def _extract_field(text: str, keys: list[str]) -> str | None:
    escaped = "|".join(re.escape(key) for key in keys)
    match = re.search(rf"(?im)^\s*(?:{escaped})\s*[:=]\s*(.+?)\s*$", text)
    if not match:
        return None
    return match.group(1)[:120]


def _meaningful_lines(text: str) -> list[str]:
    return [
        " ".join(line.strip().split())
        for line in text.splitlines()
        if len(line.strip()) >= 8
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
