"""Comprehensive tests for scan_fleet.py module."""
import os
import sys
import json
import time
import tempfile
from unittest.mock import patch, MagicMock, call
from io import StringIO

import pytest


# ============================================================================
# scan_fleet.RateLimiter
# ============================================================================

class TestRateLimiter:
    """Tests for scan_fleet.RateLimiter."""

    def test_default_initialization(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter()
        assert rl.initial_delay == 1.0
        assert rl.max_delay == 60.0
        assert rl.max_retries == 5
        assert rl.current_delay == 1.0

    def test_custom_initialization(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=2.0, max_delay=30.0, max_retries=10)
        assert rl.initial_delay == 2.0
        assert rl.max_delay == 30.0
        assert rl.max_retries == 10

    def test_backoff_attempt_zero(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0, max_delay=100.0)
        assert rl.backoff(0) == pytest.approx(1.0)

    def test_backoff_attempt_one(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0, max_delay=100.0)
        assert rl.backoff(1) == pytest.approx(2.0)

    def test_backoff_attempt_two(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0, max_delay=100.0)
        assert rl.backoff(2) == pytest.approx(4.0)

    def test_backoff_capped_at_max_delay(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0, max_delay=10.0)
        assert rl.backoff(100) == 10.0

    def test_backoff_exactly_at_max(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0, max_delay=8.0)
        assert rl.backoff(3) == 8.0  # 2^3 = 8, exactly at max

    def test_wait_calls_sleep(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=0.01, max_delay=0.01)
        with patch('time.sleep') as mock_sleep:
            rl.wait(0)
            mock_sleep.assert_called_once_with(0.01)

    def test_reset_restores_initial_delay(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=1.0, max_delay=60.0)
        rl.current_delay = 42.0
        rl.reset()
        assert rl.current_delay == 1.0

    def test_reset_idempotent(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=5.0)
        rl.reset()
        assert rl.current_delay == 5.0
        rl.reset()
        assert rl.current_delay == 5.0

    def test_backoff_deterministic(self):
        from scan_fleet import RateLimiter
        rl = RateLimiter(initial_delay=2.0, max_delay=100.0)
        assert rl.backoff(3) == rl.backoff(3)


# ============================================================================
# scan_fleet.load_github_token
# ============================================================================

class TestScanFleetLoadGithubToken:
    """Tests for scan_fleet.load_github_token."""

    def test_load_token_success(self, tmp_path):
        import scan_fleet
        token_file = tmp_path / ".token"
        token_file.write_text("ghp_SCAN_TEST_TOKEN\n")
        token = scan_fleet.load_github_token(str(token_file))
        assert token == "ghp_SCAN_TEST_TOKEN"

    def test_load_token_strips_whitespace(self, tmp_path):
        import scan_fleet
        token_file = tmp_path / ".token"
        token_file.write_text("  tok  \n")
        token = scan_fleet.load_github_token(str(token_file))
        assert token == "tok"

    def test_load_token_file_not_found(self):
        import scan_fleet
        with pytest.raises(FileNotFoundError, match="not found"):
            scan_fleet.load_github_token("/tmp/nonexistent_scan_token_xyz")

    def test_load_token_empty_file(self, tmp_path):
        import scan_fleet
        token_file = tmp_path / ".token"
        token_file.write_text("")
        with pytest.raises(ValueError, match="empty"):
            scan_fleet.load_github_token(str(token_file))


# ============================================================================
# scan_fleet.fetch_repos_paginated
# ============================================================================

class TestFetchReposPaginated:
    """Tests for scan_fleet.fetch_repos_paginated."""

    def test_single_page(self):
        import scan_fleet
        repos = [{"name": f"repo{i}"} for i in range(5)]
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(repos))
            result = scan_fleet.fetch_repos_paginated("token", per_page=100)
            assert len(result) == 5

    def test_empty_response_stops(self):
        import scan_fleet
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps([]))
            result = scan_fleet.fetch_repos_paginated("token")
            assert result == []

    def test_partial_page_stops(self):
        import scan_fleet
        repos = [{"name": "repo1"}]
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(repos))
            result = scan_fleet.fetch_repos_paginated("token", per_page=100)
            assert len(result) == 1
            assert mock_run.call_count == 1

    def test_json_decode_error_retries(self):
        import scan_fleet
        rl = scan_fleet.RateLimiter(max_retries=2)
        call_count = [0]
        def fake_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(returncode=0, stdout="not json")
            return MagicMock(returncode=0, stdout=json.dumps([]))

        with patch('subprocess.run', side_effect=fake_run):
            result = scan_fleet.fetch_repos_paginated("token", rate_limiter=rl)
            assert call_count[0] == 2

    def test_json_decode_error_exhausts_retries(self):
        import scan_fleet
        rl = scan_fleet.RateLimiter(max_retries=2)
        with patch('subprocess.run', return_value=MagicMock(returncode=0, stdout="bad")):
            with pytest.raises(RuntimeError, match="parse"):
                scan_fleet.fetch_repos_paginated("token", rate_limiter=rl)

    def test_curl_failure_retries(self):
        import scan_fleet
        rl = scan_fleet.RateLimiter(max_retries=2)
        call_count = [0]
        def fake_run(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                return MagicMock(returncode=1, stderr="error")
            return MagicMock(returncode=0, stdout=json.dumps([]))

        with patch('subprocess.run', side_effect=fake_run):
            # curl failure raises RuntimeError, caught by generic exception handler
            with pytest.raises(RuntimeError):
                scan_fleet.fetch_repos_paginated("token", rate_limiter=rl)
            # Should have retried max_retries times
            assert call_count[0] == 2

    def test_custom_rate_limiter_used(self):
        import scan_fleet
        rl = scan_fleet.RateLimiter(initial_delay=5.0)
        with patch('subprocess.run', return_value=MagicMock(returncode=0, stdout=json.dumps([]))):
            scan_fleet.fetch_repos_paginated("token", rate_limiter=rl)
            # Just verify no crash

    def test_default_rate_limiter_created(self):
        import scan_fleet
        with patch('subprocess.run', return_value=MagicMock(returncode=0, stdout=json.dumps([]))):
            result = scan_fleet.fetch_repos_paginated("token")
            assert result == []


# ============================================================================
# scan_fleet.filter_repos_by_type
# ============================================================================

class TestFilterReposByType:
    """Tests for scan_fleet.filter_repos_by_type."""

    def test_basic_filtering(self):
        import scan_fleet
        repos = [
            {"name": "own1", "fork": False, "size": 100},
            {"name": "fork1", "fork": True, "size": 100},
        ]
        own, forks = scan_fleet.filter_repos_by_type(repos)
        assert own == ["own1"]
        assert forks == ["fork1"]

    def test_empty_input(self):
        import scan_fleet
        own, forks = scan_fleet.filter_repos_by_type([])
        assert own == []
        assert forks == []

    def test_all_forks(self):
        import scan_fleet
        repos = [{"name": f"f{i}", "fork": True, "size": 100} for i in range(5)]
        own, forks = scan_fleet.filter_repos_by_type(repos)
        assert own == []
        assert len(forks) == 5

    def test_all_own(self):
        import scan_fleet
        repos = [{"name": f"o{i}", "fork": False, "size": 100} for i in range(5)]
        own, forks = scan_fleet.filter_repos_by_type(repos)
        assert len(own) == 5
        assert forks == []

    def test_size_filter(self):
        import scan_fleet
        repos = [
            {"name": "big", "fork": False, "size": 100},
            {"name": "small", "fork": False, "size": 5},
            {"name": "medium", "fork": False, "size": 11},
        ]
        own, _ = scan_fleet.filter_repos_by_type(repos, min_size_kb=10)
        assert "big" in own
        assert "medium" in own
        assert "small" not in own

    def test_size_filter_affects_forks(self):
        import scan_fleet
        repos = [
            {"name": "big_fork", "fork": True, "size": 100},
            {"name": "small_fork", "fork": True, "size": 5},
        ]
        _, forks = scan_fleet.filter_repos_by_type(repos, min_size_kb=10)
        assert forks == ["big_fork"]

    def test_missing_size_defaults_zero(self):
        import scan_fleet
        repos = [{"name": "no_size", "fork": False}]
        own, _ = scan_fleet.filter_repos_by_type(repos)
        assert own == []

    def test_missing_fork_defaults_false(self):
        import scan_fleet
        repos = [{"name": "no_fork", "size": 100}]
        own, forks = scan_fleet.filter_repos_by_type(repos)
        assert own == ["no_fork"]
        assert forks == []

    def test_exact_boundary_size(self):
        import scan_fleet
        repos = [{"name": "exact", "fork": False, "size": 10}]
        own, _ = scan_fleet.filter_repos_by_type(repos, min_size_kb=10)
        # size 10 > min_size_kb 10 is False (> not >=)
        assert own == []


# ============================================================================
# scan_fleet.print_scan_results
# ============================================================================

class TestPrintScanResults:
    """Tests for scan_fleet.print_scan_results."""

    def test_print_basic(self, capsys):
        import scan_fleet
        from mechanic import RepoHealth
        reports = [RepoHealth(repo="my-repo", has_readme=True, language="Python")]
        scan_fleet.print_scan_results(reports)
        captured = capsys.readouterr()
        assert "my-repo" in captured.out

    def test_print_empty(self, capsys):
        import scan_fleet
        scan_fleet.print_scan_results([])
        captured = capsys.readouterr()
        assert "Repo" in captured.out

    def test_print_multiple_repos(self, capsys):
        import scan_fleet
        from mechanic import RepoHealth
        reports = [
            RepoHealth(repo="repo-a", has_readme=True, language="Rust"),
            RepoHealth(repo="repo-b", has_ci=True, language="Go"),
        ]
        scan_fleet.print_scan_results(reports)
        captured = capsys.readouterr()
        assert "repo-a" in captured.out
        assert "repo-b" in captured.out

    def test_print_ci_status(self, capsys):
        import scan_fleet
        from mechanic import RepoHealth
        h = RepoHealth(repo="ci-repo", has_ci=True)
        scan_fleet.print_scan_results([h])
        captured = capsys.readouterr()
        assert "Y" in captured.out

    def test_print_no_ci_status(self, capsys):
        import scan_fleet
        from mechanic import RepoHealth
        h = RepoHealth(repo="no-ci-repo", has_ci=False)
        scan_fleet.print_scan_results([h])
        captured = capsys.readouterr()
        assert "N" in captured.out

    def test_print_test_counts(self, capsys):
        import scan_fleet
        from mechanic import RepoHealth
        h = RepoHealth(repo="tested", has_tests=True, test_count=10, test_pass=8)
        scan_fleet.print_scan_results([h])
        captured = capsys.readouterr()
        assert "8/10" in captured.out

    def test_print_no_tests_dash(self, capsys):
        import scan_fleet
        from mechanic import RepoHealth
        h = RepoHealth(repo="untested", test_count=0)
        scan_fleet.print_scan_results([h])
        captured = capsys.readouterr()
        assert "-" in captured.out


# ============================================================================
# scan_fleet.print_summary
# ============================================================================

class TestPrintSummary:
    """Tests for scan_fleet.print_summary."""

    def test_all_healthy(self, capsys):
        import scan_fleet
        from mechanic import RepoHealth
        h = RepoHealth(repo="healthy", has_readme=True, has_ci=True, has_tests=True,
                       test_count=10, test_pass=10)
        h.compute_score()
        scan_fleet.print_summary([h])
        captured = capsys.readouterr()
        assert "Healthy: 1/1" in captured.out

    def test_none_healthy(self, capsys):
        import scan_fleet
        from mechanic import RepoHealth
        h = RepoHealth(repo="sick")
        h.compute_score()
        scan_fleet.print_summary([h])
        captured = capsys.readouterr()
        assert "Healthy: 0/1" in captured.out

    def test_empty_reports(self, capsys):
        import scan_fleet
        scan_fleet.print_summary([])
        captured = capsys.readouterr()
        assert "Healthy: 0/0" in captured.out

    def test_boundary_health_score(self, capsys):
        import scan_fleet
        from mechanic import RepoHealth
        h = RepoHealth(repo="borderline", has_readme=True, has_gitignore=True,
                       has_ci=True, has_tests=True, test_count=10, test_pass=3)
        h.compute_score()
        # 0.2 + 0.1 + 0.2 + 0.2 + 0.3*0.3 = 0.79 >= 0.5, so healthy
        scan_fleet.print_summary([h])
        captured = capsys.readouterr()
        assert "Healthy: 1/1" in captured.out


# ============================================================================
# scan_fleet.fix_repos_needing_docs
# ============================================================================

class TestFixReposNeedingDocs:
    """Tests for scan_fleet.fix_repos_needing_docs."""

    def test_no_repos_need_fix(self):
        import scan_fleet
        from mechanic import FleetMechanic, RepoHealth
        m = FleetMechanic("fake-token")
        reports = [RepoHealth(repo="ok", has_gitignore=True, has_ci=True)]
        with patch.object(m, 'execute_gen_docs') as mock:
            count = scan_fleet.fix_repos_needing_docs(m, reports)
            assert count == 0
            assert not mock.called

    def test_missing_gitignore_triggers_fix(self):
        import scan_fleet
        from mechanic import FleetMechanic, RepoHealth, TaskResult, MechanicTask, TaskType
        m = FleetMechanic("fake-token")
        reports = [RepoHealth(repo="no-gi", has_gitignore=False, has_ci=True)]
        task = MechanicTask(id="T", task_type=TaskType.GEN_DOCS, target_repo="no-gi",
                           result=TaskResult.SUCCESS, diagnosis="Added .gitignore")
        with patch.object(m, 'execute_gen_docs', return_value=task):
            count = scan_fleet.fix_repos_needing_docs(m, reports)
            assert count == 1

    def test_missing_ci_triggers_fix(self):
        import scan_fleet
        from mechanic import FleetMechanic, RepoHealth, TaskResult, MechanicTask, TaskType
        m = FleetMechanic("fake-token")
        reports = [RepoHealth(repo="no-ci", has_gitignore=True, has_ci=False)]
        task = MechanicTask(id="T", task_type=TaskType.GEN_DOCS, target_repo="no-ci",
                           result=TaskResult.SUCCESS, diagnosis="Added CI")
        with patch.object(m, 'execute_gen_docs', return_value=task):
            count = scan_fleet.fix_repos_needing_docs(m, reports)
            assert count == 1

    def test_both_missing_triggers_fix(self):
        import scan_fleet
        from mechanic import FleetMechanic, RepoHealth, TaskResult, MechanicTask, TaskType
        m = FleetMechanic("fake-token")
        reports = [RepoHealth(repo="bare", has_gitignore=False, has_ci=False)]
        task = MechanicTask(id="T", task_type=TaskType.GEN_DOCS, target_repo="bare",
                           result=TaskResult.SUCCESS, diagnosis="Added both")
        with patch.object(m, 'execute_gen_docs', return_value=task):
            count = scan_fleet.fix_repos_needing_docs(m, reports)
            assert count == 1

    def test_failed_fix_does_not_count(self):
        import scan_fleet
        from mechanic import FleetMechanic, RepoHealth, TaskResult, MechanicTask, TaskType
        m = FleetMechanic("fake-token")
        reports = [RepoHealth(repo="fail-repo", has_gitignore=False)]
        task = MechanicTask(id="T", task_type=TaskType.GEN_DOCS, target_repo="fail-repo",
                           result=TaskResult.FAILED, diagnosis="Error")
        with patch.object(m, 'execute_gen_docs', return_value=task):
            count = scan_fleet.fix_repos_needing_docs(m, reports)
            assert count == 0

    def test_exception_caught_continues(self):
        import scan_fleet
        from mechanic import FleetMechanic, RepoHealth, TaskResult, MechanicTask, TaskType
        m = FleetMechanic("fake-token")
        reports = [
            RepoHealth(repo="boom", has_gitignore=False, has_ci=False),
            RepoHealth(repo="fixable", has_gitignore=False, has_ci=True),
        ]
        task = MechanicTask(id="T", task_type=TaskType.GEN_DOCS, target_repo="fixable",
                           result=TaskResult.SUCCESS, diagnosis="Ok")
        call_count = [0]
        def side_effect(repo):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("boom")
            return task
        with patch.object(m, 'execute_gen_docs', side_effect=side_effect):
            count = scan_fleet.fix_repos_needing_docs(m, reports)
            assert count == 1


# ============================================================================
# scan_fleet.main
# ============================================================================

class TestScanFleetMain:
    """Tests for scan_fleet.main."""

    def test_main_no_token(self):
        import scan_fleet
        result = scan_fleet.main()
        assert result == 1

    def test_main_success(self):
        import scan_fleet
        with patch('scan_fleet.load_github_token', return_value="fake"), \
             patch('scan_fleet.fetch_repos_paginated', return_value=[]), \
             patch('scan_fleet.filter_repos_by_type', return_value=([], [])):
            result = scan_fleet.main()
            assert result == 0

    def test_main_with_repos(self):
        import scan_fleet
        from mechanic import FleetMechanic
        m = FleetMechanic("fake-token")
        with patch('scan_fleet.load_github_token', return_value="fake"), \
             patch('scan_fleet.fetch_repos_paginated', return_value=[{"name": "r1"}]), \
             patch('scan_fleet.filter_repos_by_type', return_value=(["r1"], [])), \
             patch('scan_fleet.FleetMechanic', return_value=m), \
             patch.object(m, 'fleet_scan', return_value=[]), \
             patch('scan_fleet.fix_repos_needing_docs', return_value=0), \
             patch('scan_fleet.print_scan_results'), \
             patch('scan_fleet.print_summary'):
            result = scan_fleet.main()
            assert result == 0

    def test_main_file_not_found(self):
        import scan_fleet
        with patch('scan_fleet.load_github_token', side_effect=FileNotFoundError("no token")):
            result = scan_fleet.main()
            assert result == 1

    def test_main_runtime_error(self):
        import scan_fleet
        with patch('scan_fleet.load_github_token', side_effect=RuntimeError("api error")):
            result = scan_fleet.main()
            assert result == 1

    def test_main_unexpected_error(self):
        import scan_fleet
        with patch('scan_fleet.load_github_token', side_effect=OSError("disk error")):
            result = scan_fleet.main()
            assert result == 1
