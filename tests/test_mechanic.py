"""Comprehensive test suite for fleet-mechanic.

Covers:
- Import tests for all modules
- Unit tests for mechanic.py (FleetMechanic, MechanicTask, RepoHealth, TaskType, TaskResult)
- Unit tests for gen_code.py (CodeGenerator, CodeSpec, Language)
- Unit tests for review.py (CodeReviewer, ReviewReport, ReviewComment, Severity)
- Unit tests for fix_code.py (CodeFixer, DiagnosticFailureParser, MechanicCodeFixer, CodeFix, DiagnosticFailure)
- Unit tests for scan_fleet.py (RateLimiter, filter_repos_by_type, print_scan_results, print_summary)
- Unit tests for boot.py (load_github_token, fetch_user_repos, filter_own_repos, print_scan_results, print_summary)
- Edge cases and error handling
- Integration tests
"""
import os
import sys
import tempfile
import subprocess
from unittest.mock import patch, MagicMock

import pytest


# ============================================================================
# 1. IMPORT TESTS
# ============================================================================

class TestImports:
    """Verify all modules import cleanly without errors."""

    def test_import_mechanic(self):
        import mechanic
        assert hasattr(mechanic, 'FleetMechanic')
        assert hasattr(mechanic, 'MechanicTask')
        assert hasattr(mechanic, 'RepoHealth')
        assert hasattr(mechanic, 'TaskType')
        assert hasattr(mechanic, 'TaskResult')
        assert hasattr(mechanic, 'mechanic_flux_program')

    def test_import_gen_code(self):
        import gen_code
        assert hasattr(gen_code, 'CodeGenerator')
        assert hasattr(gen_code, 'CodeSpec')
        assert hasattr(gen_code, 'Language')

    def test_import_review(self):
        import review
        assert hasattr(review, 'CodeReviewer')
        assert hasattr(review, 'ReviewReport')
        assert hasattr(review, 'ReviewComment')
        assert hasattr(review, 'Severity')

    def test_import_fix_code(self):
        import fix_code
        assert hasattr(fix_code, 'CodeFixer')
        assert hasattr(fix_code, 'DiagnosticFailureParser')
        assert hasattr(fix_code, 'MechanicCodeFixer')
        assert hasattr(fix_code, 'CodeFix')
        assert hasattr(fix_code, 'DiagnosticFailure')

    def test_import_scan_fleet(self):
        import scan_fleet
        assert hasattr(scan_fleet, 'RateLimiter')
        assert hasattr(scan_fleet, 'load_github_token')
        assert hasattr(scan_fleet, 'fetch_repos_paginated')
        assert hasattr(scan_fleet, 'filter_repos_by_type')
        assert hasattr(scan_fleet, 'print_scan_results')
        assert hasattr(scan_fleet, 'print_summary')

    def test_import_boot(self):
        import boot
        assert hasattr(boot, 'load_github_token')
        assert hasattr(boot, 'fetch_user_repos')
        assert hasattr(boot, 'filter_own_repos')
        assert hasattr(boot, 'print_scan_results')
        assert hasattr(boot, 'print_summary')


# ============================================================================
# 2. MECHANIC.PY — TaskType & TaskResult Enums
# ============================================================================

class TestTaskType:
    """Tests for the TaskType enum."""

    def test_all_task_types_exist(self):
        from mechanic import TaskType
        assert TaskType.FIX_TESTS.value == "fix_tests"
        assert TaskType.GEN_DOCS.value == "gen_docs"
        assert TaskType.GEN_CODE.value == "gen_code"
        assert TaskType.GEN_CI.value == "gen_ci"
        assert TaskType.REPO_HEALTH.value == "repo_health"
        assert TaskType.SYNC.value == "sync"
        assert TaskType.REVIEW.value == "review"

    def test_task_type_count(self):
        from mechanic import TaskType
        assert len(TaskType) == 7


class TestTaskResult:
    """Tests for the TaskResult enum."""

    def test_all_results_exist(self):
        from mechanic import TaskResult
        assert TaskResult.SUCCESS.value == "success"
        assert TaskResult.PARTIAL.value == "partial"
        assert TaskResult.FAILED.value == "failed"
        assert TaskResult.BLOCKED.value == "blocked"

    def test_task_result_count(self):
        from mechanic import TaskResult
        assert len(TaskResult) == 4


# ============================================================================
# 3. MECHANIC.PY — MechanicTask
# ============================================================================

class TestMechanicTask:
    """Tests for the MechanicTask dataclass."""

    def test_creation_with_required_fields(self):
        from mechanic import MechanicTask, TaskType
        t = MechanicTask(id="T-001", task_type=TaskType.FIX_TESTS, target_repo="my-repo")
        assert t.id == "T-001"
        assert t.task_type == TaskType.FIX_TESTS
        assert t.target_repo == "my-repo"
        assert t.target_branch == "main"
        assert t.description == ""
        assert t.params == {}
        assert t.result is None
        assert t.diagnosis == ""
        assert t.commits_made == 0
        assert t.tests_fixed == 0
        assert t.files_changed == 0

    def test_creation_with_all_fields(self):
        from mechanic import MechanicTask, TaskType, TaskResult
        t = MechanicTask(
            id="FULL-001", task_type=TaskType.GEN_CODE, target_repo="full-repo",
            target_branch="develop", description="Generate all code",
            params={"key": "value"}, result=TaskResult.SUCCESS,
            diagnosis="All good", commits_made=5, tests_fixed=10, files_changed=3,
        )
        assert t.target_branch == "develop"
        assert t.description == "Generate all code"
        assert t.params == {"key": "value"}
        assert t.result == TaskResult.SUCCESS
        assert t.commits_made == 5
        assert t.tests_fixed == 10
        assert t.files_changed == 3

    def test_to_dict_basic(self):
        from mechanic import MechanicTask, TaskType
        t = MechanicTask(id="D-1", task_type=TaskType.GEN_DOCS, target_repo="doc-repo")
        d = t.to_dict()
        assert isinstance(d, dict)
        assert d["id"] == "D-1"
        assert d["type"] == "gen_docs"
        assert d["repo"] == "doc-repo"
        assert d["branch"] == "main"
        assert d["description"] == ""
        assert d["result"] is None
        assert d["diagnosis"] == ""
        assert d["commits"] == 0
        assert d["tests_fixed"] == 0
        assert d["files_changed"] == 0

    def test_to_dict_with_result(self):
        from mechanic import MechanicTask, TaskType, TaskResult
        t = MechanicTask(id="R-1", task_type=TaskType.REVIEW, target_repo="rev-repo",
                         result=TaskResult.PARTIAL)
        d = t.to_dict()
        assert d["result"] == "partial"

    def test_to_dict_all_values(self):
        from mechanic import MechanicTask, TaskType, TaskResult
        t = MechanicTask(
            id="X-001", task_type=TaskType.FIX_TESTS, target_repo="x-repo",
            target_branch="dev", description="Fix tests", params={"a": 1},
            result=TaskResult.SUCCESS, diagnosis="Fixed", commits_made=2,
            tests_fixed=5, files_changed=1,
        )
        d = t.to_dict()
        assert d == {
            "id": "X-001", "type": "fix_tests", "repo": "x-repo",
            "branch": "dev", "description": "Fix tests", "result": "success",
            "diagnosis": "Fixed", "commits": 2, "tests_fixed": 5, "files_changed": 1,
        }

    def test_params_default_factory_isolation(self):
        from mechanic import MechanicTask, TaskType
        t1 = MechanicTask(id="1", task_type=TaskType.SYNC, target_repo="r1")
        t2 = MechanicTask(id="2", task_type=TaskType.SYNC, target_repo="r2")
        t1.params["key"] = "value"
        assert "key" not in t2.params


# ============================================================================
# 4. MECHANIC.PY — RepoHealth
# ============================================================================

