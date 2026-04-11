#!/usr/bin/env python3
"""Fleet Mechanic Boot Sequence."""
import sys, json, subprocess
sys.path.insert(0, 'src')
from mechanic import FleetMechanic, TaskType

TOKEN = open("/tmp/.mechanic_token").read().strip()
mechanic = FleetMechanic(TOKEN, "SuperInstance")

print("🔧 Fleet Mechanic Booted")
print("=" * 40)

result = subprocess.run(
    ['curl', '-s', '-H', f'Authorization: token {TOKEN}',
     'https://api.github.com/user/repos?sort=updated&per_page=30'],
    capture_output=True, text=True
)
repos = json.loads(result.stdout)
own_repos = [r["name"] for r in repos if not r.get("fork") and r.get("size", 0) > 10]

print(f"Found {len(own_repos)} own repos with content")
print(f"Scanning top 20...\n")

reports = mechanic.fleet_scan(own_repos[:20])
reports.sort(key=lambda r: r.health_score)

print(f"{'Repo':35s} {'Score':>6s} {'Tests':>10s} {'README':>6s} {'CI':>4s} {'Lang':>6s}")
print("-" * 75)
for r in reports:
    score = f"{r.health_score:.0%}"
    tests = f"{r.test_pass}/{r.test_count}" if r.test_count > 0 else "-"
    readme = "Y" if r.has_readme else "N"
    ci = "Y" if r.has_ci else "N"
    lang = (r.language or "?")[:6]
    print(f"{r.repo:35s} {score:>6s} {tests:>10s} {readme:>6s} {ci:>4s} {lang:>6s}")

needs = [r for r in reports if r.health_score < 0.5]
healthy = [r for r in reports if r.health_score >= 0.5]
print(f"\nHealthy: {len(healthy)}/{len(reports)}, Needs attention: {len(needs)}/{len(reports)}")

fixed = 0
for r in reports:
    if not r.has_gitignore or not r.has_ci:
        print(f"\nFixing {r.repo}...")
        task = mechanic.execute_gen_docs(r.repo)
        print(f"  Result: {task.result.value} - {task.diagnosis}")
        if task.result.value == "success":
            fixed += 1

print(f"\nTotal fixes: {fixed}")
print("Mission complete.")
