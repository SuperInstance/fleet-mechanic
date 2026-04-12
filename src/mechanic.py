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
import urllib.request
import urllib.error
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
    
    def _run(self, cmd, cwd: str = None, shell: bool = True) -> Tuple[int, str]:
        """Run a shell command. Accepts str (shell=True) or list (shell=False)."""
        env = os.environ.copy()
        env["GITHUB_TOKEN"] = self.token
        work_cwd = cwd or self.work_dir
        
        if work_cwd and not os.path.isdir(work_cwd):
            raise RuntimeError(f"Working directory does not exist: {work_cwd}")
        
        try:
            result = subprocess.run(
                cmd, shell=shell, capture_output=True, text=True,
                cwd=cwd or self.work_dir, env=env, timeout=60
            )
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired as e:
            return -1, f"TIMEOUT after {timeout}s: {str(e)}"
        except Exception as e:
            return -1, f"Command execution error: {str(e)}"
    
    def _api(self, method: str, path: str, data: Dict = None) -> Dict:
        """Call GitHub API using urllib (no shell injection)."""
        url = f"https://api.github.com{path}"
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"error": f"HTTP {e.code}: {e.reason}", "status": e.code}
        except urllib.error.URLError as e:
            return {"error": f"URL error: {e.reason}"}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response"}
    
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
        """Stage, commit, and push changes (no shell injection in message)."""
        repo_dir = f"{self.work_dir}/{repo}"
        self._run("git add -A", cwd=repo_dir)
        code, _ = self._run(["git", "commit", "-m", message], cwd=repo_dir, shell=False)
        if code != 0:
            return False  # nothing to commit
        code, _ = self._run(["git", "push", "origin", branch], cwd=repo_dir, shell=False)
        return code == 0
    
    def create_pr(self, repo: str, branch: str, title: str, body: str = "") -> Optional[int]:
        """Create a pull request against the repo's default branch."""
        default_branch = self._get_default_branch(repo)
        result = self._api("POST", f"/repos/{self.org}/{repo}/pulls", {
            "title": title, "body": body,
            "head": branch, "base": default_branch
        })
        
        if "error" in result:
            print(f"Error creating PR: {result['error']}")
            return None
        
        return result.get("number")

    def _get_default_branch(self, repo: str) -> str:
        """Detect the default branch of a repository."""
        info = self._api("GET", f"/repos/{self.org}/{repo}")
        if isinstance(info, dict) and "default_branch" in info:
            return info["default_branch"]
        return "main"
    
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
            "python": 'name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with: {python-version: "3.12"}\n      - run: pip install pytest\n      - run: pytest -v\n',
            "rust": 'name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: cargo test --lib\n',
            "go": 'name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-go@v5\n        with: {go-version: "1.24"}\n      - run: go test ./...\n',
            "node": 'name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    strategy:\n      matrix:\n        node-version: [18, 20]\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-node@v4\n        with:\n          node-version: ${{ matrix.node-version }}\n      - run: npm ci\n      - run: npm test\n',
            "c": 'name: CI\non: [push, pull_request]\njobs:\n  build-and-test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: sudo apt-get update && sudo apt-get install -y build-essential gcc make\n      - run: make all\n      - run: make test\n',
        }
        return templates.get(lang)
    
    def fleet_scan(self, repos: Optional[List[str]] = None) -> List[RepoHealth]:
        """Scan fleet repos and generate health reports.
        
        Args:
            repos: Optional list of repository names. If None, fetches from organization.
        
        Returns:
            List of RepoHealth objects with scan results
        """
        if repos is None:
            repos = self._fetch_org_repos()
        
        reports = []
        for repo in repos:
            try:
                health = self.execute_repo_health(repo)
                reports.append(health)
            except Exception as e:
                h = RepoHealth(repo=repo)
                h.compute_score()
                print(f"Warning: Failed to scan {repo}: {e}")
                reports.append(h)
        
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
        node_ci = m._gen_ci("node")
        self.assertIsNotNone(node_ci)
        self.assertIn("npm", node_ci)
        self.assertIn("setup-node", node_ci)
        self.assertIsNotNone(m._gen_ci("go"))
        self.assertIsNotNone(m._gen_ci("rust"))
        self.assertIsNone(m._gen_ci("unknown"))

    def test_gen_ci_c(self):
        m = FleetMechanic("fake-token")
        c_ci = m._gen_ci("c")
        self.assertIsNotNone(c_ci)
        self.assertIn("gcc", c_ci)
        self.assertIn("make", c_ci)

    def test_gen_ci_python(self):
        m = FleetMechanic("fake-token")
        ci = m._gen_ci("python")
        self.assertIn("pytest", ci)
        self.assertIn("setup-python", ci)

    def test_gen_ci_rust(self):
        m = FleetMechanic("fake-token")
        ci = m._gen_ci("rust")
        self.assertIn("cargo test", ci)

    def test_gen_ci_go(self):
        m = FleetMechanic("fake-token")
        ci = m._gen_ci("go")
        self.assertIn("go test", ci)
        self.assertIn("setup-go", ci)

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

    def test_default_branch_detection(self):
        m = FleetMechanic("fake-token")
        # With fake token, API returns error dict without default_branch
        branch = m._get_default_branch("nonexistent")
        self.assertEqual(branch, "main")

    def test_api_uses_urllib(self):
        """Verify _api uses urllib, not shell curl."""
        import inspect
        source = inspect.getsource(FleetMechanic._api)
        self.assertIn("urllib", source)
        self.assertNotIn("curl", source)

    def test_push_changes_no_shell_injection(self):
        """Verify push_changes uses list args, not shell string."""
        import inspect
        source = inspect.getsource(FleetMechanic.push_changes)
        self.assertIn("shell=False", source)

    def test_run_with_list_args(self):
        m = FleetMechanic("fake-token")
        code, out = m._run(["echo", "hello"], shell=False)
        self.assertEqual(code, 0)
        self.assertIn("hello", out)

    def test_fleet_scan_no_cap(self):
        """Verify fleet_scan no longer has a 20-repo hard cap."""
        import inspect
        source = inspect.getsource(FleetMechanic.fleet_scan)
        self.assertNotIn(":20", source)

    def test_run_error_handling(self):
        m = FleetMechanic("fake-token")
        code, out = m._run("nonexistent_command_xyz_123")
        self.assertNotEqual(code, 0)
        self.assertTrue(len(out) > 0 or code != 0)

    def test_mechanic_init(self):
        m = FleetMechanic("test-token", org="TestOrg")
        self.assertEqual(m.token, "test-token")
        self.assertEqual(m.org, "TestOrg")
        self.assertEqual(len(m.completed_tasks), 0)
        self.assertEqual(len(m.health_reports), 0)
        self.assertTrue(os.path.exists(m.work_dir))

    def test_task_type_enum(self):
        self.assertEqual(TaskType.FIX_TESTS.value, "fix_tests")
        self.assertEqual(TaskType.GEN_DOCS.value, "gen_docs")
        self.assertEqual(TaskType.GEN_CODE.value, "gen_code")
        self.assertEqual(TaskType.GEN_CI.value, "gen_ci")
        self.assertEqual(TaskType.REPO_HEALTH.value, "repo_health")
        self.assertEqual(TaskType.SYNC.value, "sync")
        self.assertEqual(TaskType.REVIEW.value, "review")

    def test_task_result_enum(self):
        self.assertEqual(TaskResult.SUCCESS.value, "success")
        self.assertEqual(TaskResult.PARTIAL.value, "partial")
        self.assertEqual(TaskResult.FAILED.value, "failed")
        self.assertEqual(TaskResult.BLOCKED.value, "blocked")

    def test_health_score_all_fields(self):
        h = RepoHealth(
            repo="full", has_readme=True, has_gitignore=True,
            has_ci=True, has_tests=True, test_count=4, test_pass=2, test_fail=2,
        )
        h.compute_score()
        # 0.2 + 0.1 + 0.2 + 0.2 + 0.3*(2/4) = 0.85
        self.assertAlmostEqual(h.health_score, 0.85)

    def test_health_markdown_all_checks(self):
        h = RepoHealth(
            repo="check", has_readme=False, has_gitignore=True,
            has_ci=False, has_tests=True, test_count=3, test_pass=1,
            language="rust", size_kb=1024,
        )
        md = h.to_markdown()
        self.assertIn("❌", md)
        self.assertIn("rust", md)
        self.assertIn("1024KB", md)

    def test_gitignore_node(self):
        m = FleetMechanic("fake-token")
        gi = m._gen_gitignore("node")
        self.assertIn("node_modules", gi)

    def test_detect_language_all(self):
        import tempfile
        m = FleetMechanic("fake-token")
        with tempfile.TemporaryDirectory() as tmpdir:
            for marker, expected in [
                ("Cargo.toml", "rust"), ("go.mod", "go"),
                ("package.json", "node"), ("pyproject.toml", "python"),
                ("setup.py", "python"), ("Makefile", "c"),
            ]:
                d = os.path.join(tmpdir, marker.replace(".", "_"))
                os.makedirs(d)
                open(os.path.join(d, marker), "w").close()
                self.assertEqual(m._detect_language(d), expected)

    def test_clone_repo_fake(self):
        m = FleetMechanic("fake-token")
        result = m.clone_repo("nonexistent-repo-xyz")
        self.assertFalse(result)

    def test_run_tests_no_framework(self):
        import tempfile
        m = FleetMechanic("fake-token")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(f"{tmpdir}/fake-repo")
            m.work_dir = tmpdir
            total, passed, failed = m.run_tests("fake-repo")
            self.assertEqual(total, 0)
            self.assertEqual(passed, 0)
            self.assertEqual(failed, 0)

    def test_execute_repo_health_fake(self):
        m = FleetMechanic("fake-token")
        health = m.execute_repo_health("nonexistent-repo-xyz")
        # Should not crash, just return a health with default values
        self.assertIsNotNone(health)
        self.assertEqual(health.repo, "nonexistent-repo-xyz")

    def test_create_issue_with_labels(self):
        m = FleetMechanic("fake-token")
        issue = m.create_issue("nonexistent", "Test", "Body", labels=["bug", "help-wanted"])
        self.assertIsNone(issue)

    def test_completed_tasks_tracking(self):
        m = FleetMechanic("fake-token")
        self.assertEqual(len(m.completed_tasks), 0)

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
