import pytest
from src.web.web_search import (
    WebSearchConfig,
    search_public_web,
    set_runtime_web_search_config,
    validate_privacy_guard,
)


def test_privacy_guard_blocks_target_username():
    with pytest.raises(ValueError, match="target username"):
        validate_privacy_guard("info about john_doe", target_username="john_doe")


def test_privacy_guard_blocks_at_handle():
    with pytest.raises(ValueError, match="@username handles"):
        validate_privacy_guard("find out about @some_handle")


def test_privacy_guard_blocks_instagram_url():
    with pytest.raises(ValueError, match="Instagram URLs"):
        validate_privacy_guard("check https://instagram.com/target")


def test_privacy_guard_allows_public_places():
    clean = validate_privacy_guard("Milan Cathedral opening hours", target_username="target_user")
    assert clean == "Milan Cathedral opening hours"


def test_web_search_disabled_by_default():
    set_runtime_web_search_config(WebSearchConfig(enabled=False))
    with pytest.raises(RuntimeError, match="disabled"):
        search_public_web("Eiffel Tower")


def test_web_search_wikipedia_provider():
    set_runtime_web_search_config(WebSearchConfig(enabled=True, provider="wikipedia"))
    results = search_public_web("Louvre Museum")
    assert len(results) > 0
    assert any("louvre" in r["title"].lower() or "louvre" in r["snippet"].lower() for r in results)
