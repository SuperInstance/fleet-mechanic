"""Comprehensive tests for Fleet Mechanic."""
import unittest
import tempfile
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mechanic import (
    TaskType, TaskResult, MechanicTask, RepoHealth, FleetMechanic,
    mechanic_flux_program,
)
from review import (
    Severity, ReviewComment, ReviewReport, CodeReviewer,
)
from gen_code import (
    Language, CodeSpec, CodeGenerator,
)
from fix_code import (
    DiagnosticFailure, CodeFix, DiagnosticFailureParser, CodeFixer,
    MechanicCodeFixer,
)


# ========== Mechanic Core Tests ==========

class TestTaskType(unittest.TestCase):
    def test_all_task_types(self):
        types = [TaskType.FIX_TESTS, TaskType.GEN_DOCS, TaskType.GEN_CODE,
                 TaskType.GEN_CI, TaskType.REPO_HEALTH, TaskType.SYNC, TaskType.REVIEW]
        self.assertEqual(len(types), 7)

    def test_task_type_values(self):
        self.assertEqual(TaskType.FIX_TESTS.value, "fix_tests")
        self.assertEqual(TaskType.GEN_DOCS.value, "gen_docs")
        self.assertEqual(TaskType.GEN_CODE.value, "gen_code")
        self.assertEqual(TaskType.GEN_CI.value, "gen_ci")
        self.assertEqual(TaskType.REPO_HEALTH.value, "repo_health")
        self.assertEqual(TaskType.SYNC.value, "sync")
        self.assertEqual(TaskType.REVIEW.value, "review")


class TestTaskResult(unittest.TestCase):
    def test_all_results(self):
        results = [TaskResult.SUCCESS, TaskResult.PARTIAL, TaskResult.FAILED, TaskResult.BLOCKED]
        self.assertEqual(len(results), 4)

    def test_result_values(self):
        self.assertEqual(TaskResult.SUCCESS.value, "success")
        self.assertEqual(TaskResult.PARTIAL.value, "partial")
        self.assertEqual(TaskResult.FAILED.value, "failed")
        self.assertEqual(TaskResult.BLOCKED.value, "blocked")


class TestMechanicTask(unittest.TestCase):
    def test_default_values(self):
        t = MechanicTask(id="T-001", task_type=TaskType.FIX_TESTS, target_repo="test")
        self.assertIsNone(t.result)
        self.assertEqual(t.diagnosis, "")
        self.assertEqual(t.commits_made, 0)
        self.assertEqual(t.tests_fixed, 0)
        self.assertEqual(t.files_changed, 0)
        self.assertEqual(t.target_branch, "main")
        self.assertEqual(t.params, {})

    def test_to_dict_keys(self):
        t = MechanicTask(id="T-002", task_type=TaskType.GEN_DOCS, target_repo="repo")
        d = t.to_dict()
        expected_keys = {"id", "type", "repo", "branch", "description", "result",
                         "diagnosis", "commits", "tests_fixed", "files_changed"}
        self.assertEqual(set(d.keys()), expected_keys)

    def test_to_dict_with_none_result(self):
        t = MechanicTask(id="T-003", task_type=TaskType.REVIEW, target_repo="r")
        d = t.to_dict()
        self.assertIsNone(d["result"])


