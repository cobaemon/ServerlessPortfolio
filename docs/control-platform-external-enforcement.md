# Control Platform v2 External Enforcement Status

This document separates repository-local implementation from controls that require external systems. Items below are not implemented by this repository unless a future evidence entry proves otherwise.

| Item | Status | Reason | Next required work |
|---|---|---|---|
| Managed hooks | Not implemented | Repository files can define `.codex/hooks.json`, but managed hook distribution is outside this repository. | Configure the managed hook channel and record deployment evidence. |
| `requirements.toml` or MDM distribution | Not implemented | No repository-local file can enforce workstation-wide managed hook installation. | Define managed distribution policy and verify on target machines. |
| Git bot credential least privilege | Not implemented | Git credential scope is controlled outside the repository. | Create or restrict AI/CI credentials and record permission evidence. |
| AWS IAM least privilege | Not implemented | IAM roles, policies, and AWS profiles are external to this repository. | Define least-privilege AI/CI deploy and read-only roles, then verify IAM policy evidence. |
| OS sandbox or PATH wrapper | Not implemented | Repository files cannot force global PATH or OS sandbox behavior. | Install managed wrappers or sandbox profile and record runtime evidence. |
| RAG vector index | Not implemented | `controls/rag_sources.json` validates local sources only; no vector store is created. | Build an indexer and retrieval gate, then record index provenance and freshness evidence. |
| CI/CD branch protection | Not implemented | Branch protection and remote push permissions are configured outside the repository. | Configure remote branch protection and record settings evidence. |
| AWS deploy runtime enforcement | Not implemented | This implementation denies unsafe commands in local policy but cannot change AWS service-side controls. | Apply IAM, pipeline, and deployment role restrictions outside the repository. |
