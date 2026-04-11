# fleet-mechanic 🔧

Autonomous fleet maintenance agent — the Aider/Claude Code killer, but A2A-native.

## Capabilities

| Skill | Status | Description |
|-------|--------|-------------|
| `repo-health` | ✅ LIVE | Scan repos, diagnose issues, score health |
| `gen-docs` | ✅ LIVE | Generate .gitignore, CI workflows, READMEs |
| `fix_code` | ✅ NEW | Parse test failures, suggest+apply code fixes |
| `gen_code` | ✅ NEW | Generate Python/Rust/Go code from specifications |
| `review` | ✅ NEW | Review PRs and code for quality/security/fleet compliance |
| `codespace` | ✅ NEW | Run inside GitHub Codespaces (free compute) |

## How It Works

```
1. BOOT → Read taskboard or accept webhook trigger
2. CLONE → git clone target repo
3. DIAGNOSE → Run tests, parse failures, check health
4. FIX → Generate fixes for broken code
5. REVIEW → Check quality, security, fleet compliance
6. PUSH → Commit fixes, create PR if needed
7. REPORT → Upload artifact, update taskboard
```

## Codespace Deployment

The mechanic can run entirely on GitHub's infrastructure:
1. Open Codespace on this repo
2. Set GITHUB_TOKEN secret
3. Run `python3 boot.py`
4. Mechanic scans fleet, fixes repos, reports back
5. Close Codespace when done

**Cost: $0. GitHub provides free Codespace hours.**

## Test Results

- **mechanic.py**: 10 tests (core engine)
- **fix_code.py**: 8 tests (code fixing)
- **gen_code.py**: 8 tests (code generation)
- **review.py**: 9 tests (code review)
- **Total: 35 tests passing**

## First Live Run (2026-04-11)

```
🔧 Fleet Mechanic Booted
733 repos found
Scanned 20 → Fixed 15 automatically
```

Part of the [FLUX Fleet](https://github.com/SuperInstance/oracle1-index).
