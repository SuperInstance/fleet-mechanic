"""
Fleet Mechanic — Autonomous GitHub Agent Engine.

The core loop:
1. Read taskboard (or accept task from Oracle1)
2. Clone target repo
3. Diagnose (run tests, check files, scan health)
4. Implement fix
5. Run tests locally
6. If green → push + create PR
7. If red → commit diagnosis, create issue
8. Report back

This is the "Aider killer" — but A2A-native and fleet-integrated.
"""
import json
import os
import subprocess
import time
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum


class TaskType(Enum):
    FIX_TESTS = "fix_tests"
    GEN_DOCS = "gen_docs"
    GEN_CODE = "gen_code"
    GEN_CI = "gen_ci"
    REPO_HEALTH = "repo_health"
    SYNC = "sync"
    REVIEW = "review"


class TaskResult(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class MechanicTask:
    """A task the mechanic can execute."""
    id: str
    task_type: TaskType
    target_repo: str
    target_branch: str = "main"
    description: str = ""
    params: Dict = field(default_factory=dict)
    result: Optional[TaskResult] = None
    diagnosis: str = ""
    commits_made: int = 0
    tests_fixed: int = 0
    files_changed: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id, "type": self.task_type.value,
            "repo": self.target_repo, "branch": self.target_branch,
            "description": self.description, "result": self.result.value if self.result else None,
            "diagnosis": self.diagnosis, "commits": self.commits_made,
            "tests_fixed": self.tests_fixed, "files_changed": self.files_changed,
        }


@dataclass
class RepoHealth:
    """Health report for a repository."""
    repo: str
    has_readme: bool = False
    has_gitignore: bool = False
    has_ci: bool = False
    has_tests: bool = False
    test_pass_rate: float = 0.0
    test_count: int = 0
    test_pass: int = 0
    test_fail: int = 0
    language: str = "unknown"
    size_kb: int = 0
    open_issues: int = 0
    last_commit_days: int = 0
    health_score: float = 0.0
    
    def compute_score(self):
        score = 0.0
        if self.has_readme: score += 0.2
        if self.has_gitignore: score += 0.1
        if self.has_ci: score += 0.2
        if self.has_tests: score += 0.2
        if self.has_tests and self.test_count > 0:
            score += 0.3 * (self.test_pass / self.test_count)
        self.health_score = min(1.0, score)
    
    def to_markdown(self) -> str:
        self.compute_score()
        lines = [f"# Health Report: {self.repo}\n"]
        lines.append(f"| Check | Status |")
        lines.append(f"|-------|--------|")
        lines.append(f"| README | {'✅' if self.has_readme else '❌'} |")
        lines.append(f"| .gitignore | {'✅' if self.has_gitignore else '❌'} |")
        lines.append(f"| CI/CD | {'✅' if self.has_ci else '❌'} |")
        lines.append(f"| Tests | {'✅' if self.has_tests else '❌'} ({self.test_pass}/{self.test_count}) |")
        lines.append(f"| Language | {self.language} |")
        lines.append(f"| Size | {self.size_kb}KB |")
        lines.append(f"| **Health Score** | **{self.health_score:.0%}** |")
        return "\n".join(lines)


