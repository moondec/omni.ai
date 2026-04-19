"""
Load and merge per-model LLM profiles with shared fragments (e.g. tool catalog).

Profiles live in pcss_llm_app/llm_profiles/*.yaml; shared text in _shared.yaml.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import yaml

DEFAULT_MAX_TOKENS = 4096


def _load_yaml(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else None


def _append_tool_catalog(
    profile: Dict[str, Any],
    shared: Dict[str, Any],
    tool_catalog_key: str,
) -> None:
    """Append the selected tool list to instructions, or system_prompt_additions if instructions empty."""
    if tool_catalog_key in (None, "", "none"):
        return
    catalogs = shared.get("tool_catalog") if isinstance(shared.get("tool_catalog"), dict) else {}
    block = catalogs.get(tool_catalog_key)
    if block is None:
        block = catalogs.get("full", "")
    block = (block or "").strip()
    if not block:
        return

    instr = (profile.get("instructions") or "").rstrip()
    sys_add = (profile.get("system_prompt_additions") or "").rstrip()

    if instr:
        profile["instructions"] = f"{instr}\n\n{block}"
    elif sys_add:
        profile["system_prompt_additions"] = f"{sys_add}\n\n{block}"
    else:
        profile["instructions"] = block


def _prepend_common_rules(profile: Dict[str, Any], shared: Dict[str, Any]) -> None:
    """Prepend shared common_rules to system_prompt_additions.

    Existing profile content is preserved after the shared rules so model-specific
    tweaks (truncation limits, XML-format bans, etc.) still apply. Profiles that
    opt out can set `skip_common_rules: true`.
    """
    if profile.get("skip_common_rules"):
        profile.pop("skip_common_rules", None)
        return
    block = (shared.get("common_rules") or "").strip()
    if not block:
        return
    existing = (profile.get("system_prompt_additions") or "").strip()
    if existing:
        profile["system_prompt_additions"] = f"{block}\n\n{existing}"
    else:
        profile["system_prompt_additions"] = block


def merge_profile_with_shared(profile: Dict[str, Any], shared: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Mutates and returns profile with common rules prepended + tool catalog appended."""
    if not shared:
        return profile
    _prepend_common_rules(profile, shared)
    tc = profile.pop("tool_catalog", "full")
    if isinstance(tc, str):
        tc = tc.strip().lower()
    _append_tool_catalog(profile, shared, tc)
    return profile


# ---------------------------------------------------------------------------
# Multi-stage fuzzy model name resolution
# ---------------------------------------------------------------------------

def _normalize_model_name(model_name: str) -> str:
    """Strip provider prefix and tier/variant suffix, then lowercase.

    Examples:
      'google/gemma-4-31b-it:free'              -> 'gemma-4-31b-it'
      'nvidia/llama-3.1-nemotron-70b-instruct'  -> 'llama-3.1-nemotron-70b-instruct'
      'openrouter/free'                         -> 'free'
      'Qwen3-VL-235B-A22B-Instruct'            -> 'qwen3-vl-235b-a22b-instruct'
    """
    name = model_name.strip()
    # Strip provider prefix (everything before the first '/')
    if "/" in name:
        name = name.split("/", 1)[1]
    # Strip variant suffix (everything after ':')
    if ":" in name:
        name = name.split(":", 1)[0]
    return name.lower()


# Map of keyword -> family profile filename (without .yaml).
# Order matters: more-specific entries must come before broader family names
# so that e.g. 'nemotron' or 'llama-3.3' match before the generic 'llama'.
_FAMILY_MAP: List[Tuple[str, str]] = [
    # Qwen — specific profiles take precedence via exact match; these are catch-alls
    ("qwen3-vl",           "Qwen3-VL-235B-A22B-Instruct"),
    ("qwen3.5",            "Qwen3.5-397B-A17B"),
    ("qwen3-coder",        "Qwen3-Coder-Next"),
    ("qwen2.5",            "Qwen2.5-72b"),
    ("qwen",               "openrouter-qwen"),
    # GLM / Zhipu
    ("glm-4.7",            "GLM-4.7"),
    ("glm",                "openrouter-glm"),
    # MiniMax
    ("minimax-m2.5",       "MiniMax-M2.5"),
    ("minimax",            "openrouter-minimax"),
    # Mistral
    ("mistral-small-3.2",  "Mistral-Small-3.2-24b"),
    ("mistral",            "default"),
    # Llama / Nemotron — nemotron must come before llama
    ("nemotron",           "openrouter-llama"),
    ("llama-3.3",          "llama3.3-70b"),
    ("llama",              "openrouter-llama"),
    # Google Gemma
    ("gemma",              "openrouter-gemma"),
    # Elephant (OpenRouter proprietary)
    ("elephant",           "openrouter-elephant"),
    # DeepSeek
    ("deepseek",           "DeepSeek-V3.1-vLLM"),
    # Bielik
    ("bielik",             "bielik_11b"),
    # Generic OpenRouter free routing (must be last — very broad)
    ("free",               "openrouter-free"),
]


def _find_profile_file(profiles_dir: str, model_name: str) -> str:
    """Resolve model_name to the absolute path of the best-matching YAML profile.

    Resolution priority:
    1. Exact filename match: replace ':' with '-', look for <name>.yaml
    2. Normalised exact filename match (strip provider prefix & variant suffix)
    3. Family keyword match via _FAMILY_MAP
    4. Scan all *.yaml files: compare 'name:' field (case-insensitive)
    5. Fallback: default.yaml
    """
    def profile_path(stem: str) -> str:
        return os.path.join(profiles_dir, f"{stem}.yaml")

    # Stage 1: exact filename (legacy behaviour, handles local PCSS model names)
    safe = model_name.replace(":", "-")
    if os.path.exists(profile_path(safe)):
        return profile_path(safe)

    # Stage 2: normalised filename (e.g. 'google/gemma-4-31b-it:free' -> 'gemma-4-31b-it')
    norm = _normalize_model_name(model_name)
    if os.path.exists(profile_path(norm)):
        return profile_path(norm)

    # Stage 3: family keyword lookup
    for keyword, family_stem in _FAMILY_MAP:
        if keyword in norm:
            candidate = profile_path(family_stem)
            if os.path.exists(candidate):
                return candidate

    # Stage 4: scan YAML 'name:' fields
    try:
        for fname in sorted(os.listdir(profiles_dir)):
            if not fname.endswith(".yaml") or fname.startswith("_"):
                continue
            fpath = os.path.join(profiles_dir, fname)
            data = _load_yaml(fpath)
            if data and isinstance(data.get("name"), str):
                if data["name"].lower() == norm:
                    return fpath
    except OSError:
        pass

    # Stage 5: default
    return profile_path("default")


def load_llm_profile(
    model_name: str,
    profiles_dir: str,
) -> Tuple[str, int, str, int]:
    """
    Load YAML for the given model name and return the same tuple as MainWindow._get_llm_profile_data:
    (instructions, max_tokens, system_prompt_additions, context_window)
    """
    target_file = _find_profile_file(profiles_dir, model_name)

    shared_path = os.path.join(profiles_dir, "_shared.yaml")
    shared = _load_yaml(shared_path) or {}

    profile = _load_yaml(target_file)
    if not profile:
        return "", DEFAULT_MAX_TOKENS, "", 0

    merge_profile_with_shared(profile, shared)

    return (
        profile.get("instructions", "") or "",
        int(profile.get("max_tokens", DEFAULT_MAX_TOKENS)),
        profile.get("system_prompt_additions", "") or "",
        int(profile.get("context_window", 0) or 0),
    )