class TestRepoHealth(unittest.TestCase):
    def test_perfect_health(self):
        h = RepoHealth(
            repo="perfect", has_readme=True, has_gitignore=True,
            has_ci=True, has_tests=True, test_count=10, test_pass=10,
        )
        h.compute_score()
        self.assertEqual(h.health_score, 1.0)

    def test_zero_health(self):
        h = RepoHealth(repo="empty")
        h.compute_score()
        self.assertEqual(h.health_score, 0.0)

    def test_partial_health(self):
        h = RepoHealth(repo="partial", has_readme=True)
        h.compute_score()
        self.assertGreater(h.health_score, 0.0)
        self.assertLess(h.health_score, 1.0)

    def test_health_with_failing_tests(self):
        h = RepoHealth(
            repo="failing", has_readme=True, has_gitignore=True,
            has_ci=True, has_tests=True, test_count=10, test_pass=5,
        )
        h.compute_score()
        self.assertGreater(h.health_score, 0.0)
        self.assertLess(h.health_score, 1.0)

    def test_health_no_tests_with_flag(self):
        h = RepoHealth(
            repo="no_tests", has_readme=True, has_gitignore=True,
            has_ci=True, has_tests=True, test_count=0,
        )
        h.compute_score()
        self.assertEqual(h.health_score, 0.7)

    def test_health_with_language(self):
        h = RepoHealth(repo="lang", language="Python")
        self.assertEqual(h.language, "Python")

    def test_markdown_output(self):
        h = RepoHealth(repo="md-test", has_readme=True, has_tests=True,
                       test_count=5, test_pass=3, language="Go")
        md = h.to_markdown()
        self.assertIn("md-test", md)
        self.assertIn("Go", md)
        self.assertIn("3/5", md)

    def test_health_score_capped(self):
        h = RepoHealth(
            repo="over", has_readme=True, has_gitignore=True,
            has_ci=True, has_tests=True, test_count=10, test_pass=10,
        )
        h.compute_score()
        self.assertLessEqual(h.health_score, 1.0)

    def test_size_kb(self):
        h = RepoHealth(repo="big", size_kb=1024)
        self.assertEqual(h.size_kb, 1024)


class TestFleetMechanicInit(unittest.TestCase):
    def test_init_defaults(self):
        m = FleetMechanic("fake-token")
        self.assertEqual(m.token, "fake-token")
        self.assertEqual(m.org, "SuperInstance")
        self.assertEqual(m.completed_tasks, [])
        self.assertEqual(m.health_reports, {})
        self.assertTrue(os.path.exists(m.work_dir))

    def test_init_custom_org(self):
        m = FleetMechanic("token", org="CustomOrg")
        self.assertEqual(m.org, "CustomOrg")

    def test_run_command(self):
        m = FleetMechanic("fake-token")
        code, out = m._run("echo 'hello world'")
        self.assertEqual(code, 0)
        self.assertIn("hello world", out)

    def test_run_invalid_command(self):
        m = FleetMechanic("fake-token")
        code, out = m._run("false")
        self.assertNotEqual(code, 0)

    def test_detect_language_python(self):
        m = FleetMechanic("fake-token")
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("")
            self.assertEqual(m._detect_language(tmpdir), "python")

    def test_detect_language_rust(self):
        m = FleetMechanic("fake-token")
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "Cargo.toml"), "w") as f:
                f.write("")
            self.assertEqual(m._detect_language(tmpdir), "rust")

    def test_detect_language_go(self):
        m = FleetMechanic("fake-token")
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "go.mod"), "w") as f:
                f.write("")
            self.assertEqual(m._detect_language(tmpdir), "go")

    def test_detect_language_node(self):
        m = FleetMechanic("fake-token")
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "package.json"), "w") as f:
                f.write("{}")
            self.assertEqual(m._detect_language(tmpdir), "node")

    def test_detect_language_c(self):
        m = FleetMechanic("fake-token")
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "Makefile"), "w") as f:
                f.write("")
            self.assertEqual(m._detect_language(tmpdir), "c")

    def test_detect_language_unknown(self):
        m = FleetMechanic("fake-token")
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(m._detect_language(tmpdir), "unknown")

    def test_gitignore_all_languages(self):
        m = FleetMechanic("fake-token")
        for lang in ["python", "rust", "go", "node", "c", "unknown"]:
            gi = m._gen_gitignore(lang)
            self.assertGreater(len(gi), 0)

    def test_ci_python(self):
        m = FleetMechanic("fake-token")
        ci = m._gen_ci("python")
        self.assertIn("pytest", ci)
        self.assertIn("setup-python", ci)

    def test_ci_rust(self):
        m = FleetMechanic("fake-token")
        ci = m._gen_ci("rust")
        self.assertIn("cargo test", ci)

    def test_ci_go(self):
        m = FleetMechanic("fake-token")
        ci = m._gen_ci("go")
        self.assertIn("go test", ci)

    def test_ci_no_template(self):
        m = FleetMechanic("fake-token")
        self.assertIsNone(m._gen_ci("node"))
        self.assertIsNone(m._gen_ci("unknown"))

    def test_flux_program_structure(self):
        bc = mechanic_flux_program()
        self.assertGreater(len(bc), 20)
        self.assertEqual(bc[0], 0x18)
        self.assertIn(0x00, bc)
        self.assertIn(0x09, bc)
        self.assertIn(0x08, bc)


