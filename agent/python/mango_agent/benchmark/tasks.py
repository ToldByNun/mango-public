"""Representative coding tasks for the Mango agent benchmark.

Ladder: 5 easy, 5 medium, 5 hard. Stubs always fail verification until the agent edits them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class BenchTask:
    id: str
    title: str
    category: str
    difficulty: str
    goal: str
    files: dict[str, str]
    expect_in_files: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def render_goal(self, root: Path) -> str:
        goal = self.goal
        for rel in self.files:
            goal = goal.replace("{" + rel + "}", str((root / rel).resolve()))
        return goal.replace("{root}", str(root.resolve()))


def get_task(task_id: str) -> BenchTask:
    for task in TASKS:
        if task.id == task_id:
            return task
    known = ", ".join(task.id for task in TASKS)
    raise KeyError(f"unknown task {task_id!r}; expected one of: {known}")


def list_tasks() -> list[BenchTask]:
    return list(TASKS)


TASKS: tuple[BenchTask, ...] = (
    # --- easy ---
    BenchTask(
        id="feature_greet",
        title="Change greet greeting",
        category="feature",
        difficulty="easy",
        goal=(
            "Change greet(name) in {greet.py} so it returns 'Hello, {name}!' "
            "instead of 'hi {name}'."
        ),
        files={
            "greet.py": "def greet(name):\n    return f'hi {name}'\n",
            "test_greet.py": (
                "from greet import greet\n\n\n"
                "def test_greet():\n"
                "    assert greet('Ada') == 'Hello, Ada!'\n"
            ),
        },
    ),
    BenchTask(
        id="bugfix_inclusive_sum",
        title="Fix off-by-one in sum_to",
        category="bugfix",
        difficulty="easy",
        goal=(
            "Bugfix: sum_to(n) in {sumutil.py} must return the sum of 1..n inclusive. "
            "It currently misses n."
        ),
        files={
            "sumutil.py": (
                "def sum_to(n):\n"
                "    total = 0\n"
                "    for i in range(n):\n"
                "        total += i\n"
                "    return total\n"
            ),
            "test_sumutil.py": (
                "from sumutil import sum_to\n\n\n"
                "def test_sum_to():\n"
                "    assert sum_to(0) == 0\n"
                "    assert sum_to(3) == 6\n"
                "    assert sum_to(10) == 55\n"
            ),
        },
    ),
    BenchTask(
        id="feature_clamp",
        title="Implement clamp",
        category="feature",
        difficulty="easy",
        goal=(
            "Implement clamp(value, lo, hi) in {mathutil.py}: return value limited to [lo, hi]."
        ),
        files={
            "mathutil.py": "def clamp(value, lo, hi):\n    return value\n",
            "test_mathutil.py": (
                "from mathutil import clamp\n\n\n"
                "def test_clamp():\n"
                "    assert clamp(5, 0, 10) == 5\n"
                "    assert clamp(-1, 0, 10) == 0\n"
                "    assert clamp(99, 0, 10) == 10\n"
            ),
        },
    ),
    BenchTask(
        id="bugfix_none_guard",
        title="Guard label() against None",
        category="bugfix",
        difficulty="easy",
        goal=(
            "Bugfix: label(value) in {labelutil.py} should return an empty string when value "
            "is None, otherwise strip and uppercase the text."
        ),
        files={
            "labelutil.py": "def label(value):\n    return value.strip().upper()\n",
            "test_labelutil.py": (
                "from labelutil import label\n\n\n"
                "def test_label():\n"
                "    assert label(' hi ') == 'HI'\n"
                "    assert label(None) == ''\n"
            ),
        },
    ),
    BenchTask(
        id="bugfix_wrong_formula",
        title="Fix discount formula",
        category="bugfix",
        difficulty="easy",
        goal=(
            "Bugfix: discount(price, pct) in {pricing.py} must return price * (1 - pct), "
            "not price + pct."
        ),
        files={
            "pricing.py": "def discount(price, pct):\n    return price + pct\n",
            "test_pricing.py": (
                "from pricing import discount\n\n\n"
                "def test_discount():\n"
                "    assert discount(100, 0.1) == 90\n"
                "    assert discount(50, 0) == 50\n"
            ),
        },
    ),
    # --- medium ---
    BenchTask(
        id="feature_slugify",
        title="Implement slugify",
        category="feature",
        difficulty="medium",
        goal=(
            "Implement slugify(text) in {textutil.py}: lowercase, strip, and replace inner "
            "whitespace with a single hyphen. Example: 'Hello World' -> 'hello-world'."
        ),
        files={
            "textutil.py": "def slugify(text):\n    return text\n",
            "test_textutil.py": (
                "from textutil import slugify\n\n\n"
                "def test_slugify():\n"
                "    assert slugify('Hello World') == 'hello-world'\n"
                "    assert slugify('  Foo   BAR ') == 'foo-bar'\n"
            ),
        },
    ),
    BenchTask(
        id="feature_parse_query",
        title="Parse query strings",
        category="feature",
        difficulty="medium",
        goal=(
            "Implement parse_query(text) in {queryutil.py} so 'a=1&b=2' becomes "
            "{'a': '1', 'b': '2'}. Ignore empty pairs. Do not URL-decode."
        ),
        files={
            "queryutil.py": "def parse_query(text):\n    return {}\n",
            "test_queryutil.py": (
                "from queryutil import parse_query\n\n\n"
                "def test_parse_query():\n"
                "    assert parse_query('a=1&b=2') == {'a': '1', 'b': '2'}\n"
                "    assert parse_query('x=') == {'x': ''}\n"
                "    assert parse_query('') == {}\n"
            ),
        },
    ),
    BenchTask(
        id="bugfix_stable_unique",
        title="Preserve order in unique()",
        category="bugfix",
        difficulty="medium",
        goal=(
            "Bugfix: unique(items) in {uniqueutil.py} must drop duplicates while preserving "
            "first-seen order. Do not sort."
        ),
        files={
            "uniqueutil.py": "def unique(items):\n    return sorted(set(items))\n",
            "test_uniqueutil.py": (
                "from uniqueutil import unique\n\n\n"
                "def test_unique():\n"
                "    assert unique([3, 1, 2, 1]) == [3, 1, 2]\n"
                "    assert unique(['a', 'a']) == ['a']\n"
            ),
        },
    ),
    BenchTask(
        id="api_json_dumps",
        title="Serialize with json.dumps",
        category="api",
        difficulty="medium",
        goal=(
            "Implement to_json(obj) in {jsonutil.py} using the json library "
            "(json.dumps). If unsure about the signature, look it up."
        ),
        files={
            "jsonutil.py": "def to_json(obj):\n    return str(obj)\n",
            "test_jsonutil.py": (
                "import json\nfrom jsonutil import to_json\n\n\n"
                "def test_to_json():\n"
                "    assert json.loads(to_json({'a': 1})) == {'a': 1}\n"
                "    assert json.loads(to_json([1, 2])) == [1, 2]\n"
            ),
        },
        expect_in_files={"jsonutil.py": ("json.dumps",)},
    ),
    BenchTask(
        id="multistep_filter_sort",
        title="Filter ready items then sort",
        category="multi_step",
        difficulty="medium",
        goal=(
            "Implement top_ready(items) in {jobs.py}: keep items whose status is 'ready', "
            "then sort them by score descending. Return the list of names."
        ),
        files={
            "jobs.py": "def top_ready(items):\n    return []\n",
            "test_jobs.py": (
                "from jobs import top_ready\n\n\n"
                "def test_top_ready():\n"
                "    items = [\n"
                "        {'name': 'a', 'status': 'ready', 'score': 1},\n"
                "        {'name': 'b', 'status': 'blocked', 'score': 9},\n"
                "        {'name': 'c', 'status': 'ready', 'score': 5},\n"
                "    ]\n"
                "    assert top_ready(items) == ['c', 'a']\n"
            ),
        },
    ),
    # --- hard ---
    BenchTask(
        id="refactor_extract_helper",
        title="Extract shared normalize helper",
        category="refactor",
        difficulty="hard",
        goal=(
            "Refactor {names.py}: clean_name and clean_title share the same strip/lower logic. "
            "Extract a helper named normalize(text) and use it from both functions. "
            "Behavior must stay the same."
        ),
        files={
            "names.py": (
                "def clean_name(text):\n"
                "    return (text or '').strip().lower()\n\n\n"
                "def clean_title(text):\n"
                "    return (text or '').strip().lower()\n"
            ),
            "test_names.py": (
                "from names import clean_name, clean_title, normalize\n\n\n"
                "def test_clean():\n"
                "    assert clean_name('  Ada ') == 'ada'\n"
                "    assert clean_title('  Ada ') == 'ada'\n"
                "    assert normalize('  Ada ') == 'ada'\n"
            ),
        },
        expect_in_files={"names.py": ("def normalize(",)},
    ),
    BenchTask(
        id="refactor_rename_symbol",
        title="Rename greet to welcome",
        category="refactor",
        difficulty="hard",
        goal=(
            "Refactor: rename greet to welcome in {greeter.py} and update the caller in "
            "{app.py}. Tests import welcome()."
        ),
        files={
            "greeter.py": "def greet(name):\n    return f'hi {name}'\n",
            "app.py": "from greeter import greet\n\n\ndef run():\n    return greet('Ada')\n",
            "test_app.py": (
                "from greeter import welcome\nfrom app import run\n\n\n"
                "def test_welcome():\n"
                "    assert welcome('Ada') == 'hi Ada'\n"
                "    assert run() == 'hi Ada'\n"
            ),
        },
        expect_in_files={
            "greeter.py": ("def welcome(",),
            "app.py": ("welcome",),
        },
    ),
    BenchTask(
        id="multifile_pricing_format",
        title="Implement discount and money across two files",
        category="multi_step",
        difficulty="hard",
        goal=(
            "Implement discount(price, pct) in {app/pricing.py} as price * (1 - pct), "
            "and money(n) in {app/format.py} as a dollar string with two decimals "
            "(example: money(90) == '$90.00')."
        ),
        files={
            "app/__init__.py": "",
            "app/pricing.py": "def discount(price, pct):\n    return price\n",
            "app/format.py": "def money(n):\n    return str(n)\n",
            "test_feature.py": (
                "from app.pricing import discount\nfrom app.format import money\n\n\n"
                "def test_discount():\n"
                "    assert discount(100, 0.1) == 90\n\n\n"
                "def test_money():\n"
                "    assert money(90) == '$90.00'\n"
            ),
        },
    ),
    BenchTask(
        id="multifile_config_defaults",
        title="Fix timeout default used by app",
        category="multi_step",
        difficulty="hard",
        goal=(
            "The app reads TIMEOUT from {config.py} via {app.py}. "
            "TIMEOUT is currently 0; it must be 30 so get_timeout() returns 30. "
            "Do not hardcode 30 inside get_timeout — change the config default."
        ),
        files={
            "config.py": "TIMEOUT = 0\n",
            "app.py": "from config import TIMEOUT\n\n\ndef get_timeout():\n    return TIMEOUT\n",
            "test_app.py": (
                "import config\nfrom app import get_timeout\n\n\n"
                "def test_timeout():\n"
                "    assert config.TIMEOUT == 30\n"
                "    assert get_timeout() == 30\n"
            ),
        },
        expect_in_files={"config.py": ("TIMEOUT = 30",)},
    ),
    BenchTask(
        id="bugfix_syntax_then_unique",
        title="Repair syntax then preserve unique order",
        category="bugfix",
        difficulty="hard",
        goal=(
            "Bugfix {uniqueutil.py}: unique(items) must drop duplicates while preserving "
            "first-seen order. The file currently does not parse. Do not sort."
        ),
        files={
            "uniqueutil.py": "def unique(items)\n    return sorted(set(items))\n",
            "test_uniqueutil.py": (
                "from uniqueutil import unique\n\n\n"
                "def test_unique():\n"
                "    assert unique([3, 1, 2, 1]) == [3, 1, 2]\n"
                "    assert unique(['a', 'a']) == ['a']\n"
            ),
        },
    ),
)
