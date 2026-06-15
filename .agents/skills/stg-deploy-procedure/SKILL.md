---
name: stg-deploy-procedure
description: Execute the closed STG deployment procedure without discretionary push-content stops.
---

# STG Deploy Procedure Skill

Use only when the current-turn contract is `DEPLOY_ALLOWED` and `FIXED_PROCEDURE_BOUND`.

## Policy Gate

- Required invariant: `INV-FIXED-PROCEDURE`.
- This skill is not work permission. The shared policy engine must allow the action before this skill is used.

## Closed State Machine

1. Confirm current-turn STG deploy permission.
2. Load `controls/procedures/stg_deploy.json`.
3. Verify local preconditions defined by the procedure.
4. Continue each fixed step unless an allowed hard stop predicate is present.
5. Gather source revision, pipeline, CloudFormation, HTTP, and browser evidence required by the contract.
6. Report with requirement, evidence, judgment, and unknowns.

## Non-Triggers

- A question about deploy is not deploy permission.
- A review request is not deploy permission.
- A performance investigation is not deploy permission unless it explicitly includes the deploy procedure.

## Forbidden

- Do not stop because `origin/dev..branch` has multiple commits.
- Do not ask whether to split scope unless the user explicitly requested subset deployment.
- Do not treat post-push evidence as a pre-push prerequisite.
- Do not directly mutate STG or prod outside the fixed procedure.

## Required Evidence

- Source revision.
- Pipeline state.
- CloudFormation state.
- HTTP evidence.
- Browser evidence when user-visible or browser performance is claimed.
- Unknowns explicitly listed.
