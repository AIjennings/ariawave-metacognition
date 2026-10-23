#!/usr/bin/env python3
"""
metacognition_auditor.py
AriaWave METACOGNITION™ (v1.0.0) — Deterministic Self-Auditing Recursive Agent Harness.

Built and operated by Aria Technology Group LLC (https://www.ariawave.tech)
127 E 3rd St, Rochester, MI 48307 | (248) 429-1497
Authors: Andrew Jennings (CAIO) & Dominic Serra (Principal Architect)

Implements 4 zero-dependency production guardrails:
  1. Epistemic Confidence & Entropy Firewall (ECEF)
  2. Read-Live / Write-Draft MCP Cleanroom Gate (HMAC-SHA256 HITL verification)
  3. Anti-Amnesia Tool-Loop Detector & 180KB Rolling Context Budget Slimmer
  4. Pre-Flight URL / Soft-404 Content Verifier
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import re
import sys
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# 1. Epistemic Confidence & Entropy Firewall (ECEF)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class EpistemicVerdict:
    confidence_score: float
    shannon_entropy_bits: float
    provenance_ratio: float
    schema_completeness: float
    decision: str  # "EXECUTE_ALLOWED", "STAGE_DRAFT_ONLY", "HALT_LOW_CONFIDENCE"
    reasons: List[str]


def compute_shannon_entropy(tokens: Sequence[str]) -> float:
    """Computes normalized Shannon entropy (bits per token) across candidate samples."""
    if not tokens:
        return 0.0
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    n = len(tokens)
    entropy = -sum((c / n) * math.log2(c / n) for c in counts.values())
    return round(entropy, 4)


def evaluate_epistemic_confidence(
    required_fields: Sequence[str],
    payload: Dict[str, Any],
    verified_source_fields: Sequence[str],
    sample_consistency_tokens: Sequence[str],
    min_execute_threshold: float = 0.82,
    min_draft_threshold: float = 0.55,
) -> EpistemicVerdict:
    """
    Scores an agent's epistemic certainty before allowing tool execution.
    Combines schema completeness, live-provenance field ratio, and sample consistency.
    """
    reasons: List[str] = []
    if not required_fields:
        completeness = 1.0
    else:
        present = [f for f in required_fields if payload.get(f) not in (None, "", [], {})]
        completeness = len(present) / len(required_fields)
        if completeness < 1.0:
            missing = [f for f in required_fields if f not in present]
            reasons.append(f"Missing required schema fields: {missing}")

    if not required_fields:
        provenance_ratio = 1.0
    else:
        verified = [f for f in required_fields if f in verified_source_fields]
        provenance_ratio = len(verified) / len(required_fields)
        if provenance_ratio < 0.75:
            reasons.append(f"Low live-source provenance ratio ({provenance_ratio:.2f})")

    entropy = compute_shannon_entropy(sample_consistency_tokens)
    # Lower entropy across repeated verification samples = higher agreement
    max_entropy = math.log2(max(len(sample_consistency_tokens), 2))
    agreement_factor = max(0.0, 1.0 - (entropy / max_entropy)) if max_entropy > 0 else 1.0

    score = round(0.45 * completeness + 0.35 * provenance_ratio + 0.20 * agreement_factor, 4)

    if score >= min_execute_threshold and completeness == 1.0:
        decision = "EXECUTE_ALLOWED"
    elif score >= min_draft_threshold:
        decision = "STAGE_DRAFT_ONLY"
        reasons.append(f"Confidence {score:.2f} below live execution gate ({min_execute_threshold}); routing to HITL draft.")
    else:
        decision = "HALT_LOW_CONFIDENCE"
        reasons.append(f"Confidence {score:.2f} critically low; blocking tool call.")

    return EpistemicVerdict(
        confidence_score=score,
        shannon_entropy_bits=entropy,
        provenance_ratio=round(provenance_ratio, 4),
        schema_completeness=round(completeness, 4),
        decision=decision,
        reasons=reasons,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Read-Live / Write-Draft MCP Cleanroom Firewall
# ─────────────────────────────────────────────────────────────────────────────
DESTRUCTIVE_VERBS = (
    "send_invoice",
    "email_client",
    "charge_card",
    "delete_deal",
    "delete_ticket",
    "drop_table",
    "publish_live",
    "wire_transfer",
)


def issue_hitl_approval_token(secret_key: str, tool_name: str, payload_canonical: str) -> str:
    msg = f"{tool_name}:{payload_canonical}".encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_cleanroom_mutation(
    tool_name: str,
    payload: Dict[str, Any],
    secret_key: str,
    hitl_token: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Enforces AriaWave's Read-Live / Write-Draft Cleanroom policy:
    - Any record tagged TEST-FIXTURE or DO-NOT-SYNC is unconditionally blocked.
    - Any destructive/external tool requires draft_only=True OR a valid HMAC-SHA256 HITL token.
    """
    serialized = json.dumps(payload, sort_keys=True)
    if "TEST-FIXTURE" in serialized or "DO-NOT-SYNC" in serialized:
        return False, "BLOCKED_FIXTURE: Payload contains TEST-FIXTURE or DO-NOT-SYNC marker."

    is_destructive = any(v in tool_name.lower() for v in DESTRUCTIVE_VERBS)
    if not is_destructive:
        return True, "ALLOWED_READ_OR_SAFE_TOOL"

    if payload.get("draft_only") is True or payload.get("status") == "DRAFT":
        return True, "ALLOWED_DRAFT_STAGE"

    if hitl_token:
        expected = issue_hitl_approval_token(secret_key, tool_name, serialized)
        if hmac.compare_digest(expected, hitl_token):
            return True, "ALLOWED_VERIFIED_HITL_TOKEN"
        return False, "BLOCKED_INVALID_HITL_SIGNATURE"

    return False, f"BLOCKED_UNGAURDED_MUTATION: '{tool_name}' requires draft_only=True or cryptographic HITL token."