# ========== Review Module Tests ==========

class TestSeverity(unittest.TestCase):
    def test_all_severities(self):
        sevs = [Severity.INFO, Severity.WARNING, Severity.ERROR, Severity.CRITICAL]
        self.assertEqual(len(sevs), 4)

    def test_severity_values(self):
        self.assertEqual(Severity.INFO.value, "info")
        self.assertEqual(Severity.WARNING.value, "warning")
        self.assertEqual(Severity.ERROR.value, "error")
        self.assertEqual(Severity.CRITICAL.value, "critical")


class TestReviewComment(unittest.TestCase):
    def test_comment_creation(self):
        c = ReviewComment(
            file="test.py", line=10, severity=Severity.ERROR,
            category="testing", message="No tests", suggestion="Add tests"
        )
        self.assertEqual(c.file, "test.py")
        self.assertEqual(c.line, 10)
        self.assertEqual(c.severity, Severity.ERROR)

    def test_comment_default_suggestion(self):
        c = ReviewComment(file="a.py", line=1, severity=Severity.INFO,
                          category="style", message="Long line")
        self.assertEqual(c.suggestion, "")


class TestReviewReport(unittest.TestCase):
    def test_empty_report(self):
        r = ReviewReport(repo="test", pr_number=None)
        self.assertEqual(r.comments, [])
        self.assertFalse(r.approved)

    def test_approved_report(self):
        r = ReviewReport(repo="test", pr_number=None, score=85, approved=True)
        self.assertTrue(r.approved)

    def test_markdown_approved(self):
        r = ReviewReport(repo="test", pr_number=42, score=90, approved=True)
        md = r.to_markdown()
        self.assertIn("APPROVE", md)
        self.assertIn("90", md)
        self.assertIn("PR #42", md)

    def test_markdown_rejected(self):
        r = ReviewReport(repo="test", pr_number=None, score=30, approved=False,
                         comments=[ReviewComment("a.py", 1, Severity.CRITICAL, "sec", "bad")])
        md = r.to_markdown()
        self.assertIn("CHANGES REQUESTED", md)
        self.assertIn("Critical", md)

    def test_markdown_no_comments(self):
        r = ReviewReport(repo="test", pr_number=None, score=100, approved=True)
        md = r.to_markdown()
        self.assertIn("No issues found", md)

    def test_markdown_grouped_by_severity(self):
        r = ReviewReport(repo="test", pr_number=1,
                         comments=[
                             ReviewComment("a.py", 1, Severity.INFO, "style", "info"),
                             ReviewComment("b.py", 2, Severity.CRITICAL, "sec", "crit"),
                             ReviewComment("c.py", 3, Severity.WARNING, "comp", "warn"),
                         ])
        md = r.to_markdown()
        self.assertIn("Info", md)
        self.assertIn("Critical", md)
        self.assertIn("Warning", md)


