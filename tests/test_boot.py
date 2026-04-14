"""Comprehensive tests for boot.py module."""
import os
import sys
import json
import tempfile
from unittest.mock import patch, MagicMock, call
from io import StringIO

import pytest


# ============================================================================
# boot.load_github_token
# ============================================================================

class TestBootLoadGithubToken:
    """Tests for boot.load_github_token."""

    def test_load_token_from_file(self, tmp_path):
        import boot
        token_file = tmp_path / ".mechanic_token"
        token_file.write_text("ghp_ABCDEFG1234567890\n")
        token = boot.load_github_token(str(token_file))
        assert token == "ghp_ABCDEFG1234567890"

    def test_load_token_strips_whitespace(self, tmp_path):
        import boot
        token_file = tmp_path / ".mechanic_token"
        token_file.write_text("  ghp_TOKEN_WITH_SPACES  \n")
        token = boot.load_github_token(str(token_file))
        assert token == "ghp_TOKEN_WITH_SPACES"

    def test_load_token_file_not_found(self):
        import boot
        with pytest.raises(FileNotFoundError, match="not found"):
            boot.load_github_token("/tmp/nonexistent_token_file_xyz")

    def test_load_token_empty_file_raises(self, tmp_path):
        import boot
        token_file = tmp_path / ".mechanic_token"
        token_file.write_text("\n")
        with pytest.raises(ValueError, match="empty"):
            boot.load_github_token(str(token_file))

    def test_load_token_whitespace_only_raises(self, tmp_path):
        import boot
        token_file = tmp_path / ".mechanic_token"
        token_file.write_text("   \n  \n")
        with pytest.raises(ValueError, match="empty"):
            boot.load_github_token(str(token_file))


# ============================================================================
# boot.fetch_user_repos
# ============================================================================

class TestBootFetchUserRepos:
    """Tests for boot.fetch_user_repos."""

    def test_fetch_repos_success(self):
        import boot
        fake_repos = [{"name": "repo1"}, {"name": "repo2"}]
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(fake_repos)
            )
            repos = boot.fetch_user_repos("token")
            assert len(repos) == 2
            assert repos[0]["name"] == "repo1"

    def test_fetch_repos_custom_per_page(self):
        import boot
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps([])
            )
            boot.fetch_user_repos("token", per_page=50)
            call_args = mock_run.call_args[0][0]
            # Verify the command was constructed (it's a list passed to subprocess.run)
            assert "50" in str(call_args)

    def test_fetch_repos_curl_failure(self):
        import boot
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="connection refused"
            )
            with pytest.raises(RuntimeError, match="curl failed"):
                boot.fetch_user_repos("token")

    def test_fetch_repos_json_decode_error(self):
        import boot
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="not json"
            )
            with pytest.raises(RuntimeError, match="parse"):
                boot.fetch_user_repos("token")

    def test_fetch_repos_timeout(self):
        import boot
        import subprocess
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("cmd", 30)):
            with pytest.raises(RuntimeError, match="timed out"):
                boot.fetch_user_repos("token")


# ============================================================================
# boot.filter_own_repos
# ============================================================================

class TestBootFilterOwnRepos:
    """Tests for boot.filter_own_repos."""

    def test_filter_own_non_forks(self):
        import boot
        repos = [
            {"name": "own1", "fork": False, "size": 100},
            {"name": "own2", "fork": False, "size": 200},
            {"name": "fork1", "fork": True, "size": 100},
        ]
        result = boot.filter_own_repos(repos)
        assert result == ["own1", "own2"]

    def test_filter_own_excludes_small(self):
        import boot
        repos = [
            {"name": "big", "fork": False, "size": 100},
            {"name": "small", "fork": False, "size": 5},
        ]
        result = boot.filter_own_repos(repos, min_size_kb=10)
        assert result == ["big"]

    def test_filter_own_empty_list(self):
        import boot
        result = boot.filter_own_repos([])
        assert result == []

    def test_filter_own_all_forks(self):
        import boot
        repos = [
            {"name": "f1", "fork": True, "size": 100},
            {"name": "f2", "fork": True, "size": 200},
        ]
        result = boot.filter_own_repos(repos)
        assert result == []

    def test_filter_own_missing_size_defaults_zero(self):
        import boot
        repos = [{"name": "nosize", "fork": False}]
        result = boot.filter_own_repos(repos)
        assert result == []

    def test_filter_own_custom_min_size(self):
        import boot
        repos = [
            {"name": "tiny", "fork": False, "size": 50},
            {"name": "large", "fork": False, "size": 500},
        ]
        result = boot.filter_own_repos(repos, min_size_kb=100)
        assert result == ["large"]


# ============================================================================
# boot.print_scan_results
# ============================================================================

class TestBootPrintScanResults:
    """Tests for boot.print_scan_results."""

    def test_print_scan_results_output(self, capsys):
        import boot
        from mechanic import RepoHealth
        reports = [
            RepoHealth(repo="test-repo", has_readme=True, has_ci=True,
                       has_tests=True, test_count=10, test_pass=8,
                       language="Python"),
        ]
        reports[0].compute_score()
        boot.print_scan_results(reports)
        captured = capsys.readouterr()
        assert "test-repo" in captured.out
        assert "Python" in captured.out

    def test_print_scan_results_empty(self, capsys):
        import boot
        boot.print_scan_results([])
        captured = capsys.readouterr()
        assert "Repo" in captured.out

    def test_print_scan_results_no_tests(self, capsys):
        import boot
        from mechanic import RepoHealth
        reports = [RepoHealth(repo="no-tests")]
        boot.print_scan_results(reports)
        captured = capsys.readouterr()
        assert "-" in captured.out


