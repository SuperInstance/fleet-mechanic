#!/usr/bin/env python3
"""Fleet Mechanic — Full autonomous scan of all SuperInstance repos."""
import sys
import json
import subprocess
import time
from typing import List, Dict, Optional

sys.path.insert(0, 'src')
from mechanic import FleetMechanic, RepoHealth

try:
    TOKEN = open("/tmp/.mechanic_token").read().strip()
except FileNotFoundError:
    print("ERROR: Token file not found at /tmp/.mechanic_token")
    print("Set it with: echo $GITHUB_TOKEN > /tmp/.mechanic_token")
    sys.exit(1)
except PermissionError:
    print("ERROR: Cannot read /tmp/.mechanic_token (permission denied)")
    sys.exit(1)
if not TOKEN:
    print("ERROR: Token file is empty")
    sys.exit(1)
mechanic = FleetMechanic(TOKEN, "SuperInstance")

class RateLimiter:
    """Handle API rate limiting with exponential backoff."""

    def __init__(self, initial_delay: float = 1.0, max_delay: float = 60.0, max_retries: int = 5):
        """Initialize rate limiter.

        Args:
            initial_delay: Initial delay between requests in seconds
            max_delay: Maximum delay between requests in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.current_delay = initial_delay

    def backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay.

        Args:
            attempt: Current attempt number (starting from 0)

        Returns:
            Delay in seconds for this attempt
        """
        delay = min(self.initial_delay * (2 ** attempt), self.max_delay)
        return delay

    def wait(self, attempt: int) -> None:
        """Wait with exponential backoff.

        Args:
            attempt: Current attempt number
        """
        delay = self.backoff(attempt)
        time.sleep(delay)

    def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        self.current_delay = self.initial_delay


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


def fetch_repos_paginated(
    token: str,
    per_page: int = 100,
    rate_limiter: Optional[RateLimiter] = None
) -> List[Dict]:
    """Fetch all user repositories with pagination and rate limiting.

    Args:
        token: GitHub authentication token
        per_page: Number of repos per page
        rate_limiter: Optional RateLimiter instance for backoff

    Returns:
        List of repository dictionaries

    Raises:
        RuntimeError: If API request fails after retries
    """
    if rate_limiter is None:
        rate_limiter = RateLimiter()

    all_repos = []
    page = 1

    while True:
        for attempt in range(rate_limiter.max_retries):
            try:
                result = subprocess.run(
                    ['curl', '-s', '-H', f'Authorization: token {token}',
                     f'https://api.github.com/user/repos?sort=updated&per_page={per_page}&page={page}'],
                    capture_output=True, text=True, timeout=30
                )

                if result.returncode != 0:
                    raise RuntimeError(f"curl failed: {result.stderr}")

                repos = json.loads(result.stdout)

                if not repos:
                    # No more repos
                    return all_repos

                all_repos.extend(repos)

                # Check if we got a full page
                if len(repos) < per_page:
                    return all_repos

                page += 1

                # Wait before next request
                rate_limiter.wait(0)

            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse API response (attempt {attempt + 1}): {e}")
                if attempt < rate_limiter.max_retries - 1:
                    rate_limiter.wait(attempt)
                    continue
                else:
                    raise RuntimeError(f"Failed to parse GitHub API response after {rate_limiter.max_retries} attempts")

            except subprocess.TimeoutExpired:
                print(f"Warning: API request timed out (attempt {attempt + 1})")
                if attempt < rate_limiter.max_retries - 1:
                    rate_limiter.wait(attempt)
                    continue
                else:
                    raise RuntimeError(f"GitHub API request timed out after {rate_limiter.max_retries} attempts")

            except Exception as e:
                print(f"Warning: Unexpected error (attempt {attempt + 1}): {e}")
                if attempt < rate_limiter.max_retries - 1:
                    rate_limiter.wait(attempt)
                    continue
                else:
                    raise RuntimeError(f"Unexpected error after {rate_limiter.max_retries} attempts: {e}")


def filter_repos_by_type(repos: List[Dict], min_size_kb: int = 10) -> tuple[List[str], List[str]]:
    """Filter repos into own and forks based on type and size.

    Args:
        repos: List of repository dictionaries
        min_size_kb: Minimum repository size in KB

    Returns:
        Tuple of (own_repo_names, fork_repo_names)
    """
    own = [
        r["name"] for r in repos
        if not r.get("fork") and r.get("size", 0) > min_size_kb
    ]
    forks = [
        r["name"] for r in repos
        if r.get("fork") and r.get("size", 0) > min_size_kb
    ]
    return own, forks


def print_scan_results(reports: List[RepoHealth]) -> None:
    """Print scan results in a formatted table.

    Args:
        reports: List of RepoHealth objects
    """
    print(f"{'Repo':40s} {'Score':>6s} {'Tests':>8s} {'CI':>3s} {'Lang':>6s}")
    print("-" * 68)
    for r in reports:
        score = f"{r.health_score:.0%}"
        tests = f"{r.test_pass}/{r.test_count}" if r.test_count > 0 else "-"
        ci = "Y" if r.has_ci else "N"
        lang = (r.language or "?")[:6]
        print(f"{r.repo:40s} {score:>6s} {tests:>8s} {ci:>3s} {lang:>6s}")


def print_summary(reports: List[RepoHealth]) -> None:
    """Print summary statistics.

    Args:
        reports: List of RepoHealth objects
    """
    healthy = sum(1 for r in reports if r.health_score >= 0.5)
    print(f"\nHealthy: {healthy}/{len(reports)}")


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
            try:
                task = mechanic.execute_gen_docs(r.repo)
                if task.result and task.result.value == "success":
                    print(f"Fixed {r.repo}: {task.diagnosis.strip()}")
                    fixed += 1
            except Exception as e:
                print(f"Failed to fix {r.repo}: {e}")
    return fixed


def main() -> int:
    """Main scan function.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Load token and initialize mechanic
        token = load_github_token()
        mechanic = FleetMechanic(token, "SuperInstance")

        print("🔧 Fleet Mechanic — Full Fleet Scan")
        print("=" * 50)

        # Initialize rate limiter with conservative defaults
        rate_limiter = RateLimiter(initial_delay=1.0, max_delay=30.0, max_retries=3)

        # Fetch all repos with pagination and rate limiting
        all_repos = fetch_repos_paginated(token, rate_limiter=rate_limiter)
        own, forks = filter_repos_by_type(all_repos)

        print(f"Total repos: {len(all_repos)} (own: {len(own)}, forks: {len(forks)})")
        print(f"\nScanning own repos...\n")

        # Limit to 30 repos for practical scanning
        scan_limit = min(30, len(own))
        reports = mechanic.fleet_scan(own[:scan_limit])
        reports.sort(key=lambda r: r.health_score)

        # Print results
        print_scan_results(reports)
        print_summary(reports)

        # Auto-fix repos that need attention
        fixed = fix_repos_needing_docs(mechanic, reports)
        print(f"\n🔧 Auto-fixes applied: {fixed}")
        print("🏁 Scan complete.")

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
