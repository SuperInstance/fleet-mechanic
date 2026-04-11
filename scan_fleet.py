#!/usr/bin/env python3
"""Fleet Mechanic — Full autonomous scan of all SuperInstance repos."""
import sys, json, subprocess
sys.path.insert(0, 'src')
from mechanic import FleetMechanic

TOKEN = open("/tmp/.mechanic_token").read().strip()
mechanic = FleetMechanic(TOKEN, "SuperInstance")

print("🔧 Fleet Mechanic — Full Fleet Scan")
print("=" * 50)

# Get ALL repos (paginate)
all_repos = []
page = 1
while True:
    result = subprocess.run(
        ['curl', '-s', '-H', f'Authorization: token {TOKEN}',
         f'https://api.github.com/user/repos?sort=updated&per_page=100&page={page}'],
        capture_output=True, text=True
    )
    repos = json.loads(result.stdout)
    if not repos:
        break
    all_repos.extend(repos)
    page += 1
    if len(repos) < 100:
        break

own = [r for r in all_repos if not r.get("fork") and r.get("size", 0) > 10]
forks = [r for r in all_repos if r.get("fork") and r.get("size", 0) > 10]

print(f"Total repos: {len(all_repos)} (own: {len(own)}, forks: {len(forks)})")
print(f"\nScanning own repos...\n")

reports = mechanic.fleet_scan([r["name"] for r in own[:30]])
reports.sort(key=lambda r: r.health_score)

print(f"{'Repo':40s} {'Score':>6s} {'Tests':>8s} {'CI':>3s} {'Lang':>6s}")
print("-" * 68)
for r in reports:
    score = f"{r.health_score:.0%}"
    tests = f"{r.test_pass}/{r.test_count}" if r.test_count > 0 else "-"
    ci = "Y" if r.has_ci else "N"
    lang = (r.language or "?")[:6]
    print(f"{r.repo:40s} {score:>6s} {tests:>8s} {ci:>3s} {lang:>6s}")

healthy = sum(1 for r in reports if r.health_score >= 0.5)
print(f"\nHealthy: {healthy}/{len(reports)}")

# Auto-fix repos that need attention
fixed = 0
for r in reports:
    if not r.has_gitignore or not r.has_ci:
        task = mechanic.execute_gen_docs(r.repo)
        if task.result and task.result.value == "success":
            print(f"Fixed {r.repo}: {task.diagnosis.strip()}")
            fixed += 1

print(f"\n🔧 Auto-fixes applied: {fixed}")
print("🏁 Scan complete.")