class TestCodeReviewer(unittest.TestCase):
    def test_clean_python_file(self):
        r = CodeReviewer()
        comments = r.review_file("clean.py", 'def hello():\n    """Say hi."""\n    return "hi"\n')
        critical = [c for c in comments if c.severity == Severity.CRITICAL]
        self.assertEqual(len(critical), 0)

    def test_detect_api_key(self):
        r = CodeReviewer()
        comments = r.review_file("cfg.py", 'api_key = "sk-12345678abcdef"\n')
        security = [c for c in comments if c.category == "security"]
        self.assertGreater(len(security), 0)

    def test_detect_password(self):
        r = CodeReviewer()
        comments = r.review_file("cfg.py", 'password = "supersecret12345"\n')
        security = [c for c in comments if c.category == "security"]
        self.assertGreater(len(security), 0)

    def test_detect_eval(self):
        r = CodeReviewer()
        comments = r.review_file("danger.py", "result = eval(input)\n")
        evals = [c for c in comments if "eval" in c.message.lower()]
        self.assertGreater(len(evals), 0)

    def test_detect_exec(self):
        r = CodeReviewer()
        comments = r.review_file("danger.py", "exec(code)\n")
        execs = [c for c in comments if "exec" in c.message.lower()]
        self.assertGreater(len(execs), 0)

    def test_detect_missing_docstring(self):
        r = CodeReviewer()
        comments = r.review_file("undoc.py", "def calc(x, y):\n    return x + y\n")
        docs = [c for c in comments if c.category == "docs"]
        self.assertGreater(len(docs), 0)

    def test_detect_long_line(self):
        r = CodeReviewer()
        long_line = "x = " + "a" * 130
        comments = r.review_file("wide.py", long_line + "\n")
        style = [c for c in comments if "long" in c.message.lower()]
        self.assertGreater(len(style), 0)

    def test_detect_todo(self):
        r = CodeReviewer()
        comments = r.review_file("temp.py", "# TODO: fix this\nx = 1\n")
        todos = [c for c in comments if "TODO" in c.message]
        self.assertGreater(len(todos), 0)

    def test_detect_fixme(self):
        r = CodeReviewer()
        comments = r.review_file("temp.py", "# FIXME: broken\nx = 1\n")
        fixmes = [c for c in comments if "FIXME" in c.message]
        self.assertGreater(len(fixmes), 0)

    def test_detect_complex_function(self):
        r = CodeReviewer()
        lines = ["def huge():"] + ["    x = 1"] * 60 + ["\ndef next():\n    pass\n"]
        comments = r.review_file("big.py", "\n".join(lines))
        complexity = [c for c in comments if c.category == "complexity"]
        self.assertGreater(len(complexity), 0)

    def test_detect_shell_injection(self):
        r = CodeReviewer()
        comments = r.review_file("run.py", 'subprocess.call("rm -rf /", shell=True)\n')
        security = [c for c in comments if "shell" in c.message.lower()]
        self.assertGreater(len(security), 0)

    def test_detect_os_system(self):
        r = CodeReviewer()
        comments = r.review_file("run.py", 'os.system("ls")\n')
        security = [c for c in comments if "os_system" in c.message.lower()]
        self.assertGreater(len(security), 0)

    def test_fleet_compliance_readme(self):
        r = CodeReviewer()
        comments = r.review_file("README.md", "# My Project\nSome code.\n")
        fleet = [c for c in comments if c.category == "fleet"]
        self.assertGreater(len(fleet), 0)

    def test_fleet_compliant_readme(self):
        r = CodeReviewer()
        comments = r.review_file("README.md", "# My Project\nPart of the FLUX Fleet.\nTests: 42\n")
        fleet = [c for c in comments if c.category == "fleet" and "reference" in c.message.lower()]
        self.assertEqual(len(fleet), 0)

    def test_private_function_no_docstring_warning(self):
        r = CodeReviewer()
        comments = r.review_file("priv.py", "def _internal():\n    pass\n")
        docs = [c for c in comments if c.category == "docs"]
        self.assertEqual(len(docs), 0)

    def test_score_computation_clean(self):
        r = CodeReviewer()
        report = ReviewReport(repo="clean", pr_number=None)
        r._compute_score(report)
        self.assertEqual(report.score, 100.0)
        self.assertTrue(report.approved)

    def test_score_computation_critical(self):
        r = CodeReviewer()
        report = ReviewReport(repo="bad", pr_number=None,
                              comments=[ReviewComment("a", 1, Severity.CRITICAL, "sec", "bad")])
        r._compute_score(report)
        self.assertEqual(report.score, 80.0)
        self.assertFalse(report.approved)

    def test_score_floor(self):
        r = CodeReviewer()
        comments = [ReviewComment(f"f{i}", 1, Severity.CRITICAL, "sec", "bad") for i in range(10)]
        report = ReviewReport(repo="terrible", pr_number=None, comments=comments)
        r._compute_score(report)
        self.assertGreaterEqual(report.score, 0.0)

    def test_multiple_security_issues(self):
        r = CodeReviewer()
        content = 'api_key = "sk-longsecretkey123"\npassword = "mypassword"\neval(x)\nexec(y)\n'
        comments = r.review_file("bad.py", content)
        security = [c for c in comments if c.category == "security"]
        self.assertGreater(len(security), 2)


