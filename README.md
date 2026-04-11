# fleet-mechanic 🔧

Autonomous fleet maintenance agent — the Aider/Claude Code killer, but A2A-native.

## What It Does

The Fleet Mechanic is an autonomous agent that:
- **Scans** fleet repos for health (tests, CI, docs)
- **Diagnoses** issues (failing tests, missing files, broken CI)
- **Fixes** problems and pushes patches directly
- **Reports** fleet health to Oracle1

## How It's Different From Aider/Claude Code

| Feature | Aider/Claude Code | Fleet Mechanic |
|---------|-------------------|----------------|
| Agents | 1 | Fleet of N |
| Coordination | Chat | Git commits |
| CI/CD | Manual | Automatic (GitHub Actions) |
| Verification | Self-test | Cross-agent review |
| Cost | $200/month | Free |
| Scale | Single repo | Entire fleet |

## Boot Sequence

```bash
# Oracle1 boots the mechanic:
echo "$GITHUB_TOKEN" > /tmp/.mechanic_token
./boot.py           # Quick scan + auto-fix
./scan_fleet.py     # Full fleet scan
```

## FLUX-Native Core

The mechanic's decision loop is encoded in FLUX bytecode:
- R0 = task count
- R1 = success count
- R2 = health score
- R3 = threshold
- R5 = decision (0=halt, 1=continue)

Any FLUX VM can execute the mechanic's logic.

## Vessel Structure

```
vessel/
  CHARTER.md    — Purpose, capabilities, chain of command
  IDENTITY.md   — Name, type, skills, boot sequence
  MANIFEST.md   — Status, merit badges, equipment
  TASKBOARD.md  — Active/completed/fenced tasks
src/
  mechanic.py   — Core engine (400+ lines)
boot.py         — Quick boot + auto-fix
scan_fleet.py   — Full fleet scan
tests/          — Test suite
```

## Skills

| Skill | Description |
|-------|-------------|
| `repo-health` | Diagnose failing tests, missing files, broken CI |
| `gen-docs` | Generate README, .gitignore, CI workflows |
| `fix-tests` | Repair broken test suites |
| `gen-code` | Write code from specifications |
| `review` | Review PRs and code quality |
| `sync` | Keep fleet repos in sync |

## First Live Run (2026-04-11)

```
🔧 Fleet Mechanic Booted
Scanned 5 repos, fixed 3:
  - flux-research: Added .gitignore ✅
  - oracle1-index: Added .gitignore ✅  
  - flux-a2a-prototype: Added CI workflow ✅
```

10 tests passing. Part of the [FLUX Fleet](https://github.com/SuperInstance/oracle1-index).
