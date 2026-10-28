"""LLM client supporting both LM Studio (OpenAI-compatible local server) and Ollama."""
import configparser
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

try:
    import ollama
except ImportError:
    ollama = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from src.web.tools import tool_specs

# In-memory runtime override if set via web UI
_RUNTIME_AI_CONFIG: Dict[str, Any] = {}


@dataclass
class LLMFunctionCall:
    name: str
    arguments: dict

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)


@dataclass
class LLMToolCall:
    id: str
    function: LLMFunctionCall

    def __getitem__(self, item: str):
        if item == "name":
            return self.function.name
        if item == "arguments":
            return self.function.arguments
        if item == "id":
            return self.id
        if item == "function":
            return self.function
        return getattr(self, item)

    def get(self, item: str, default=None):
        try:
            return self[item]
        except (AttributeError, KeyError):
            return default

    @property
    def name(self) -> str:
        return self.function.name

    @property
    def arguments(self) -> dict:
        return self.function.arguments


def _detect_wsl_host() -> Optional[str]:
    try:
        with open("/proc/version", "r") as f:
            if "microsoft" in f.read().lower():
                import subprocess
                out = subprocess.check_output(["ip", "route"], text=True)
                for line in out.splitlines():
                    if line.startswith("default via"):
                        return line.split()[2]
    except Exception:
        pass
    return None


def _default_lmstudio_host() -> str:
    explicit = (
        os.getenv("LMSTUDIO_BASE_URL")
        or os.getenv("LMSTUDIO_HOST")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("LMSTUDIO_URL")
    )
    if explicit:
        return explicit.strip()
    wsl_ip = _detect_wsl_host()
    if wsl_ip:
        try:
            req = Request("http://127.0.0.1:1234/v1/models", headers={"User-Agent": "Osintgram"})
            with urlopen(req, timeout=0.3) as resp:
                if resp.status == 200:
                    return "http://127.0.0.1:1234/v1"
        except Exception:
            return f"http://{wsl_ip}:1234/v1"
    return "http://127.0.0.1:1234/v1"


def _read_ai_config() -> dict:
    # Single source of truth supporting both #2698 and #2703 env vars
    provider = os.getenv("LLM_PROVIDER") or os.getenv("LLM_BACKEND") or "auto"
    base_url = (
        os.getenv("LMSTUDIO_BASE_URL")
        or os.getenv("LMSTUDIO_HOST")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("LMSTUDIO_URL")
        or _default_lmstudio_host()
    )
    model = os.getenv("LMSTUDIO_MODEL") or os.getenv("OPENAI_MODEL") or ""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LMSTUDIO_API_KEY") or ""
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    ollama_url = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

    config = {
        "provider": provider.lower().strip(),
        "base_url": base_url.strip(),
        "model": model.strip(),
        "api_key": api_key.strip(),
        "ollama_model": ollama_model.strip(),
        "ollama_url": ollama_url.strip(),
    }
    ini_path = "config/credentials.ini"
    if os.path.exists(ini_path):
        try:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(ini_path)
            if parser.has_section("AI"):
                sec = parser["AI"]
                if not (os.getenv("LLM_PROVIDER") or os.getenv("LLM_BACKEND")):
                    prov = sec.get("provider", fallback="") or sec.get("backend", fallback="")
                    if prov:
                        config["provider"] = prov.strip().lower()
                if not (os.getenv("LMSTUDIO_BASE_URL") or os.getenv("LMSTUDIO_HOST") or os.getenv("OPENAI_BASE_URL") or os.getenv("LMSTUDIO_URL")):
                    url = sec.get("base_url", fallback="") or sec.get("host", fallback="") or sec.get("lmstudio_url", fallback="")
                    if url:
                        config["base_url"] = url.strip()
                if not (os.getenv("LMSTUDIO_MODEL") or os.getenv("OPENAI_MODEL")):
                    m = sec.get("model", fallback="") or sec.get("lmstudio_model", fallback="")
                    if m:
                        config["model"] = m.strip()
                if not (os.getenv("OPENAI_API_KEY") or os.getenv("LMSTUDIO_API_KEY")):
                    k = sec.get("api_key", fallback="") or sec.get("lmstudio_api_key", fallback="")
                    if k:
                        config["api_key"] = k.strip()
                if not os.getenv("OLLAMA_MODEL"):
                    om = sec.get("ollama_model", fallback="")
                    if om:
                        config["ollama_model"] = om.strip()
                if not os.getenv("OLLAMA_HOST"):
                    ou = sec.get("ollama_url", fallback="") or sec.get("ollama_host", fallback="")
                    if ou:
                        config["ollama_url"] = ou.strip()
        except Exception:
            pass

    # Runtime overrides take precedence
    config.update(_RUNTIME_AI_CONFIG)
    return config


