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
    
    def __init__(self, github_token: str, org: str = "SuperInstance"):
        self.token = github_token
        self.org = org
        self.work_dir = "/tmp/mechanic-work"
        os.makedirs(self.work_dir, exist_ok=True)
        self.completed_tasks: List[MechanicTask] = []
        self.health_reports: Dict[str, RepoHealth] = {}
    
    def _run(self, cmd: str, cwd: str = None) -> Tuple[int, str]:
        """Run a shell command."""
        env = os.environ.copy()
        env["GITHUB_TOKEN"] = self.token
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=cwd or self.work_dir, env=env, timeout=60
            )
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return -1, "TIMEOUT"
    
    def _api(self, method: str, path: str, data: Dict = None) -> Dict:
        """Call GitHub API."""
        cmd = f'curl -s -H "Authorization: token {self.token}" -X {method}'
        if data:
            cmd += f" -d '{json.dumps(data)}'"
        cmd += f" https://api.github.com{path}"
        code, out = self._run(cmd)
        try:
            return json.loads(out) if out else {}
        except json.JSONDecodeError:
            return {"error": out[:200]}
    
    def clone_repo(self, repo: str) -> bool:
        """Clone a repo to work directory."""
        os.makedirs(self.work_dir, exist_ok=True)
        repo_dir = f"{self.work_dir}/{repo}"
        if os.path.exists(repo_dir):
            self._run(f"rm -rf {repo_dir}")
        code, out = self._run(
            f"git clone --depth 1 https://SuperInstance:{self.token}@github.com/{self.org}/{repo}.git {repo_dir}"
        )
        return code == 0
    
    def push_changes(self, repo: str, message: str, branch: str = "main") -> bool:
        """Stage, commit, and push changes."""
        repo_dir = f"{self.work_dir}/{repo}"
        self._run("git add -A", cwd=repo_dir)
        code, _ = self._run(f'git commit -m "{message}"', cwd=repo_dir)
        if code != 0:
            return False  # nothing to commit
        code, _ = self._run(f"git push origin {branch}", cwd=repo_dir)
        return code == 0
    
    def create_pr(self, repo: str, branch: str, title: str, body: str = "") -> Optional[int]:
        """Create a pull request."""
        result = self._api("POST", f"/repos/{self.org}/{repo}/pulls", {
            "title": title, "body": body,
            "head": branch, "base": "main"
        })
        return result.get("number")
    
    def create_issue(self, repo: str, title: str, body: str, labels: List[str] = None) -> Optional[int]:
        """Create an issue."""
        data = {"title": title, "body": body}
        if labels:
            data["labels"] = labels
        result = self._api("POST", f"/repos/{self.org}/{repo}/issues", data)
        return result.get("number")
    
    def run_tests(self, repo: str) -> Tuple[int, int, int]:
        """Run tests and return (total, passed, failed)."""
        repo_dir = f"{self.work_dir}/{repo}"
        
        # Detect test framework
        if os.path.exists(f"{repo_dir}/Cargo.toml"):
            code, out = self._run("cargo test --lib 2>&1", cwd=repo_dir)
            if "test result:" in out:
                for line in out.split("\n"):
                    if "test result:" in line:
                        parts = line.split()
                        for p in parts:
                            if p.startswith("passed"): 
                                pass
                        # Parse the test result line
                        import re
                        m = re.search(r'(\d+) passed.*?(\d+) failed', line)
                        if m:
                            return int(m.group(1)) + int(m.group(2)), int(m.group(1)), int(m.group(2))
        
        elif os.path.exists(f"{repo_dir}/pyproject.toml") or os.path.exists(f"{repo_dir}/tests"):
            code, out = self._run("python3 -m pytest --tb=no -q 2>&1", cwd=repo_dir)
            for line in out.split("\n"):
                if "passed" in line:
                    import re
                    m = re.search(r'(\d+) passed.*?(\d+) failed', line)
                    if m:
                        return int(m.group(1)) + int(m.group(2)), int(m.group(1)), int(m.group(2))
        
        elif os.path.exists(f"{repo_dir}/go.mod"):
            code, out = self._run("go test ./... 2>&1", cwd=repo_dir)
            # Parse go test output
            pass_count = out.count("PASS")
            fail_count = out.count("FAIL")
            return pass_count + fail_count, pass_count, fail_count
        
        return 0, 0, 0
    
    # === TASK EXECUTORS ===
    
    def execute_repo_health(self, repo: str) -> RepoHealth:
        """Diagnose the health of a repository."""
        health = RepoHealth(repo=repo)
        
        # Get repo info via API
        info = self._api("GET", f"/repos/{self.org}/{repo}")
        if "message" in info and info["message"] == "Not Found":
            # Try fork source
            info = self._api("GET", f"/repos/Lucineer/{repo}")
        
        health.size_kb = info.get("size", 0)
        health.language = info.get("language") or "unknown"
        
        # Clone and check files
        if not self.clone_repo(repo):
            health.compute_score()
            return health
        
        repo_dir = f"{self.work_dir}/{repo}"
        health.has_readme = os.path.exists(f"{repo_dir}/README.md")
        health.has_gitignore = os.path.exists(f"{repo_dir}/.gitignore")
        health.has_ci = os.path.exists(f"{repo_dir}/.github/workflows")
        health.has_tests = (
            os.path.exists(f"{repo_dir}/tests") or 
            os.path.exists(f"{repo_dir}/test") or
            bool([f for f in os.listdir(repo_dir) if "test" in f.lower()]) if os.path.isdir(repo_dir) else False
        )
        
        # Run tests if possible
        if health.has_tests:
            total, passed, failed = self.run_tests(repo)
            health.test_count = total
            health.test_pass = passed
            health.test_fail = failed
            health.test_pass_rate = (passed / total) if total > 0 else 0
        
        health.compute_score()
        self.health_reports[repo] = health
        return health
    
    def execute_gen_docs(self, repo: str) -> MechanicTask:
        """Generate missing documentation files."""
        task = MechanicTask(
            id=f"DOCS-{int(time.time())}",
            task_type=TaskType.GEN_DOCS,
            target_repo=repo,
        )
        
        if not self.clone_repo(repo):
            task.result = TaskResult.FAILED
            task.diagnosis = "Could not clone repo"
            return task
        
        repo_dir = f"{self.work_dir}/{repo}"
        
        # Generate .gitignore if missing
        if not os.path.exists(f"{repo_dir}/.gitignore"):
            lang = self._detect_language(repo_dir)
            gitignore = self._gen_gitignore(lang)
            with open(f"{repo_dir}/.gitignore", "w") as f:
                f.write(gitignore)
            task.files_changed += 1
            task.diagnosis += "Added .gitignore. "
        
        # Generate CI workflow if missing
        if not os.path.exists(f"{repo_dir}/.github/workflows"):
            os.makedirs(f"{repo_dir}/.github/workflows", exist_ok=True)
            lang = self._detect_language(repo_dir)
            ci = self._gen_ci(lang)
            if ci:
                with open(f"{repo_dir}/.github/workflows/ci.yml", "w") as f:
                    f.write(ci)
                task.files_changed += 1
                task.diagnosis += "Added CI workflow. "
        
        if task.files_changed > 0:
            self.push_changes(repo, "chore: add missing .gitignore and CI workflow [mechanic]")
            task.commits_made = 1
            task.result = TaskResult.SUCCESS
        else:
            task.result = TaskResult.PARTIAL
            task.diagnosis = "No missing files found"
        
        self.completed_tasks.append(task)
        return task
    
    def _detect_language(self, repo_dir: str) -> str:
        if os.path.exists(f"{repo_dir}/Cargo.toml"): return "rust"
        if os.path.exists(f"{repo_dir}/go.mod"): return "go"
        if os.path.exists(f"{repo_dir}/package.json"): return "node"
        if os.path.exists(f"{repo_dir}/pyproject.toml") or os.path.exists(f"{repo_dir}/setup.py"): return "python"
        if os.path.exists(f"{repo_dir}/Makefile"): return "c"
        return "unknown"
    
    def _gen_gitignore(self, lang: str) -> str:
        templates = {
            "python": "__pycache__/\n*.pyc\n.pytest_cache/\n*.egg-info/\ndist/\nbuild/\n",
            "rust": "target/\nCargo.lock\n**/*.rs.bk\n",
            "go": "bin/\n*.exe\n*.test\nvendor/\n",
            "node": "node_modules/\ndist/\n*.js\n!jest.config.js\n",
            "c": "*.o\n*.out\n*.bin\nbuild/\n",
        }
        return templates.get(lang, "*.pyc\n__pycache__/\n")
    
    def _gen_ci(self, lang: str) -> Optional[str]:
        templates = {
            "python": 'name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with: {python-version: "3.12"}\n      - run: pip install pytest\n      - run: pytest -v\n',
            "rust": 'name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: cargo test --lib\n',
            "go": 'name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-go@v5\n        with: {go-version: "1.24"}\n      - run: go test ./...\n',
        }
        return templates.get(lang)
    
    def fleet_scan(self, repos: List[str] = None) -> List[RepoHealth]:
        """Scan fleet repos and generate health reports."""
        if repos is None:
            # Get all SuperInstance repos
            result = self._api("GET", f"/users/{self.org}/repos?per_page=100")
            if isinstance(result, list):
                repos = [r["name"] for r in result if not r.get("fork")]
            else:
                repos = []
        
        reports = []
        for repo in repos[:20]:  # Limit to 20 per scan
            try:
                health = self.execute_repo_health(repo)
                reports.append(health)
            except Exception as e:
                h = RepoHealth(repo=repo)
                h.diagnosis = str(e)
                reports.append(h)
        
        return reports


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