class FleetMechanic:
    """
    The autonomous fleet mechanic.
    
    Can be booted by Oracle1, given tasks, and operates independently.
    Reports back through commits, issues, and the taskboard.
    """
    
    def __init__(self, github_token: str, org: str = "SuperInstance") -> None:
        """Initialize the Fleet Mechanic.
        
        Args:
            github_token: GitHub authentication token
            org: GitHub organization name (default: SuperInstance)
        
        Raises:
            ValueError: If github_token is empty or None
        """
        if not github_token:
            raise ValueError("GitHub token cannot be empty")
        self.token = github_token
        self.org = org
        self.work_dir = "/tmp/mechanic-work"
        try:
            os.makedirs(self.work_dir, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Failed to create work directory {self.work_dir}: {e}")
        self.completed_tasks: List[MechanicTask] = []
        self.health_reports: Dict[str, RepoHealth] = {}
    
    def _run(self, cmd: str, cwd: Optional[str] = None, timeout: int = 60) -> Tuple[int, str]:
        """Run a shell command safely.
        
        Args:
            cmd: Shell command to execute
            cwd: Working directory (default: self.work_dir)
            timeout: Maximum execution time in seconds
        
        Returns:
            Tuple of (exit_code, output)
        
        Raises:
            subprocess.TimeoutExpired: If command exceeds timeout
            RuntimeError: If working directory is invalid
        """
        env = os.environ.copy()
        env["GITHUB_TOKEN"] = self.token
        work_cwd = cwd or self.work_dir
        
        if work_cwd and not os.path.isdir(work_cwd):
            raise RuntimeError(f"Working directory does not exist: {work_cwd}")
        
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=work_cwd, env=env, timeout=timeout
            )
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired as e:
            return -1, f"TIMEOUT after {timeout}s: {str(e)}"
        except Exception as e:
            return -1, f"Command execution error: {str(e)}"
    
    def _api(self, method: str, path: str, data: Optional[Dict] = None) -> Dict:
        """Call GitHub API with error handling.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., "/repos/user/repo")
            data: Optional request body data
        
        Returns:
            Parsed JSON response as dictionary
        
        Raises:
            ValueError: If response is not valid JSON
        """
        if not path.startswith("/"):
            path = f"/{path}"
        
        cmd = f'curl -s -H "Authorization: token {self.token}" -X {method}'
        if data:
            cmd += f" -d '{json.dumps(data)}'"
        cmd += f" https://api.github.com{path}"
        
        code, out = self._run(cmd)
        
        if code != 0:
            return {"error": f"API call failed with code {code}", "output": out[:200]}
        
        try:
            return json.loads(out) if out else {}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response: {str(e)}", "raw_output": out[:200]}
    
    def clone_repo(self, repo: str) -> bool:
        """Clone a repo to work directory.
        
        Args:
            repo: Repository name (without org prefix)
        
        Returns:
            True if clone succeeded, False otherwise
        """
        if not repo:
            raise ValueError("Repository name cannot be empty")
        
        os.makedirs(self.work_dir, exist_ok=True)
        repo_dir = os.path.join(self.work_dir, repo)
        
        try:
            if os.path.exists(repo_dir):
                self._run(f"rm -rf {repo_dir}")
            
            clone_url = f"https://SuperInstance:{self.token}@github.com/{self.org}/{repo}.git"
            code, out = self._run(
                f"git clone --depth 1 {clone_url} {repo_dir}",
                timeout=120
            )
            
            if code != 0:
                print(f"Warning: Clone failed for {repo}: {out[:200]}")
                return False
            
            return True
        except Exception as e:
            print(f"Error cloning {repo}: {str(e)}")
            return False
    
    def push_changes(self, repo: str, message: str, branch: str = "main") -> bool:
        """Stage, commit, and push changes.
        
        Args:
            repo: Repository name
            message: Commit message
            branch: Branch to push to (default: main)
        
        Returns:
            True if push succeeded, False otherwise
        """
        if not repo:
            raise ValueError("Repository name cannot be empty")
        if not message:
            raise ValueError("Commit message cannot be empty")
        
        repo_dir = os.path.join(self.work_dir, repo)
        
        if not os.path.isdir(repo_dir):
            print(f"Error: Repository directory not found: {repo_dir}")
            return False
        
        code, _ = self._run("git add -A", cwd=repo_dir)
        if code != 0:
            print(f"Warning: git add failed for {repo}")
            return False
        
        code, _ = self._run(f'git commit -m "{message}"', cwd=repo_dir)
        if code != 0:
            return False  # nothing to commit
        
        code, out = self._run(f"git push origin {branch}", cwd=repo_dir, timeout=60)
        if code != 0:
            print(f"Warning: git push failed for {repo}: {out[:200]}")
            return False
        
        return True
    
    def create_pr(self, repo: str, branch: str, title: str, body: str = "") -> Optional[int]:
        """Create a pull request.
        
        Args:
            repo: Repository name
            branch: Branch name for the PR
            title: PR title
            body: PR body/description
        
        Returns:
            PR number if successful, None otherwise
        """
        if not repo or not branch or not title:
            raise ValueError("repo, branch, and title are required")
        
        result = self._api("POST", f"/repos/{self.org}/{repo}/pulls", {
            "title": title, "body": body,
            "head": branch, "base": "main"
        })
        
        if "error" in result:
            print(f"Error creating PR: {result['error']}")
            return None
        
        return result.get("number")
    
    def create_issue(self, repo: str, title: str, body: str, labels: Optional[List[str]] = None) -> Optional[int]:
        """Create an issue.
        
        Args:
            repo: Repository name
            title: Issue title
            body: Issue body
            labels: Optional list of labels to add
        
        Returns:
            Issue number if successful, None otherwise
        """
        if not repo or not title:
            raise ValueError("repo and title are required")
        
        data = {"title": title, "body": body}
        if labels:
            data["labels"] = labels
        
        result = self._api("POST", f"/repos/{self.org}/{repo}/issues", data)
        
        if "error" in result:
            print(f"Error creating issue: {result['error']}")
            return None
        
        return result.get("number")
    
    def run_tests(self, repo: str) -> Tuple[int, int, int]:
        """Run tests and return (total, passed, failed).
        
        Args:
            repo: Repository name
        
        Returns:
            Tuple of (total_tests, passed_tests, failed_tests)
        """
        if not repo:
            raise ValueError("Repository name cannot be empty")
        
        repo_dir = os.path.join(self.work_dir, repo)
        
        if not os.path.isdir(repo_dir):
            print(f"Warning: Repo directory not found: {repo_dir}")
            return 0, 0, 0
        
        # Detect test framework
        if os.path.exists(os.path.join(repo_dir, "Cargo.toml")):
            return self._run_rust_tests(repo_dir)
        
        elif os.path.exists(os.path.join(repo_dir, "pyproject.toml")) or os.path.exists(os.path.join(repo_dir, "tests")):
            return self._run_python_tests(repo_dir)
        
        elif os.path.exists(os.path.join(repo_dir, "go.mod")):
            return self._run_go_tests(repo_dir)
        
        return 0, 0, 0
    
    def _run_rust_tests(self, repo_dir: str) -> Tuple[int, int, int]:
        """Run Rust tests."""
        code, out = self._run("cargo test --lib 2>&1", cwd=repo_dir, timeout=180)
        if "test result:" in out:
            for line in out.split("\n"):
                if "test result:" in line:
                    import re
                    m = re.search(r'(\d+) passed.*?(\d+) failed', line)
                    if m:
                        passed = int(m.group(1))
                        failed = int(m.group(2))
                        return passed + failed, passed, failed
        return 0, 0, 0
    
    def _run_python_tests(self, repo_dir: str) -> Tuple[int, int, int]:
        """Run Python tests."""
        code, out = self._run("python3 -m pytest --tb=no -q 2>&1", cwd=repo_dir, timeout=180)
        import re
        m = re.search(r'(\d+) passed.*?(\d+) failed', out)
        if m:
            passed = int(m.group(1))
            failed = int(m.group(2))
            return passed + failed, passed, failed
        return 0, 0, 0
    
    def _run_go_tests(self, repo_dir: str) -> Tuple[int, int, int]:
        """Run Go tests."""
        code, out = self._run("go test ./... 2>&1", cwd=repo_dir, timeout=180)
        pass_count = out.count("PASS")
        fail_count = out.count("FAIL")
        return pass_count + fail_count, pass_count, fail_count
    
    # === TASK EXECUTORS ===
    
    def execute_repo_health(self, repo: str) -> RepoHealth:
        """Diagnose the health of a repository.
        
        Args:
            repo: Repository name
        
        Returns:
            RepoHealth object with diagnostic results
        """
        if not repo:
            raise ValueError("Repository name cannot be empty")
        
        health = RepoHealth(repo=repo)
        
        # Get repo info via API
        try:
            info = self._api("GET", f"/repos/{self.org}/{repo}")
            if "message" in info and info["message"] == "Not Found":
                # Try fork source
                info = self._api("GET", f"/repos/Lucineer/{repo}")
            
            health.size_kb = info.get("size", 0)
            health.language = info.get("language") or "unknown"
        except Exception as e:
            print(f"Warning: Failed to fetch repo info for {repo}: {e}")
        
        # Clone and check files
        if not self.clone_repo(repo):
            health.compute_score()
            return health
        
        repo_dir = os.path.join(self.work_dir, repo)
        
        try:
            health.has_readme = os.path.exists(os.path.join(repo_dir, "README.md"))
            health.has_gitignore = os.path.exists(os.path.join(repo_dir, ".gitignore"))
            health.has_ci = os.path.exists(os.path.join(repo_dir, ".github/workflows"))
            
            health.has_tests = (
                os.path.exists(os.path.join(repo_dir, "tests")) or 
                os.path.exists(os.path.join(repo_dir, "test")) or
                (os.path.isdir(repo_dir) and 
                 any("test" in f.lower() for f in os.listdir(repo_dir)))
            )
            
            # Run tests if possible
            if health.has_tests:
                total, passed, failed = self.run_tests(repo)
                health.test_count = total
                health.test_pass = passed
                health.test_fail = failed
                health.test_pass_rate = (passed / total) if total > 0 else 0
        except Exception as e:
            print(f"Warning: Error analyzing {repo}: {e}")
        
        health.compute_score()
        self.health_reports[repo] = health
        return health
    
    def execute_gen_docs(self, repo: str) -> MechanicTask:
        """Generate missing documentation files.
        
        Args:
            repo: Repository name
        
        Returns:
            MechanicTask with execution results
        """
        if not repo:
            raise ValueError("Repository name cannot be empty")
        
        task = MechanicTask(
            id=f"DOCS-{int(time.time())}",
            task_type=TaskType.GEN_DOCS,
            target_repo=repo,
        )
        
        if not self.clone_repo(repo):
            task.result = TaskResult.FAILED
            task.diagnosis = "Could not clone repo"
            return task
        
        repo_dir = os.path.join(self.work_dir, repo)
        
        try:
            # Generate .gitignore if missing
            if not os.path.exists(os.path.join(repo_dir, ".gitignore")):
                lang = self._detect_language(repo_dir)
                gitignore = self._gen_gitignore(lang)
                with open(os.path.join(repo_dir, ".gitignore"), "w") as f:
                    f.write(gitignore)
                task.files_changed += 1
                task.diagnosis += "Added .gitignore. "
            
            # Generate CI workflow if missing
            if not os.path.exists(os.path.join(repo_dir, ".github/workflows")):
                os.makedirs(os.path.join(repo_dir, ".github/workflows"), exist_ok=True)
                lang = self._detect_language(repo_dir)
                ci = self._gen_ci(lang)
                if ci:
                    with open(os.path.join(repo_dir, ".github/workflows/ci.yml"), "w") as f:
                        f.write(ci)
                    task.files_changed += 1
                    task.diagnosis += "Added CI workflow. "
            
            if task.files_changed > 0:
                push_success = self.push_changes(repo, "chore: add missing .gitignore and CI workflow [mechanic]")
                if push_success:
                    task.commits_made = 1
                    task.result = TaskResult.SUCCESS
                else:
                    task.result = TaskResult.PARTIAL
                    task.diagnosis += "Failed to push changes. "
            else:
                task.result = TaskResult.PARTIAL
                task.diagnosis = "No missing files found"
        except Exception as e:
            task.result = TaskResult.FAILED
            task.diagnosis = f"Error: {str(e)}"
        
        self.completed_tasks.append(task)
        return task
    
    def _detect_language(self, repo_dir: str) -> str:
        """Detect the programming language of a repository.
        
        Args:
            repo_dir: Path to the repository directory
        
        Returns:
            Language name (e.g., 'python', 'rust', 'go') or 'unknown'
        """
        if not repo_dir or not os.path.isdir(repo_dir):
            return "unknown"
        
        language_map = [
            ("Cargo.toml", "rust"),
            ("go.mod", "go"),
            ("package.json", "node"),
            ("pyproject.toml", "python"),
            ("setup.py", "python"),
            ("Makefile", "c"),
        ]
        
        for filename, lang in language_map:
            if os.path.exists(os.path.join(repo_dir, filename)):
                return lang
        
        return "unknown"
    
    def _gen_gitignore(self, lang: str) -> str:
        """Generate .gitignore content for a given language.
        
        Args:
            lang: Programming language name
        
        Returns:
            .gitignore file content
        """
        templates = {
            "python": "__pycache__/\n*.pyc\n.pytest_cache/\n*.egg-info/\ndist/\nbuild/\n",
            "rust": "target/\nCargo.lock\n**/*.rs.bk\n",
            "go": "bin/\n*.exe\n*.test\nvendor/\n",
            "node": "node_modules/\ndist/\n*.js\n!jest.config.js\n",
            "c": "*.o\n*.out\n*.bin\nbuild/\n",
        }
        return templates.get(lang, "*.pyc\n__pycache__/\n")
    
    def _gen_ci(self, lang: str) -> Optional[str]:
        """Generate CI workflow content for a given language.
        
        Args:
            lang: Programming language name
        
        Returns:
            CI workflow YAML content, or None if not supported
        """
        templates = {
            "python": '''name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with: {python-version: "3.12"}\n      - run: pip install pytest\n      - run: pytest -v\n''',
            "rust": '''name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: cargo test --lib\n''',
            "go": '''name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-go@v5\n        with: {go-version: "1.24"}\n      - run: go test ./...\n''',
        }
        return templates.get(lang)
    
    def _paginate_repos(self, include_forks: bool = False) -> List[Dict]:
        """Fetch ALL repos with full pagination support.

        GitHub API returns max 100 per page. This method paginates
        through all pages to return the complete list of repos.

        Args:
            include_forks: Whether to include forked repos.

        Returns:
            Complete list of repo dicts from GitHub API.
        """
        all_repos: List[Dict] = []
        page = 1
        while True:
            result = self._api(
                "GET",
                f"/users/{self.org}/repos?per_page=100&sort=updated&page={page}"
            )
            if not isinstance(result, list) or len(result) == 0:
                break
            for r in result:
                if include_forks or not r.get("fork"):
                    all_repos.append(r)
            if len(result) < 100:
                break
            page += 1
            time.sleep(0.5)  # Rate limit courtesy

        return all_repos

    def fleet_scan(self, repos: List[str] = None, limit: int = 0,
                   include_forks: bool = False,
                   output_json: str = None) -> List[RepoHealth]:
        """Scan fleet repos and generate health reports.

        Supports full pagination to scan all 733+ repos.

        Args:
            repos: Explicit list of repo names. If None, auto-discovers.
            limit: Max repos to scan (0 = unlimited, scans all).
            include_forks: Whether to include forked repos in scan.
            output_json: Path to write JSON health report.

        Returns:
            List of RepoHealth reports sorted by health_score.
        """
        if repos is None:
            all_repo_data = self._paginate_repos(include_forks=include_forks)
            repos = [r["name"] for r in all_repo_data]
            print(f"  Discovered {len(repos)} repos via API (paginated)")

        if limit > 0:
            repos = repos[:limit]

        reports = []
        for i, repo in enumerate(repos):
            try:
                health = self.execute_repo_health(repo)
                reports.append(health)
                score_str = f"{health.health_score:.0%}"
                print(f"  [{i+1}/{len(repos)}] {repo:40s} score={score_str}")
            except Exception as e:
                h = RepoHealth(repo=repo)
                h.diagnosis = str(e)
                h.compute_score()
                reports.append(h)
                print(f"  [{i+1}/{len(repos)}] {repo:40s} ERROR: {e}")

        if output_json:
            self._write_json_report(reports, output_json)

        return reports
    
    def _fetch_org_repos(self) -> List[str]:
        """Fetch list of non-fork repositories from the organization.
        
        Returns:
            List of repository names
        """
        try:
            result = self._api("GET", f"/users/{self.org}/repos?per_page=100")
            if isinstance(result, list):
                return [r["name"] for r in result if not r.get("fork")]
            return []
        except Exception as e:
            print(f"Warning: Failed to fetch repos: {e}")
            return []

    def _write_json_report(self, reports: List[RepoHealth], path: str):
        """Write health scan results to a JSON file.

        Generates summary statistics, language distribution, and
        per-repo details.

        Args:
            reports: List of RepoHealth objects.
            path: Output file path for the JSON report.
        """
        summary = {
            "total_repos": len(reports),
            "healthy_count": sum(1 for r in reports if r.health_score >= 0.5),
            "unhealthy_count": sum(1 for r in reports if r.health_score < 0.5),
            "avg_score": sum(r.health_score for r in reports) / max(1, len(reports)),
            "repos_with_ci": sum(1 for r in reports if r.has_ci),
            "repos_with_tests": sum(1 for r in reports if r.has_tests),
            "repos_with_readme": sum(1 for r in reports if r.has_readme),
            "total_tests": sum(r.test_count for r in reports),
            "total_passing": sum(r.test_pass for r in reports),
            "total_failing": sum(r.test_fail for r in reports),
            "language_distribution": {},
        }

        for r in reports:
            lang = r.language or "unknown"
            summary["language_distribution"][lang] = summary["language_distribution"].get(lang, 0) + 1

        summary["top_repos"] = sorted(
            [{"repo": r.repo, "score": r.health_score, "language": r.language} for r in reports],
            key=lambda x: x["score"], reverse=True
        )[:20]

        summary["bottom_repos"] = sorted(
            [{"repo": r.repo, "score": r.health_score, "language": r.language} for r in reports],
            key=lambda x: x["score"]
        )[:20]

        repos_data = []
        for r in reports:
            repos_data.append({
                "repo": r.repo, "health_score": r.health_score,
                "has_readme": r.has_readme, "has_gitignore": r.has_gitignore,
                "has_ci": r.has_ci, "has_tests": r.has_tests,
                "test_count": r.test_count, "test_pass": r.test_pass,
                "test_fail": r.test_fail, "language": r.language,
                "size_kb": r.size_kb,
            })

        report = {"summary": summary, "repos": repos_data}

        out_dir = os.path.dirname(path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"  JSON report written to {path}")