# ========== Code Generator Tests ==========

class TestLanguage(unittest.TestCase):
    def test_all_languages(self):
        langs = [Language.PYTHON, Language.RUST, Language.GO, Language.TYPESCRIPT]
        self.assertEqual(len(langs), 4)


class TestCodeSpec(unittest.TestCase):
    def test_spec_defaults(self):
        spec = CodeSpec(name="test", description="test desc", language=Language.PYTHON)
        self.assertEqual(spec.functions, [])
        self.assertEqual(spec.classes, [])
        self.assertEqual(spec.test_cases, [])
        self.assertEqual(spec.imports, [])

    def test_spec_to_prompt(self):
        spec = CodeSpec(
            name="calc", description="Calculator",
            language=Language.PYTHON,
            functions=[{"name": "add", "params": "a, b"}],
        )
        prompt = spec.to_prompt()
        self.assertIn("Calculator", prompt)
        self.assertIn("add", prompt)


class TestCodeGenerator(unittest.TestCase):
    def test_python_function(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="calc", description="Calculator", language=Language.PYTHON,
            functions=[{"name": "add", "params": "a, b", "returns": "int",
                         "body": "return a + b", "doc": "Add numbers"}],
        )
        code = gen.generate(spec)
        self.assertIn("def add", code)
        self.assertIn("return a + b", code)

    def test_python_with_imports(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="math", description="Math utils", language=Language.PYTHON,
            functions=[{"name": "sqrt", "params": "x"}],
            imports=["math", "json"],
        )
        code = gen.generate(spec)
        self.assertIn("import math", code)
        self.assertIn("import json", code)

    def test_rust_function(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="trust", description="Trust", language=Language.RUST,
            functions=[{"name": "score", "params": "agent: &str", "returns": "f64", "body": "0.5"}],
        )
        code = gen.generate(spec)
        self.assertIn("pub fn score", code)
        self.assertIn("f64", code)

    def test_rust_struct(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="models", description="Models", language=Language.RUST,
            classes=[{"name": "Agent", "fields": [
                {"name": "id", "type": "u64"}, {"name": "name", "type": "String"},
            ]}],
        )
        code = gen.generate(spec)
        self.assertIn("pub struct Agent", code)

    def test_go_function(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="fleet", description="Fleet", language=Language.GO,
            functions=[{"name": "Run", "params": "agents []string", "returns": "error", "body": "return nil"}],
        )
        code = gen.generate(spec)
        self.assertIn("func Run", code)
        self.assertIn("package fleet", code)

    def test_python_tests(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="math", description="Math", language=Language.PYTHON,
            test_cases=[
                {"name": "add_basic", "body": "self.assertEqual(add(1,2), 3)"},
                {"name": "add_negative", "body": "self.assertEqual(add(-1,-1), -2)"},
            ],
        )
        tests = gen.generate_tests(spec)
        self.assertIn("unittest", tests)
        self.assertIn("test_add_basic", tests)
        self.assertIn("test_add_negative", tests)

    def test_rust_tests(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="trust", description="", language=Language.RUST,
            test_cases=[{"name": "initial_score", "body": "assert_eq!(score(\"a\"), 0.5);"}],
        )
        tests = gen.generate_tests(spec)
        self.assertIn("#[cfg(test)]", tests)
        self.assertIn("#[test]", tests)

    def test_go_tests(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="handler", description="Handler", language=Language.GO,
            test_cases=[{"name": "HandleGet", "body": "// test get"}],
        )
        tests = gen.generate_tests(spec)
        self.assertIn("func TestHandleGet", tests)
        self.assertIn("testing", tests)

    def test_from_description(self):
        gen = CodeGenerator()
        source, tests = gen.generate_from_description(
            "stats", "calculate mean from numbers", Language.PYTHON
        )
        self.assertIn("calculate_mean", source)
        self.assertIn("unittest", tests)

    def test_typescript_fallback(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="app", description="App", language=Language.TYPESCRIPT,
            functions=[{"name": "run", "params": "", "body": ""}],
        )
        self.assertEqual(gen.generate(spec), "")
        self.assertEqual(gen.generate_tests(spec), "")

    def test_python_dataclass(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="models", description="Models", language=Language.PYTHON,
            classes=[{"name": "User", "fields": [
                {"name": "name", "type": "str"}, {"name": "age", "type": "int"},
            ]}],
        )
        code = gen.generate(spec)
        self.assertIn("@dataclass", code)
        self.assertIn("class User", code)

    def test_python_class_with_function(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="app", description="Application", language=Language.PYTHON,
            classes=[{"name": "Config", "fields": [{"name": "debug", "type": "bool"}]}],
            functions=[{"name": "run", "params": "config: Config", "body": "print(config.debug)"}],
        )
        code = gen.generate(spec)
        self.assertIn("class Config", code)
        self.assertIn("def run", code)


