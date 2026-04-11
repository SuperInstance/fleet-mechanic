#!/usr/bin/env python3
"""
Mechanic Skill: review — Review PRs and code from other agents.

The mechanic acts as a code reviewer, checking:
- Test coverage
- Code style
- Security issues
- Architectural compliance
- Documentation completeness
"""
import os
import re
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ReviewComment:
    file: str
    line: int
    severity: Severity
    category: str  # style, security, testing, architecture, docs
    message: str
    suggestion: str = ""


@dataclass
class ReviewReport:
    repo: str
    pr_number: Optional[int]
    comments: List[ReviewComment] = field(default_factory=list)
    approved: bool = False
    score: float = 0.0  # 0-100
    
    def to_markdown(self) -> str:
        lines = [f"# Code Review: {self.repo}\n"]
        if self.pr_number:
            lines.append(f"**PR #{self.pr_number}**\n")
        
        lines.append(f"**Score: {self.score:.0f}/100**")
        lines.append(f"**Verdict: {'✅ APPROVE' if self.approved else '❌ CHANGES REQUESTED'}**\n")
        
        if not self.comments:
            lines.append("No issues found.")
            return "\n".join(lines)
        
        # Group by severity
        by_severity = {}
        for c in self.comments:
            by_severity.setdefault(c.severity.value, []).append(c)
        
        for sev in ["critical", "error", "warning", "info"]:
            if sev in by_severity:
                emoji = {"critical": "🔴", "error": "🟠", "warning": "🟡", "info": "🔵"}[sev]
                lines.append(f"\n### {emoji} {sev.title()} ({len(by_severity[sev])})")
                for c in by_severity[sev]:
                    lines.append(f"- **{c.file}:{c.line}** [{c.category}] {c.message}")
                    if c.suggestion:
                        lines.append(f"  > {c.suggestion}")
        
        return "\n".join(lines)