# ─────────────────────────────────────────────────────────────────────────────
# 3. Anti-Amnesia Loop Detector & Rolling Prompt Budget Slimmer (180KB Gate)
# ─────────────────────────────────────────────────────────────────────────────
def detect_tool_loop(recent_calls: Sequence[Tuple[str, str]], threshold: float = 0.85) -> Tuple[bool, str]:
    """
    Detects when an agent is stuck calling the same tool with near-identical arguments.
    Uses token-set Jaccard similarity across the last 3 calls.
    """
    if len(recent_calls) < 3:
        return False, "NO_LOOP"
    last_three = recent_calls[-3:]
    names = {c[0] for c in last_three}
    if len(names) != 1:
        return False, "DIVERSE_TOOLS"

    def tokenize(text: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z0-9_/-]+", text.lower()))

    sets = [tokenize(c[1]) for c in last_three]
    if not all(sets):
        return True, f"IDENTICAL_EMPTY_CALL_LOOP:{last_three[0][0]}"

    sim_01 = len(sets[0] & sets[1]) / max(len(sets[0] | sets[1]), 1)
    sim_12 = len(sets[1] & sets[2]) / max(len(sets[1] | sets[2]), 1)
    avg_sim = (sim_01 + sim_12) / 2.0
    if avg_sim >= threshold:
        return True, f"LOOP_DETECTED:{last_three[0][0]} (Jaccard={avg_sim:.2f})"
    return False, f"HEALTHY_PROGRESSION (Jaccard={avg_sim:.2f})"