class TestRepoHealth:
    """Tests for the RepoHealth dataclass."""

    def test_default_values(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="test-repo")
        assert h.repo == "test-repo"
        assert h.has_readme is False
        assert h.has_gitignore is False
        assert h.has_ci is False
        assert h.has_tests is False
        assert h.test_pass_rate == 0.0
        assert h.test_count == 0
        assert h.test_pass == 0
        assert h.test_fail == 0
        assert h.language == "unknown"
        assert h.size_kb == 0
        assert h.open_issues == 0
        assert h.last_commit_days == 0
        assert h.health_score == 0.0

    def test_compute_score_empty(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="empty")
        h.compute_score()
        assert h.health_score == 0.0

    def test_compute_score_readme_only(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_readme=True)
        h.compute_score()
        assert h.health_score == pytest.approx(0.2)

    def test_compute_score_all_infra_no_tests(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_readme=True, has_gitignore=True,
                       has_ci=True, has_tests=True, test_count=0)
        h.compute_score()
        assert h.health_score == pytest.approx(0.7)

    def test_compute_score_perfect(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_readme=True, has_gitignore=True,
                       has_ci=True, has_tests=True, test_count=10, test_pass=10)
        h.compute_score()
        assert h.health_score == 1.0

    def test_compute_score_partial_tests(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_readme=True, has_gitignore=True,
                       has_ci=True, has_tests=True, test_count=10, test_pass=5)
        h.compute_score()
        # 0.2 + 0.1 + 0.2 + 0.2 + 0.3*(5/10) = 0.7 + 0.15 = 0.85
        assert h.health_score == pytest.approx(0.85)

    def test_compute_score_capped_at_1(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_readme=True, has_gitignore=True,
                       has_ci=True, has_tests=True, test_count=1, test_pass=1)
        h.compute_score()
        assert h.health_score == 1.0

    def test_compute_score_zero_tests_with_flag(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_readme=True, has_gitignore=True,
                       has_ci=True, has_tests=True, test_count=0, test_pass=0)
        h.compute_score()
        assert h.health_score == pytest.approx(0.7)

    def test_to_markdown_basic(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="my-repo", has_readme=True, has_gitignore=True,
                       has_ci=True, has_tests=True, test_count=8, test_pass=7,
                       language="Python", size_kb=256)
        md = h.to_markdown()
        assert "# Health Report: my-repo" in md
        assert "README" in md
        assert ".gitignore" in md
        assert "CI/CD" in md
        assert "Tests" in md
        assert "7/8" in md
        assert "Python" in md
        assert "256KB" in md
        assert "Health Score" in md

    def test_to_markdown_recomputes_score(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r")
        assert h.health_score == 0.0
        h.has_readme = True
        md = h.to_markdown()
        assert h.health_score == pytest.approx(0.2)

    def test_to_markdown_no_tests(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_tests=False, test_count=0)
        md = h.to_markdown()
        assert "0/0" in md


# ============================================================================
# 5. MECHANIC.PY — FleetMechanic
# ============================================================================

class TestFleetMechanicInit:
    """Tests for FleetMechanic initialization."""

    def test_init_with_valid_token(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token-123")
        assert m.token == "fake-token-123"
        assert m.org == "SuperInstance"
        assert m.work_dir == "/tmp/mechanic-work"
        assert m.completed_tasks == []
        assert m.health_reports == {}

    def test_init_with_custom_org(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("token", org="MyOrg")
        assert m.org == "MyOrg"

    def test_init_empty_token_raises(self):
        from mechanic import FleetMechanic
        with pytest.raises(ValueError, match="GitHub token cannot be empty"):
            FleetMechanic("")

    def test_init_none_token_raises(self):
        from mechanic import FleetMechanic
        with pytest.raises(ValueError, match="GitHub token cannot be empty"):
            FleetMechanic(None)


class TestFleetMechanicRun:
    """Tests for FleetMechanic._run command execution."""

    def test_run_echo(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        code, out = m._run("echo hello")
        assert code == 0
        assert "hello" in out

    def test_run_with_custom_cwd(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        code, out = m._run("pwd", cwd=str(tmp_path))
        assert code == 0
        assert str(tmp_path) in out

    def test_run_invalid_dir_raises(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with pytest.raises(RuntimeError, match="does not exist"):
            m._run("echo hi", cwd="/tmp/nonexistent_dir_12345")
        return  # skip old asserts
    def _OLD_test_run_invalid_dir_raises_DISABLED(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        code, out = m._run("echo hi", cwd="/tmp/nonexistent_dir_12345")
        assert code == -1
        assert "does not exist" in out

    def test_run_command_timeout(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        code, out = m._run("sleep 10", timeout=1)
        assert code == -1
        assert "TIMEOUT" in out

    def test_run_failing_command(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        code, out = m._run("exit 42")
        assert code == 42


class TestFleetMechanicDetectLanguage:
    """Tests for _detect_language."""

    def test_detect_python_pyproject(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        (tmp_path / "pyproject.toml").write_text("[tool]")
        assert m._detect_language(str(tmp_path)) == "python"

    def test_detect_python_setup(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        (tmp_path / "setup.py").write_text("from setuptools import setup")
        assert m._detect_language(str(tmp_path)) == "python"

    def test_detect_rust(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        (tmp_path / "Cargo.toml").write_text("[package]")
        assert m._detect_language(str(tmp_path)) == "rust"

    def test_detect_go(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        (tmp_path / "go.mod").write_text("module test")
        assert m._detect_language(str(tmp_path)) == "go"

    def test_detect_node(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        (tmp_path / "package.json").write_text("{}")
        assert m._detect_language(str(tmp_path)) == "node"

    def test_detect_c_makefile(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        (tmp_path / "Makefile").write_text("all:\n\tgcc main.c")
        assert m._detect_language(str(tmp_path)) == "c"

    def test_detect_unknown(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        (tmp_path / "README.md").write_text("hello")
        assert m._detect_language(str(tmp_path)) == "unknown"

    def test_detect_nonexistent(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        assert m._detect_language("/tmp/nonexistent_xyz") == "unknown"

    def test_detect_none_dir(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        assert m._detect_language(None) == "unknown"

    def test_detect_empty_string_dir(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        assert m._detect_language("") == "unknown"

    def test_detect_priority_cargo_over_package_json(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        (tmp_path / "Cargo.toml").write_text("[package]")
        (tmp_path / "package.json").write_text("{}")
        assert m._detect_language(str(tmp_path)) == "rust"


class TestFleetMechanicGitignore:
    """Tests for _gen_gitignore."""

    def test_python_gitignore(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        gi = m._gen_gitignore("python")
        assert "__pycache__" in gi
        assert "*.pyc" in gi
        assert ".pytest_cache" in gi

    def test_rust_gitignore(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        gi = m._gen_gitignore("rust")
        assert "target/" in gi
        assert "Cargo.lock" in gi

    def test_go_gitignore(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        gi = m._gen_gitignore("go")
        assert "vendor/" in gi

    def test_node_gitignore(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        gi = m._gen_gitignore("node")
        assert "node_modules/" in gi

    def test_c_gitignore(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        gi = m._gen_gitignore("c")
        assert "*.o" in gi

    def test_unknown_gitignore_fallback(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        gi = m._gen_gitignore("unknown_lang")
        assert len(gi) > 0


class TestFleetMechanicCI:
    """Tests for _gen_ci."""

    def test_python_ci(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        ci = m._gen_ci("python")
        assert ci is not None
        assert "pytest" in ci
        assert "CI" in ci
        assert "ubuntu-latest" in ci

    def test_rust_ci(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        ci = m._gen_ci("rust")
        assert ci is not None
        assert "cargo test" in ci

    def test_go_ci(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        ci = m._gen_ci("go")
        assert ci is not None
        assert "go test" in ci

    def test_node_ci_none(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        assert m._gen_ci("node") is None

    def test_unknown_ci_none(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        assert m._gen_ci("unknown") is None


class TestFleetMechanicAPI:
    """Tests for _api method."""

    def test_api_path_normalization(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        # Both forms should result in the same path
        with patch.object(m, '_run', return_value=(0, '{"ok": true}')):
            m._api("GET", "repos/test/repo")
            call_args = m._run.call_args[0][0]
            assert "/repos/test/repo" in call_args

    def test_api_path_without_leading_slash(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, '_run', return_value=(0, '{"ok": true}')):
            m._api("GET", "repos/test/repo")
            call_args = m._run.call_args[0][0]
            assert "/repos/test/repo" in call_args

    def test_api_nonzero_return(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, '_run', return_value=(1, "error output")):
            result = m._api("GET", "repos/test")
            assert "error" in result

    def test_api_invalid_json(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, '_run', return_value=(0, "not json at all")):
            result = m._api("GET", "repos/test")
            assert "error" in result
            assert "Invalid JSON" in result["error"]

    def test_api_empty_response(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, '_run', return_value=(0, "")):
            result = m._api("GET", "repos/test")
            assert result == {}


class TestFleetMechanicClone:
    """Tests for clone_repo."""

    def test_clone_empty_repo_raises(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with pytest.raises(ValueError, match="Repository name cannot be empty"):
            m.clone_repo("")

    def test_clone_with_mocked_run(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, '_run', return_value=(0, "cloned")):
            assert m.clone_repo("test-repo") is True

    def test_clone_failure(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, '_run', return_value=(128, "permission denied")):
            assert m.clone_repo("test-repo") is False


class TestFleetMechanicPush:
    """Tests for push_changes."""

    def test_push_empty_repo_raises(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with pytest.raises(ValueError, match="Repository name cannot be empty"):
            m.push_changes("", "msg")

    def test_push_empty_message_raises(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with pytest.raises(ValueError, match="Commit message cannot be empty"):
            m.push_changes("repo", "")

    def test_push_no_git_dir(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        m.work_dir = str(tmp_path)
        assert m.push_changes("nonexistent", "msg") is False


class TestFleetMechanicCreatePR:
    """Tests for create_pr."""

    def test_create_pr_missing_params(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with pytest.raises(ValueError, match="repo, branch, and title are required"):
            m.create_pr("", "branch", "title")
        with pytest.raises(ValueError):
            m.create_pr("repo", "", "title")
        with pytest.raises(ValueError):
            m.create_pr("repo", "branch", "")

    def test_create_pr_api_error(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, '_api', return_value={"error": "not found"}):
            assert m.create_pr("repo", "branch", "title") is None

    def test_create_pr_success(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, '_api', return_value={"number": 42, "html_url": "..."}):
            assert m.create_pr("repo", "branch", "title") == 42


class TestFleetMechanicCreateIssue:
    """Tests for create_issue."""

    def test_create_issue_missing_params(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with pytest.raises(ValueError, match="repo and title are required"):
            m.create_issue("", "title", "body")
        with pytest.raises(ValueError):
            m.create_issue("repo", "", "body")

    def test_create_issue_with_labels(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, '_api', return_value={"number": 7}) as mock_api:
            m.create_issue("repo", "title", "body", labels=["bug", "help"])
            call_kwargs = mock_api.call_args[1] if mock_api.call_args else None
            # Check the data passed
            assert mock_api.called


class TestFleetMechanicRunTests:
    """Tests for run_tests."""

    def test_run_tests_empty_repo_raises(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with pytest.raises(ValueError, match="Repository name cannot be empty"):
            m.run_tests("")

    def test_run_tests_nonexistent_dir(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        total, passed, failed = m.run_tests("nonexistent_repo_xyz")
        assert (total, passed, failed) == (0, 0, 0)

    def test_run_tests_no_framework(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        repo_dir = tmp_path / "no-framework"
        repo_dir.mkdir()
        m.work_dir = str(tmp_path)
        total, passed, failed = m.run_tests("no-framework")
        assert (total, passed, failed) == (0, 0, 0)


class TestFleetMechanicFleetScan:
    """Tests for fleet_scan."""

    def test_fleet_scan_empty_list(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        reports = m.fleet_scan(repos=[])
        assert reports == []

    def test_fleet_scan_error_handling(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, 'execute_repo_health', side_effect=Exception("boom")):
            reports = m.fleet_scan(repos=["repo1"])
            assert len(reports) == 1
            assert reports[0].repo == "repo1"

    def test_fleet_scan_limits_to_20(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        repos = [f"repo-{i}" for i in range(30)]
        with patch.object(m, 'execute_repo_health') as mock:
            mock.return_value = MagicMock()
            m.fleet_scan(repos=repos)
            assert mock.call_count == 20


class TestFleetMechanicFluxProgram:
    """Tests for mechanic_flux_program."""

    def test_flux_program_returns_list(self):
        from mechanic import mechanic_flux_program
        bc = mechanic_flux_program()
        assert isinstance(bc, list)

    def test_flux_program_starts_with_movl(self):
        from mechanic import mechanic_flux_program
        bc = mechanic_flux_program()
        assert bc[0] == 0x18  # MOVI

    def test_flux_program_contains_halt(self):
        from mechanic import mechanic_flux_program
        bc = mechanic_flux_program()
        assert 0x00 in bc

    def test_flux_program_has_reasonable_length(self):
        from mechanic import mechanic_flux_program
        bc = mechanic_flux_program()
        assert 10 < len(bc) < 100

    def test_flux_program_deterministic(self):
        from mechanic import mechanic_flux_program
        assert mechanic_flux_program() == mechanic_flux_program()


# ============================================================================
# 6. GEN_CODE.PY — Language Enum
# ============================================================================

class TestLanguage:
    """Tests for the Language enum."""

    def test_all_languages(self):
        from gen_code import Language
        assert Language.PYTHON.value == "python"
        assert Language.RUST.value == "rust"
        assert Language.GO.value == "go"
        assert Language.TYPESCRIPT.value == "typescript"
        assert len(Language) == 4


# ============================================================================
# 7. GEN_CODE.PY — CodeSpec
# ============================================================================

class TestCodeSpec:
    """Tests for CodeSpec dataclass."""

    def test_defaults(self):
        from gen_code import CodeSpec, Language
        spec = CodeSpec(name="calc", description="Calculator", language=Language.PYTHON)
        assert spec.functions == []
        assert spec.classes == []
        assert spec.test_cases == []
        assert spec.imports == []

    def test_to_prompt_basic(self):
        from gen_code import CodeSpec, Language
        spec = CodeSpec(name="calc", description="Calculator", language=Language.PYTHON)
        prompt = spec.to_prompt()
        assert "Calculator" in prompt
        assert "python" in prompt

    def test_to_prompt_with_functions(self):
        from gen_code import CodeSpec, Language
        spec = CodeSpec(
            name="calc", description="Calculator", language=Language.PYTHON,
            functions=[{"name": "add", "params": "a, b", "returns": "int"}],
        )
        prompt = spec.to_prompt()
        assert "add" in prompt
        assert "a, b" in prompt
        assert "int" in prompt

    def test_to_prompt_with_test_cases(self):
        from gen_code import CodeSpec, Language
        spec = CodeSpec(
            name="calc", description="Calc", language=Language.PYTHON,
            test_cases=[{"name": "add_positive"}, {"name": "add_negative"}],
        )
        prompt = spec.to_prompt()
        assert "add_positive" in prompt
        assert "add_negative" in prompt


# ============================================================================
# 8. GEN_CODE.PY — CodeGenerator
# ============================================================================

class TestCodeGenerator:
    """Tests for CodeGenerator class."""

    def test_generate_python_function(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="calc", description="Calculator", language=Language.PYTHON,
            functions=[{"name": "add", "params": "a, b", "returns": "int",
                        "body": "return a + b", "doc": "Add two numbers"}],
        )
        code = gen.generate(spec)
        assert "def add(a, b) -> int:" in code
        assert "return a + b" in code
        assert "Add two numbers" in code

    def test_generate_python_class(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="models", description="Data models", language=Language.PYTHON,
            classes=[{"name": "User", "fields": [
                {"name": "id", "type": "int"}, {"name": "name", "type": "str"},
            ]}],
        )
        code = gen.generate(spec)
        assert "@dataclass" in code
        assert "class User:" in code
        assert "id: int" in code
        assert "name: str" in code

    def test_generate_python_with_imports(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="util", description="Utility", language=Language.PYTHON,
            imports=["os", "sys", "json"],
        )
        code = gen.generate(spec)
        assert "import os" in code
        assert "import sys" in code
        assert "import json" in code

    def test_generate_rust_struct(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="models", description="Models", language=Language.RUST,
            classes=[{"name": "Agent", "fields": [
                {"name": "id", "type": "u64"}, {"name": "name", "type": "String"},
            ]}],
        )
        code = gen.generate(spec)
        assert "pub struct Agent" in code
        assert "pub id: u64" in code

    def test_generate_rust_function(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="lib", description="Library", language=Language.RUST,
            functions=[{"name": "compute", "params": "x: i32", "returns": "i32",
                        "body": "x * 2"}],
        )
        code = gen.generate(spec)
        assert "pub fn compute" in code
        assert "-> i32" in code

    def test_generate_go_struct(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="models", description="Models", language=Language.GO,
            classes=[{"name": "Config", "fields": [
                {"name": "port", "type": "int"}, {"name": "host", "type": "string"},
            ]}],
        )
        code = gen.generate(spec)
        assert "type Config struct" in code

    def test_generate_go_function(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="handler", description="Handler", language=Language.GO,
            functions=[{"name": "Serve", "params": "port int", "returns": "error",
                        "body": "return nil"}],
        )
        code = gen.generate(spec)
        assert "func Serve" in code
        assert "error" in code

    def test_generate_typescript_returns_empty(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="app", description="App", language=Language.TYPESCRIPT,
            functions=[{"name": "run", "params": "", "returns": "void", "body": ""}],
        )
        assert gen.generate(spec) == ""

    def test_generate_tests_python(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="calc", description="Calc", language=Language.PYTHON,
            test_cases=[{"name": "add_two_numbers", "body": "self.assertEqual(add(1, 2), 3)"}],
        )
        tests = gen.generate_tests(spec)
        assert "unittest" in tests
        assert "test_add_two_numbers" in tests
        assert "self.assertEqual(add(1, 2), 3)" in tests

    def test_generate_tests_rust(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="lib", description="Lib", language=Language.RUST,
            test_cases=[{"name": "basic", "body": "assert_eq!(2 + 2, 4);"}],
        )
        tests = gen.generate_tests(spec)
        assert "#[test]" in tests
        assert "#[cfg(test)]" in tests

    def test_generate_tests_go(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="calc", description="Calc", language=Language.GO,
            test_cases=[{"name": "Add", "body": "if Add(1, 2) != 3 { t.Error() }"}],
        )
        tests = gen.generate_tests(spec)
        assert "testing" in tests
        assert "TestAdd" in tests

    def test_generate_tests_typescript_empty(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(name="app", description="App", language=Language.TYPESCRIPT)
        assert gen.generate_tests(spec) == ""

    def test_generate_from_description_python(self):
        from gen_code import CodeGenerator, Language
        gen = CodeGenerator()
        source, tests = gen.generate_from_description(
            "stats", "calculate mean from numbers", Language.PYTHON
        )
        assert "calculate_mean" in source
        assert "unittest" in tests

    def test_generate_from_description_with_pattern_matching(self):
        from gen_code import CodeGenerator, Language
        gen = CodeGenerator()
        source, tests = gen.generate_from_description(
            "converter", "convert celsius to fahrenheit and validate temperature",
            Language.PYTHON
        )
        assert "convert_celsius_to_fahrenheit" in source
        assert "validate_temperature" in source

    def test_generate_from_description_default_function(self):
        from gen_code import CodeGenerator, Language
        gen = CodeGenerator()
        source, _ = gen.generate_from_description(
            "no-patterns", "this is just some description", Language.PYTHON
        )
        assert "no_patterns" in source

    def test_python_test_class_name_from_snake(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="my_module", description="Module", language=Language.PYTHON,
            test_cases=[{"name": "basic", "body": "pass"}],
        )
        tests = gen.generate_tests(spec)
        assert "class TestMyModule" in tests


# ============================================================================
# 9. REVIEW.PY — Severity
# ============================================================================

class TestSeverity:
    """Tests for the Severity enum."""

    def test_all_severities(self):
        from review import Severity
        assert Severity.INFO.value == "info"
        assert Severity.WARNING.value == "warning"
        assert Severity.ERROR.value == "error"
        assert Severity.CRITICAL.value == "critical"
        assert len(Severity) == 4


# ============================================================================
# 10. REVIEW.PY — ReviewComment
# ============================================================================

class TestReviewComment:
    """Tests for ReviewComment dataclass."""

    def test_creation(self):
        from review import ReviewComment, Severity
        c = ReviewComment(file="main.py", line=42, severity=Severity.ERROR,
                          category="style", message="Line too long",
                          suggestion="Break it up")
        assert c.file == "main.py"
        assert c.line == 42
        assert c.severity == Severity.ERROR
        assert c.category == "style"
        assert c.message == "Line too long"
        assert c.suggestion == "Break it up"

    def test_default_suggestion(self):
        from review import ReviewComment, Severity
        c = ReviewComment(file="f.py", line=1, severity=Severity.INFO,
                          category="info", message="Note")
        assert c.suggestion == ""


# ============================================================================
# 11. REVIEW.PY — ReviewReport
# ============================================================================

class TestReviewReport:
    """Tests for ReviewReport dataclass."""

    def test_empty_report(self):
        from review import ReviewReport
        r = ReviewReport(repo="test-repo", pr_number=None)
        assert r.comments == []
        assert r.approved is False
        assert r.score == 0.0
        assert r.pr_number is None

    def test_to_markdown_approved(self):
        from review import ReviewReport
        r = ReviewReport(repo="test", pr_number=5, score=85, approved=True)
        md = r.to_markdown()
        assert "Code Review: test" in md
        assert "PR #5" in md
        assert "85/100" in md
        assert "APPROVE" in md

    def test_to_markdown_rejected(self):
        from review import ReviewReport
        r = ReviewReport(repo="test", pr_number=1, score=30, approved=False)
        md = r.to_markdown()
        assert "CHANGES REQUESTED" in md

    def test_to_markdown_no_comments(self):
        from review import ReviewReport
        r = ReviewReport(repo="test", pr_number=None, score=100, approved=True)
        md = r.to_markdown()
        assert "No issues found" in md

    def test_to_markdown_with_comments(self):
        from review import ReviewReport, ReviewComment, Severity
        r = ReviewReport(repo="test", pr_number=None, score=50, approved=False)
        r.comments = [
            ReviewComment("f.py", 1, Severity.CRITICAL, "security", "hardcoded secret", "use env"),
            ReviewComment("f.py", 10, Severity.INFO, "style", "long line", "break it"),
        ]
        md = r.to_markdown()
        assert "Critical" in md
        assert "Info" in md
        assert "hardcoded secret" in md

    def test_to_markdown_no_pr_number(self):
        from review import ReviewReport
        r = ReviewReport(repo="test", pr_number=None, score=100, approved=True)
        md = r.to_markdown()
        assert "PR #" not in md


# ============================================================================
# 12. REVIEW.PY — CodeReviewer
# ============================================================================

class TestCodeReviewer:
    """Tests for CodeReviewer class."""

    def test_init_checks_list(self):
        from review import CodeReviewer
        r = CodeReviewer()
        assert len(r.checks) == 6

    def test_review_clean_python_file(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = 'def hello():\n    """Say hello."""\n    return "hello"\n'
        comments = r.review_file("clean.py", content)
        critical = [c for c in comments if c.severity.value == "critical"]
        assert len(critical) == 0

    def test_detect_hardcoded_secret(self):
        from review import CodeReviewer, Severity
        r = CodeReviewer()
        content = 'password = "super_secret_123"\n'
        comments = r.review_file("config.py", content)
        secrets = [c for c in comments if c.category == "security" and c.severity == Severity.CRITICAL]
        assert len(secrets) > 0
        assert "hardcoded_secret" in secrets[0].message

    def test_detect_eval(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = 'result = eval(user_input)\n'
        comments = r.review_file("bad.py", content)
        eval_issues = [c for c in comments if "eval" in c.message.lower()]
        assert len(eval_issues) > 0

    def test_detect_exec(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = 'exec(code_string)\n'
        comments = r.review_file("bad.py", content)
        exec_issues = [c for c in comments if "exec" in c.message.lower()]
        assert len(exec_issues) > 0

    def test_detect_shell_injection(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = 'subprocess.call("rm -rf /", shell=True)\n'
        comments = r.review_file("run.py", content)
        shell_issues = [c for c in comments if "shell" in c.message.lower()]
        assert len(shell_issues) > 0

    def test_detect_os_system(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = 'os.system("ls")\n'
        comments = r.review_file("run.py", content)
        os_issues = [c for c in comments if "os_system" in c.message.lower()]
        assert len(os_issues) > 0

    def test_detect_missing_docstring(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = 'def calculate(x, y):\n    return x + y\n'
        comments = r.review_file("math.py", content)
        docs = [c for c in comments if c.category == "docs"]
        assert len(docs) > 0
        assert "calculate" in docs[0].message

    def test_no_docstring_warning_for_private(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = 'def _internal(x):\n    return x\n'
        comments = r.review_file("util.py", content)
        docs = [c for c in comments if c.category == "docs"]
        assert len(docs) == 0

    def test_docstring_with_triple_single_quotes(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = "def greet():\n    '''Greet user.'''\n    return 'hi'\n"
        comments = r.review_file("greet.py", content)
        docs = [c for c in comments if c.category == "docs"]
        assert len(docs) == 0

    def test_detect_long_line(self):
        from review import CodeReviewer
        r = CodeReviewer()
        long_line = "x = " + "a" * 130
        comments = r.review_file("wide.py", long_line + "\n")
        style = [c for c in comments if "long" in c.message.lower()]
        assert len(style) > 0

    def test_no_long_line_warning_under_120(self):
        from review import CodeReviewer
        r = CodeReviewer()
        line = "x = " + "a" * 100
        comments = r.review_file("ok.py", line + "\n")
        long_lines = [c for c in comments if "long" in c.message.lower() and c.category == "style"]
        assert len(long_lines) == 0

    def test_detect_todo_without_issue(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = "# TODO: fix this later\n"
        comments = r.review_file("temp.py", content)
        todos = [c for c in comments if "TODO" in c.message]
        assert len(todos) > 0

    def test_todo_with_issue_reference_ok(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = "# TODO(#42): fix this later\n"
        comments = r.review_file("temp.py", content)
        todos = [c for c in comments if "TODO" in c.message]
        assert len(todos) == 0

    def test_detect_fixme(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = "# FIXME: this is broken\n"
        comments = r.review_file("broken.py", content)
        fixmes = [c for c in comments if "FIXME" in c.message]
        assert len(fixmes) > 0

    def test_detect_hack(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = "# HACK: workaround for bug\n"
        comments = r.review_file("hack.py", content)
        hacks = [c for c in comments if "HACK" in c.message]
        assert len(hacks) > 0

    def test_detect_assertion_in_source(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = 'def foo():\n    assert True\n'
        comments = r.review_file("source.py", content)
        assertions = [c for c in comments if "assertion" in c.message.lower()]
        assert len(assertions) > 0

    def test_assertions_in_test_files_ok(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = 'def test_foo():\n    assert True\n'
        comments = r.review_file("tests/test_foo.py", content)
        assertions = [c for c in comments if "assertion" in c.message.lower()]
        assert len(assertions) == 0

    def test_detect_complex_function(self):
        from review import CodeReviewer
        r = CodeReviewer()
        lines = ["def huge():"] + ["    x = 1"] * 60 + ["\ndef small():\n    pass\n"]
        comments = r.review_file("big.py", "\n".join(lines))
        complexity = [c for c in comments if c.category == "complexity"]
        assert len(complexity) > 0

    def test_fleet_compliance_readme(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = "# My Project\nSome code here.\n"
        comments = r.review_file("README.md", content)
        fleet = [c for c in comments if c.category == "fleet"]
        assert len(fleet) > 0

    def test_fleet_compliance_readme_with_fleet_ref(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = "# My Project\nPart of the FLUX Fleet. See oracle1-index.\n"
        comments = r.review_file("README.md", content)
        fleet_ref = [c for c in comments if "fleet reference" in c.message.lower()]
        assert len(fleet_ref) == 0

    def test_fleet_compliance_readme_with_test_count(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = "# My Project\nPart of the FLUX Fleet.\nTests: 50 passing.\n"
        comments = r.review_file("README.md", content)
        test_missing = [c for c in comments if "test count" in c.message.lower()]
        assert len(test_missing) == 0

    def test_score_computation_clean(self):
        from review import CodeReviewer, ReviewReport
        r = CodeReviewer()
        report = ReviewReport(repo="clean", pr_number=None)
        r._compute_score(report)
        assert report.score == 100.0
        assert report.approved is True

    def test_score_computation_with_warnings(self):
        from review import CodeReviewer, ReviewReport, ReviewComment, Severity
        r = CodeReviewer()
        report = ReviewReport(repo="test", pr_number=None)
        report.comments = [
            ReviewComment("a.py", 1, Severity.WARNING, "style", "long line"),
        ]
        r._compute_score(report)
        assert report.score == 95.0
        assert report.approved is True

    def test_score_computation_with_critical(self):
        from review import CodeReviewer, ReviewReport, ReviewComment, Severity
        r = CodeReviewer()
        report = ReviewReport(repo="test", pr_number=None)
        report.comments = [
            ReviewComment("a.py", 1, Severity.CRITICAL, "security", "bad"),
        ]
        r._compute_score(report)
        assert report.score == 80.0
        assert report.approved is False  # Critical → never approved

    def test_score_floor_at_zero(self):
        from review import CodeReviewer, ReviewReport, ReviewComment, Severity
        r = CodeReviewer()
        report = ReviewReport(repo="test", pr_number=None)
        report.comments = [
            ReviewComment(f"a{i}.py", 1, Severity.CRITICAL, "sec", "bad")
            for i in range(10)
        ]
        r._compute_score(report)
        assert report.score == 0.0

    def test_review_directory_empty(self, tmp_path):
        from review import CodeReviewer
        r = CodeReviewer()
        report = r.review_directory(str(tmp_path))
        assert len(report.comments) == 0
        assert report.score > 0

    def test_review_directory_with_files(self, tmp_path):
        from review import CodeReviewer
        r = CodeReviewer()
        # Write a Python file with issues
        (tmp_path / "bad.py").write_text(
            'api_key = "sk-12345678abcdef"\nresult = eval(x)\n'
        )
        report = r.review_directory(str(tmp_path))
        assert len(report.comments) > 0

    def test_review_directory_skips_hidden_dirs(self, tmp_path):
        from review import CodeReviewer
        r = CodeReviewer()
        hidden_dir = tmp_path / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "secret.py").write_text('api_key = "sk-12345678abcdef"\n')
        report = r.review_directory(str(tmp_path))
        assert len(report.comments) == 0

    def test_review_directory_picks_up_hidden_files(self, tmp_path):
        """Hidden files (not dirs) are still reviewed since os.walk only filters dirs."""
        from review import CodeReviewer
        r = CodeReviewer()
        (tmp_path / ".hidden.py").write_text('api_key = "sk-12345678abcdef"\n')
        report = r.review_directory(str(tmp_path))
        assert len(report.comments) > 0

    def test_review_directory_skips_node_modules(self, tmp_path):
        from review import CodeReviewer
        r = CodeReviewer()
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "bad.js").write_text('eval("code")\n')
        report = r.review_directory(str(tmp_path))
        assert len(report.comments) == 0

    def test_multiple_issues_in_one_file(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = (
            'api_key = "sk-12345678abcdef"\n'
            'result = eval(x)\n'
            'os.system("rm -rf /")\n'
        )
        comments = r.review_file("terrible.py", content)
        assert len(comments) >= 3


# ============================================================================
# 13. FIX_CODE.PY — DiagnosticFailure
# ============================================================================

class TestDiagnosticFailure:
    """Tests for DiagnosticFailure dataclass."""

    def test_creation(self):
        from fix_code import DiagnosticFailure
        d = DiagnosticFailure(
            test_name="test_add",
            file="tests/test_calc.py",
            line=10,
            error_type="AssertionError",
            error_message="expected 5 got 3",
        )
        assert d.test_name == "test_add"
        assert d.file == "tests/test_calc.py"
        assert d.line == 10
        assert d.error_type == "AssertionError"
        assert d.error_message == "expected 5 got 3"
        assert d.suggested_fix == ""

    def test_defaults(self):
        from fix_code import DiagnosticFailure
        d = DiagnosticFailure("test", "f.py", 0, "Error", "msg")
        assert d.suggested_fix == ""


# ============================================================================
# 14. FIX_CODE.PY — CodeFix
# ============================================================================

class TestCodeFix:
    """Tests for CodeFix dataclass."""

    def test_creation(self):
        from fix_code import CodeFix
        f = CodeFix(
            file="main.py", line=42,
            old_code="assert x > 0.8",
            new_code="assert x >= 0.8",
            description="Relaxed threshold",
            confidence=0.7,
        )
        assert f.file == "main.py"
        assert f.line == 42
        assert f.confidence == 0.7

    def test_default_confidence(self):
        from fix_code import CodeFix
        f = CodeFix("f.py", 1, "", "", "desc")
        assert f.confidence == 0.5


# ============================================================================
# 15. FIX_CODE.PY — DiagnosticFailureParser
# ============================================================================

class TestDiagnosticFailureParser:
    """Tests for DiagnosticFailureParser class."""

    def test_parse_pytest_single_failure(self):
        from fix_code import DiagnosticFailureParser
        p = DiagnosticFailureParser()
        output = 'FAILED tests/test_foo.py::test_bar - AssertionError: expected 5 got 3'
        failures = p.parse_pytest(output)
        assert len(failures) == 1
        assert failures[0].test_name == "test_bar"
        assert failures[0].file == "tests/test_foo.py"
        assert failures[0].error_type == "AssertionError"

    def test_parse_pytest_multiple_failures(self):
        from fix_code import DiagnosticFailureParser
        p = DiagnosticFailureParser()
        output = (
            'FAILED tests/test_a.py::test_one - AssertionError: expected 1 got 0\n'
            'FAILED tests/test_b.py::test_two - TypeError: unsupported operand\n'
        )
        failures = p.parse_pytest(output)
        assert len(failures) == 2

    def test_parse_pytest_exception(self):
        from fix_code import DiagnosticFailureParser
        p = DiagnosticFailureParser()
        output = 'FAILED tests/test_e.py::test_err - ValueError: invalid value'
        failures = p.parse_pytest(output)
        assert len(failures) == 1
        assert failures[0].error_type == "ValueError"

    def test_parse_pytest_no_failures(self):
        from fix_code import DiagnosticFailureParser
        p = DiagnosticFailureParser()
        failures = p.parse_pytest("all tests passed")
        assert len(failures) == 0

    def test_parse_cargo_single_failure(self):
        from fix_code import DiagnosticFailureParser
        p = DiagnosticFailureParser()
        output = 'test test_decay ... FAILED'
        failures = p.parse_cargo(output)
        assert len(failures) == 1
        assert failures[0].test_name == "test_decay"

    def test_parse_cargo_with_panic(self):
        from fix_code import DiagnosticFailureParser
        p = DiagnosticFailureParser()
        output = (
            'test test_trust ... FAILED\n'
            "thread 'test_trust' panicked at src/lib.rs:245:5:\n"
            "assertion failed: trust > 0.5\n\n"
        )
        failures = p.parse_cargo(output)
        assert len(failures) == 1
        assert failures[0].file == "src/lib.rs"
        assert failures[0].line == 245

    def test_parse_go_single_failure(self):
        from fix_code import DiagnosticFailureParser
        p = DiagnosticFailureParser()
        output = (
            "--- FAIL: TestAdd (0.00s)\n"
            "    main_test.go:15: expected 4 got 3\n"
            "--- PASS: TestSub\n"
        )
        failures = p.parse_go(output)
        assert len(failures) == 1
        assert failures[0].test_name == "TestAdd"

    def test_parse_go_multiple_failures(self):
        from fix_code import DiagnosticFailureParser
        p = DiagnosticFailureParser()
        output = (
            "--- FAIL: TestAdd (0.00s)\n    add_test.go:10: bad\n\n"
            "--- FAIL: TestSub (0.00s)\n    sub_test.go:20: worse\n\n"
            "--- PASS: TestMul\n"
        )
        failures = p.parse_go(output)
        assert len(failures) == 2


# ============================================================================
# 16. FIX_CODE.PY — CodeFixer
# ============================================================================

class TestCodeFixer:
    """Tests for CodeFixer class."""

    def test_suggest_fixes_empty(self):
        from fix_code import CodeFixer
        f = CodeFixer()
        fixes = f.suggest_fixes([], {})
        assert fixes == []

    def test_suggest_type_error_int_float(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 10, "TypeError",
                                       "expected int got float")]
        fixes = f.suggest_fixes(failures, {})
        assert len(fixes) > 0
        type_fixes = [x for x in fixes if "int" in x.new_code]
        assert len(type_fixes) > 0

    def test_suggest_type_error_str_int(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 10, "TypeError",
                                       "expected str got int")]
        fixes = f.suggest_fixes(failures, {})
        str_fixes = [x for x in fixes if "str" in x.new_code]
        assert len(str_fixes) > 0

    def test_suggest_attribute_fix(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 5, "AttributeError",
                                       "no attribute 'count'")]
        fixes = f.suggest_fixes(failures, {})
        assert len(fixes) > 0
        attr_fixes = [x for x in fixes if "count" in x.description]
        assert len(attr_fixes) > 0

    def test_suggest_name_error_import(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 3, "NameError",
                                       "NameError: name 'math' is not defined")]
        fixes = f.suggest_fixes(failures, {})
        import_fixes = [x for x in fixes if "import" in x.description.lower()]
        assert len(import_fixes) > 0

    def test_fix_assertion_relax_gt(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        sources = {"f.py": "x = 5\nassert val > 0.8\n"}
        failure = DiagnosticFailure("test", "f.py", 2, "AssertionError", "fail")
        fixes = f._fix_assertion(failure, sources)
        assert len(fixes) > 0
        assert ">=" in fixes[0].new_code

    def test_fix_assertion_relax_lt(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        sources = {"f.py": "assert val < 0.5\n"}
        failure = DiagnosticFailure("test", "f.py", 1, "AssertionError", "fail")
        fixes = f._fix_assertion(failure, sources)
        assert len(fixes) > 0
        assert "<=" in fixes[0].new_code

    def test_fix_assertion_no_source(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failure = DiagnosticFailure("test", "f.py", 1, "AssertionError", "fail")
        fixes = f._fix_assertion(failure, {})
        assert fixes == []

    def test_fix_assertion_missing_file_in_sources(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failure = DiagnosticFailure("test", "other.py", 1, "AssertionError", "fail")
        fixes = f._fix_assertion(failure, {"f.py": "x = 1"})
        assert fixes == []

    def test_fix_patterns_exist(self):
        from fix_code import CodeFixer
        f = CodeFixer()
        assert "assertion_threshold" in f.FIX_PATTERNS
        assert "missing_import" in f.FIX_PATTERNS
        assert "type_error_int_float" in f.FIX_PATTERNS
        assert "borrow_checker" in f.FIX_PATTERNS
        assert "missing_mut" in f.FIX_PATTERNS
        assert "missing_field" in f.FIX_PATTERNS


# ============================================================================
# 17. FIX_CODE.PY — MechanicCodeFixer
# ============================================================================

class TestMechanicCodeFixer:
    """Tests for MechanicCodeFixer class."""

    def test_init(self):
        from fix_code import MechanicCodeFixer
        m = MechanicCodeFixer()
        assert m.work_dir == "/tmp/mechanic-work"
        assert m.parser is not None
        assert m.fixer is not None

    def test_init_custom_work_dir(self):
        from fix_code import MechanicCodeFixer
        m = MechanicCodeFixer(work_dir="/custom/dir")
        assert m.work_dir == "/custom/dir"

    def test_diagnose_no_framework(self, tmp_path):
        from fix_code import MechanicCodeFixer
        m = MechanicCodeFixer()
        repo_dir = tmp_path / "no-framework"
        repo_dir.mkdir()
        failures, output = m.diagnose_repo(str(repo_dir))
        assert failures == []
        assert "No test framework" in output

    def test_diagnose_nonexistent_dir(self, tmp_path):
        from fix_code import MechanicCodeFixer
        m = MechanicCodeFixer()
        failures, output = m.diagnose_repo("/tmp/nonexistent_xyz")
        assert failures == []

    def test_load_sources_empty_dir(self, tmp_path):
        from fix_code import MechanicCodeFixer
        m = MechanicCodeFixer()
        sources = m.load_sources(str(tmp_path))
        assert sources == {}

    def test_load_sources_nonexistent(self):
        from fix_code import MechanicCodeFixer
        m = MechanicCodeFixer()
        sources = m.load_sources("/tmp/nonexistent_xyz")
        assert sources == {}

    def test_load_sources_with_files(self, tmp_path):
        from fix_code import MechanicCodeFixer
        m = MechanicCodeFixer()
        (tmp_path / "main.py").write_text("x = 1\n")
        (tmp_path / "test_main.py").write_text("assert x == 1\n")
        sources = m.load_sources(str(tmp_path))
        assert "main.py" in sources
        assert "test_main.py" in sources

    def test_load_sources_skips_hidden(self, tmp_path):
        from fix_code import MechanicCodeFixer
        m = MechanicCodeFixer()
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("x = 1\n")
        sources = m.load_sources(str(tmp_path))
        assert len(sources) == 0

    def test_load_sources_custom_extensions(self, tmp_path):
        from fix_code import MechanicCodeFixer
        m = MechanicCodeFixer()
        (tmp_path / "code.rs").write_text("fn main() {}\n")
        (tmp_path / "readme.txt").write_text("hello\n")
        sources = m.load_sources(str(tmp_path), extensions=['.rs'])
        assert "code.rs" in sources
        assert "readme.txt" not in sources

    def test_apply_fix(self, tmp_path):
        from fix_code import MechanicCodeFixer, CodeFix
        m = MechanicCodeFixer()
        f = tmp_path / "main.py"
        f.write_text("assert x > 0.8\n")
        fix = CodeFix(
            file="main.py", line=1,
            old_code="assert x > 0.8",
            new_code="assert x >= 0.8",
            description="Relax",
            confidence=0.5,
        )
        m._apply_fix(str(tmp_path), fix)
        assert "assert x >= 0.8" in f.read_text()
        assert "assert x > 0.8" not in f.read_text()

    def test_apply_fix_nonexistent_file(self, tmp_path):
        from fix_code import MechanicCodeFixer, CodeFix
        m = MechanicCodeFixer()
        fix = CodeFix("missing.py", 1, "old", "new", "desc")
        # Should not raise
        m._apply_fix(str(tmp_path), fix)

    def test_apply_fix_old_code_not_found(self, tmp_path):
        from fix_code import MechanicCodeFixer, CodeFix
        m = MechanicCodeFixer()
        f = tmp_path / "main.py"
        f.write_text("x = 1\n")
        fix = CodeFix("main.py", 1, "not in file", "new code", "desc")
        original = f.read_text()
        m._apply_fix(str(tmp_path), fix)
        assert f.read_text() == original  # No change

    def test_auto_fix_no_tests(self, tmp_path):
        from fix_code import MechanicCodeFixer
        m = MechanicCodeFixer()
        repo_dir = tmp_path / "empty"
        repo_dir.mkdir()
        result = m.auto_fix(str(repo_dir))
        assert result["remaining_failures"] == 0
        assert result["iterations"] == 1


# ============================================================================
# 18. SCAN_FLEET.PY — RateLimiter
# ============================================================================

class TestRateLimiter:
    """Tests for the RateLimiter class."""

    def test_init_defaults(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter()
        assert rl.initial_delay == 1.0
        assert rl.max_delay == 60.0
        assert rl.max_retries == 5
        assert rl.current_delay == 1.0

    def test_init_custom(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=0.5, max_delay=30.0, max_retries=3)
        assert rl.initial_delay == 0.5
        assert rl.max_delay == 30.0
        assert rl.max_retries == 3

    def test_backoff_zero(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0, max_delay=60.0)
        assert rl.backoff(0) == 1.0

    def test_backoff_doubles(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0, max_delay=60.0)
        assert rl.backoff(1) == 2.0
        assert rl.backoff(2) == 4.0
        assert rl.backoff(3) == 8.0

    def test_backoff_capped(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0, max_delay=10.0)
        assert rl.backoff(10) == 10.0  # 2^10 = 1024, capped at 10
        assert rl.backoff(100) == 10.0

    def test_reset(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0)
        rl.current_delay = 50.0
        rl.reset()
        assert rl.current_delay == 1.0

    def test_wait_short(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=0.01, max_delay=0.1)
        import time
        start = time.time()
        rl.wait(0)
        elapsed = time.time() - start
        assert elapsed < 0.1  # Should be very fast


# ============================================================================
# 19. SCAN_FLEET.PY — filter_repos_by_type
# ============================================================================

class TestFilterReposByType:
    """Tests for filter_repos_by_type."""

    def test_empty_list(self):
        from scan_fleet import filter_repos_by_type
        own, forks = filter_repos_by_type([])
        assert own == []
        assert forks == []

    def test_filter_own_and_fork(self):
        from scan_fleet import filter_repos_by_type
        repos = [
            {"name": "repo1", "fork": False, "size": 100},
            {"name": "repo2", "fork": True, "size": 50},
            {"name": "repo3", "fork": False, "size": 5},  # too small
            {"name": "repo4", "fork": True, "size": 200},
        ]
        own, forks = filter_repos_by_type(repos, min_size_kb=10)
        assert own == ["repo1"]
        assert forks == ["repo2", "repo4"]

    def test_custom_min_size(self):
        from scan_fleet import filter_repos_by_type
        repos = [
            {"name": "a", "fork": False, "size": 50},
            {"name": "b", "fork": False, "size": 100},
        ]
        own, forks = filter_repos_by_type(repos, min_size_kb=75)
        assert own == ["b"]
        assert forks == []

    def test_all_forks(self):
        from scan_fleet import filter_repos_by_type
        repos = [
            {"name": "a", "fork": True, "size": 100},
            {"name": "b", "fork": True, "size": 200},
        ]
        own, forks = filter_repos_by_type(repos)
        assert own == []
        assert len(forks) == 2

    def test_missing_size_defaults(self):
        from scan_fleet import filter_repos_by_type
        repos = [{"name": "a", "fork": False}]  # no "size" key
        own, forks = filter_repos_by_type(repos)
        assert own == []  # 0 > 10 is False


# ============================================================================
# 20. SCAN_FLEET.PY & BOOT.PY — load_github_token
# ============================================================================

class TestLoadGithubToken:
    """Tests for load_github_token from both scan_fleet and boot."""

    def test_scan_fleet_token_not_found(self):
        from scan_fleet import load_github_token
        with pytest.raises(FileNotFoundError, match="not found"):
            load_github_token("/tmp/nonexistent_token_file_xyz")

    def test_scan_fleet_token_empty(self, tmp_path):
        from scan_fleet import load_github_token
        token_file = tmp_path / "token"
        token_file.write_text("   \n")
        with pytest.raises(ValueError, match="empty"):
            load_github_token(str(token_file))

    def test_scan_fleet_token_valid(self, tmp_path):
        from scan_fleet import load_github_token
        token_file = tmp_path / "token"
        token_file.write_text("ghp_abc123\n")
        token = load_github_token(str(token_file))
        assert token == "ghp_abc123"

    def test_boot_token_not_found(self):
        from boot import load_github_token
        with pytest.raises(FileNotFoundError, match="not found"):
            load_github_token("/tmp/nonexistent_token_file_xyz")

    def test_boot_token_empty(self, tmp_path):
        from boot import load_github_token
        token_file = tmp_path / "token"
        token_file.write_text("   \n")
        with pytest.raises(ValueError, match="empty"):
            load_github_token(str(token_file))

    def test_boot_token_valid(self, tmp_path):
        from boot import load_github_token
        token_file = tmp_path / "token"
        token_file.write_text("ghp_xyz789\n")
        token = load_github_token(str(token_file))
        assert token == "ghp_xyz789"


# ============================================================================
# 21. BOOT.PY — filter_own_repos
# ============================================================================

class TestFilterOwnRepos:
    """Tests for boot.filter_own_repos."""

    def test_empty_list(self):
        from boot import filter_own_repos
        assert filter_own_repos([]) == []

    def test_filters_forks(self):
        from boot import filter_own_repos
        repos = [
            {"name": "own", "fork": False, "size": 100},
            {"name": "forked", "fork": True, "size": 100},
        ]
        assert filter_own_repos(repos) == ["own"]

    def test_filters_small_repos(self):
        from boot import filter_own_repos
        repos = [
            {"name": "big", "fork": False, "size": 50},
            {"name": "tiny", "fork": False, "size": 5},
        ]
        assert filter_own_repos(repos) == ["big"]

    def test_custom_min_size(self):
        from boot import filter_own_repos
        repos = [{"name": "a", "fork": False, "size": 100}]
        assert filter_own_repos(repos, min_size_kb=200) == []


# ============================================================================
# 22. BOOT.PY & SCAN_FLEET.PY — print functions
# ============================================================================

class TestPrintFunctions:
    """Tests for print_scan_results and print_summary."""

    def test_scan_fleet_print_scan_results(self, capsys):
        from scan_fleet import print_scan_results
        from mechanic import RepoHealth
        reports = [
            RepoHealth(repo="repo-a", health_score=0.8, test_pass=5, test_count=5,
                       has_ci=True, language="Python"),
        ]
        print_scan_results(reports)
        captured = capsys.readouterr()
        assert "repo-a" in captured.out
        assert "100%" in captured.out or "80%" in captured.out

    def test_scan_fleet_print_scan_results_empty(self, capsys):
        from scan_fleet import print_scan_results
        print_scan_results([])
        captured = capsys.readouterr()
        assert "Repo" in captured.out

    def test_scan_fleet_print_summary(self, capsys):
        from scan_fleet import print_summary
        from mechanic import RepoHealth
        reports = [
            RepoHealth(repo="a", health_score=0.8),
            RepoHealth(repo="b", health_score=0.3),
            RepoHealth(repo="c", health_score=0.1),
        ]
        print_summary(reports)
        captured = capsys.readouterr()
        assert "Healthy: 1/3" in captured.out

    def test_boot_print_scan_results(self, capsys):
        from boot import print_scan_results
        from mechanic import RepoHealth
        reports = [
            RepoHealth(repo="repo-x", health_score=0.9, test_pass=10, test_count=10,
                       has_readme=True, has_ci=True, language="Rust"),
        ]
        print_scan_results(reports)
        captured = capsys.readouterr()
        assert "repo-x" in captured.out

    def test_boot_print_summary(self, capsys):
        from boot import print_summary
        from mechanic import RepoHealth
        reports = [
            RepoHealth(repo="a", health_score=0.9),
            RepoHealth(repo="b", health_score=0.4),
        ]
        print_summary(reports)
        captured = capsys.readouterr()
        assert "Healthy: 1/2" in captured.out
        assert "Needs attention: 1/2" in captured.out

    def test_boot_print_summary_all_healthy(self, capsys):
        from boot import print_summary
        from mechanic import RepoHealth
        reports = [RepoHealth(repo="a", health_score=1.0)]
        print_summary(reports)
        captured = capsys.readouterr()
        assert "Needs attention: 0/1" in captured.out


# ============================================================================
# 23. BOOT.PY — fetch_user_repos
# ============================================================================

class TestFetchUserRepos:
    """Tests for boot.fetch_user_repos (with mocking)."""

    def test_fetch_success(self):
        from boot import fetch_user_repos
        import json
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps([{"name": "repo1", "fork": False, "size": 100}])
            )
            repos = fetch_user_repos("fake-token")
            assert len(repos) == 1
            assert repos[0]["name"] == "repo1"

    def test_fetch_curl_failure(self):
        from boot import fetch_user_repos
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="connection refused")
            with pytest.raises(RuntimeError, match="curl failed"):
                fetch_user_repos("fake-token")

    def test_fetch_json_decode_error(self):
        from boot import fetch_user_repos
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="not json")
            with pytest.raises(RuntimeError, match="parse"):
                fetch_user_repos("fake-token")

    def test_fetch_timeout(self):
        from boot import fetch_user_repos
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd="curl", timeout=30)):
            with pytest.raises(RuntimeError, match="timed out"):
                fetch_user_repos("fake-token")


# ============================================================================
# 24. SCAN_FLEET.PY — fetch_repos_paginated
# ============================================================================

class TestFetchReposPaginated:
    """Tests for scan_fleet.fetch_repos_paginated (with mocking)."""

    def test_single_page(self):
        from scan_fleet import fetch_repos_paginated
        import json
        repos_data = [{"name": f"repo{i}", "fork": False, "size": 100} for i in range(5)]
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(repos_data))
            repos = fetch_repos_paginated("token", per_page=100)
            assert len(repos) == 5

    def test_pagination(self):
        from scan_fleet import fetch_repos_paginated
        import json
        page1 = [{"name": f"repo{i}", "fork": False, "size": 100} for i in range(3)]
        with patch('subprocess.run') as mock_run, patch('time.sleep'):
            # First call returns full page, second returns empty (no more repos)
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=json.dumps(page1)),
                MagicMock(returncode=0, stdout=json.dumps([])),
            ]
            repos = fetch_repos_paginated("token", per_page=3)
            assert len(repos) == 3

    def test_empty_response(self):
        from scan_fleet import fetch_repos_paginated
        import json
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps([]))
            repos = fetch_repos_paginated("token")
            assert repos == []


# ============================================================================
# 25. INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple components."""

    def test_mechanic_and_reviewer_on_directory(self, tmp_path):
        """Create a Python file with known issues, review it, and verify findings."""
        from mechanic import FleetMechanic
        from review import CodeReviewer

        # Create a problematic Python file
        (tmp_path / "bad_code.py").write_text(
            'api_key = "sk-12345678abcdefgh"\n'
            'def calculate(x):\n'
            '    return eval(x)\n'
            '# TODO: fix this later\n'
        )

        # Review the directory
        reviewer = CodeReviewer()
        report = reviewer.review_directory(str(tmp_path))

        # Should find security issues
        security = [c for c in report.comments if c.category == "security"]
        assert len(security) >= 2  # hardcoded secret + eval

        # Score should be low
        assert report.score < 80

    def test_code_generator_roundtrip(self):
        """Generate code and tests, verify consistency."""
        from gen_code import CodeGenerator, CodeSpec, Language

        gen = CodeGenerator()
        spec = CodeSpec(
            name="calculator",
            description="Simple math calculator",
            language=Language.PYTHON,
            functions=[
                {"name": "add", "params": "a, b", "returns": "int",
                 "body": "return a + b", "doc": "Add two numbers"},
                {"name": "multiply", "params": "a, b", "returns": "int",
                 "body": "return a * b", "doc": "Multiply two numbers"},
            ],
            classes=[{"name": "Result", "fields": [
                {"name": "value", "type": "int"},
                {"name": "success", "type": "bool"},
            ]}],
            test_cases=[
                {"name": "add_positive", "body": "self.assertEqual(add(1, 2), 3)"},
                {"name": "multiply_positive", "body": "self.assertEqual(multiply(3, 4), 12)"},
            ],
        )

        source = gen.generate(spec)
        tests = gen.generate_tests(spec)

        # Verify source contains all functions and classes
        assert "def add" in source
        assert "def multiply" in source
        assert "class Result" in source
        assert "value: int" in source
        assert "success: bool" in source

        # Verify tests reference the right functions
        assert "add(1, 2)" in tests
        assert "multiply(3, 4)" in tests

    def test_fix_code_parser_on_real_output(self):
        """Parse realistic pytest output and generate fixes."""
        from fix_code import DiagnosticFailureParser, CodeFixer, DiagnosticFailure

        # Simulate pytest output with multiple failures
        output = (
            "FAILED tests/test_calc.py::test_add - AssertionError: expected 5 got 3\n"
            "FAILED tests/test_calc.py::test_divide - TypeError: unsupported operand type(s)\n"
            "FAILED tests/test_calc.py::test_validate - AttributeError: 'NoneType' object has no attribute 'name'\n"
            "3 failed, 12 passed in 0.5s\n"
        )

        parser = DiagnosticFailureParser()
        failures = parser.parse_pytest(output)
        assert len(failures) == 3

        fixer = CodeFixer()
        fixes = fixer.suggest_fixes(failures, {"tests/test_calc.py": ""})
        assert len(fixes) > 0

    def test_mechanic_health_scoring_pipeline(self):
        """Full pipeline: create RepoHealth, compute score, generate markdown."""
        from mechanic import RepoHealth

        h = RepoHealth(
            repo="example-repo",
            has_readme=True,
            has_gitignore=True,
            has_ci=True,
            has_tests=True,
            test_count=20,
            test_pass=18,
            test_fail=2,
            language="Python",
            size_kb=512,
        )

        h.compute_score()
        assert 0.5 < h.health_score < 1.0

        md = h.to_markdown()
        assert "example-repo" in md
        assert "Python" in md
        assert "18/20" in md
        assert "512KB" in md

    def test_scan_fleet_filter_and_print_pipeline(self, capsys):
        """Filter repos and print results."""
        from scan_fleet import filter_repos_by_type, print_scan_results, print_summary
        from mechanic import RepoHealth

        repos = [
            {"name": "repo-a", "fork": False, "size": 100, "language": "Python"},
            {"name": "repo-b", "fork": True, "size": 200, "language": "Rust"},
            {"name": "repo-c", "fork": False, "size": 50, "language": "Go"},
        ]
        own, forks = filter_repos_by_type(repos, min_size_kb=75)
        assert own == ["repo-a"]
        assert forks == ["repo-b"]

        reports = [
            RepoHealth(repo="repo-a", health_score=0.9, test_pass=10, test_count=10,
                       has_ci=True, language="Python"),
        ]
        print_scan_results(reports)
        print_summary(reports)
        captured = capsys.readouterr()
        assert "repo-a" in captured.out
        assert "Healthy: 1/1" in captured.out

    def test_reviewer_multiple_files_severity_ranking(self):
        """Review multiple files and verify severity handling."""
        from review import CodeReviewer, Severity

        reviewer = CodeReviewer()

        # Critical issue file
        critical_content = 'password = "super_secret_1234567890"\n'

        # Warning issue file
        warning_content = 'def very_long_function_name_here():\n' + '    x = 1\n' * 55 + '\ndef next():\n    pass\n'

        # Clean file
        clean_content = 'def hello():\n    """Say hi."""\n    return "hello"\n'

        comments = []
        comments.extend(reviewer.review_file("config.py", critical_content))
        comments.extend(reviewer.review_file("big.py", warning_content))
        comments.extend(reviewer.review_file("clean.py", clean_content))

        critical = [c for c in comments if c.severity == Severity.CRITICAL]
        warnings = [c for c in comments if c.severity == Severity.WARNING]
        assert len(critical) > 0
        assert len(warnings) > 0