# ============================================================================
# boot.print_summary
# ============================================================================

class TestBootPrintSummary:
    """Tests for boot.print_summary."""

    def test_print_summary_healthy(self, capsys):
        import boot
        from mechanic import RepoHealth
        r1 = RepoHealth(repo="r1", has_readme=True, has_ci=True, has_tests=True,
                       test_count=10, test_pass=10)
        r2 = RepoHealth(repo="r2", has_readme=True, has_ci=True, has_tests=True,
                       test_count=10, test_pass=10)
        r1.compute_score()
        r2.compute_score()
        boot.print_summary([r1, r2])
        captured = capsys.readouterr()
        assert "Healthy: 2/2" in captured.out

    def test_print_summary_mixed(self, capsys):
        import boot
        from mechanic import RepoHealth
        h1 = RepoHealth(repo="healthy", has_readme=True, has_ci=True, has_tests=True,
                       test_count=10, test_pass=10)
        h1.compute_score()
        h2 = RepoHealth(repo="unhealthy")
        h2.compute_score()
        boot.print_summary([h1, h2])
        captured = capsys.readouterr()
        assert "Healthy: 1/2" in captured.out

    def test_print_summary_empty(self, capsys):
        import boot
        boot.print_summary([])
        captured = capsys.readouterr()
        assert "Healthy: 0/0" in captured.out


# ============================================================================
# boot.fix_repos_needing_docs
# ============================================================================

class TestBootFixReposNeedingDocs:
    """Tests for boot.fix_repos_needing_docs."""

    def test_fix_no_repos_need_fix(self):
        import boot
        from mechanic import FleetMechanic, RepoHealth, TaskResult, MechanicTask, TaskType
        m = FleetMechanic("fake-token")
        reports = [RepoHealth(repo="perfect", has_gitignore=True, has_ci=True)]
        with patch.object(m, 'execute_gen_docs') as mock:
            count = boot.fix_repos_needing_docs(m, reports)
            assert count == 0
            assert not mock.called

    def test_fix_repos_calls_gen_docs(self):
        import boot
        from mechanic import FleetMechanic, RepoHealth, TaskResult, MechanicTask, TaskType
        m = FleetMechanic("fake-token")
        reports = [RepoHealth(repo="needs-fix", has_gitignore=False)]
        task = MechanicTask(id="T", task_type=TaskType.GEN_DOCS, target_repo="needs-fix",
                           result=TaskResult.SUCCESS, diagnosis="Added .gitignore")
        with patch.object(m, 'execute_gen_docs', return_value=task):
            count = boot.fix_repos_needing_docs(m, reports)
            assert count == 1

    def test_fix_repos_partial_does_not_count(self):
        import boot
        from mechanic import FleetMechanic, RepoHealth, TaskResult, MechanicTask, TaskType
        m = FleetMechanic("fake-token")
        reports = [RepoHealth(repo="partial", has_gitignore=False)]
        task = MechanicTask(id="T", task_type=TaskType.GEN_DOCS, target_repo="partial",
                           result=TaskResult.PARTIAL, diagnosis="No changes needed")
        with patch.object(m, 'execute_gen_docs', return_value=task):
            count = boot.fix_repos_needing_docs(m, reports)
            assert count == 0

    def test_fix_repos_exception_is_caught(self):
        import boot
        from mechanic import FleetMechanic, RepoHealth
        m = FleetMechanic("fake-token")
        reports = [RepoHealth(repo="error-repo", has_gitignore=False)]
        with patch.object(m, 'execute_gen_docs', side_effect=Exception("boom")):
            count = boot.fix_repos_needing_docs(m, reports)
            assert count == 0


# ============================================================================
# boot.main
# ============================================================================

class TestBootMain:
    """Tests for boot.main."""

    def test_main_no_token_file(self):
        import boot
        result = boot.main()
        assert result == 1

    def test_main_success_flow(self, tmp_path):
        import boot
        token_file = tmp_path / ".mechanic_token"
        token_file.write_text("fake-token")

        with patch('boot.load_github_token', return_value="fake-token"), \
             patch('boot.fetch_user_repos', return_value=[]), \
             patch('boot.filter_own_repos', return_value=[]):
            result = boot.main()
            assert result == 0

    def test_main_with_repos_flow(self, tmp_path):
        import boot
        from mechanic import FleetMechanic, RepoHealth
        token_file = tmp_path / ".mechanic_token"
        token_file.write_text("fake-token")

        m = FleetMechanic("fake-token")
        with patch('boot.load_github_token', return_value="fake-token"), \
             patch('boot.fetch_user_repos', return_value=[{"name": "r1"}]), \
             patch('boot.filter_own_repos', return_value=["r1"]), \
             patch('boot.FleetMechanic', return_value=m), \
             patch.object(m, 'fleet_scan', return_value=[]) as mock_scan, \
             patch('boot.fix_repos_needing_docs', return_value=0), \
             patch('boot.print_scan_results'), \
             patch('boot.print_summary'):
            result = boot.main()
            assert result == 0
            mock_scan.assert_called_once()

    def test_main_handles_value_error(self):
        import boot
        with patch('boot.load_github_token', side_effect=ValueError("empty token")):
            result = boot.main()
            assert result == 1

    def test_main_handles_runtime_error(self):
        import boot
        with patch('boot.load_github_token', side_effect=RuntimeError("api fail")):
            result = boot.main()
            assert result == 1

    def test_main_handles_unexpected_error(self):
        import boot
        with patch('boot.load_github_token', side_effect=Exception("unexpected")):
            result = boot.main()
            assert result == 1