def enforce_prompt_budget(
    messages: List[Dict[str, str]],
    max_chars: int = 180000,
    keep_recent: int = 6,
) -> Tuple[List[Dict[str, str]], int, int]:
    """
    Deterministically compacts a conversation trajectory so total characters never exceed max_chars.
    Preserves index 0 (system prompt) and the last `keep_recent` messages intact, compacting middle
    tool outputs first and dropping stale middle turns if still over budget.
    """
    def total_len(msgs: Sequence[Dict[str, str]]) -> int:
        return sum(len(m.get("content", "")) for m in msgs)

    before = total_len(messages)
    if before <= max_chars or len(messages) <= keep_recent + 1:
        return list(messages), before, before

    head = [dict(messages[0])]
    tail = [dict(m) for m in messages[-keep_recent:]]
    middle = [dict(m) for m in messages[1:-keep_recent]]

    # Pass 1: truncate middle tool/assistant blobs to 320 chars
    for m in middle:
        content = m.get("content", "")
        if len(content) > 320:
            m["content"] = content[:280] + "... [METACOGNITION_COMPACTED]"

    candidate = head + middle + tail
    if total_len(candidate) <= max_chars:
        return candidate, before, total_len(candidate)

    # Pass 2: drop oldest middle messages until under budget
    while middle and total_len(head + middle + tail) > max_chars:
        middle.pop(0)

    # Pass 3: if tail alone exceeds max_chars, trim oversized tail tool outputs
    result = head + middle + tail
    if total_len(result) > max_chars:
        per_msg_cap = max(1000, (max_chars - len(head[0].get("content", ""))) // max(len(tail), 1))
        for m in tail:
            if len(m.get("content", "")) > per_msg_cap:
                m["content"] = m["content"][: per_msg_cap - 40] + "... [TAIL_BUDGET_TRIMMED]"
        result = head + tail

    return result, before, total_len(result)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Pre-Flight Link & Soft-404 Content Gate
# ─────────────────────────────────────────────────────────────────────────────
SOFT_404_PATTERNS = (
    r"404\s*:\s*this page could not be found",
    r"<title>[^<]*404[^<]*</title>",
    r"page not found",
    r"profile not found",
)


def audit_outbound_url_response(url: str, status_code: int, html_snippet: str) -> Tuple[bool, str]:
    """
    Verifies an outbound URL is both HTTP 200 and free of Next.js/SPA soft-404 markers.
    """
    if not url.startswith(("https://", "http://")):
        return False, "INVALID_SCHEME"
    if status_code < 200 or status_code >= 300:
        return False, f"HTTP_STATUS_{status_code}"
    lower_html = html_snippet.lower()
    for pat in SOFT_404_PATTERNS:
        if re.search(pat, lower_html):
            return False, f"SOFT_404_DETECTED ({pat})"
    return True, "VERIFIED_LIVE_200"


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic Self-Test Suite
# ─────────────────────────────────────────────────────────────────────────────
def run_selftest() -> int:
    # 1. Test Epistemic Confidence Firewall
    high_verdict = evaluate_epistemic_confidence(
        required_fields=["customer_id", "amount_usd", "qbo_item_id"],
        payload={"customer_id": "CUST-88", "amount_usd": 4500.0, "qbo_item_id": "ITEM-LABOR-01"},
        verified_source_fields=["customer_id", "amount_usd", "qbo_item_id"],
        sample_consistency_tokens=["ITEM-LABOR-01", "ITEM-LABOR-01", "ITEM-LABOR-01"],
    )
    assert high_verdict.decision == "EXECUTE_ALLOWED", f"Expected EXECUTE_ALLOWED, got {high_verdict}"

    low_verdict = evaluate_epistemic_confidence(
        required_fields=["customer_id", "amount_usd", "qbo_item_id"],
        payload={"customer_id": "CUST-88", "amount_usd": 4500.0, "qbo_item_id": "GUESS-1"},
        verified_source_fields=["customer_id"],
        sample_consistency_tokens=["GUESS-1", "GUESS-2", "GUESS-3"],
    )
    assert low_verdict.decision == "STAGE_DRAFT_ONLY", f"Expected STAGE_DRAFT_ONLY, got {low_verdict}"

    # 2. Test Cleanroom Mutation Firewall
    secret = "ariawave-sovereign-cleanroom-key"
    ok_fixture, reason_fixture = verify_cleanroom_mutation(
        "send_invoice", {"customer": "TEST-FIXTURE-ACME", "draft_only": True}, secret
    )
    assert not ok_fixture and "BLOCKED_FIXTURE" in reason_fixture

    ok_raw, reason_raw = verify_cleanroom_mutation(
        "send_invoice", {"customer": "M1 Concourse", "amount": 9500}, secret
    )
    assert not ok_raw and "BLOCKED_UNGAURDED_MUTATION" in reason_raw

    ok_draft, _ = verify_cleanroom_mutation(
        "send_invoice", {"customer": "M1 Concourse", "amount": 9500, "draft_only": True}, secret
    )
    assert ok_draft

    payload_live = {"customer": "M1 Concourse", "amount": 9500}
    token = issue_hitl_approval_token(secret, "send_invoice", json.dumps(payload_live, sort_keys=True))
    ok_token, reason_token = verify_cleanroom_mutation("send_invoice", payload_live, secret, hitl_token=token)
    assert ok_token and reason_token == "ALLOWED_VERIFIED_HITL_TOKEN"

    # 3. Test Anti-Amnesia Loop Detector & 180KB Prompt Budget Slimmer
    loop_detected, loop_reason = detect_tool_loop([
        ("search_crm", "query=Ingram Roofing status=open"),
        ("search_crm", "query=Ingram Roofing status=open"),
        ("search_crm", "query=Ingram Roofing status=open limit=10"),
    ])
    assert loop_detected and "LOOP_DETECTED" in loop_reason

    synthetic_msgs = [{"role": "system", "content": "System prompt: AriaWave Sovereign Agent."}]
    for i in range(40):
        synthetic_msgs.append({"role": "tool", "content": f"Turn {i} dump: " + ("X" * 6000)})
    slimmed, before_chars, after_chars = enforce_prompt_budget(synthetic_msgs, max_chars=180000, keep_recent=6)
    assert before_chars > 240000
    assert after_chars <= 180000
    assert slimmed[0]["role"] == "system"

    # 4. Test Pre-Flight Soft-404 Link Verifier
    ok_url, _ = audit_outbound_url_response(
        "https://www.ariawave.tech/case-studies/m1-concourse",
        200,
        "<html><head><title>M1 Concourse Case Study | Aria Technology Group</title></head></html>",
    )
    assert ok_url

    bad_url, bad_reason = audit_outbound_url_response(
        "https://www.ariawave.tech/case-studies/ingram-enterprise",
        200,
        "<html><head><title>404: This page could not be found.</title></head><body>404: This page could not be found.</body></html>",
    )
    assert not bad_url and "SOFT_404_DETECTED" in bad_reason

    print(
        json.dumps(
            {
                "status": "PASS",
                "engine": "AriaWave METACOGNITION™ v1.0.0",
                "checks_verified": [
                    "Epistemic Confidence & Entropy Firewall (ECEF)",
                    "Read-Live / Write-Draft MCP Cleanroom Gate (HMAC-SHA256)",
                    "Anti-Amnesia Loop Detector & 180KB Rolling Context Slimmer",
                    "Pre-Flight URL & Soft-404 Verifier",
                ],
                "sample_epistemic_verdict": asdict(high_verdict),
                "budget_compression": {"before_chars": before_chars, "after_chars": after_chars},
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AriaWave METACOGNITION™ Deterministic Auditor")
    parser.add_argument("--selftest", action="store_true", help="Run built-in deterministic verification suite")
    args = parser.parse_args()
    if args.selftest:
        return run_selftest()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