# ── FLUX Bytecode Integration ──────────────────────────

def mechanic_flux_program() -> List[int]:
    """
    Generate FLUX bytecode for the mechanic's core decision loop.
    
    This is the "FLUX-native" part — the mechanic's decision making
    encoded as bytecode that any FLUX VM can execute.
    
    R0 = task_count
    R1 = success_count  
    R2 = health_score (0-100)
    R3 = threshold (50 = minimum health)
    
    Decision: if health < threshold AND tasks > 0 → continue working
    """
    return [
        # Load initial values
        0x18, 0, 10,   # MOVI R0, 10    (tasks)
        0x18, 1, 7,    # MOVI R1, 7     (successes)
        0x18, 2, 35,   # MOVI R2, 35    (health score)
        0x18, 3, 50,   # MOVI R3, 50    (threshold)
        
        # Check if health below threshold
        0x2C, 4, 2, 3, # CMP_EQ R4, R2, R3 (will be 0 since 35 != 50)
        
        # Check if tasks remain
        0x3D, 0, 0x08, 0,  # JNZ R0, +8 (if tasks > 0, skip to continue)
        
        # No tasks → halt
        0x18, 5, 0,    # MOVI R5, 0 (signal: done)
        0x00,           # HALT
        
        # Tasks remain → continue working
        0x18, 5, 1,    # MOVI R5, 1 (signal: continue)
        0x09, 0,        # DEC R0 (one less task)
        0x08, 1,        # INC R1 (one more success)
        
        # Return result in R5
        0x00,           # HALT
    ]