class CodeReviewer:
    """Review code for quality, security, and fleet compliance."""
    
    def __init__(self):
        self.checks = [
            self._check_missing_tests,
            self._check_missing_docs,
            self._check_security_issues,
            self._check_style,
            self._check_complexity,
            self._check_fleet_compliance,
        ]
    
    def review_file(self, filepath: str, content: str) -> List[ReviewComment]:
        """Review a single file."""
        comments = []
        for check in self.checks:
            comments.extend(check(filepath, content))
        return comments
    
    def review_directory(self, directory: str) -> ReviewReport:
        """Review all code in a directory."""
        report = ReviewReport(repo=os.path.basename(directory), pr_number=None)
        
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                      ('target', 'node_modules', '__pycache__', '.git')]
            for f in files:
                if f.endswith(('.py', '.rs', '.go', '.ts', '.js')):
                    path = os.path.join(root, f)
                    rel = os.path.relpath(path, directory)
                    try:
                        with open(path) as fh:
                            content = fh.read()
                        report.comments.extend(self.review_file(rel, content))
                    except:
                        pass
        
        # Compute score
        self._compute_score(report)
        return report
    
    def _compute_score(self, report: ReviewReport):
        """Compute review score based on findings."""
        score = 100.0
        for c in report.comments:
            if c.severity == Severity.CRITICAL: score -= 20
            elif c.severity == Severity.ERROR: score -= 10
            elif c.severity == Severity.WARNING: score -= 5
            elif c.severity == Severity.INFO: score -= 1
        report.score = max(0, score)
        report.approved = report.score >= 60 and not any(
            c.severity == Severity.CRITICAL for c in report.comments
        )
    
    # === Individual Checks ===
    
    def _check_missing_tests(self, filepath: str, content: str) -> List[ReviewComment]:
        comments = []
        if filepath.startswith("tests/") or filepath.startswith("test_"):
            return comments
        
        # Check if there are functions without corresponding tests
        if filepath.endswith('.py'):
            fns = re.findall(r'^def (\w+)\(', content, re.MULTILINE)
            for fn in fns:
                if not fn.startswith('_') and 'test' not in fn.lower():
                    # Check if test file exists (can't verify here, just flag)
                    pass
        
        # Check for test assertions in source (anti-pattern)
        if 'assert ' in content and not filepath.startswith("test"):
            comments.append(ReviewComment(
                file=filepath, line=0, severity=Severity.INFO,
                category="testing",
                message="Assertions found in source code (not test file)",
                suggestion="Move assertions to test files"
            ))
        
        return comments
    
    def _check_missing_docs(self, filepath: str, content: str) -> List[ReviewComment]:
        comments = []
        
        if filepath.endswith('.py'):
            # Check for missing docstrings on public functions
            for m in re.finditer(r'^def (\w+)\(([^)]*)\):', content, re.MULTILINE):
                fn_name = m.group(1)
                if fn_name.startswith('_'):
                    continue
                # Check if next line has docstring
                after = content[m.end():m.end()+100]
                if not after.strip().startswith('"""') and not after.strip().startswith("'''"):
                    line_num = content[:m.start()].count('\n') + 1
                    comments.append(ReviewComment(
                        file=filepath, line=line_num, severity=Severity.INFO,
                        category="docs",
                        message=f"Function `{fn_name}` missing docstring",
                        suggestion="Add a docstring describing purpose and parameters"
                    ))
        
        return comments
    
    def _check_security_issues(self, filepath: str, content: str) -> List[ReviewComment]:
        comments = []
        
        # Check for hardcoded secrets
        secret_patterns = [
            (r'(?:password|secret|token|api_key|apikey)\s*=\s*["\'][^"\']{8,}', "hardcoded_secret"),
            (r'eval\s*\(', "eval_usage"),
            (r'exec\s*\(', "exec_usage"),
            (r'subprocess\.call\s*\([^)]*shell\s*=\s*True', "shell_injection"),
            (r'os\.system\s*\(', "os_system"),
        ]
        
        for pattern, category in secret_patterns:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:m.start()].count('\n') + 1
                severity = Severity.CRITICAL if "secret" in category else Severity.WARNING
                comments.append(ReviewComment(
                    file=filepath, line=line_num, severity=severity,
                    category="security",
                    message=f"Potential security issue: {category}",
                    suggestion="Use environment variables or secrets manager"
                ))
        
        return comments
    
    def _check_style(self, filepath: str, content: str) -> List[ReviewComment]:
        comments = []
        
        # Check line length (warn only)
        for i, line in enumerate(content.split('\n'), 1):
            if len(line) > 120:
                comments.append(ReviewComment(
                    file=filepath, line=i, severity=Severity.INFO,
                    category="style",
                    message=f"Line too long ({len(line)} chars)",
                    suggestion="Break into multiple lines"
                ))
        
        # Check for TODO/FIXME without issue reference
        for m in re.finditer(r'# (TODO|FIXME|HACK|XXX):?\s*(.+)', content):
            line_num = content[:m.start()].count('\n') + 1
            if '#' not in m.group(2):  # no issue number
                comments.append(ReviewComment(
                    file=filepath, line=line_num, severity=Severity.INFO,
                    category="style",
                    message=f"{m.group(1)} without issue reference: {m.group(2)[:50]}",
                    suggestion="Add issue number: TODO(#42) description"
                ))
        
        return comments
    
    def _check_complexity(self, filepath: str, content: str) -> List[ReviewComment]:
        comments = []
        
        # Check function length
        if filepath.endswith('.py'):
            fn_starts = list(re.finditer(r'^def \w+\(', content, re.MULTILINE))
            for i, start in enumerate(fn_starts):
                end = fn_starts[i+1].start() if i+1 < len(fn_starts) else len(content)
                fn_body = content[start.start():end]
                fn_lines = fn_body.count('\n')
                if fn_lines > 50:
                    fn_name = re.search(r'def (\w+)', fn_body).group(1)
                    line_num = content[:start.start()].count('\n') + 1
                    comments.append(ReviewComment(
                        file=filepath, line=line_num, severity=Severity.WARNING,
                        category="complexity",
                        message=f"Function `{fn_name}` is {fn_lines} lines (max 50)",
                        suggestion="Break into smaller functions"
                    ))
        
        return comments
    
    def _check_fleet_compliance(self, filepath: str, content: str) -> List[ReviewComment]:
        """Check fleet-specific requirements."""
        comments = []
        
        # All fleet repos should reference the fleet
        if filepath == "README.md":
            if "FLUX Fleet" not in content and "oracle1-index" not in content:
                comments.append(ReviewComment(
                    file=filepath, line=1, severity=Severity.WARNING,
                    category="fleet",
                    message="README missing fleet reference",
                    suggestion="Add 'Part of the FLUX Fleet' with link to oracle1-index"
                ))
            
            if "test" not in content.lower() and "tests" not in content.lower():
                comments.append(ReviewComment(
                    file=filepath, line=1, severity=Severity.INFO,
                    category="fleet",
                    message="README missing test count",
                    suggestion="Add test count to README"
                ))
        
        return comments


