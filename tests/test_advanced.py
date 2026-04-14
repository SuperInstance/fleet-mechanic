"""Advanced test suite for fleet-mechanic.

Covers additional scenarios:
- execute_repo_health with mocked clone/API
- execute_gen_docs with mocked clone/push
- FleetMechanic._fetch_org_repos
- Edge cases for RepoHealth scoring
- CodeReviewer fleet compliance edge cases
- CodeFixer with complex patterns
- RateLimiter advanced scenarios
- Boot/scan_fleet main functions
- Data class field isolation and mutation
- Task lifecycle integration
"""
import os
import sys
import json
import tempfile
from unittest.mock import patch, MagicMock, call

import pytest


# ============================================================================
# 1. FleetMechanic.execute_repo_health (mocked)
# ============================================================================

class TestExecuteRepoHealth:
    """Tests for execute_repo_health with mocked dependencies."""

    def test_empty_repo_raises(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with pytest.raises(ValueError, match="Repository name cannot be empty"):
            m.execute_repo_health("")

    def test_clone_failure_returns_partial_health(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, 'clone_repo', return_value=False):
            health = m.execute_repo_health("bad-repo")
            assert health.repo == "bad-repo"
            assert health.health_score == 0.0
            assert health.has_readme is False

    def test_clone_failure_does_not_store_report(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        # When clone fails, the early return does NOT store in health_reports
        with patch.object(m, 'clone_repo', return_value=False):
            m.execute_repo_health("my-repo")
            assert "my-repo" not in m.health_reports

    def test_stores_health_report_on_successful_clone(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        m.work_dir = str(tmp_path)
        repo_dir = tmp_path / "my-repo"
        repo_dir.mkdir()
        (repo_dir / "README.md").write_text("# Readme")

        def fake_clone(r):
            import shutil
            target = os.path.join(str(tmp_path), r)
            if os.path.exists(target):
                shutil.rmtree(target)
            template = tmp_path / "template-my-repo"
            if template.exists():
                shutil.copytree(str(template), target)
            else:
                os.makedirs(target, exist_ok=True)
            return True

        template = tmp_path / "template-my-repo"
        template.mkdir()
        (template / "README.md").write_text("# Readme")

        with patch.object(m, 'clone_repo', side_effect=fake_clone), \
             patch.object(m, '_api', return_value={}):
            health = m.execute_repo_health("my-repo")
            assert "my-repo" in m.health_reports

    def test_api_fallback_on_not_found(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token", org="TestOrg")
        with patch.object(m, 'clone_repo', return_value=False), \
             patch.object(m, '_api', side_effect=[
                 {"message": "Not Found"},
                 {"language": "Python", "size": 100},
             ]):
            health = m.execute_repo_health("repo")
            assert health.language == "Python"
            assert health.size_kb == 100

    def test_api_error_gracefully_handled(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, 'clone_repo', return_value=False), \
             patch.object(m, '_api', side_effect=Exception("API error")):
            health = m.execute_repo_health("repo")
            assert health.repo == "repo"

    def test_health_check_with_cloned_repo(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        m.work_dir = str(tmp_path)
        template = tmp_path / "tmpl-good-repo"
        template.mkdir()
        (template / "README.md").write_text("# Good Repo")
        (template / ".gitignore").write_text("__pycache__/\n")
        wf = template / ".github" / "workflows"
        wf.mkdir(parents=True)
        (template / "tests").mkdir()

        def fake_clone(r):
            import shutil
            target = os.path.join(str(tmp_path), r)
            if os.path.exists(target):
                shutil.rmtree(target)
            shutil.copytree(str(template), target)
            return True

        with patch.object(m, 'clone_repo', side_effect=fake_clone), \
             patch.object(m, '_api', return_value={"language": "Python", "size": 50}):
            health = m.execute_repo_health("good-repo")
            assert health.has_readme is True
            assert health.has_gitignore is True
            assert health.has_ci is True
            assert health.has_tests is True
            assert health.language == "Python"

    def test_health_check_detects_test_files(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        m.work_dir = str(tmp_path)
        template = tmp_path / "tmpl-test-repo"
        template.mkdir()
        (template / "test_something.py").write_text("# test")

        def fake_clone(r):
            import shutil
            target = os.path.join(str(tmp_path), r)
            if os.path.exists(target):
                shutil.rmtree(target)
            shutil.copytree(str(template), target)
            return True

        with patch.object(m, 'clone_repo', side_effect=fake_clone), \
             patch.object(m, '_api', return_value={}):
            health = m.execute_repo_health("test-repo")
            assert health.has_tests is True

    def test_multiple_health_reports_accumulate_on_success(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        m.work_dir = str(tmp_path)

        for name in ["repo-a", "repo-b"]:
            tmpl = tmp_path / f"tmpl-{name}"
            tmpl.mkdir()

        def fake_clone(r):
            import shutil
            target = os.path.join(str(tmp_path), r)
            if os.path.exists(target):
                shutil.rmtree(target)
            tmpl = tmp_path / f"tmpl-{r}"
            shutil.copytree(str(tmpl), target)
            return True

        with patch.object(m, 'clone_repo', side_effect=fake_clone), \
             patch.object(m, '_api', return_value={}):
            m.execute_repo_health("repo-a")
            m.execute_repo_health("repo-b")
        assert len(m.health_reports) == 2


# ============================================================================
# 2. FleetMechanic.execute_gen_docs (mocked)
# ============================================================================

class TestExecuteGenDocs:
    """Tests for execute_gen_docs with mocked dependencies."""

    def test_empty_repo_raises(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with pytest.raises(ValueError, match="Repository name cannot be empty"):
            m.execute_gen_docs("")

    def test_clone_failure_returns_failed_task(self):
        from mechanic import FleetMechanic, TaskResult
        m = FleetMechanic("fake-token")
        with patch.object(m, 'clone_repo', return_value=False):
            task = m.execute_gen_docs("bad-repo")
            assert task.result == TaskResult.FAILED
            assert "Could not clone" in task.diagnosis

    def test_task_not_added_to_completed_on_clone_failure(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, 'clone_repo', return_value=False):
            m.execute_gen_docs("repo")
        # execute_gen_docs returns early on clone failure, before appending
        assert len(m.completed_tasks) == 0

    def test_task_type_is_gen_docs(self):
        from mechanic import FleetMechanic, TaskType
        m = FleetMechanic("fake-token")
        with patch.object(m, 'clone_repo', return_value=False):
            task = m.execute_gen_docs("repo")
            assert task.task_type == TaskType.GEN_DOCS

    def test_gen_gitignore_and_ci_when_missing(self, tmp_path):
        from mechanic import FleetMechanic, TaskResult
        m = FleetMechanic("fake-token")
        m.work_dir = str(tmp_path)
        template = tmp_path / "tmpl-bare-repo"
        template.mkdir()
        (template / "pyproject.toml").write_text("[tool]")

        def fake_clone(r):
            import shutil
            target = os.path.join(str(tmp_path), r)
            if os.path.exists(target):
                shutil.rmtree(target)
            shutil.copytree(str(template), target)
            return True

        with patch.object(m, 'clone_repo', side_effect=fake_clone), \
             patch.object(m, 'push_changes', return_value=True) as mock_push:
            task = m.execute_gen_docs("bare-repo")
            assert task.result == TaskResult.SUCCESS
            assert task.files_changed >= 1
            assert mock_push.called

    def test_no_changes_when_files_exist(self, tmp_path):
        from mechanic import FleetMechanic, TaskResult
        m = FleetMechanic("fake-token")
        m.work_dir = str(tmp_path)
        template = tmp_path / "tmpl-complete-repo"
        template.mkdir()
        (template / ".gitignore").write_text("*")
        wf = template / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("ci")

        def fake_clone(r):
            import shutil
            target = os.path.join(str(tmp_path), r)
            if os.path.exists(target):
                shutil.rmtree(target)
            shutil.copytree(str(template), target)
            return True

        with patch.object(m, 'clone_repo', side_effect=fake_clone):
            task = m.execute_gen_docs("complete-repo")
            assert task.result == TaskResult.PARTIAL
            assert "No missing files" in task.diagnosis

    def test_push_failure_results_in_partial(self, tmp_path):
        from mechanic import FleetMechanic, TaskResult
        m = FleetMechanic("fake-token")
        m.work_dir = str(tmp_path)
        template = tmp_path / "tmpl-push-fail"
        template.mkdir()
        (template / "pyproject.toml").write_text("[tool]")

        def fake_clone(r):
            import shutil
            target = os.path.join(str(tmp_path), r)
            if os.path.exists(target):
                shutil.rmtree(target)
            shutil.copytree(str(template), target)
            return True

        with patch.object(m, 'clone_repo', side_effect=fake_clone), \
             patch.object(m, 'push_changes', return_value=False):
            task = m.execute_gen_docs("push-fail-repo")
            assert task.result == TaskResult.PARTIAL

    def test_clone_crash_propagates(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        # execute_gen_docs does NOT catch clone exceptions
        with patch.object(m, 'clone_repo', side_effect=RuntimeError("clone crash")):
            with pytest.raises(RuntimeError, match="clone crash"):
                m.execute_gen_docs("repo")

    def test_task_id_format(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, 'clone_repo', return_value=False):
            task = m.execute_gen_docs("repo")
            assert task.id.startswith("DOCS-")


# ============================================================================
# 3. FleetMechanic._fetch_org_repos
# ============================================================================

class TestFetchOrgRepos:
    """Tests for _fetch_org_repos."""

    def test_returns_empty_on_exception(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, '_api', side_effect=Exception("API error")):
            repos = m._fetch_org_repos()
            assert repos == []

    def test_filters_out_forks(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        result = [
            {"name": "repo1", "fork": False},
            {"name": "repo2", "fork": True},
            {"name": "repo3", "fork": False},
        ]
        with patch.object(m, '_api', return_value=result):
            repos = m._fetch_org_repos()
            assert repos == ["repo1", "repo3"]

    def test_handles_non_list_response(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch.object(m, '_api', return_value={"message": "Bad credentials"}):
            repos = m._fetch_org_repos()
            assert repos == []

    def test_returns_names_from_list(self):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        result = [{"name": "a"}, {"name": "b", "fork": False}]
        with patch.object(m, '_api', return_value=result):
            repos = m._fetch_org_repos()
            assert repos == ["a", "b"]


# ============================================================================
# 4. FleetMechanic.run_tests language detection
# ============================================================================

class TestRunTestsLanguageDetection:
    """Tests for run_tests with different language indicators."""

    def test_detects_rust_cargo_toml(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        repo_dir = tmp_path / "rust-repo"
        repo_dir.mkdir()
        (repo_dir / "Cargo.toml").write_text("[package]")
        m.work_dir = str(tmp_path)
        with patch.object(m, '_run_rust_tests', return_value=(5, 5, 0)):
            total, passed, failed = m.run_tests("rust-repo")
            assert total == 5

    def test_detects_python_pyproject(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        repo_dir = tmp_path / "py-repo"
        repo_dir.mkdir()
        (repo_dir / "pyproject.toml").write_text("[tool]")
        m.work_dir = str(tmp_path)
        with patch.object(m, '_run_python_tests', return_value=(10, 8, 2)):
            total, passed, failed = m.run_tests("py-repo")
            assert (total, passed, failed) == (10, 8, 2)

    def test_detects_go_go_mod(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        repo_dir = tmp_path / "go-repo"
        repo_dir.mkdir()
        (repo_dir / "go.mod").write_text("module test")
        m.work_dir = str(tmp_path)
        with patch.object(m, '_run_go_tests', return_value=(3, 3, 0)):
            total, passed, failed = m.run_tests("go-repo")
            assert total == 3

    def test_detects_python_tests_dir(self, tmp_path):
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        repo_dir = tmp_path / "py-test-repo"
        repo_dir.mkdir()
        (repo_dir / "tests").mkdir()
        m.work_dir = str(tmp_path)
        with patch.object(m, '_run_python_tests', return_value=(1, 1, 0)):
            total, _, _ = m.run_tests("py-test-repo")
            assert total == 1


# ============================================================================
# 5. RepoHealth edge cases
# ============================================================================

class TestRepoHealthAdvanced:
    """Advanced edge case tests for RepoHealth scoring."""

    def test_score_with_only_gitignore(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_gitignore=True)
        h.compute_score()
        assert h.health_score == pytest.approx(0.1)

    def test_score_with_only_ci(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_ci=True)
        h.compute_score()
        assert h.health_score == pytest.approx(0.2)

    def test_score_with_only_tests_flag(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_tests=True)
        h.compute_score()
        assert h.health_score == pytest.approx(0.2)

    def test_score_with_tests_but_zero_count(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_readme=True, has_tests=True, test_count=0)
        h.compute_score()
        assert h.health_score == pytest.approx(0.4)

    def test_score_with_all_passing_tests(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_readme=True, has_ci=True, has_tests=True,
                       test_count=100, test_pass=100)
        h.compute_score()
        assert h.health_score == pytest.approx(0.9)

    def test_score_with_half_passing_tests(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_readme=True, has_gitignore=True,
                       has_ci=True, has_tests=True, test_count=20, test_pass=10)
        h.compute_score()
        assert h.health_score == pytest.approx(0.85)

    def test_score_near_zero_with_failing_tests(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_tests=True, test_count=10, test_pass=0)
        h.compute_score()
        assert h.health_score == pytest.approx(0.2)

    def test_score_never_negative(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_readme=True, has_gitignore=True,
                       has_ci=True, has_tests=True, test_count=10, test_pass=-5)
        h.compute_score()
        assert h.health_score >= 0.0

    def test_markdown_uses_emoji(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_readme=True, has_gitignore=False)
        md = h.to_markdown()
        assert "\u2705" in md or "\u274c" in md

    def test_markdown_table_format(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="test")
        md = h.to_markdown()
        assert "| Check | Status |" in md
        assert "|-------|--------|" in md

    def test_idempotent_compute_score(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r", has_readme=True, has_ci=True,
                       has_tests=True, test_count=10, test_pass=5)
        h.compute_score()
        s1 = h.health_score
        h.compute_score()
        s2 = h.health_score
        assert s1 == s2

    def test_update_fields_recompute(self):
        from mechanic import RepoHealth
        h = RepoHealth(repo="r")
        h.compute_score()
        assert h.health_score == 0.0
        h.has_readme = True
        h.has_ci = True
        h.has_tests = True
        h.test_count = 10
        h.test_pass = 10
        h.compute_score()
        assert h.health_score > 0.5


# ============================================================================
# 6. CodeReviewer advanced checks
# ============================================================================

class TestCodeReviewerAdvanced:
    """Advanced tests for CodeReviewer checks."""

    def test_review_file_with_exec_usage(self):
        from review import CodeReviewer
        r = CodeReviewer()
        comments = r.review_file("bad.py", 'exec(user_input)\n')
        exec_comments = [c for c in comments if "exec" in c.message.lower()]
        assert len(exec_comments) > 0

    def test_review_file_with_fixme(self):
        from review import CodeReviewer
        r = CodeReviewer()
        comments = r.review_file("temp.py", "# FIXME: this is broken\nx = 1\n")
        fixme = [c for c in comments if "FIXME" in c.message]
        assert len(fixme) > 0

    def test_review_file_with_hack_has_issue_ref(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = "# HACK: workaround for bug #42\nx = 1\n"
        comments = r.review_file("temp.py", content)
        hack = [c for c in comments if "HACK" in c.message]
        assert len(hack) == 0

    def test_review_file_with_todo_has_issue_ref(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = "# TODO(#123): fix this later\nx = 1\n"
        comments = r.review_file("temp.py", content)
        todos = [c for c in comments if "TODO" in c.message]
        assert len(todos) == 0

    def test_review_file_with_secret_password(self):
        from review import CodeReviewer
        r = CodeReviewer()
        comments = r.review_file("config.py", 'password = "mysecretpassword123"\n')
        secrets = [c for c in comments if c.category == "security"]
        assert len(secrets) > 0

    def test_review_file_short_secret_ignored(self):
        from review import CodeReviewer
        r = CodeReviewer()
        comments = r.review_file("config.py", 'password = "short"\n')
        secrets = [c for c in comments if "secret" in (c.message or "").lower()]
        assert len(secrets) == 0

    def test_review_file_multiple_long_lines(self):
        from review import CodeReviewer
        r = CodeReviewer()
        long_content = "\n".join(["x = " + "a" * 150] * 3)
        comments = r.review_file("wide.py", long_content)
        style = [c for c in comments if c.category == "style"]
        assert len(style) == 3

    def test_review_file_multiple_functions_complexity(self):
        from review import CodeReviewer
        r = CodeReviewer()
        fn1 = "def big_fn():\n" + "    x = 1\n" * 55
        fn2 = "def small_fn():\n    return 1\n"
        fn3 = "def medium_fn():\n" + "    y = 2\n" * 20
        comments = r.review_file("mod.py", fn1 + "\n" + fn2 + "\n" + fn3 + "\n")
        complexity = [c for c in comments if c.category == "complexity"]
        assert len(complexity) == 1
        assert "big_fn" in complexity[0].message

    def test_review_directory_with_mixed_files(self, tmp_path):
        from review import CodeReviewer
        r = CodeReviewer()
        (tmp_path / "good.py").write_text('def hello():\n    """Say hi"""\n    return "hi"\n')
        (tmp_path / "bad.py").write_text('api_key = "sk-12345678abcdef"\n')
        (tmp_path / "README.md").write_text("# My Project\n")
        report = r.review_directory(str(tmp_path))
        assert report.score < 100
        assert len(report.comments) > 0

    def test_review_directory_skips_hidden_dirs(self, tmp_path):
        from review import CodeReviewer
        r = CodeReviewer()
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("")
        report = r.review_directory(str(tmp_path))
        assert report.score == 100

    def test_review_score_with_critical(self):
        from review import CodeReviewer, ReviewReport, ReviewComment, Severity
        r = CodeReviewer()
        report = ReviewReport(repo="test", pr_number=None)
        report.comments = [
            ReviewComment("f.py", 1, Severity.CRITICAL, "security", "bad"),
        ]
        r._compute_score(report)
        # Critical = -20, so 100 - 20 = 80
        assert report.approved is False
        assert report.score == 80.0

    def test_review_score_at_boundary(self):
        from review import CodeReviewer, ReviewReport, ReviewComment, Severity
        r = CodeReviewer()
        report = ReviewReport(repo="test", pr_number=None)
        report.comments = [
            ReviewComment("f.py", 1, Severity.WARNING, "style", "long"),
            ReviewComment("f.py", 2, Severity.WARNING, "style", "todo"),
            ReviewComment("f.py", 3, Severity.WARNING, "style", "fixme"),
            ReviewComment("f.py", 4, Severity.WARNING, "style", "hack"),
            ReviewComment("f.py", 5, Severity.WARNING, "style", "xxx"),
            ReviewComment("f.py", 6, Severity.WARNING, "style", "another"),
            ReviewComment("f.py", 7, Severity.WARNING, "style", "more"),
            ReviewComment("f.py", 8, Severity.ERROR, "testing", "no test"),
        ]
        r._compute_score(report)
        # 7 warnings * 5 = 35, 1 error * 10 = 10, total deduction = 45, score = 55
        assert report.score == pytest.approx(55.0)
        assert report.approved is False

    def test_fleet_compliance_no_fleet_ref_triggers_warning(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = "# My Project\nSome code.\n"
        comments = r.review_file("README.md", content)
        fleet = [c for c in comments if c.category == "fleet" and "fleet" in c.message.lower()]
        assert len(fleet) > 0

    def test_fleet_compliance_with_fleet_reference_no_test_count(self):
        from review import CodeReviewer
        r = CodeReviewer()
        # Has FLUX Fleet reference but no test/test mention -> test_count warning
        content = "# My Project\nPart of the FLUX Fleet\nCode here.\n"
        comments = r.review_file("README.md", content)
        fleet = [c for c in comments if c.category == "fleet"]
        # Should have fleet ref check passing but test count missing
        missing_fleet = [c for c in fleet if "fleet reference" in c.message.lower()]
        assert len(missing_fleet) == 0  # fleet ref check passes

    def test_fleet_compliance_with_fleet_and_test_reference(self):
        from review import CodeReviewer
        r = CodeReviewer()
        content = "# My Project\nPart of the FLUX Fleet\nTest count: 50\n"
        comments = r.review_file("README.md", content)
        fleet = [c for c in comments if c.category == "fleet"]
        assert len(fleet) == 0  # Both checks pass


# ============================================================================
# 7. CodeFixer advanced patterns
# ============================================================================

class TestCodeFixerAdvanced:
    """Advanced tests for CodeFixer patterns."""

    def test_fix_borrow_checker_pattern(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "lib.rs", 10, "DiagnosticFailure",
                                      "cannot borrow x as mutable because it is also borrowed")]
        fixes = f.suggest_fixes(failures, {})
        assert len(fixes) > 0
        assert any("borrow" in fx.description.lower() for fx in fixes)

    def test_fix_missing_mut_pattern(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "lib.rs", 5, "DiagnosticFailure",
                                      "cannot assign to data.x as data is not declared as mutable")]
        fixes = f.suggest_fixes(failures, {})
        assert len(fixes) > 0
        assert any("mut" in fx.description.lower() for fx in fixes)

    def test_fix_missing_field_pattern(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "lib.rs", 3, "DiagnosticFailure",
                                      "no field `trust_score` on type Agent")]
        fixes = f.suggest_fixes(failures, {})
        assert len(fixes) > 0
        assert any("field" in fx.description.lower() for fx in fixes)

    def test_fix_type_error_str_int(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 1, "TypeError",
                                      "TypeError: expected str got int")]
        fixes = f.suggest_fixes(failures, {})
        str_fixes = [fx for fx in fixes if "str" in fx.new_code]
        assert len(str_fixes) > 0

    def test_empty_suggest_fixes_with_unknown_error(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 1, "WeirdError", "something weird")]
        fixes = f.suggest_fixes(failures, {})
        assert isinstance(fixes, list)

    def test_assertion_fix_less_than_relaxation(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        sources = {"f.py": "x = 5\nassert val < 0.3\n"}
        failures = [DiagnosticFailure("test", "f.py", 2, "AssertionError", "0.5 < 0.3 failed")]
        fixes = f._fix_assertion(failures[0], sources)
        assert len(fixes) > 0
        assert "<=" in fixes[0].new_code

    def test_assertion_fix_no_relaxation_needed(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        sources = {"f.py": "x = 5\nassert val >= 0.3\n"}
        failures = [DiagnosticFailure("test", "f.py", 2, "AssertionError", "0.1 >= 0.3 failed")]
        fixes = f._fix_assertion(failures[0], sources)
        assert len(fixes) == 0

    def test_type_error_no_match(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 1, "TypeError", "unhashable type: list")]
        fixes = f._fix_type_error(failures[0], {})
        assert len(fixes) == 0

    def test_attribute_fix_no_match(self):
        from fix_code import CodeFixer, DiagnosticFailure
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 1, "AttributeError", "object has no attribute")]
        fixes = f._fix_attribute(failures[0], {})
        assert len(fixes) == 0

    def test_parse_pytest_multiple_failures(self):
        from fix_code import DiagnosticFailureParser
        p = DiagnosticFailureParser()
        output = (
            "FAILED tests/test_a.py::test_one - AssertionError: expected 1 got 2\n"
            "FAILED tests/test_b.py::test_two - TypeError: expected str got int\n"
            "FAILED tests/test_c.py::test_three - AttributeError: no attribute 'x'\n"
        )
        failures = p.parse_pytest(output)
        assert len(failures) == 3
        assert failures[0].test_name == "test_one"
        assert failures[1].error_type == "TypeError"
        assert failures[2].file == "tests/test_c.py"

    def test_parse_pytest_no_failures(self):
        from fix_code import DiagnosticFailureParser
        p = DiagnosticFailureParser()
        output = "10 passed in 0.5s\n"
        failures = p.parse_pytest(output)
        assert len(failures) == 0

    def test_parse_go_multiple_failures(self):
        from fix_code import DiagnosticFailureParser
        p = DiagnosticFailureParser()
        output = (
            "--- FAIL: TestAdd (0.00s)\n    main_test.go:15: expected 4\n"
            "--- FAIL: TestSub (0.00s)\n    main_test.go:20: expected 0\n"
            "--- PASS: TestMul\n"
        )
        failures = p.parse_go(output)
        assert len(failures) == 2

    def test_parse_go_no_failures(self):
        from fix_code import DiagnosticFailureParser
        p = DiagnosticFailureParser()
        output = "--- PASS: TestAll (0.00s)\n"
        failures = p.parse_go(output)
        assert len(failures) == 0


# ============================================================================
# 8. RateLimiter advanced tests
# ============================================================================

class TestRateLimiterAdvanced:
    """Advanced tests for RateLimiter."""

    def test_custom_initial_delay(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=5.0)
        assert rl.backoff(0) == pytest.approx(5.0)

    def test_custom_max_delay(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0, max_delay=10.0)
        assert rl.backoff(10) == 10.0

    def test_custom_max_retries(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(max_retries=10)
        assert rl.max_retries == 10

    def test_backoff_is_exponential(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0, max_delay=1000.0)
        d0 = rl.backoff(0)
        d1 = rl.backoff(1)
        d2 = rl.backoff(2)
        assert d0 < d1 < d2

    def test_reset(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=2.0)
        rl.current_delay = 50.0
        rl.reset()
        assert rl.current_delay == 2.0

    def test_backoff_capped_at_max(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0, max_delay=10.0)
        assert rl.backoff(100) == 10.0


# ============================================================================
# 9. filter_repos_by_type edge cases
# ============================================================================

class TestFilterReposByTypeAdvanced:
    """Advanced tests for filter_repos_by_type."""

    def test_empty_list(self):
        from scan_fleet import filter_repos_by_type
        own, forks = filter_repos_by_type([])
        assert own == []
        assert forks == []

    def test_all_forks(self):
        from scan_fleet import filter_repos_by_type
        repos = [{"name": f"fork-{i}", "fork": True, "size": 100} for i in range(5)]
        own, forks = filter_repos_by_type(repos)
        assert own == []
        assert len(forks) == 5

    def test_all_own(self):
        from scan_fleet import filter_repos_by_type
        repos = [{"name": f"own-{i}", "fork": False, "size": 100} for i in range(5)]
        own, forks = filter_repos_by_type(repos)
        assert len(own) == 5
        assert forks == []

    def test_size_filter_excludes_small(self):
        from scan_fleet import filter_repos_by_type
        repos = [
            {"name": "big", "fork": False, "size": 100},
            {"name": "tiny", "fork": False, "size": 5},
        ]
        own, _ = filter_repos_by_type(repos, min_size_kb=10)
        assert own == ["big"]

    def test_custom_min_size(self):
        from scan_fleet import filter_repos_by_type
        repos = [
            {"name": "med", "fork": False, "size": 50},
            {"name": "small", "fork": False, "size": 10},
        ]
        own, _ = filter_repos_by_type(repos, min_size_kb=30)
        assert own == ["med"]

    def test_missing_size_defaults_zero(self):
        from scan_fleet import filter_repos_by_type
        repos = [{"name": "nosize", "fork": False}]
        own, _ = filter_repos_by_type(repos)
        assert own == []

    def test_missing_fork_defaults_false(self):
        from scan_fleet import filter_repos_by_type
        repos = [{"name": "nofork", "size": 100}]
        own, forks = filter_repos_by_type(repos)
        assert own == ["nofork"]
        assert forks == []


# ============================================================================
# 10. MechanicTask advanced
# ============================================================================

class TestMechanicTaskAdvanced:
    """Advanced tests for MechanicTask."""

    def test_result_blocked_serialization(self):
        from mechanic import MechanicTask, TaskType, TaskResult
        t = MechanicTask(id="B-1", task_type=TaskType.SYNC, target_repo="repo",
                         result=TaskResult.BLOCKED)
        d = t.to_dict()
        assert d["result"] == "blocked"

    def test_task_mutation(self):
        from mechanic import MechanicTask, TaskType, TaskResult
        t = MechanicTask(id="M-1", task_type=TaskType.GEN_CI, target_repo="repo")
        assert t.result is None
        t.result = TaskResult.SUCCESS
        assert t.result == TaskResult.SUCCESS
        t.commits_made = 10
        assert t.commits_made == 10

    def test_all_task_types_have_values(self):
        from mechanic import TaskType
        for tt in TaskType:
            assert isinstance(tt.value, str)
            assert len(tt.value) > 0

    def test_all_task_results_have_values(self):
        from mechanic import TaskResult
        for tr in TaskResult:
            assert isinstance(tr.value, str)
            assert len(tr.value) > 0


# ============================================================================
# 11. CodeGenerator edge cases
# ============================================================================

class TestCodeGeneratorAdvanced:
    """Advanced tests for CodeGenerator."""

    def test_python_empty_spec(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(name="empty", description="Empty", language=Language.PYTHON)
        code = gen.generate(spec)
        assert "Empty" in code

    def test_go_empty_spec(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(name="pkg", description="Package", language=Language.GO)
        code = gen.generate(spec)
        assert "package pkg" in code

    def test_python_multiple_classes(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="models", description="Models", language=Language.PYTHON,
            classes=[
                {"name": "User", "fields": [{"name": "id", "type": "int"}]},
                {"name": "Post", "fields": [{"name": "title", "type": "str"}]},
            ],
        )
        code = gen.generate(spec)
        assert "class User" in code
        assert "class Post" in code

    def test_python_multiple_functions(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(
            name="calc", description="Calc", language=Language.PYTHON,
            functions=[
                {"name": "add", "params": "a, b", "returns": "int", "body": "return a + b", "doc": "Add"},
                {"name": "sub", "params": "a, b", "returns": "int", "body": "return a - b", "doc": "Subtract"},
            ],
        )
        code = gen.generate(spec)
        assert "def add" in code
        assert "def sub" in code

    def test_rust_struct_with_many_fields(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        fields = [{"name": f"field{i}", "type": "String"} for i in range(10)]
        spec = CodeSpec(
            name="model", description="Model", language=Language.RUST,
            classes=[{"name": "BigStruct", "fields": fields}],
        )
        code = gen.generate(spec)
        assert "pub struct BigStruct" in code
        assert "pub field0" in code
        assert "pub field9" in code

    def test_generate_tests_python_empty_cases(self):
        from gen_code import CodeGenerator, CodeSpec, Language
        gen = CodeGenerator()
        spec = CodeSpec(name="calc", description="Calc", language=Language.PYTHON,
                        test_cases=[])
        tests = gen.generate_tests(spec)
        assert "class TestCalc" in tests
        assert "unittest" in tests

    def test_description_pattern_compute_the(self):
        from gen_code import CodeGenerator, Language
        gen = CodeGenerator()
        source, _ = gen.generate_from_description(
            "stats", "compute the average of numbers", Language.PYTHON
        )
        assert "compute_the_average" in source

    def test_description_pattern_find_the_between(self):
        from gen_code import CodeGenerator, Language
        gen = CodeGenerator()
        source, _ = gen.generate_from_description(
            "math", "find the distance between x and y", Language.PYTHON
        )
        # Pattern: find the (\w+) between (\w+) and (\w+) -> "distance" "x" "y"
        assert "find_the_distance_between" in source

    def test_description_pattern_check_if(self):
        from gen_code import CodeGenerator, Language
        gen = CodeGenerator()
        source, _ = gen.generate_from_description(
            "validator", "check if user is active", Language.PYTHON
        )
        assert "check_if_user" in source

    def test_description_pattern_parse_and_extract(self):
        from gen_code import CodeGenerator, Language
        gen = CodeGenerator()
        source, _ = gen.generate_from_description(
            "parser", "parse JSON and extract fields", Language.PYTHON
        )
        assert "parse_json" in source


# ============================================================================
# 12. MechanicCodeFixer advanced
# ============================================================================

class TestMechanicCodeFixerAdvanced:
    """Advanced tests for MechanicCodeFixer."""

    def test_diagnose_empty_dir(self):
        from fix_code import MechanicCodeFixer
        mcf = MechanicCodeFixer()
        failures, output = mcf.diagnose_repo("/tmp/nonexistent_xyz_dir")
        assert failures == []
        assert "No test framework" in output

    def test_load_sources_with_specific_extensions(self, tmp_path):
        from fix_code import MechanicCodeFixer
        mcf = MechanicCodeFixer()
        (tmp_path / "main.py").write_text("# python")
        (tmp_path / "lib.rs").write_text("// rust")
        (tmp_path / "main.go").write_text("// go")
        sources = mcf.load_sources(str(tmp_path), extensions=['.py'])
        assert len(sources) == 1
        assert "main.py" in sources

    def test_load_sources_skips_hidden_dirs(self, tmp_path):
        from fix_code import MechanicCodeFixer
        mcf = MechanicCodeFixer()
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("# secret")
        (tmp_path / "main.py").write_text("# main")
        sources = mcf.load_sources(str(tmp_path))
        assert len(sources) == 1
        assert "main.py" in sources

    def test_load_sources_skips_build_dirs(self, tmp_path):
        from fix_code import MechanicCodeFixer
        mcf = MechanicCodeFixer()
        target = tmp_path / "target"
        target.mkdir()
        (target / "build.rs").write_text("// build")
        (tmp_path / "lib.rs").write_text("// lib")
        sources = mcf.load_sources(str(tmp_path))
        assert len(sources) == 1
        assert "lib.rs" in sources

    def test_apply_fix_nonexistent_file(self):
        from fix_code import MechanicCodeFixer, CodeFix
        mcf = MechanicCodeFixer()
        fix = CodeFix(file="nonexistent.py", line=1, old_code="old", new_code="new",
                      description="test", confidence=0.5)
        mcf._apply_fix("/tmp/nonexistent_xyz_dir", fix)

    def test_apply_fix_no_match_in_content(self, tmp_path):
        from fix_code import MechanicCodeFixer, CodeFix
        mcf = MechanicCodeFixer()
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        fix = CodeFix(file="test.py", line=1, old_code="y = 2", new_code="y = 3",
                      description="test", confidence=0.5)
        mcf._apply_fix(str(tmp_path), fix)
        assert f.read_text() == "x = 1\n"

    def test_auto_fix_with_max_iterations_zero(self, tmp_path):
        from fix_code import MechanicCodeFixer
        mcf = MechanicCodeFixer()
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        result = mcf.auto_fix(str(repo_dir), max_iterations=0)
        assert result["iterations"] == 0

    def test_diagnose_rust_repo_with_proper_output(self, tmp_path):
        from fix_code import MechanicCodeFixer
        mcf = MechanicCodeFixer()
        repo_dir = tmp_path / "rust-repo"
        repo_dir.mkdir()
        (repo_dir / "Cargo.toml").write_text("[package]")
        # Output must include FAILED test lines for parse_cargo to match
        output = ("running 3 tests\n"
                  "test test_one ... ok\n"
                  "test test_two ... FAILED\n"
                  "test test_three ... FAILED\n"
                  "test result: 1 passed; 2 failed")
        with patch.object(mcf, '_run', return_value=(101, output)):
            failures, _ = mcf.diagnose_repo(str(repo_dir))
            assert len(failures) == 2

    def test_diagnose_go_repo_with_proper_output(self, tmp_path):
        from fix_code import MechanicCodeFixer
        mcf = MechanicCodeFixer()
        repo_dir = tmp_path / "go-repo"
        repo_dir.mkdir()
        (repo_dir / "go.mod").write_text("module test")
        output = ("--- FAIL: TestAdd (0.00s)\n"
                  "    main_test.go:15: expected 4\n"
                  "--- PASS: TestSub (0.00s)\n")
        with patch.object(mcf, '_run', return_value=(1, output)):
            failures, _ = mcf.diagnose_repo(str(repo_dir))
            assert len(failures) >= 1


# ============================================================================
# 13. Boot functions with mocks
# ============================================================================

class TestBootFunctions:
    """Tests for boot.py functions with mocks."""

    def test_fix_repos_needing_docs_none_need_fix(self):
        from boot import fix_repos_needing_docs
        from mechanic import FleetMechanic, RepoHealth
        m = FleetMechanic("fake-token")
        reports = [
            RepoHealth(repo="good", has_gitignore=True, has_ci=True),
        ]
        fixed = fix_repos_needing_docs(m, reports)
        assert fixed == 0

    def test_fix_repos_needing_docs_handles_error(self):
        from boot import fix_repos_needing_docs
        from mechanic import FleetMechanic, RepoHealth
        m = FleetMechanic("fake-token")
        reports = [
            RepoHealth(repo="bad", has_gitignore=False),
        ]
        with patch.object(m, 'execute_gen_docs', side_effect=Exception("fail")):
            fixed = fix_repos_needing_docs(m, reports)
            assert fixed == 0

    def test_print_scan_results_no_crash(self, capsys):
        from boot import print_scan_results
        from mechanic import RepoHealth
        reports = [
            RepoHealth(repo="a", health_score=0.9, test_count=10, test_pass=8,
                       has_readme=True, has_ci=True, language="Python"),
        ]
        print_scan_results(reports)
        captured = capsys.readouterr()
        assert "a" in captured.out

    def test_print_summary_no_crash(self, capsys):
        from boot import print_summary
        from mechanic import RepoHealth
        reports = [
            RepoHealth(repo="a", health_score=0.8),
            RepoHealth(repo="b", health_score=0.3),
        ]
        print_summary(reports)
        captured = capsys.readouterr()
        assert "Healthy" in captured.out


# ============================================================================
# 14. Scan fleet functions with mocks
# ============================================================================

class TestScanFleetFunctions:
    """Tests for scan_fleet.py functions with mocks."""

    def test_fix_repos_needing_docs_scan_fleet(self):
        from scan_fleet import fix_repos_needing_docs
        from mechanic import FleetMechanic, RepoHealth, TaskResult
        m = FleetMechanic("fake-token")
        reports = [
            RepoHealth(repo="needs-fix", has_gitignore=False),
        ]
        task = type('Task', (), {
            'result': TaskResult.SUCCESS,
            'diagnosis': 'Added .gitignore',
        })()
        with patch.object(m, 'execute_gen_docs', return_value=task):
            fixed = fix_repos_needing_docs(m, reports)
            assert fixed == 1

    def test_print_scan_results_scan_fleet(self, capsys):
        from scan_fleet import print_scan_results
        from mechanic import RepoHealth
        reports = [
            RepoHealth(repo="test-repo", health_score=0.5, test_count=5, test_pass=3,
                       has_ci=True, language="Rust"),
        ]
        print_scan_results(reports)
        captured = capsys.readouterr()
        assert "test-repo" in captured.out

    def test_print_summary_scan_fleet(self, capsys):
        from scan_fleet import print_summary
        from mechanic import RepoHealth
        reports = [
            RepoHealth(repo="a", health_score=0.9),
            RepoHealth(repo="b", health_score=0.4),
        ]
        print_summary(reports)
        captured = capsys.readouterr()
        assert "Healthy" in captured.out

    def test_load_github_token_not_found(self):
        from scan_fleet import load_github_token
        with pytest.raises(FileNotFoundError):
            load_github_token("/tmp/nonexistent_token_file_xyz")


# ============================================================================
# 15. Integration: end-to-end task lifecycle
# ============================================================================

class TestTaskLifecycle:
    """Integration tests for the full task lifecycle."""

    def test_full_task_lifecycle(self):
        from mechanic import FleetMechanic, MechanicTask, TaskType, TaskResult
        m = FleetMechanic("fake-token")
        task = MechanicTask(
            id="LIFECYCLE-001",
            task_type=TaskType.FIX_TESTS,
            target_repo="lifecycle-repo",
        )
        assert task.result is None
        task.result = TaskResult.SUCCESS
        task.commits_made = 2
        task.tests_fixed = 5
        task.files_changed = 3
        task.diagnosis = "All tests fixed"
        m.completed_tasks.append(task)

        assert len(m.completed_tasks) == 1
        d = task.to_dict()
        assert d["result"] == "success"
        assert d["commits"] == 2
        assert d["tests_fixed"] == 5

    def test_multiple_tasks_same_mechanic(self):
        from mechanic import FleetMechanic, MechanicTask, TaskType, TaskResult
        m = FleetMechanic("fake-token")
        for i in range(5):
            task = MechanicTask(
                id=f"TASK-{i}",
                task_type=TaskType.GEN_DOCS,
                target_repo=f"repo-{i}",
                result=TaskResult.SUCCESS if i % 2 == 0 else TaskResult.PARTIAL,
            )
            m.completed_tasks.append(task)

        assert len(m.completed_tasks) == 5
        successes = sum(1 for t in m.completed_tasks if t.result == TaskResult.SUCCESS)
        assert successes == 3


# ============================================================================
# 16. Dataclass field tests
# ============================================================================

class TestDataclassFields:
    """Tests for dataclass fields."""

    def test_diagnostic_failure_all_fields(self):
        from fix_code import DiagnosticFailure
        df = DiagnosticFailure(
            test_name="test_something",
            file="tests/test_foo.py",
            line=42,
            error_type="AssertionError",
            error_message="expected 5 got 3",
            suggested_fix="change 3 to 5",
        )
        assert df.test_name == "test_something"
        assert df.file == "tests/test_foo.py"
        assert df.line == 42
        assert df.error_type == "AssertionError"
        assert df.error_message == "expected 5 got 3"
        assert df.suggested_fix == "change 3 to 5"

    def test_diagnostic_failure_default_suggested_fix(self):
        from fix_code import DiagnosticFailure
        df = DiagnosticFailure("test", "f.py", 1, "Error", "msg")
        assert df.suggested_fix == ""

    def test_code_fix_confidence_range(self):
        from fix_code import CodeFix
        cf = CodeFix(file="f.py", line=1, old_code="a", new_code="b",
                     description="test", confidence=0.99)
        assert 0 <= cf.confidence <= 1.0

    def test_code_fix_default_confidence(self):
        from fix_code import CodeFix
        cf = CodeFix(file="f.py", line=1, old_code="a", new_code="b", description="test")
        assert cf.confidence == 0.5
