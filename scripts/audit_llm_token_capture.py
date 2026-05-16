#!/usr/bin/env python3
"""Audit LLM call sites for silently dropped token usage.

The project LLM clients return 3-tuples:

    payload, input_tokens, output_tokens = gemini_client.generate_json(...)

This script catches the dangerous variants, especially ``payload, _, _ = ...``,
and checks that captured token variables are returned, costed, or surfaced in a
token-shaped dict.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CLIENT_NAMES = {"gemini_client", "openai_client"}
LLM_METHODS = {"generate_json", "generate_text"}
TOKEN_KEYWORDS = ("token", "tokens", "input", "output")
PROVIDER_KEYS = {"gemini", "openai"}

try:
    from app.services.llm_cost_utils import MODEL_PRICING
except Exception:
    MODEL_PRICING = {}


@dataclass(frozen=True)
class Finding:
    severity: str
    path: str
    line: int
    message: str

    def format(self) -> str:
        return f"[{self.severity}] {self.path}:{self.line} — {self.message}"


def _is_llm_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in LLM_METHODS:
        return False
    return isinstance(func.value, ast.Name) and func.value.id in CLIENT_NAMES


def _target_name(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _contains_name(node: ast.AST, name: str) -> bool:
    return any(isinstance(child, ast.Name) and child.id == name for child in ast.walk(node))


def _token_is_surfaced(function: ast.FunctionDef | ast.AsyncFunctionDef, token_name: str) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.Return) and node.value and _contains_name(node.value, token_name):
            return True
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if not _contains_name(value, token_name):
                    continue
                if isinstance(key, ast.Constant):
                    key_text = str(key.value).lower()
                    if any(word in key_text for word in TOKEN_KEYWORDS):
                        return True
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "compute_llm_cost":
                if any(_contains_name(arg, token_name) for arg in node.args):
                    return True
        if isinstance(node, ast.AugAssign):
            if _contains_name(node.value, token_name):
                return True
        if isinstance(node, ast.Assign):
            if _contains_name(node.value, token_name):
                for target in node.targets:
                    target_text = ast.unparse(target).lower()
                    if any(word in target_text for word in TOKEN_KEYWORDS):
                        return True
    return False


def _audit_function(
    path: Path,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign):
            continue
        if not _is_llm_call(node.value):
            continue
        line = getattr(node, "lineno", getattr(node.value, "lineno", 0))
        if not node.targets:
            findings.append(
                Finding("P0", str(path), line, "LLM call result is not assigned; token usage is lost.")
            )
            continue
        target = node.targets[0]
        if not isinstance(target, (ast.Tuple, ast.List)) or len(target.elts) < 3:
            findings.append(
                Finding("P0", str(path), line, "LLM 3-tuple is not unpacked into payload/input_tokens/output_tokens.")
            )
            continue
        input_name = _target_name(target.elts[1])
        output_name = _target_name(target.elts[2])
        if input_name in {None, "_"} or output_name in {None, "_"}:
            findings.append(
                Finding(
                    "P0",
                    str(path),
                    line,
                    "LLM token outputs are assigned to '_' and will disappear from cost reporting.",
                )
            )
            continue
        missing = [
            name
            for name in (input_name, output_name)
            if name and not _token_is_surfaced(function, name)
        ]
        if missing:
            findings.append(
                Finding(
                    "P1",
                    str(path),
                    line,
                    f"Captured token variable(s) {', '.join(missing)} are not surfaced/aggregated in this function.",
                )
            )
    return findings


def _audit_cost_calls(path: Path, tree: ast.AST) -> list[Finding]:
    findings: list[Finding] = []
    known_models = set(MODEL_PRICING)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "compute_llm_cost":
            continue
        if not node.args:
            findings.append(
                Finding("P1", str(path), getattr(node, "lineno", 0), "compute_llm_cost called without model name.")
            )
            continue
        model_arg = node.args[0]
        if isinstance(model_arg, ast.Constant):
            model_name = str(model_arg.value or "")
            if model_name.lower() in PROVIDER_KEYS:
                findings.append(
                    Finding(
                        "P1",
                        str(path),
                        getattr(node, "lineno", 0),
                        f"compute_llm_cost uses provider key '{model_name}' instead of concrete model name.",
                    )
                )
            elif known_models and model_name not in known_models:
                findings.append(
                    Finding(
                        "P1",
                        str(path),
                        getattr(node, "lineno", 0),
                        f"compute_llm_cost uses unknown model '{model_name}'.",
                    )
                )
    return findings


def audit_file(path: Path) -> list[Finding]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [Finding("P0", str(path), exc.lineno or 0, f"Python parse failed: {exc}")]
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(_audit_function(path, node))
    findings.extend(_audit_cost_calls(path, tree))
    return findings


def iter_python_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            yield path
        elif path.is_dir():
            yield from sorted(
                p
                for p in path.rglob("*.py")
                if ".venv" not in p.parts and "__pycache__" not in p.parts
            )


def audit_paths(paths: Iterable[str | Path]) -> list[Finding]:
    root_paths = [Path(p) for p in paths]
    findings: list[Finding] = []
    for path in iter_python_files(root_paths):
        findings.extend(audit_file(path))
    return sorted(findings, key=lambda f: (f.severity, f.path, f.line))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit LLM token capture at generate_json/generate_text call sites.")
    parser.add_argument("paths", nargs="*", default=["app/services"], help="Files or directories to audit.")
    args = parser.parse_args()

    findings = audit_paths(args.paths)
    if not findings:
        print("[ok] no LLM token-capture violations found")
        return 0
    for finding in findings:
        print(finding.format())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