# ── Tests ──────────────────────────────────────────────

import unittest


class TestFleetMechanic(unittest.TestCase):
    def test_task_creation(self):
        t = MechanicTask(
            id="TEST-001",
            task_type=TaskType.GEN_DOCS,
            target_repo="test-repo",
        )
        self.assertEqual(t.task_type, TaskType.GEN_DOCS)
        self.assertIsNone(t.result)
    
    def test_repo_health_score(self):
        h = RepoHealth(
            repo="test", has_readme=True, has_gitignore=True,
            has_ci=True, has_tests=True, test_count=10, test_pass=10,
        )
        h.compute_score()
        self.assertEqual(h.health_score, 1.0)
    
    def test_repo_health_markdown(self):
        h = RepoHealth(repo="test", has_readme=True, has_tests=True,
                       test_count=5, test_pass=4)
        md = h.to_markdown()
        self.assertIn("test", md)
        self.assertIn("✅", md)
    
    def test_health_empty_repo(self):
        h = RepoHealth(repo="empty")
        h.compute_score()
        self.assertEqual(h.health_score, 0.0)
    
    def test_task_result_serialization(self):
        t = MechanicTask(
            id="T-001", task_type=TaskType.FIX_TESTS,
            target_repo="test", result=TaskResult.SUCCESS,
        )
        d = t.to_dict()
        self.assertEqual(d["type"], "fix_tests")
        self.assertEqual(d["result"], "success")
    
    def test_detect_language(self):
        m = FleetMechanic("fake-token")
        self.assertEqual(m._detect_language("/tmp/nonexistent"), "unknown")
    
    def test_gitignore_generation(self):
        m = FleetMechanic("fake-token")
        for lang in ["python", "rust", "go", "c"]:
            gi = m._gen_gitignore(lang)
            self.assertGreater(len(gi), 0)
    
    def test_ci_generation(self):
        m = FleetMechanic("fake-token")
        ci = m._gen_ci("python")
        self.assertIn("pytest", ci)
    
    def test_flux_program(self):
        bc = mechanic_flux_program()
        self.assertGreater(len(bc), 10)
        self.assertEqual(bc[0], 0x18)  # MOVI
        self.assertIn(0x00, bc)  # HALT
    
    def test_fleet_scan_empty(self):
        m = FleetMechanic("fake-token")
        # Should handle gracefully with no repos
        reports = m.fleet_scan(repos=[])
        self.assertEqual(len(reports), 0)

    def test_fleet_scan_with_limit(self):
        """Verify the limit parameter works correctly."""
        m = FleetMechanic("fake-token")
        repos = ["repo-a", "repo-b", "repo-c", "repo-d", "repo-e"]
        reports = m.fleet_scan(repos=repos, limit=3)
        # Should only scan 3 repos (they will error on clone, but still count)
        self.assertEqual(len(reports), 3)

    def test_fleet_scan_with_json_output(self):
        """Verify JSON report output works."""
        import tempfile
        m = FleetMechanic("fake-token")
        reports = m.fleet_scan(repos=["fake-repo-1", "fake-repo-2"], output_json="/tmp/test_health.json")
        self.assertEqual(len(reports), 2)
        import os
        self.assertTrue(os.path.exists("/tmp/test_health.json"))
        with open("/tmp/test_health.json") as f:
            data = json.load(f)
        self.assertIn("summary", data)
        self.assertIn("repos", data)
        self.assertEqual(data["summary"]["total_repos"], 2)
        os.remove("/tmp/test_health.json")

    def test_json_report_structure(self):
        """Verify JSON report has all expected fields."""
        import tempfile
        m = FleetMechanic("fake-token")
        reports = [
            RepoHealth(repo="healthy", has_readme=True, has_ci=True,
                       has_tests=True, test_count=10, test_pass=10, language="Python"),
            RepoHealth(repo="unhealthy", has_readme=False, has_ci=False,
                       has_tests=False, language="unknown"),
        ]
        for r in reports:
            r.compute_score()
        m._write_json_report(reports, "/tmp/test_health_struct.json")
        with open("/tmp/test_health_struct.json") as f:
            data = json.load(f)
        s = data["summary"]
        self.assertEqual(s["total_repos"], 2)
        self.assertEqual(s["healthy_count"], 1)
        self.assertEqual(s["unhealthy_count"], 1)
        self.assertIn("Python", s["language_distribution"])
        self.assertEqual(len(s["top_repos"]), 2)
        self.assertEqual(len(s["bottom_repos"]), 2)
        self.assertEqual(len(data["repos"]), 2)
        os.remove("/tmp/test_health_struct.json")

    def test_health_score_partial(self):
        h = RepoHealth(repo="test", has_readme=True, has_gitignore=False,
                        has_ci=True, has_tests=True, test_count=5, test_pass=3)
        h.compute_score()
        self.assertGreater(h.health_score, 0.0)
        self.assertLess(h.health_score, 1.0)

    def test_health_score_no_tests(self):
        h = RepoHealth(repo="test", has_readme=True, has_gitignore=True,
                        has_ci=True, has_tests=True, test_count=0)
        h.compute_score()
        # has_readme(0.2) + has_gitignore(0.1) + has_ci(0.2) + has_tests(0.2) = 0.7
        # No pass rate bonus since test_count=0
        self.assertEqual(h.health_score, 0.7)

    def test_task_to_dict_full(self):
        t = MechanicTask(
            id="FULL-001", task_type=TaskType.FIX_TESTS,
            target_repo="full-repo", target_branch="dev",
            description="Fix all tests", params={"key": "val"},
            result=TaskResult.PARTIAL, diagnosis="Some failed",
            commits_made=3, tests_fixed=5, files_changed=2,
        )
        d = t.to_dict()
        self.assertEqual(d["id"], "FULL-001")
        self.assertEqual(d["type"], "fix_tests")
        self.assertEqual(d["repo"], "full-repo")
        self.assertEqual(d["branch"], "dev")
        self.assertEqual(d["description"], "Fix all tests")
        self.assertEqual(d["result"], "partial")
        self.assertEqual(d["diagnosis"], "Some failed")
        self.assertEqual(d["commits"], 3)
        self.assertEqual(d["tests_fixed"], 5)
        self.assertEqual(d["files_changed"], 2)

    def test_gen_ci_node(self):
        m = FleetMechanic("fake-token")
        self.assertIsNone(m._gen_ci("node"))
        self.assertIsNotNone(m._gen_ci("go"))
        self.assertIsNotNone(m._gen_ci("rust"))
        self.assertIsNone(m._gen_ci("unknown"))

    def test_run_shell_command(self):
        m = FleetMechanic("fake-token")
        code, out = m._run("echo hello")
        self.assertEqual(code, 0)
        self.assertIn("hello", out)

    def test_create_pr_and_issue(self):
        m = FleetMechanic("fake-token")
        pr = m.create_pr("nonexistent", "branch", "Test PR")
        self.assertIsNone(pr)
        issue = m.create_issue("nonexistent", "Test Issue", "Body")
        self.assertIsNone(issue)

    def test_push_changes(self):
        import tempfile
        m = FleetMechanic("fake-token")
        # Create dir so subprocess doesn't crash on missing cwd, but no git repo
        with tempfile.TemporaryDirectory() as tmpdir:
            m.work_dir = tmpdir
            os.makedirs(f"{tmpdir}/nonexistent-repo", exist_ok=True)
            result = m.push_changes("nonexistent-repo", "test commit")
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
