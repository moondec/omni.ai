"""Tests for LLM profile loading and shared tool catalog merge."""
import os
import unittest

from omni_agent.core.llm_profile_loader import load_llm_profile, merge_profile_with_shared


class TestLlmProfileLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "llm_profiles")
        )
        cls.shared_path = os.path.join(cls.profiles_dir, "_shared.yaml")

    def test_shared_yaml_exists(self):
        self.assertTrue(os.path.isfile(self.shared_path), "_shared.yaml must exist")

    def test_default_load_includes_tool_catalog(self):
        instr, max_tok, sys_add, ctx = load_llm_profile("nonexistent-model-xyz", self.profiles_dir)
        self.assertIn("AVAILABLE TOOLS", instr)
        self.assertIn("playwright_navigate", instr)
        self.assertIn("copy_file", instr)
        self.assertGreater(max_tok, 0)
        self.assertEqual(ctx, 0)

    def test_full_has_verbose_headers_compact_does_not(self):
        full, _, _, _ = load_llm_profile("default", self.profiles_dir)
        compact, _, _, _ = load_llm_profile("Mistral-Small-3.2-24b", self.profiles_dir)
        self.assertIn("Workspace — read", full)
        self.assertNotIn("Workspace — read", compact)
        self.assertIn("playwright_navigate", compact)

    def test_merge_respects_tool_catalog_none(self):
        shared = {"tool_catalog": {"full": "TOOLS_FULL", "compact": "TOOLS_COMPACT"}}
        profile = {"instructions": "Hello", "tool_catalog": "none"}
        merge_profile_with_shared(profile, shared)
        self.assertEqual(profile["instructions"], "Hello")

    def test_bielik_context_window(self):
        _, _, _, ctx = load_llm_profile("bielik_11b", self.profiles_dir)
        self.assertEqual(ctx, 32768)


if __name__ == "__main__":
    unittest.main()
