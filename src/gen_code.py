#!/usr/bin/env python3
"""
Mechanic Skill: gen_code — Write code from specifications.

Takes a spec (natural language description) and generates
Python/Rust/Go code that implements it. Uses template-based
generation with FLUX vocabulary patterns.
"""
import os
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum


class Language(Enum):
    PYTHON = "python"
    RUST = "rust"
    GO = "go"
    TYPESCRIPT = "typescript"


@dataclass
class CodeSpec:
    """A specification for code generation."""
    name: str
    description: str
    language: Language
    functions: List[Dict] = field(default_factory=list)
    classes: List[Dict] = field(default_factory=list)
    test_cases: List[Dict] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    
    def to_prompt(self) -> str:
        parts = [f"Generate {self.language.value} code for: {self.name}",
                 f"Description: {self.description}"]
        if self.functions:
            parts.append("Functions:")
            for fn in self.functions:
                parts.append(f"  - {fn.get('name','?')}({fn.get('params','')}): {fn.get('returns','void')}")
        if self.test_cases:
            parts.append("Test cases:")
            for tc in self.test_cases:
                parts.append(f"  - {tc}")
        return "\n".join(parts)


class CodeGenerator:
    """Generate code from specifications."""
    
    # Templates for common patterns
    TEMPLATES = {
        Language.PYTHON: {
            "module": "{imports}\n\n{body}\n",
            "class": "class {name}:\n{docstring}\n{methods}\n",
            "function": "def {name}({params}):\n    \"\"\"{doc}\"\"\"\n    {body}\n",
            "test_class": "import unittest\n\n\nclass Test{subject}(unittest.TestCase):\n{methods}\n",
            "test_method": "    def test_{name}(self):\n        {body}\n",
            "dataclass": "@dataclass\nclass {name}:\n{fields}\n",
        },
        Language.RUST: {
            "module": "{imports}\n\n{body}\n",
            "struct": "#[derive(Debug, Clone)]\npub struct {name} {{\n{fields}\n}}\n",
            "impl": "impl {name} {{\n{methods}\n}}\n",
            "function": "pub fn {name}({params}) -> {returns} {{\n    {body}\n}}\n",
            "test": "#[cfg(test)]\nmod tests {{\n    use super::*;\n{methods}\n}}\n",
            "test_method": "    #[test]\n    fn test_{name}() {{\n        {body}\n    }}\n",
        },
        Language.GO: {
            "module": "package {package}\n\n{imports}\n\n{body}\n",
            "struct": "type {name} struct {{\n{fields}\n}}\n",
            "function": "func {name}({params}) {returns} {{\n{body}\n}}\n",
            "test": "package {package}_test\n\n{imports}\n\n{methods}\n",
            "test_method": "func Test{name}(t *testing.T) {{\n{body}\n}}\n",
        },
    }
    
    def generate(self, spec: CodeSpec) -> str:
        """Generate code from a specification."""
        templates = self.TEMPLATES.get(spec.language, self.TEMPLATES[Language.PYTHON])
        
        if spec.language == Language.PYTHON:
            return self._gen_python(spec, templates)
        elif spec.language == Language.RUST:
            return self._gen_rust(spec, templates)
        elif spec.language == Language.GO:
            return self._gen_go(spec, templates)
        return ""
    
    def generate_tests(self, spec: CodeSpec) -> str:
        """Generate test file for a spec."""
        if spec.language == Language.PYTHON:
            return self._gen_python_tests(spec)
        elif spec.language == Language.RUST:
            return self._gen_rust_tests(spec)
        elif spec.language == Language.GO:
            return self._gen_go_tests(spec)
        return ""
    
    def _gen_python(self, spec: CodeSpec, t: Dict) -> str:
        imports = list(spec.imports)
        if spec.classes:
            imports.append("from dataclasses import dataclass, field")
        imports_str = "\n".join(f"import {i}" for i in imports) if imports else ""
        
        body_parts = []
        for cls in spec.classes:
            fields_str = "\n".join(f"    {f['name']}: {f['type']}" for f in cls.get("fields", []))
            body_parts.append(f"@dataclass\nclass {cls['name']}:\n{fields_str}\n")
        
        for fn in spec.functions:
            params = fn.get("params", "")
            returns = fn.get("returns", "")
            body = fn.get("body", "pass")
            doc = fn.get("doc", fn.get("name", ""))
            ret_annotation = f" -> {returns}" if returns else ""
            body_parts.append(f"def {fn['name']}({params}){ret_annotation}:\n    \"\"\"{doc}\"\"\"\n    {body}\n")
        
        body = "\n\n".join(body_parts)
        return f'"""{spec.description}"""\n\n{imports_str}\n\n{body}\n'
    
    def _gen_python_tests(self, spec: CodeSpec) -> str:
        methods = []
        for i, tc in enumerate(spec.test_cases):
            name = tc.get("name", f"case_{i}")
            body = tc.get("body", "assert True")
            methods.append(f"    def test_{name}(self):\n        {body}\n")
        
        subject = spec.name.replace("_", " ").title().replace(" ", "")
        return f"import unittest\nfrom {spec.name} import *\n\n\nclass Test{subject}(unittest.TestCase):\n{''.join(methods)}\n\nif __name__ == '__main__':\n    unittest.main()\n"
    
    def _gen_rust(self, spec: CodeSpec, t: Dict) -> str:
        parts = []
        for cls in spec.classes:
            fields = "\n".join(f"    pub {f['name']}: {f['type']}," for f in cls.get("fields", []))
            parts.append(f"#[derive(Debug, Clone)]\npub struct {cls['name']} {{\n{fields}\n}}\n")
        
        for fn in spec.functions:
            params = fn.get("params", "")
            returns = fn.get("returns", "()")
            body = fn.get("body", "todo!()")
            parts.append(f"pub fn {fn['name']}({params}) -> {returns} {{\n    {body}\n}}\n")
        
        return "\n\n".join(parts)
    
    def _gen_rust_tests(self, spec: CodeSpec) -> str:
        methods = []
        for i, tc in enumerate(spec.test_cases):
            name = tc.get("name", f"case_{i}")
            body = tc.get("body", "assert!(true);")
            methods.append(f"    #[test]\n    fn test_{name}() {{\n        {body}\n    }}\n")
        
        return f"#[cfg(test)]\nmod tests {{\n    use super::*;\n{''.join(methods)}}}\n"
    
    def _gen_go(self, spec: CodeSpec, t: Dict) -> str:
        parts = [f"package {spec.name}"]
        parts.append("")
        for cls in spec.classes:
            fields = "\n".join(f"    {f['name'].title()} {f['type']}" for f in cls.get("fields", []))
            parts.append(f"type {cls['name']} struct {{\n{fields}\n}}\n")
        
        for fn in spec.functions:
            params = fn.get("params", "")
            returns = fn.get("returns", "")
            body = fn.get("body", "")
            ret = f" {returns}" if returns else ""
            parts.append(f"func {fn['name']}({params}){ret} {{\n{body}\n}}\n")
        
        return "\n\n".join(parts)
    
    def _gen_go_tests(self, spec: CodeSpec) -> str:
        methods = []
        for i, tc in enumerate(spec.test_cases):
            name = tc.get("name", f"Case{i}")
            body = tc.get("body", "")
            methods.append(f"func Test{name}(t *testing.T) {{\n{body}\n}}\n")
        
        return f"package {spec.name}_test\n\nimport \"testing\"\n\n{''.join(methods)}"
    
    def generate_from_description(self, name: str, description: str,
                                   language: Language = Language.PYTHON) -> Tuple[str, str]:
        """Generate code + tests from a natural language description.
        
        This is the main entry point for code generation.
        Returns (source_code, test_code).
        """
        spec = self._parse_description(name, description, language)
        source = self.generate(spec)
        tests = self.generate_tests(spec)
        return source, tests
    
    def _parse_description(self, name: str, desc: str, 
                           lang: Language) -> CodeSpec:
        """Parse a natural language description into a CodeSpec."""
        spec = CodeSpec(
            name=name,
            description=desc,
            language=lang,
        )
        
        # Extract function-like patterns from description
        # "calculate X from Y" → function calculate_x(y)
        fn_patterns = [
            r"calculate (\w+) from (\w+)",
            r"compute the (\w+) of (\w+)",
            r"find the (\w+) between (\w+) and (\w+)",
            r"check if (\w+) is (\w+)",
            r"convert (\w+) to (\w+)",
            r"validate (\w+)",
            r"parse (\w+) and extract (\w+)",
        ]
        
        for pat in fn_patterns:
            for m in re.finditer(pat, desc, re.IGNORECASE):
                fn_name = re.sub(r'[^a-z0-9]', '_', m.group(0).lower())
                spec.functions.append({
                    "name": fn_name,
                    "doc": m.group(0),
                    "params": "",
                    "returns": "",
                    "body": "pass" if lang == Language.PYTHON else "todo!()",
                })
        
        # If no functions found, create a default one
        if not spec.functions:
            spec.functions.append({
                "name": name.replace("-", "_"),
                "doc": desc,
                "params": "",
                "returns": "",
                "body": "pass" if lang == Language.PYTHON else "todo!()",
            })
        
        # Generate basic test cases
        spec.test_cases = [
            {"name": "basic", "body": "# TODO: implement test"},
            {"name": "edge_case", "body": "# TODO: test edge cases"},
        ]
        
        return spec


