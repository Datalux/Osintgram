"""Guards against the documentation drifting away from the code.

Deliberately narrow: it checks the facts that go stale silently when someone
adds a feature (a new command, a new environment variable), not the prose -
asserting on wording would just make editing the docs annoying.
"""
import re
from pathlib import Path

import pytest

import src.web.app as appmod
from src.web.tools import tool_specs

GUIDE = Path(__file__).resolve().parent.parent / "doc" / "web-ui.md"
SOURCES = ["src/osint_service.py", "src/web/app.py", "src/instagrapi_backend.py"]


@pytest.fixture(scope="module")
def guide():
    return GUIDE.read_text()


def test_the_guide_exists_and_the_readme_links_to_it(guide):
    readme = (GUIDE.parent.parent / "README.md").read_text()
    assert "doc/web-ui.md" in readme
    assert len(guide.splitlines()) > 100


def test_every_environment_variable_is_documented(guide):
    """A new knob nobody can discover is a knob that doesn't exist."""
    root = GUIDE.parent.parent
    code = "".join((root / path).read_text() for path in SOURCES)
    variables = set(re.findall(r'os\.getenv\("([A-Z][A-Z0-9_]+)"', code))
    assert variables, "no environment variables found - did the sources move?"
    assert sorted(v for v in variables if v not in guide) == []


def test_the_command_count_is_current(guide):
    assert f"{len(tool_specs())} commands" in guide


def test_every_command_is_mentioned_by_its_ui_name(guide):
    """Each command must be findable in the guide under the label the UI shows
    for it - the name the reader actually sees on screen."""
    page = (GUIDE.parent.parent / "src/web/static/index.html").read_text()
    labels = dict(re.findall(r'^\s{4}(\w+): \["[^"]*", "([^"]+)"', page, re.M))
    assert len(labels) >= len(tool_specs()), "could not read TOOL_META labels"
    missing = sorted(labels[s["name"]] for s in tool_specs()
                     if s["name"] in labels and labels[s["name"]] not in guide)
    assert missing == []


def test_internal_anchors_resolve(guide):
    def slug(heading):
        return re.sub(r"\s+", "-", re.sub(r"[^\w\s-]", "", heading.strip().lower())).strip("-")

    headings = {slug(m.group(2)) for m in re.finditer(r"^(#{1,6})\s+(.*)$", guide, re.M)}
    broken = [link for link in re.findall(r"\]\(#([^)]+)\)", guide) if link not in headings]
    assert broken == []


def test_documented_defaults_match_the_code(guide):
    assert f"`{appmod.OLLAMA_MODEL}`" in guide
    assert f"`{appmod.CACHE_PATH}`" in guide
    for spec in tool_specs():
        for param in spec["params"]:
            if param["name"] == "limit" and spec["name"] == "get_followers":
                assert f"`limit` ({param['default']})" in guide