# ========== Code Fixer Tests ==========

class TestDiagnosticFailure(unittest.TestCase):
    def test_failure_creation(self):
        f = DiagnosticFailure(
            test_name="test_add", file="test_math.py", line=10,
            error_type="AssertionError", error_message="expected 5 got 3"
        )
        self.assertEqual(f.test_name, "test_add")
        self.assertEqual(f.file, "test_math.py")
        self.assertEqual(f.line, 10)
        self.assertEqual(f.suggested_fix, "")


class TestCodeFix(unittest.TestCase):
    def test_fix_creation(self):
        fix = CodeFix(
            file="math.py", line=10,
            old_code="assert x > 0.8", new_code="assert x >= 0.8",
            description="Relax assertion", confidence=0.5,
        )
        self.assertEqual(fix.confidence, 0.5)


class TestDiagnosticFailureParser(unittest.TestCase):
    def test_parse_pytest(self):
        p = DiagnosticFailureParser()
        output = 'FAILED tests/test_foo.py::test_bar - AssertionError: expected 5 got 3'
        failures = p.parse_pytest(output)
        self.assertGreater(len(failures), 0)
        self.assertEqual(failures[0].test_name, "test_bar")

    def test_parse_pytest_multiple(self):
        p = DiagnosticFailureParser()
        output = ('FAILED tests/test_a.py::test_x - AssertionError: 1 != 2\n'
                  'FAILED tests/test_b.py::test_y - TypeError: bad type')
        failures = p.parse_pytest(output)
        self.assertGreaterEqual(len(failures), 2)

    def test_parse_cargo(self):
        p = DiagnosticFailureParser()
        output = "test test_trust ... FAILED\nthread 'tests' panicked at src/lib.rs:245:5:\nassertion failed"
        failures = p.parse_cargo(output)
        self.assertGreater(len(failures), 0)

    def test_parse_go(self):
        p = DiagnosticFailureParser()
        output = "--- FAIL: TestAdd (0.00s)\n    main_test.go:15: expected 4 got 3\n--- PASS: TestSub\n"
        failures = p.parse_go(output)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].test_name, "TestAdd")

    def test_parse_go_multiple(self):
        p = DiagnosticFailureParser()
        output = "--- FAIL: TestAdd (0.00s)\n    main_test.go:10: expected 4 got 3\n--- FAIL: TestMul (0.00s)\n    main_test.go:20: expected 9 got 6\n--- PASS: TestSub\n"
        failures = p.parse_go(output)
        self.assertGreaterEqual(len(failures), 2)

    def test_parse_empty(self):
        p = DiagnosticFailureParser()
        self.assertEqual(len(p.parse_pytest("")), 0)
        self.assertEqual(len(p.parse_cargo("")), 0)
        self.assertEqual(len(p.parse_go("")), 0)


