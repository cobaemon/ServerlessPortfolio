# ServerlessPortfolio Codex Hooks

CodexHook is the primary runtime control layer for this workspace.  It does not
replace GitHook.  GitHook is the auxiliary guarantee layer for commit and push
boundaries.

## Files

- `.codex/hooks.json`: project-local Codex hook configuration.
- `.codex/hooks/serverless_portfolio_guard.py`: thin wrapper for the shared guard.
- `scripts/project_control_guard.py`: shared policy engine used by CodexHook and GitHook.
- `.codex/audit/state/`: runtime audit state ignored by Git.

## Events

The configuration covers `SessionStart`, `UserPromptSubmit`, `PreToolUse`,
`PermissionRequest`, `PostToolUse`, and `Stop`.

## Verification

```powershell
python -B scripts/project_control_guard.py --self-test
python -m json.tool .codex/hooks.json
```

Non-managed Codex hooks must be reviewed and trusted in Codex with `/hooks`
before Codex runs them automatically.
