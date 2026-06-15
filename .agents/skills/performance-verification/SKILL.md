---
name: performance-verification
description: Verify performance without mixing server, HTTP, browser, paint, real-user, cold-like, and warm samples.
---

# Performance Verification Skill

Use when the contract asks for performance, user-visible improvement, browser validation, memory comparison, SnapStart, or cold-start evidence.

## Policy Gate

- Required invariants: `INV-PERF-LAYER`, `INV-ENV-MUTATION`, and `INV-SNAPSTART-READY`.
- This skill does not authorize AWS, deploy, alias changes, package installs, or external network access.

## Measurement Taxonomy

- `server_execution`: Lambda Duration and Restore Duration.
- `server_platform`: Lambda and API Gateway metrics.
- `HTTP_client`: curl or local HTTP client timing.
- `browser_navigation`: Navigation Timing, DOMContentLoaded, and load.
- `browser_paint`: FCP, LCP, layout, and paint evidence.
- `real_user`: RUM or actual user telemetry.

## Non-Triggers

- CloudWatch-only evidence does not trigger browser or user-visible performance claims.
- curl-only evidence does not trigger LCP, FCP, DOMContentLoaded, load, or browser display claims.

## Environment Mutation

Changing STG or prod Lambda memory, version, alias, API Gateway, CloudFormation, CodePipeline, or permissions requires a fixed deployment procedure or explicit measurement procedure.

## Cold-Like First Request

- SnapStart targets require `State=Active` and `SnapStart.OptimizationStatus=On`.
- HTTP 500 after alias or version change invalidates the run.
- The first HTTP 200 after a 500 is `recovery_after_failure_first_success`, not cold-like first request.
- Warm or stabilized samples must not be reported as cold-start improvement.
