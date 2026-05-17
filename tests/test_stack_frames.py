from loopsentry.stack_frames import analyze_stack_for_user_code, classify_path


def _frame(path: str, line: int = 10, func: str = "f") -> str:
    return f'  File "{path}", line {line}, in {func}\n'


def test_classify_stdlib_and_site_packages():
    assert classify_path("/usr/lib/python3.12/linecache.py", ()) == "stdlib"
    assert classify_path("/venv/lib/python3.12/site-packages/uvicorn/main.py", ()) == "third_party"
    assert classify_path("/home/dev/myapp/routes.py", ()) == "user"


def test_synthetic_paths_are_not_user():
    assert classify_path("<string>", ()) == "synthetic"
    assert classify_path("<stdin>", ()) == "synthetic"
    assert classify_path("<frozen importlib._bootstrap>", ()) == "synthetic"


def test_project_root_forces_user_under_site_packages():
    pkg = "/venv/lib/python3.12/site-packages/myapp/handler.py"
    assert classify_path(pkg, ()) == "third_party"
    roots = ("/venv/lib/python3.12/site-packages/myapp",)
    assert classify_path(pkg, roots) == "user"


def test_analyze_stack_prefers_nearest_user_frame_from_inner():
    stack = [
        _frame("/proj/main.py", 1, "run"),
        _frame("/venv/lib/python3.12/site-packages/fastapi/routing.py", 2, "app"),
        _frame("/usr/lib/python3.12/linecache.py", 99, "checkline"),
    ]
    info = analyze_stack_for_user_code(stack, ())
    assert info["user_location"] == "main.py:1"
    assert info["blocking_location"] == "linecache.py:99"
    assert len(info["user_frames"]) == 1
    assert info["user_frames"][0]["file"].endswith("main.py")


def test_string_outer_frame_does_not_dominate_user_location():
    stack = [
        '  File "<string>", line 1, in <module>\n',
        _frame("/proj/app.py", 5, "handler"),
        _frame("/venv/lib/python3.12/site-packages/uvicorn/server.py", 10, "run"),
    ]
    info = analyze_stack_for_user_code(stack, ())
    assert info["user_location"] == "app.py:5"
    assert len(info["user_frames"]) == 1


def test_only_framework_and_synthetic_yields_no_user_frames():
    stack = [
        '  File "<string>", line 1, in <module>\n',
        _frame("/venv/lib/python3.12/site-packages/uvicorn/server.py", 75, "run"),
        _frame("/usr/lib/python3.12/asyncio/base_events.py", 463, "create_task"),
    ]
    info = analyze_stack_for_user_code(stack, ())
    assert info["user_frames"] == []
    assert info["user_location"] == ""
    assert info["blocking_location"] == "base_events.py:463"


def test_loopsentry_monitor_is_not_user_code():
    stack = [
        _frame("/proj/app.py", 5, "handler"),
        _frame("/venv/lib/python3.12/site-packages/loopsentry/monitor.py", 220, "_watchdog"),
    ]
    info = analyze_stack_for_user_code(stack, ())
    assert info["user_location"] == "app.py:5"
    assert len(info["user_frames"]) == 1