from typing import Tuple
import unittest


class TestCodeGenerator(unittest.TestCase):
    def test_python_generation(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="calculator",
            description="Simple calculator",
            language=Language.PYTHON,
            functions=[{"name": "add", "params": "a, b", "returns": "int", "body": "return a + b", "doc": "Add two numbers"}],
        )
        code = gen.generate(spec)
        self.assertIn("def add", code)
        self.assertIn("return a + b", code)
    
    def test_rust_generation(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="trust",
            description="Trust engine",
            language=Language.RUST,
            functions=[{"name": "trust_score", "params": "agent: &str", "returns": "f64", "body": "0.5"}],
        )
        code = gen.generate(spec)
        self.assertIn("pub fn trust_score", code)
        self.assertIn("f64", code)
    
    def test_go_generation(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="fleet",
            description="Fleet coordinator",
            language=Language.GO,
            functions=[{"name": "Coordinate", "params": "agents []string", "returns": "error", "body": "return nil"}],
        )
        code = gen.generate(spec)
        self.assertIn("func Coordinate", code)
    
    def test_python_tests(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="math",
            description="Math functions",
            language=Language.PYTHON,
            test_cases=[{"name": "addition", "body": "self.assertEqual(add(1,2), 3)"}],
        )
        tests = gen.generate_tests(spec)
        self.assertIn("unittest", tests)
        self.assertIn("test_addition", tests)
    
    def test_generate_from_description(self):
        gen = CodeGenerator()
        source, tests = gen.generate_from_description(
            "stats", "calculate mean from numbers", Language.PYTHON
        )
        self.assertIn("calculate_mean", source)
        self.assertIn("unittest", tests)
    
    def test_rust_tests(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="trust",
            description="",
            language=Language.RUST,
            test_cases=[{"name": "initial", "body": "assert!(true);"}],
        )
        tests = gen.generate_tests(spec)
        self.assertIn("#[test]", tests)
    
    def test_spec_to_prompt(self):
        spec = CodeSpec(name="vm", description="FLUX VM", language=Language.PYTHON,
                       functions=[{"name": "execute", "params": "bytecode", "returns": "Result"}])
        prompt = spec.to_prompt()
        self.assertIn("execute", prompt)
    
    def test_dataclass_generation(self):
        gen = CodeGenerator()
        spec = CodeSpec(
            name="agent",
            description="Agent entity",
            language=Language.PYTHON,
            classes=[{"name": "Agent", "fields": [
                {"name": "name", "type": "str"},
                {"name": "trust", "type": "float"},
            ]}],
        )
        code = gen.generate(spec)
        self.assertIn("@dataclass", code)
        self.assertIn("name: str", code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
