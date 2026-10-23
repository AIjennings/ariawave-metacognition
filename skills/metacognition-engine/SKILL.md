---
name: metacognition-engine
description: AriaWave METACOGNITION™ — Self-auditing recursive agent harness, epistemic confidence firewall, anti-amnesia loop recovery, and pre-flight URL/media gate.
version: 1.0.0
author: Aria Technology Group (Andrew Jennings & Dominic Serra)
---

# AriaWave METACOGNITION™ (`metacognition-engine`)

## Overview
**AriaWave METACOGNITION™** is an open-source, zero-dependency recursive agent governance engine built and operated in production by **[Aria Technology Group](https://www.ariawave.tech)** (`127 E 3rd St, Rochester, MI 48307`) across **1.55B+ cumulative agent tokens** and **743+ multi-agent sessions**.

While standard LLM agent wrappers blindly execute tool calls, hallucinate broken URLs, spiral into infinite tool loops, or exceed prompt context budgets, **AriaWave METACOGNITION™** wraps every autonomous agent turn in four deterministic mathematical and cryptographic guardrails:

1. **Epistemic Confidence & Entropy Firewall (`ECEF`):**
   Computes a deterministic pre-execution confidence score $C \in [0, 1]$ from source provenance weight, schema completeness, and token entropy before any external mutation is permitted. If $C < \tau_{\text{gate}}$, execution automatically downgrades from autonomous action to a Human-in-the-Loop (HITL) draft.
2. **Read-Live / Write-Draft MCP Cleanroom Gate:**
   Separates read-only telemetry inspection (`LIVE_READ`) from financial, CRM, email, and infrastructure mutations (`DRAFT_STAGE_ONLY`). Blocks raw mutation keys (`send_invoice`, `delete_deal`, `publish_unverified`) unless accompanied by a verified HMAC-SHA256 human approval token or draft-only flag.
3. **Anti-Amnesia Loop Recovery & Rolling Prompt Budget Slimmer (`180KB Gate`):**
   Detects repetitive tool-call signatures (Jaccard similarity $\ge 0.85$ across consecutive turns) to break infinite agent loops, and enforces a strict `180,000`-character rolling context budget by deterministically compacting stale tool outputs while preserving system instructions, active task state, and recent turns.
4. **Pre-Flight URL, DNS & Soft-404 Media Verifier:**
   Inspects every outbound link and media asset in social posts, emails, and client deliverables—verifying DNS resolution, HTTP status, canonical redirect targets, and scanning HTML titles/bodies for soft-404 markers (`Page Not Found`, `404: This page could not be found`) before publication.

## Quick Start & Self-Test
```bash
python skills/metacognition-engine/metacognition_auditor.py --selftest
```
