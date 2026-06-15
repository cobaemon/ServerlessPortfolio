---
name: evidence-reporting
description: Produce reports that separate facts, evidence, judgments, and unknowns.
---

# Evidence Reporting Skill

Use for final reports, incident reports, verification reports, and any response that contains completion or success claims.

## Policy Gate

- Required invariant: `INV-P1-EVIDENCE`.

## Report Requirements

- Separate facts, evidence, judgment, and unknowns.
- Every important judgment must cite command output, file path, diff, or explicit evidence absence.
- Completion claims require the obligation/evidence/unknown matrix.
- If any requirement is unmet or unverified, do not report completion.

## Non-Triggers

- This skill does not make unverified facts true.
- This skill does not waive missing evidence.
