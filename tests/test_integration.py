"""Fleet Mechanic — integration tests.

Run with: python -m pytest tests/ -v
"""
import sys
import os
import unittest

# Ensure src modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mechanic import FleetMechanic, MechanicTask, TaskType, TaskResult, RepoHealth


class TestFleetMechanicIntegration(unittest.TestCase):
    """Integration tests that exercise multiple components together."""

    def test_full_health_to_markdown_pipeline(self):
        """Create a health report, compute score, and generate markdown."""
        h = RepoHealth(
            repo="pipeline-test", has_readme=True, has_gitignore=True,
            has_ci=True, has_tests=True, test_count=8, test_pass=6, test_fail=2,
            language="python", size_kb=2048, open_issues=3, last_commit_days=2,
        )
        h.compute_score()
        md = h.to_markdown()
        self.assertIn("pipeline-test", md)
        self.assertIn("✅", md)
        self.assertIn("python", md)
        self.assertIn("2048KB", md)
        self.assertGreater(h.health_score, 0.5)
        self.assertLess(h.health_score, 1.0)

    def test_task_lifecycle(self):
        """Simulate a full task lifecycle: create → execute → report."""
        task = MechanicTask(
            id="LIFECYCLE-001",
            task_type=TaskType.FIX_TESTS,
            target_repo="test-repo",
            target_branch="dev",
            description="Fix failing tests",
        )
        self.assertIsNone(task.result)
        task.result = TaskResult.SUCCESS
        task.diagnosis = "Fixed 3 tests"
        task.commits_made = 1
        task.tests_fixed = 3
        task.files_changed = 2

        d = task.to_dict()
        self.assertEqual(d["result"], "success")
        self.assertEqual(d["tests_fixed"], 3)

    def test_mechanic_scan_with_mock_repos(self):
        """fleet_scan with explicit repo list should process all of them."""
        m = FleetMechanic("fake-token")
        # Fleet scan with nonexistent repos should not crash
        reports = m.fleet_scan(repos=["repo-a", "repo-b", "repo-c"])
        self.assertEqual(len(reports), 3)
        for r in reports:
            self.assertIsNotNone(r)
            self.assertIn(r.repo, ["repo-a", "repo-b", "repo-c"])
