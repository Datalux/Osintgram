import os
from src.instagrapi_backend import resolve_instagrapi_proxy
from src.web.app import mask_proxy


def test_resolve_instagrapi_proxy_from_env(monkeypatch):
    monkeypatch.setenv("INSTAGRAPI_PROXY", "http://user:pass@proxy.example.com:8080")
    assert resolve_instagrapi_proxy() == "http://user:pass@proxy.example.com:8080"


def test_mask_proxy():
    assert mask_proxy("http://admin:secret123@myproxy.net:3128") == "http://admin:***@myproxy.net:3128"
    assert mask_proxy("socks5://127.0.0.1:9050") == "socks5://127.0.0.1:9050"
    assert mask_proxy("") == ""
