from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

FrameKind = Literal["user", "stdlib", "third_party", "instrumentation", "synthetic"]

_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+)(?:, in ([^\n]+))?')

_STDLIB_LIB_RE = re.compile(r"/lib/python\d+(?:\.\d+)?/", re.IGNORECASE)
_WIN_LIB_RE = re.compile(r"[/\\]Python\d+[/\\]Lib[/\\]", re.IGNORECASE)


def _norm_path(path: str) -> str:
    return path.replace("\\", "/")


def _is_instrumentation(path: str) -> bool:
    p = _norm_path(path).lower()
    return "loopsentry" in p and p.endswith("monitor.py")


def _is_synthetic_source_path(path: str) -> bool:
    p = path.strip()
    if not p:
        return True
    if p == "<string>":
        return True
    if len(p) >= 2 and p[0] == "<" and p[-1] == ">":
        return True
    return False


def _is_third_party(path: str) -> bool:
    p = _norm_path(path).lower()
    return "site-packages" in p or "dist-packages" in p


def _is_stdlib(path: str) -> bool:
    p = _norm_path(path)
    low = p.lower()
    if _is_third_party(path):
        return False
    if _STDLIB_LIB_RE.search(p) or _WIN_LIB_RE.search(p):
        return True
    if ".zip/" in low and "python" in low:
        return True
    return False


def classify_path(path: str, project_roots: tuple[str, ...]) -> FrameKind:
    if _is_instrumentation(path):
        return "instrumentation"
    if _is_synthetic_source_path(path):
        return "synthetic"
    norm = _norm_path(path)
    for root in project_roots:
        r = _norm_path(root).rstrip("/")
        if r and (norm == r or norm.startswith(r + "/")):
            return "user"
    if _is_third_party(path):
        return "third_party"
    if _is_stdlib(path):
        return "stdlib"
    return "user"


def parse_stack_line(line: str) -> tuple[str, int, str | None] | None:
    m = _FRAME_RE.search(line)
    if not m:
        return None
    func = m.group(3)
    if func:
        func = func.strip()
    return m.group(1), int(m.group(2)), func or None


def analyze_stack_for_user_code(
    stack: list[str],
    project_roots: tuple[str, ...] = (),
) -> dict[str, Any]:
    if not stack:
        return {
            "user_frames": [],
            "user_location": "",
            "blocking_location": "",
            "blocking_file": "",
        }

    user_frames: list[dict[str, Any]] = []
    for line in reversed(stack):
        parsed = parse_stack_line(line)
        if not parsed:
            continue
        file, lineno, func = parsed
        kind = classify_path(file, project_roots)
        if kind != "user":
            continue
        short = f"{Path(file).name}:{lineno}"
        user_frames.append(
            {
                "file": file,
                "line": lineno,
                "func": func or "",
                "short": short,
            }
        )

    inner = parse_stack_line(stack[-1])
    blocking_location = ""
    blocking_file = ""
    if inner:
        f, ln, _ = inner
        blocking_location = f"{Path(f).name}:{ln}"
        blocking_file = f

    user_location = user_frames[0]["short"] if user_frames else ""

    return {
        "user_frames": user_frames,
        "user_location": user_location,
        "blocking_location": blocking_location,
        "blocking_file": blocking_file,
    }