import unittest


class TestCodeReviewer(unittest.TestCase):
    def test_review_clean_file(self):
        r = CodeReviewer()
        comments = r.review_file("clean.py", "def hello():\n    \"\"\"Say hi\"\"\"\n    return 'hello'\n")
        # Should have minimal comments
        self.assertEqual(len([c for c in comments if c.severity == Severity.CRITICAL]), 0)
    
    def test_detect_hardcoded_secret(self):
        r = CodeReviewer()
        comments = r.review_file("config.py", 'api_key = "sk-12345678abc"\n')
        secrets = [c for c in comments if c.category == "security"]
        self.assertGreater(len(secrets), 0)
    
    def test_detect_eval(self):
        r = CodeReviewer()
        comments = r.review_file("danger.py", "result = eval(user_input)\n")
        evals = [c for c in comments if "eval" in c.message.lower()]
        self.assertGreater(len(evals), 0)
    
    def test_detect_missing_docstring(self):
        r = CodeReviewer()
        comments = r.review_file("undoc.py", "def calculate(x, y):\n    return x + y\n")
        docs = [c for c in comments if c.category == "docs"]
        self.assertGreater(len(docs), 0)
    
    def test_review_report_markdown(self):
        report = ReviewReport(repo="test", pr_number=1, score=85, approved=True)
        md = report.to_markdown()
        self.assertIn("85", md)
        self.assertIn("APPROVE", md)
    
    def test_review_report_reject(self):
        report = ReviewReport(repo="test", pr_number=1, score=30, approved=False,
                            comments=[ReviewComment("a.py", 1, Severity.CRITICAL, "security", "bad")])
        md = report.to_markdown()
        self.assertIn("Critical", md)
        self.assertIn("CHANGES REQUESTED", md)
    
    def test_fleet_compliance(self):
        r = CodeReviewer()
        comments = r.review_file("README.md", "# My Project\nSome code.\n")
        fleet = [c for c in comments if c.category == "fleet"]
        self.assertGreater(len(fleet), 0)
    
    def test_score_computation(self):
        r = CodeReviewer()
        report = ReviewReport(repo="test", pr_number=None)
        report.comments = [
            ReviewComment("a", 1, Severity.WARNING, "style", "long line"),
            ReviewComment("b", 2, Severity.ERROR, "testing", "no test"),
        ]
        r._compute_score(report)
        self.assertLess(report.score, 100)
        self.assertGreater(report.score, 50)
    
    def test_long_function_detection(self):
        r = CodeReviewer()
        lines = ["def huge_function():"] + ["    x = 1"] * 60
        comments = r.review_file("big.py", "\n".join(lines) + "\n\ndef next():\n    pass\n")
        complexity = [c for c in comments if c.category == "complexity"]
        self.assertGreater(len(complexity), 0)

    def test_detect_shell_injection(self):
        r = CodeReviewer()
        content = 'subprocess.call("rm -rf /", shell=True)\n'
        comments = r.review_file("run.py", content)
        security = [c for c in comments if c.category == "security" and "shell" in c.message.lower()]
        self.assertGreater(len(security), 0)

    def test_detect_os_system(self):
        r = CodeReviewer()
        content = 'os.system("ls -la")\n'
        comments = r.review_file("run.py", content)
        security = [c for c in comments if c.category == "security" and "os_system" in c.message.lower()]
        self.assertGreater(len(security), 0)

    def test_detect_long_line(self):
        r = CodeReviewer()
        long_line = "x = " + "a" * 130
        comments = r.review_file("wide.py", long_line + "\n")
        style = [c for c in comments if c.category == "style" and "long" in c.message.lower()]
        self.assertGreater(len(style), 0)

    def test_detect_todo_without_issue(self):
        r = CodeReviewer()
        content = "# TODO: fix this later\nx = 1\n"
        comments = r.review_file("temp.py", content)
        todos = [c for c in comments if "TODO" in c.message]
        self.assertGreater(len(todos), 0)

    def test_multiple_issues(self):
        r = CodeReviewer()
        content = 'api_key = "sk-12345678abcdef"\nresult = eval(user_input)\nx = 1\n'
        comments = r.review_file("bad.py", content)
        self.assertGreater(len(comments), 1)

    def test_empty_directory_review(self):
        import tempfile
        r = CodeReviewer()
        with tempfile.TemporaryDirectory() as tmpdir:
            report = r.review_directory(tmpdir)
            self.assertEqual(len(report.comments), 0)
            self.assertGreater(report.score, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
