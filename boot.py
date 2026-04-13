#!/usr/bin/env python3
"""Fleet Mechanic Boot Sequence."""
import sys
import json
import subprocess
from typing import List, Optional

sys.path.insert(0, 'src')
from mechanic import FleetMechanic, RepoHealth


def load_github_token(token_path: str = "/tmp/.mechanic_token") -> str:
    """Load GitHub token from file.

    Args:
        token_path: Path to the token file

    Returns:
        GitHub token string

    Raises:
        FileNotFoundError: If token file does not exist
        ValueError: If token file is empty
    """
    try:
        with open(token_path, 'r') as f:
            token = f.read().strip()
        if not token:
            raise ValueError("GitHub token file is empty")
        return token
    except FileNotFoundError:
        raise FileNotFoundError(f"GitHub token file not found: {token_path}")


def fetch_user_repos(token: str, per_page: int = 30) -> List[dict]:
    """Fetch user's repositories from GitHub API.

    Args:
        token: GitHub authentication token
        per_page: Number of repos per page

    Returns:
        List of repository dictionaries

    Raises:
        RuntimeError: If API request fails
    """
    try:
        result = subprocess.run(
            ['curl', '-s', '-H', f'Authorization: token {token}',
             f'https://api.github.com/user/repos?sort=updated&per_page={per_page}'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl failed: {result.stderr}")
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse GitHub API response: {e}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("GitHub API request timed out")


def filter_own_repos(repos: List[dict], min_size_kb: int = 10) -> List[str]:
    """Filter non-fork repos with minimum size.

    Args:
        repos: List of repository dictionaries
        min_size_kb: Minimum repository size in KB

    Returns:
        List of repository names
    """
    return [
        r["name"] for r in repos
        if not r.get("fork") and r.get("size", 0) > min_size_kb
    ]


def print_scan_results(reports: List[RepoHealth]) -> None:
    """Print scan results in a formatted table.

    Args:
        reports: List of RepoHealth objects
    """
    print(f"{'Repo':35s} {'Score':>6s} {'Tests':>10s} {'README':>6s} {'CI':>4s} {'Lang':>6s}")
    print("-" * 75)
    for r in reports:
        score = f"{r.health_score:.0%}"
        tests = f"{r.test_pass}/{r.test_count}" if r.test_count > 0 else "-"
        readme = "Y" if r.has_readme else "N"
        ci = "Y" if r.has_ci else "N"
        lang = (r.language or "?")[:6]
        print(f"{r.repo:35s} {score:>6s} {tests:>10s} {readme:>6s} {ci:>4s} {lang:>6s}")


def print_summary(reports: List[RepoHealth]) -> None:
    """Print summary statistics.

    Args:
        reports: List of RepoHealth objects
    """
    needs = [r for r in reports if r.health_score < 0.5]
    healthy = [r for r in reports if r.health_score >= 0.5]
    print(f"\nHealthy: {len(healthy)}/{len(reports)}, Needs attention: {len(needs)}/{len(reports)}")


def fix_repos_needing_docs(mechanic: FleetMechanic, reports: List[RepoHealth]) -> int:
    """Auto-fix repos missing gitignore or CI.

    Args:
        mechanic: FleetMechanic instance
        reports: List of RepoHealth objects

    Returns:
        Number of repos successfully fixed
    """
    fixed = 0
    for r in reports:
        if not r.has_gitignore or not r.has_ci:
            print(f"\nFixing {r.repo}...")
            try:
                task = mechanic.execute_gen_docs(r.repo)
                print(f"  Result: {task.result.value} - {task.diagnosis}")
                if task.result.value == "success":
                    fixed += 1
            except Exception as e:
                print(f"  Error: {e}")
    return fixed


def main() -> int:
    """Main boot sequence.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Load token and initialize mechanic
        token = load_github_token()
        mechanic = FleetMechanic(token, "SuperInstance")

        print("🔧 Fleet Mechanic Booted")
        print("=" * 40)

        # Fetch repositories
        repos = fetch_user_repos(token)
        own_repos = filter_own_repos(repos)

        if not own_repos:
            print("No repositories found to scan.")
            return 0

        print(f"Found {len(own_repos)} own repos with content")
        print(f"Scanning top 20...\n")

        # Scan fleet
        reports = mechanic.fleet_scan(own_repos[:20])
        reports.sort(key=lambda r: r.health_score)

        # Print results
        print_scan_results(reports)
        print_summary(reports)

        # Fix repos that need attention
        fixed = fix_repos_needing_docs(mechanic, reports)
        print(f"\nTotal fixes: {fixed}")
        print("Mission complete.")

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
