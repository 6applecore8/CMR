# CRM AWR Workflow

## Project

- Development checkout: `D:\Code\CMR`.
- Project name: `CMR Agent Workbench`.
- External key: `cmr-agent-workbench`.
- Ledger: `awr-work-ledger.yaml`; source configuration: `awr-project.toml`.
- AWR CLI version used for initialization: `0.5.0`.
- This is development task tracking, not an embedded CRM Agent runtime or model integration.

## Start And Resume

```powershell
Set-Location D:\Code\CMR
awr status --json
awr work show CMR-P2-IDENTITY-DATA --json
awr session start --help
awr client bind --help
awr context compile --help
```

Confirm project identity, inspect the task and dependencies, and start or resume an owned session. Bind the actual Codex conversation ID, not a guessed ID. Read the full compiled context before changing code. Keep the Dashboard A2A handoff gate in place.

On a fresh clone without `.awr`, run `awr init --help` and initialize from the checked-in manifest with preview/accept confirmation. Never copy another project's runtime database or reuse its project/session identifiers.

## Verification And Completion

```powershell
pwsh -NoProfile -File scripts/verify-agent-phase1.ps1
awr work prepare-completion --help
awr evidence add --help
awr work complete --help
```

The verification script actually executes tests and emits a version-1 completion report in `.awr/reports/`. Copy the final report, without modifying it, to a unique path under `docs/verification/` before registering completion evidence. Never overwrite an accepted report. AWR records assertions and validates bindings; it does not run the test command for you.

In AWR 0.5.0, the prepared evidence JSON uses `work`/`branch` output names, while `evidence add` accepts `work_item_key`/`branch_id`. Normalize those keys before registration. Preserve `sha256`, `source_sha`, `command`, `scope`, and `verified_at`. Use fresh project revisions for mutations and map every acceptance criterion in the completion input to registered evidence.

Phase-one `source_sha` is a SHA256 of the sorted source-content manifest, not a Git commit. The report includes individual file hashes, base Git HEAD and a dirty-worktree flag. Re-run verification after relevant source changes; do not substitute current HEAD for historical evidence.

To check historical completion currency, pass the report's actual `source_sha` to `awr status --source-sha <hash> --json`. A plain status without a source hash may show historical completion as `not_checked`. YAML evidence locators are unverified source references; the separately registered `CMR-P1-VERSIONED-TESTS` and the recorded completion event carry the full verification bindings.

## Current Boundary

- `CMR-P1-RULES`: locally verified, 52 domain tests and 44 existing regression tests passed; compilation, existing JavaScript syntax, diff whitespace and unchanged legacy entry points checked.
- Report: `docs/verification/cmr-phase1-20261026T160130070Z.json`.
- `CMR-P2-IDENTITY-DATA`: planned; database, authentication and endpoint authorization are not integrated.
- `CMR-P3-ROLE-UI`: planned; no new role-based UI or browser acceptance.
- `CMR-P4-MODEL-WIKI`: planned; no live Qwen invocation or Wiki integration.
- No real customer data migration, paid model invocation or remote Git push was performed.

Before handoff, use `awr client progress --help` and `awr session checkpoint --help` to record the actual digest, next action, open loops and the last context hash read. Runtime state under `.awr/` stays local; the ledger, manifest, workflow, verifier and versioned reports are reviewable source files.
