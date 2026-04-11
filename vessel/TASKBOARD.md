# Fleet Mechanic — Taskboard

## Active Tasks

### TASK-001: Deploy CI to all fleet repos
**Priority**: P1  
**Status**: IN_PROGRESS  
**Details**: 15 repos fixed in first scan. Continue deploying CI workflows to remaining repos that need them. Use the scan_fleet.py to find more.

### TASK-002: Generate READMEs for forked cognitive repos
**Priority**: P2  
**Status**: OPEN  
**Details**: The 9 forked cuda-* repos (cuda-trust, cuda-confidence, etc.) have our test fixes but no fleet-contextual READMEs. Generate READMEs explaining: what the repo is, how it fits the fleet, test status, and link back to the original Lucineer repo.

### TASK-003: Health scan all 733 repos
**Priority**: P2  
**Status**: OPEN  
**Details**: Full fleet health scan. The scan_fleet.py currently only checks 30. Extend to paginate through all repos and generate a comprehensive health report.

## Fenced Tasks (available for pickup)

### TASK-004: Fix remaining cuda-genepool failures
**Priority**: P3  
**Status**: OPEN  
**Details**: 26/31 tests passing. 5 integration failures in the RNA→Protein pipeline. Deep Rust debugging needed.

### TASK-005: Add GitHub Actions badges to READMEs
**Priority**: P3  
**Status**: OPEN  
**Details**: Every repo with CI should have a build status badge in its README.

### TASK-006: Create .gitignore for all repos missing one
**Priority**: P3  
**Status**: OPEN  
**Details**: First scan found several repos without .gitignore. Mechanic already fixed 15 — find the rest.

### TASK-007: Verify CI workflows actually pass
**Priority**: P2  
**Status**: OPEN  
**Details**: We deployed CI workflows to 20+ repos. Verify they actually trigger and pass by checking recent Actions runs.

## Completed Tasks
- [x] Fleet health scan (20 repos) — 15 auto-fixed
- [x] Deploy CI to 6 Python repos
- [x] Deploy .gitignore + CI to 15 repos
