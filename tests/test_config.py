import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcpick3.config import get_mcp_token


class ConfigTests(unittest.TestCase):
    def test_missing_credential(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(get_mcp_token(Path(root)))

    def test_reads_local_file_without_mutating_environment(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            path = Path(root) / ".env.local"
            path.write_text('# Local fixture\nMCD_MCP_TOKEN="fixture-value"\n', encoding="utf-8")
            self.assertEqual(get_mcp_token(Path(root)), "fixture-value")
            self.assertNotIn("MCD_MCP_TOKEN", os.environ)

    def test_environment_has_precedence(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"MCD_MCP_TOKEN": "fixture-env"}):
            (Path(root) / ".env.local").write_text("MCD_MCP_TOKEN=fixture-file\n", encoding="utf-8")
            self.assertEqual(get_mcp_token(Path(root)), "fixture-env")

    def test_does_not_evaluate_shell_code(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            (Path(root) / ".env.local").write_text("MCD_MCP_TOKEN=$(echo fixture)\n", encoding="utf-8")
            self.assertEqual(get_mcp_token(Path(root)), "$(echo fixture)")
