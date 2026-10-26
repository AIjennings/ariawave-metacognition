---
name: metacognition-engine
description: AriaWave METACOGNITION™ — Self-auditing recursive agent harness, epistemic confidence firewall, anti-amnesia loop recovery, pre-flight URL/media gate, multi-lane inference isolation, and dual-surface singleton verification.
version: 1.1.0
author: Aria Technology Group (Andrew Jennings & Dominic Serra)
---

# AriaWave METACOGNITION™ (`metacognition-engine`)

## Overview
**AriaWave METACOGNITION™** is an open-source, zero-dependency recursive agent governance engine built and operated in production by **[Aria Technology Group](https://www.ariawave.tech)** (`127 E 3rd St, Rochester, MI 48307`) across **1.55B+ cumulative agent tokens** and **743+ multi-agent sessions**.

While standard LLM agent wrappers blindly execute tool calls, hallucinate broken URLs, spiral into infinite tool loops, cause inference starvation on interactive channels, or exceed prompt context budgets, **AriaWave METACOGNITION™** wraps every autonomous agent turn in six deterministic mathematical and cryptographic guardrails:

1. **Epistemic Confidence & Entropy Firewall (`ECEF`):**
   Computes a deterministic pre-execution confidence score $C \in [0, 1]$ from source provenance weight, schema completeness, and token entropy before any external mutation is permitted. If $C < \tau_{\text{gate}}$, execution automatically downgrades from autonomous action to a Human-in-the-Loop (HITL) draft.
2. **Read-Live / Write-Draft MCP Cleanroom Gate:**
   Separates read-only telemetry inspection (`LIVE_READ`) from financial, CRM, email, and infrastructure mutations (`DRAFT_STAGE_ONLY`). Blocks raw mutation keys (`send_invoice`, `delete_deal`, `publish_unverified`) unless accompanied by a verified HMAC-SHA256 human approval token or draft-only flag.
3. **Anti-Amnesia Loop Recovery & Rolling Prompt Budget Slimmer (`180KB Gate`):**
   Detects repetitive tool-call signatures (Jaccard similarity $\ge 0.85$ across consecutive turns) to break infinite agent loops, and enforces a strict `180,000`-character rolling context budget by deterministically compacting stale tool outputs while preserving system instructions, active task state, and recent turns.
4. **Pre-Flight URL, DNS & Soft-404 Media Verifier:**
   Inspects every outbound link and media asset in social posts, emails, and client deliverables—verifying DNS resolution, HTTP status, canonical redirect targets, and scanning HTML titles/bodies for soft-404 markers (`Page Not Found`, `404: This page could not be found`) before publication.
5. **Multi-Lane Inference Admission & Cron Contention Auditor (`audit_inference_lane_isolation`):**
   Prevents background scheduled cron jobs from squatting on interactive human-facing inference lanes (`HTTP 503: Bridge busy` starvation). Enforces strict background lane isolation (e.g. port 8790 / `custom:agy-background`), flags unpinned model-drift hazards that cause safety spending blocks, and mandates `[SILENT]` delta-gating on high-frequency monitors ($\le 180$ minutes) to eliminate notification spam.
6. **Dual-Surface Singleton & Split-Brain Config Verifier (`audit_surface_singleton_and_config_parity`):**
   Detects shared-UUID WebChannel daemon collisions when multiple `remote-control serve` processes compete for a single `installation_uuid` stream. Detects and flags split-brain configuration drift across parallel agent surfaces (e.g. `busy_input_mode: "queue"` vs `"steer"`, and unstable `tool_progress: "new"` modes).

## Quick Start & Self-Test
```bash
python skills/metacognition-engine/metacognition_auditor.py --selftest
```
