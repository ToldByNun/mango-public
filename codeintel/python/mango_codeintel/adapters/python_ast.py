from __future__ import annotations

import ast
import warnings
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedSymbol:
    name: str
    qualname: str
    kind: str
    line: int
    col: int
    end_line: int
    signature: str


@dataclass
class ParsedRef:
    name: str
    line: int
    col: int
    kind: str


@dataclass
class ParsedImport:
    module: str
    names: list[str]
    resolved_path: str | None = None


@dataclass
class ParseResult:
    symbols: list[ParsedSymbol] = field(default_factory=list)
    refs: list[ParsedRef] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)


def parse_python(source: str, *, rel_path: str, root: Path) -> ParseResult:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source, filename=rel_path)
    except SyntaxError:
        return ParseResult()
    visitor = _Visitor(rel_path=rel_path, root=root)
    visitor.visit(tree)
    return ParseResult(symbols=visitor.symbols, refs=visitor.refs, imports=visitor.imports)


class _Visitor(ast.NodeVisitor):
    def __init__(self, *, rel_path: str, root: Path) -> None:
        self.rel_path = rel_path
        self.root = root
        self.symbols: list[ParsedSymbol] = []
        self.refs: list[ParsedRef] = []
        self.imports: list[ParsedImport] = []
        self._class_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qual = ".".join([*self._class_stack, node.name])
        self.symbols.append(
            ParsedSymbol(
                name=node.name,
                qualname=qual,
                kind="class",
                line=node.lineno,
                col=node.col_offset,
                end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                signature=f"class {node.name}",
            )
        )
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add_function(node, async_def=False)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add_function(node, async_def=True)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        if name:
            self.refs.append(ParsedRef(name=name, line=node.lineno, col=node.col_offset, kind="call"))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            module = alias.name
            self.imports.append(
                ParsedImport(module=module, names=[alias.asname or alias.name], resolved_path=_resolve(self.root, module))
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        names = [alias.name for alias in node.names]
        resolved = _resolve_from(self.root, self.rel_path, module, node.level)
        self.imports.append(ParsedImport(module=module or ".", names=names, resolved_path=resolved))
        self.generic_visit(node)

    def _add_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, *, async_def: bool) -> None:
        kind = "method" if self._class_stack else "function"
        qual = ".".join([*self._class_stack, node.name])
        prefix = "async def " if async_def else "def "
        self.symbols.append(
            ParsedSymbol(
                name=node.name,
                qualname=qual,
                kind=kind,
                line=node.lineno,
                col=node.col_offset,
                end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                signature=prefix + node.name + _arg_sig(node.args),
            )
        )


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def _arg_sig(args: ast.arguments) -> str:
    parts = [arg.arg for arg in args.args]
    return "(" + ", ".join(parts) + ")"


def _resolve(root: Path, module: str) -> str | None:
    rel = Path(*module.split("."))
    for candidate in (rel.with_suffix(".py"), rel / "__init__.py"):
        if (root / candidate).is_file():
            return candidate.as_posix()
    return None


def _resolve_from(root: Path, rel_path: str, module: str, level: int) -> str | None:
    if level:
        base = Path(rel_path).parent
        for _ in range(level - 1):
            base = base.parent
        if module:
            base = base / Path(*module.split("."))
        for candidate in (base.with_suffix(".py"), base / "__init__.py"):
            if (root / candidate).is_file():
                return candidate.as_posix()
        return None
    return _resolve(root, module) if module else None
