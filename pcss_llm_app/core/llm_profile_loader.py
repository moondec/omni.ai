"""
Load and merge per-model LLM profiles with shared fragments (e.g. tool catalog).

Profiles live in pcss_llm_app/llm_profiles/*.yaml; shared text in _shared.yaml.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

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


def merge_profile_with_shared(profile: Dict[str, Any], shared: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Mutates and returns profile with tool catalog appended; pops tool_catalog key."""
    if not shared:
        return profile
    tc = profile.pop("tool_catalog", "full")
    if isinstance(tc, str):
        tc = tc.strip().lower()
    _append_tool_catalog(profile, shared, tc)
    return profile


def load_llm_profile(
    model_name: str,
    profiles_dir: str,
) -> Tuple[str, int, str, int]:
    """
    Load YAML for the given model name and return the same tuple as MainWindow._get_llm_profile_data:
    (instructions, max_tokens, system_prompt_additions, context_window)
    """
    safe_model_name = model_name.replace(":", "-")
    target_file = os.path.join(profiles_dir, f"{safe_model_name}.yaml")
    if not os.path.exists(target_file):
        target_file = os.path.join(profiles_dir, "default.yaml")

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
