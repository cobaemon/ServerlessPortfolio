---
name: incident-response
description: Record and analyze incidents with root cause, violated invariant, control change, regression test, and residual risk.
---

# Incident Response Skill

Use when the current-turn contract asks to record, analyze, or remediate an incident.

## Policy Gate

- Required invariant: `INV-INCIDENT-LIFECYCLE`.
- This skill is not permission to deploy, push, mutate AWS, or install packages.

## Required Sections

- Incident record.
- Confirmed facts.
- Unknowns.
- Violated principles.
- Violated invariants.
- Root cause.
- Control change.
- Regression self-test.
- Verification evidence.
- Remaining risk.

## Non-Triggers

- A general bug fix is not an incident response unless the user or policy classifies it as incident work.

## Completion Rule

Do not report recurrence prevention complete unless the control change and regression self-test are implemented and verified.
