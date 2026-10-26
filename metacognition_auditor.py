#!/usr/bin/env python3
"""
metacognition_auditor.py
AriaWave METACOGNITION™ (v1.1.0) — Deterministic Self-Auditing Recursive Agent Harness.

Built and operated by Aria Technology Group LLC (https://www.ariawave.tech)
127 E 3rd St, Rochester, MI 48307 | (248) 429-1497
Authors: Andrew Jennings (CAIO) & Dominic Serra (Principal Architect)

Implements 6 zero-dependency production guardrails:
  1. Epistemic Confidence & Entropy Firewall (ECEF)
  2. Read-Live / Write-Draft MCP Cleanroom Gate (HMAC-SHA256 HITL verification)
  3. Anti-Amnesia Tool-Loop Detector & 180KB Rolling Context Budget Slimmer
  4. Pre-Flight URL / Soft-404 Content Verifier
  5. Multi-Lane Inference Admission & Cron Contention Auditor
  6. Dual-Surface Singleton & Split-Brain Config Verifier
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
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


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
# 5. Multi-Lane Inference Admission & Cron Contention Auditor (Guardrail #5)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class LaneViolation:
    job_id: str
    job_name: str
    violation_type: str  # "INTERACTIVE_LANE_SQUATTING", "UNPINNED_MODEL_DRIFT", "MISSING_SILENT_GATE"
    details: str
    remediation: str


@dataclass
class GuardrailResult:
    passed: bool
    guardrail: str
    summary: str
    violations: List[Dict[str, Any]]
    details: Dict[str, Any]
    is_clean: bool = True
    is_healthy: bool = True
    squatting_count: int = 0
    unpinned_count: int = 0
    noisy_count: int = 0
    conflicts: List[str] = None
    drift_keys: Dict[str, Any] = None
    remediations: List[str] = None

    def __post_init__(self):
        if self.conflicts is None:
            self.conflicts = []
        if self.drift_keys is None:
            self.drift_keys = {}
        if self.remediations is None:
            self.remediations = []
        self.is_clean = self.passed
        self.is_healthy = self.passed


# Type aliases for API flexibility
LaneAuditVerdict = GuardrailResult
SurfaceConfigVerdict = GuardrailResult


def audit_inference_lane_isolation(
    jobs_data: Any,
    interactive_port: int = 8420,
    interactive_providers: Sequence[str] = ("agy", "interactive", "primary", "default", ""),
    interactive_ports: Sequence[int] = (8420,),
    allowed_background_providers: Sequence[str] = ("custom:agy-background", "background", "secondary", "batch"),
    high_frequency_threshold_minutes: int = 180,
) -> GuardrailResult:
    """
    Audits scheduled/background cron jobs against interactive lane contention,
    model-drift hazards, and notification spam.
    
    Zero-dependency, portable, and deterministic.
    """
    if isinstance(jobs_data, dict):
        if "jobs" in jobs_data and isinstance(jobs_data["jobs"], list):
            jobs = jobs_data["jobs"]
        elif "cron_jobs" in jobs_data and isinstance(jobs_data["cron_jobs"], list):
            jobs = jobs_data["cron_jobs"]
        else:
            jobs = [jobs_data]
    elif isinstance(jobs_data, (list, tuple)):
        jobs = list(jobs_data)
    else:
        jobs = [jobs_data]

    violations: List[Dict[str, Any]] = []
    remediations: List[str] = []
    squatting_count = 0
    unpinned_count = 0
    noisy_count = 0
    target_ports = set(interactive_ports) | {interactive_port}

    for job in jobs:
        if not isinstance(job, dict):
            continue

        job_id = str(job.get("id") or job.get("job_id") or "unknown_job")
        job_name = str(job.get("name") or job.get("title") or job_id)
        enabled = job.get("enabled", True)
        no_agent = job.get("no_agent", False)

        # Only evaluate enabled jobs that execute LLM agent turns
        if not enabled or no_agent:
            continue

        provider = str(job.get("provider") or "").strip()
        provider_lower = provider.lower()
        base_url = str(job.get("base_url") or job.get("url") or job.get("endpoint") or "")

        # 1. Interactive Lane Squatting Check
        is_squatting = False
        squat_reason = ""
        if not provider or provider_lower in [p.lower() for p in interactive_providers]:
            is_squatting = True
            squat_reason = f"Provider '{provider or '<null>'}' is mapped to interactive primary lane."
        elif any(f":{p}" in base_url or f":{p}" in provider for p in target_ports):
            is_squatting = True
            squat_reason = f"Endpoint/Provider targets interactive port ({target_ports})."

        if is_squatting:
            squatting_count += 1
            v = LaneViolation(
                job_id=job_id,
                job_name=job_name,
                violation_type="INTERACTIVE_LANE_SQUATTING",
                details=f"Job routes to interactive inference lane: {squat_reason}",
                remediation="Pin provider to isolated background lane (e.g. 'custom:agy-background' on port 8790).",
            )
            violations.append(asdict(v))
            remediations.append(f"[{job_id}] Pin to background provider: 'custom:agy-background'")

        # 2. Unpinned Model Drift Hazard Check
        model = job.get("model")
        last_error = str(job.get("last_error") or "").lower()
        is_unpinned = False
        unpinned_reason = ""

        if not model or str(model).strip() == "":
            is_unpinned = True
            unpinned_reason = "Model field is null or empty string."
        elif "unintended spend" in last_error or "unpinned" in last_error:
            is_unpinned = True
            unpinned_reason = f"Model drift triggered safeguard: {job.get('last_error')}"

        if is_unpinned:
            unpinned_count += 1
            v = LaneViolation(
                job_id=job_id,
                job_name=job_name,
                violation_type="UNPINNED_MODEL_DRIFT",
                details=f"Hazard of unpinned model drift or spending block: {unpinned_reason}",
                remediation="Pin explicit model (e.g. 'antigravity-flash' or 'gemini-4-argon-medium').",
            )
            violations.append(asdict(v))
            remediations.append(f"[{job_id}] Pin explicit model: 'antigravity-flash'")

        # 3. Missing [SILENT] Delta-Gate Check
        is_high_freq = False
        interval = job.get("interval_minutes")
        if interval is not None:
            try:
                if int(interval) <= high_frequency_threshold_minutes:
                    is_high_freq = True
            except (ValueError, TypeError):
                pass

        schedule = str(job.get("schedule") or job.get("cron") or job.get("cron_expression") or "")
        if schedule:
            parts = schedule.strip().split()
            if len(parts) >= 5:
                # cron: minute hour dom month dow
                hour_part = parts[1]
                min_part = parts[0]
                if hour_part == "*" or any(hour_part.startswith(f"*/{h}") for h in ("1", "2", "3")) or min_part.startswith("*/"):
                    is_high_freq = True
            elif any(token in schedule.lower() for token in ("hourly", "30m", "every")):
                is_high_freq = True

        if is_high_freq:
            prompt_text = " ".join([
                str(job.get("prompt") or ""),
                str(job.get("instructions") or ""),
                str(job.get("message") or "")
            ])
            has_silent_gate = (
                "[silent]" in prompt_text.lower()
                or "silent when" in prompt_text.lower()
                or "delta gate" in prompt_text.lower()
            )
            if not has_silent_gate:
                noisy_count += 1
                v = LaneViolation(
                    job_id=job_id,
                    job_name=job_name,
                    violation_type="MISSING_SILENT_GATE",
                    details=f"High-frequency autonomous job (schedule: '{schedule or interval}m') lacks [SILENT] delta-gating.",
                    remediation="Inject [SILENT] instruction to ensure zero notifications when no state delta exists.",
                )
                violations.append(asdict(v))
                remediations.append(f"[{job_id}] Add [SILENT] gating instruction to prompt")

    passed = (len(violations) == 0)
    summary = (
        f"Audited {len(jobs)} jobs: all inference lanes isolated, models pinned, and notifications delta-gated."
        if passed
        else f"Audited {len(jobs)} jobs: found {len(violations)} lane/drift/noise violations ({squatting_count} squatting, {unpinned_count} unpinned, {noisy_count} noisy)."
    )

    return GuardrailResult(
        passed=passed,
        guardrail="Multi-Lane Inference Admission & Cron Contention Auditor",
        summary=summary,
        violations=violations,
        details={
            "total_audited": len(jobs),
            "squatting_count": squatting_count,
            "unpinned_count": unpinned_count,
            "noisy_count": noisy_count,
        },
        is_clean=passed,
        is_healthy=passed,
        squatting_count=squatting_count,
        unpinned_count=unpinned_count,
        noisy_count=noisy_count,
        remediations=remediations,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Dual-Surface Singleton & Split-Brain Config Verifier (Guardrail #6)
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_nested_key(cfg: Dict[str, Any], key_path: str) -> Any:
    if key_path in cfg:
        return cfg[key_path]
    parts = key_path.split(".")
    curr: Any = cfg
    for p in parts:
        if isinstance(curr, dict) and p in curr:
            curr = curr[p]
        else:
            return None
    return curr


def audit_surface_singleton_and_config_parity(
    processes: Any,
    config_data: Any,
    singleton_targets: Sequence[str] = ("remote-control serve", "remote_control_serve"),
    supervisor_targets: Sequence[str] = ("supervise_remote_control.py", "supervise_remote_control"),
    required_invariants: Optional[Dict[str, Any]] = None,
) -> GuardrailResult:
    """
    Verifies that singleton daemons do not suffer shared-UUID collision storms and
    parallel agent surface configs do not suffer split-brain drift (e.g. queue vs steer).
    
    Zero-dependency, portable, and deterministic.
    """
    conflicts: List[str] = []
    drift_keys: Dict[str, Any] = {}
    remediations: List[str] = []
    violations: List[Dict[str, Any]] = []

    # 1. Process Singleton and Supervision Analysis
    process_counts: Dict[str, int] = {}
    if isinstance(processes, dict):
        process_counts = dict(processes)
    elif isinstance(processes, (list, tuple)):
        for item in processes:
            if isinstance(item, str):
                line = item.lower()
                for target in list(singleton_targets) + list(supervisor_targets):
                    if target.lower() in line:
                        process_counts[target] = process_counts.get(target, 0) + 1
            elif isinstance(item, dict):
                cmd = " ".join([
                    str(item.get("name") or ""),
                    str(item.get("cmdline") or ""),
                    str(item.get("cmd") or ""),
                    str(item.get("command") or ""),
                ]).lower()
                for target in list(singleton_targets) + list(supervisor_targets):
                    if target.lower() in cmd:
                        process_counts[target] = process_counts.get(target, 0) + 1

    # Check singleton targets
    for target in singleton_targets:
        cnt = process_counts.get(target, 0)
        if cnt == 0:
            cnt = sum(c for k, c in process_counts.items() if target.lower() in k.lower())

        if cnt > 1:
            msg = f"SINGLETON_COLLISION_HAZARD: Multiple '{target}' instances running concurrently ({cnt} > 1). Shared installation_uuid WebChannel storm risk."
            conflicts.append(msg)
            violations.append({"type": "SINGLETON_COLLISION_HAZARD", "target": target, "count": cnt, "details": msg})
            remediations.append(f"Kill duplicate '{target}' processes to maintain strict singleton daemon.")

        # Supervisor check
        sup_cnt = sum(process_counts.get(s, 0) for s in supervisor_targets)
        if sup_cnt == 0:
            sup_cnt = sum(c for k, c in process_counts.items() if any(s.lower() in k.lower() for s in supervisor_targets))

        if cnt >= 1 and sup_cnt == 0:
            msg = f"ORPHAN_UNSUPERVISED_SINGLETON: '{target}' is running ({cnt} instance) but supervisor '{supervisor_targets[0]}' is dead/missing."
            conflicts.append(msg)
            violations.append({"type": "ORPHAN_UNSUPERVISED_SINGLETON", "target": target, "details": msg})
            remediations.append(f"Launch supervisor daemon: '{supervisor_targets[0]}'.")

    # 2. Config Invariants & Split-Brain Analysis
    if required_invariants is None:
        required_invariants = {
            "display.busy_input_mode": "steer",
            "display.busy_text_mode": "steer",
            "gateway.busy_input_mode": "steer",
            "display.platforms.telegram.tool_progress": ["edit", "off"],
        }

    # Extract configs / surfaces
    surfaces: Dict[str, Dict[str, Any]] = {}
    if isinstance(config_data, dict):
        sub_surfaces = {
            k: v for k, v in config_data.items()
            if isinstance(v, dict) and any(
                isinstance(_resolve_nested_key(v, req), (str, int, bool))
                for req in ("display.busy_input_mode", "gateway.busy_input_mode", "busy_input_mode")
            )
        }
        if sub_surfaces and len(sub_surfaces) >= 2:
            surfaces = sub_surfaces
        else:
            surfaces = {"primary": config_data}
    elif isinstance(config_data, (list, tuple)):
        for idx, item in enumerate(config_data):
            if isinstance(item, dict):
                surfaces[f"surface_{idx}"] = item
    else:
        surfaces = {"primary": {}}

    # Invariant Checks
    for s_name, cfg in surfaces.items():
        for req_key, expected in required_invariants.items():
            val = _resolve_nested_key(cfg, req_key)
            if val is None:
                short_key = req_key.split(".")[-1]
                val = cfg.get(short_key)

            if val is not None:
                if isinstance(expected, (list, tuple, set)):
                    if val not in expected:
                        msg = f"CONFIG_INVARIANT_VIOLATION [{s_name}]: '{req_key}' is '{val}', expected one of {expected}."
                        conflicts.append(msg)
                        violations.append({"type": "CONFIG_INVARIANT_VIOLATION", "surface": s_name, "key": req_key, "value": val, "expected": list(expected)})
                        remediations.append(f"[{s_name}] Set '{req_key}' to '{expected[0]}'")
                else:
                    if val != expected:
                        if val == "queue" and expected == "steer":
                            msg = f"SPLIT_BRAIN_DRIFT [{s_name}]: '{req_key}' is set to 'queue' instead of 'steer', causing single-threaded session stalls."
                        else:
                            msg = f"CONFIG_INVARIANT_VIOLATION [{s_name}]: '{req_key}' is '{val}', expected '{expected}'."
                        conflicts.append(msg)
                        violations.append({"type": "SPLIT_BRAIN_DRIFT" if val == "queue" else "CONFIG_INVARIANT_VIOLATION", "surface": s_name, "key": req_key, "value": val, "expected": expected})
                        remediations.append(f"[{s_name}] Update '{req_key}' to '{expected}'")

        # Internal parity check within a single surface config
        bim = _resolve_nested_key(cfg, "display.busy_input_mode")
        gim = _resolve_nested_key(cfg, "gateway.busy_input_mode")
        btm = _resolve_nested_key(cfg, "display.busy_text_mode")
        modes = [m for m in (bim, gim, btm) if m is not None]
        if "queue" in modes and "steer" in modes:
            msg = f"SPLIT_BRAIN_DRIFT [{s_name}]: Internal mode collision between display ({bim}/{btm}) and gateway ({gim}). Both must be 'steer'."
            conflicts.append(msg)
            violations.append({"type": "INTERNAL_SPLIT_BRAIN", "surface": s_name, "display_mode": bim, "gateway_mode": gim})
            remediations.append(f"[{s_name}] Align all busy modes to 'steer'.")

    # Cross-Surface Drift Check
    if len(surfaces) > 1:
        surface_names = list(surfaces.keys())
        for req_key in required_invariants.keys():
            vals = {}
            for s_name in surface_names:
                v = _resolve_nested_key(surfaces[s_name], req_key)
                if v is not None:
                    vals[s_name] = v
            unique_vals = set(vals.values())
            if len(unique_vals) > 1:
                msg = f"CROSS_SURFACE_DRIFT: Invariant '{req_key}' diverged across surfaces: {vals}."
                conflicts.append(msg)
                drift_keys[req_key] = vals
                violations.append({"type": "CROSS_SURFACE_DRIFT", "key": req_key, "values": vals})
                remediations.append(f"Synchronize '{req_key}' across all surfaces to match production baseline.")

    passed = (len(conflicts) == 0 and len(violations) == 0)
    summary = (
        "All surface singletons healthy and configuration parity verified across all agent surfaces."
        if passed
        else f"Surface audit failed: {len(conflicts)} conflict(s) detected across singletons and configuration parity."
    )

    return GuardrailResult(
        passed=passed,
        guardrail="Dual-Surface Singleton & Split-Brain Config Verifier",
        summary=summary,
        violations=violations,
        details={
            "conflicts_count": len(conflicts),
            "surfaces_evaluated": list(surfaces.keys()),
            "drift_keys": drift_keys,
        },
        is_clean=passed,
        is_healthy=passed,
        conflicts=conflicts,
        drift_keys=drift_keys,
        remediations=remediations,
    )


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

    # 5. Test Multi-Lane Inference Admission & Cron Contention Auditor (Guardrail #5)
    dirty_jobs = [
        {
            "id": "job_squat",
            "name": "Hourly Trends Scraper",
            "provider": "agy",
            "base_url": "http://127.0.0.1:8420/v1",
            "model": "antigravity-flash",
            "interval_minutes": 60,
            "prompt": "Scrape trends [SILENT]",
        },
        {
            "id": "job_drift",
            "name": "Outreach Sales Agent",
            "provider": "custom:agy-background",
            "model": "",
            "last_error": "Skipped to prevent unintended spend: model not specified",
            "interval_minutes": 60,
            "prompt": "Find leads [SILENT]",
        },
        {
            "id": "job_noisy",
            "name": "Health Pinger",
            "provider": "custom:agy-background",
            "model": "antigravity-flash",
            "interval_minutes": 30,
            "prompt": "Unconditional status dump to Telegram",
        },
    ]
    dirty_lane_verdict = audit_inference_lane_isolation(dirty_jobs)
    assert not dirty_lane_verdict.passed, "Expected dirty jobs to fail lane audit"
    assert dirty_lane_verdict.squatting_count == 1
    assert dirty_lane_verdict.unpinned_count == 1
    assert dirty_lane_verdict.noisy_count == 1
    assert len(dirty_lane_verdict.violations) == 3

    clean_jobs = [
        {
            "id": "job_sales_clean",
            "name": "Outbound Engagement & Sales Agent",
            "provider": "custom:agy-background",
            "model": "antigravity-flash",
            "interval_minutes": 60,
            "prompt": "Process qualified leads. [SILENT] when no new verified leads exist.",
        },
        {
            "id": "job_health_clean",
            "name": "Hermes Self-Healing Watchdog",
            "no_agent": True,
            "interval_minutes": 30,
        },
    ]
    clean_lane_verdict = audit_inference_lane_isolation(clean_jobs)
    assert clean_lane_verdict.passed and clean_lane_verdict.is_clean, f"Expected clean lane verdict, got: {clean_lane_verdict}"
    assert len(clean_lane_verdict.violations) == 0

    # 6. Test Dual-Surface Singleton & Split-Brain Config Verifier (Guardrail #6)
    dirty_processes = [
        "agy.exe remote-control serve",
        "agy.exe remote-control serve",  # Duplicate process collision!
    ]
    dirty_config = {
        "display": {"busy_input_mode": "steer", "busy_text_mode": "steer"},
        "gateway": {"busy_input_mode": "queue"},  # Split-brain drift!
        "display.platforms.telegram.tool_progress": "new",  # Invalid progress mode!
    }
    dirty_surface_verdict = audit_surface_singleton_and_config_parity(dirty_processes, dirty_config)
    assert not dirty_surface_verdict.passed, "Expected dirty surface to fail"
    assert len(dirty_surface_verdict.conflicts) >= 2

    clean_processes = [
        "agy.exe remote-control serve",
        "python supervise_remote_control.py",
    ]
    clean_config = {
        "display": {"busy_input_mode": "steer", "busy_text_mode": "steer"},
        "gateway": {"busy_input_mode": "steer"},
        "display.platforms.telegram.tool_progress": "edit",
    }
    clean_surface_verdict = audit_surface_singleton_and_config_parity(clean_processes, clean_config)
    assert clean_surface_verdict.passed and clean_surface_verdict.is_healthy, f"Expected clean surface verdict, got: {clean_surface_verdict}"
    assert len(clean_surface_verdict.conflicts) == 0

    print(
        json.dumps(
            {
                "status": "PASS",
                "engine": "AriaWave METACOGNITION™ v1.1.0",
                "checks_verified": [
                    "Epistemic Confidence & Entropy Firewall (ECEF)",
                    "Read-Live / Write-Draft MCP Cleanroom Gate (HMAC-SHA256)",
                    "Anti-Amnesia Loop Detector & 180KB Rolling Context Slimmer",
                    "Pre-Flight URL & Soft-404 Verifier",
                    "Multi-Lane Inference Admission & Cron Contention Auditor",
                    "Dual-Surface Singleton & Split-Brain Config Verifier",
                ],
                "sample_epistemic_verdict": asdict(high_verdict),
                "budget_compression": {"before_chars": before_chars, "after_chars": after_chars},
                "lane_isolation_sample": {
                    "is_clean": clean_lane_verdict.is_clean,
                    "violations_caught_in_simulation": len(dirty_lane_verdict.violations),
                },
                "surface_singleton_sample": {
                    "is_healthy": clean_surface_verdict.is_healthy,
                    "conflicts_caught_in_simulation": len(dirty_surface_verdict.conflicts),
                },
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