def set_runtime_ai_config(cfg: dict) -> None:
    _RUNTIME_AI_CONFIG.update(cfg)


def save_ai_config(provider: str, base_url: str, model: str, api_key: Optional[str] = None) -> bool:
    ini_path = Path("config/credentials.ini")
    parser = configparser.ConfigParser(interpolation=None)
    if ini_path.exists():
        try:
            parser.read(ini_path)
        except Exception:
            pass

    if not parser.has_section("AI"):
        parser.add_section("AI")

    parser.set("AI", "provider", provider.lower().strip())
    parser.set("AI", "base_url", base_url.strip())
    parser.set("AI", "model", model.strip())
    if api_key is not None:
        parser.set("AI", "api_key", api_key.strip())

    try:
        ini_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ini_path, "w", encoding="utf-8") as f:
            parser.write(f)
        return True
    except Exception:
        return False


def is_lmstudio_reachable(url: str, timeout: float = 1.0) -> bool:
    try:
        models_url = url.rstrip("/")
        if not models_url.endswith("/v1"):
            models_url += "/v1"
        models_url += "/models"
        req = Request(models_url, headers={"User-Agent": "Osintgram"})
        with urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def is_ollama_reachable(url: str, timeout: float = 1.0) -> bool:
    try:
        tags_url = url.rstrip("/") + "/api/tags"
        req = Request(tags_url, headers={"User-Agent": "Osintgram"})
        with urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def fetch_available_models(provider: str, base_url: str, api_key: str = "") -> List[str]:
    provider = provider.lower().strip()
    if provider in ("lmstudio", "openai"):
        if OpenAI is None:
            raise RuntimeError("The 'openai' Python package is required for LM Studio/OpenAI support. Install it via: pip install openai")
        client = OpenAI(base_url=base_url or "http://127.0.0.1:1234/v1", api_key=api_key or "lm-studio", timeout=3.0)
        res = client.models.list()
        return [m.id for m in res.data]
    elif provider == "ollama":
        if ollama is None:
            raise RuntimeError("The 'ollama' Python package is required for Ollama support. Install it via: pip install ollama")
        host = base_url or "http://127.0.0.1:11434"
        client = ollama.Client(host=host)
        res = client.list()
        return [m.model for m in res.models]
    return []


def resolve_llm_info() -> dict:
    cfg = _read_ai_config()
    provider = cfg["provider"]

    if provider == "auto":
        if is_lmstudio_reachable(cfg["base_url"]):
            provider = "lmstudio"
        else:
            provider = "ollama"

    model_name = cfg["model"]
    if provider == "lmstudio":
        if not model_name:
            try:
                models = fetch_available_models("lmstudio", cfg["base_url"], cfg.get("api_key", ""))
                if models:
                    model_name = models[0]
            except Exception:
                model_name = "local-model"
    else:
        model_name = model_name or cfg["ollama_model"]

    return {
        "provider": provider,
        "model": model_name,
        "base_url": cfg["base_url"],
        "api_key": cfg.get("api_key", ""),
        "ollama_model": cfg["ollama_model"],
        "ollama_url": cfg["ollama_url"],
    }


def convert_specs_to_openai_tools(tools_list: list) -> list:
    """Convert Osintgram tool specs to OpenAI function-calling tool format."""
    all_specs = tool_specs()
    tool_names = {getattr(fn, "__name__", str(fn)) for fn in tools_list}
    active_specs = [s for s in all_specs if s["name"] in tool_names]

    openai_tools = []
    for spec in active_specs:
        properties = {}
        for p in spec.get("params", []):
            prop: dict = {
                "type": p.get("type", "string"),
                "description": p.get("description", ""),
            }
            if p.get("choices"):
                prop["enum"] = p["choices"]
            properties[p["name"]] = prop

        openai_tools.append({
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec.get("description", ""),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                },
            },
        })
    return openai_tools


