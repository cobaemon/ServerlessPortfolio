---
name: control-change
description: Modify the control platform without incident-specific if-statements or unconnected controls.
---

# Control Change Skill

Use when modifying policy, hooks, Git hooks, source manifests, report gates, runtime adapters, or self-tests.

## Policy Gate

- Required invariant: `INV-REPORT-GATE`.
- Current-turn implementation permission is required.

## Required Work

- Update `controls/policy.json` when behavior changes.
- Update `scripts/control_platform/engine.py` or adapter wiring when runtime behavior changes.
- Update self-tests for negative and positive examples.
- Update documentation and evidence-reporting expectations.
- Keep old entrypoints only as connected compatibility shims.

## Forbidden

- Do not add incident-ID-specific conditional logic.
- Do not leave unconnected wrappers, hooks, policies, skills, or tests.
- Do not replace requirements with narrower local assumptions.