class TestCodeFixer(unittest.TestCase):
    def test_empty_failures(self):
        f = CodeFixer()
        fixes = f.suggest_fixes([], {})
        self.assertEqual(len(fixes), 0)

    def test_type_error_fix(self):
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 10, "TypeError", "expected int got float")]
        fixes = f.suggest_fixes(failures, {})
        self.assertGreater(len(fixes), 0)

    def test_attribute_fix(self):
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 5, "AttributeError", "no attribute 'count'")]
        fixes = f.suggest_fixes(failures, {})
        self.assertGreater(len(fixes), 0)

    def test_missing_import_fix(self):
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 3, "NameError",
                                        "NameError: name 'math' is not defined")]
        fixes = f.suggest_fixes(failures, {})
        self.assertGreater(len(fixes), 0)

    def test_str_int_fix(self):
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 10, "TypeError", "expected str got int")]
        fixes = f.suggest_fixes(failures, {})
        self.assertGreater(len(fixes), 0)

    def test_assertion_relax(self):
        f = CodeFixer()
        sources = {"f.py": "x = 5\nassert val > 0.8\n"}
        failures = [DiagnosticFailure("test", "f.py", 2, "AssertionError", "0.7 > 0.8 failed")]
        fixes = f._fix_assertion(failures[0], sources)
        self.assertGreater(len(fixes), 0)

    def test_assertion_relax_less_than(self):
        f = CodeFixer()
        sources = {"f.py": "x = 5\nassert val < 0.2\n"}
        failures = [DiagnosticFailure("test", "f.py", 2, "AssertionError", "0.3 < 0.2 failed")]
        fixes = f._fix_assertion(failures[0], sources)
        self.assertGreater(len(fixes), 0)

    def test_fix_patterns_count(self):
        f = CodeFixer()
        self.assertGreater(len(f.FIX_PATTERNS), 3)

    def test_confidence_range(self):
        f = CodeFixer()
        failures = [DiagnosticFailure("test", "f.py", 1, "AttributeError", "no attribute 'x'")]
        fixes = f.suggest_fixes(failures, {})
        for fix in fixes:
            self.assertGreater(fix.confidence, 0.0)
            self.assertLessEqual(fix.confidence, 1.0)


class TestMechanicCodeFixer(unittest.TestCase):
    def test_load_sources_empty(self):
        m = MechanicCodeFixer()
        sources = m.load_sources("/tmp/nonexistent-path-12345")
        self.assertEqual(len(sources), 0)

    def test_load_sources(self):
        m = MechanicCodeFixer()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "src"))
            with open(os.path.join(tmpdir, "src", "main.py"), "w") as f:
                f.write("x = 1\n")
            sources = m.load_sources(tmpdir)
            self.assertEqual(len(sources), 1)

    def test_apply_fix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.py")
            with open(filepath, "w") as f:
                f.write("x = 5\nassert x > 0.8\n")
            fix = CodeFix(
                file="test.py", line=2,
                old_code="assert x > 0.8", new_code="assert x >= 0.8",
                description="Relax", confidence=0.5,
            )
            mcf = MechanicCodeFixer()
            mcf._apply_fix(tmpdir, fix)
            with open(filepath) as f:
                content = f.read()
            self.assertIn("assert x >= 0.8", content)
            self.assertNotIn("assert x > 0.8", content)

    def test_apply_fix_nonexistent(self):
        mcf = MechanicCodeFixer()
        fix = CodeFix(file="nope.py", line=1, old_code="x", new_code="y", description="test")
        mcf._apply_fix("/tmp/nonexistent-xyz", fix)

    def test_auto_fix_no_tests(self):
        mcf = MechanicCodeFixer()
        result = mcf.auto_fix("/tmp/nonexistent-dir-xyz")
        self.assertEqual(result["remaining_failures"], 0)

    def test_diagnose_no_framework(self):
        mcf = MechanicCodeFixer()
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "README.md"), "w") as f:
                f.write("test")
            failures, output = mcf.diagnose_repo(tmpdir)
            self.assertEqual(failures, [])
            self.assertIn("No test framework", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