def run_llm_chat(
    provider: str,
    model: str,
    messages: list,
    tools: list,
    options: dict,
    lmstudio_url: str = "http://127.0.0.1:1234/v1",
    api_key: str = "",
) -> Generator[dict, None, Tuple[str, List[LLMToolCall]]]:
    """Execute streaming chat completion with either LM Studio or Ollama."""
    content_parts: list = []
    tool_calls: list = []

    if provider in ("lmstudio", "openai"):
        if OpenAI is None:
            raise RuntimeError("The 'openai' Python package is required for LM Studio/OpenAI support. Install it via: pip install openai")
        client = OpenAI(base_url=lmstudio_url, api_key=api_key or "lm-studio")
        openai_tools = convert_specs_to_openai_tools(tools)

        # Prepare OpenAI messages
        openai_msgs = []
        for msg in messages:
            role = msg["role"]
            if role == "tool":
                openai_msgs.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", f"call_{msg.get('tool_name', 'tool')}"),
                    "name": msg.get("tool_name", "tool"),
                    "content": str(msg.get("content", "")),
                })
            elif role == "assistant":
                tc_list = []
                for tc in msg.get("tool_calls", []):
                    tc_id = getattr(tc, "id", f"call_{getattr(getattr(tc, 'function', None), 'name', 'tool')}")
                    fn_name = getattr(getattr(tc, "function", None), "name", "tool")
                    fn_args = getattr(getattr(tc, "function", None), "arguments", {})
                    if not isinstance(fn_args, str):
                        fn_args = json.dumps(fn_args)
                    tc_list.append({
                        "id": tc_id,
                        "type": "function",
                        "function": {"name": fn_name, "arguments": fn_args},
                    })
                assistant_payload: dict = {"role": "assistant", "content": msg.get("content") or None}
                if tc_list:
                    assistant_payload["tool_calls"] = tc_list
                openai_msgs.append(assistant_payload)
            else:
                openai_msgs.append({"role": role, "content": msg.get("content", "")})

        response = client.chat.completions.create(
            model=model or "local-model",
            messages=openai_msgs,
            tools=openai_tools if openai_tools else None,
            stream=True,
            temperature=options.get("temperature", 0.1),
            max_tokens=options.get("num_predict", 1024),
        )

        tool_chunks: Dict[int, dict] = {}
        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                yield {"type": "answer_delta", "text": delta.content}
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index if tc.index is not None else 0
                    if idx not in tool_chunks:
                        tool_chunks[idx] = {
                            "id": tc.id or f"call_{idx}",
                            "name": (tc.function.name if tc.function else "") or "",
                            "arguments": (tc.function.arguments if tc.function else "") or "",
                        }
                    else:
                        if tc.function and tc.function.name:
                            tool_chunks[idx]["name"] += tc.function.name
                        if tc.function and tc.function.arguments:
                            tool_chunks[idx]["arguments"] += tc.function.arguments

        for idx in sorted(tool_chunks.keys()):
            c = tool_chunks[idx]
            raw_args = c["arguments"]
            parsed_args = {}
            if raw_args:
                try:
                    parsed_args = json.loads(raw_args)
                except Exception:
                    parsed_args = {}
            tool_calls.append(
                LLMToolCall(id=c["id"], function=LLMFunctionCall(name=c["name"], arguments=parsed_args))
            )

    else:
        # Default Ollama provider
        if ollama is None:
            raise RuntimeError("The 'ollama' Python package is required for Ollama support. Install it via: pip install ollama")
        chat_fn = ollama.chat

        for chunk in chat_fn(
            model=model,
            messages=messages,
            tools=tools,
            stream=True,
            options=options,
        ):
            piece = chunk.message
            if piece.content:
                content_parts.append(piece.content)
                yield {"type": "answer_delta", "text": piece.content}
            if piece.tool_calls:
                for tc in piece.tool_calls:
                    name = getattr(getattr(tc, "function", None), "name", "")
                    args = dict(getattr(getattr(tc, "function", None), "arguments", {}) or {})
                    call_id = f"call_{name}"
                    tool_calls.append(LLMToolCall(id=call_id, function=LLMFunctionCall(name=name, arguments=args)))

    content = "".join(content_parts)
    return content, tool_calls
