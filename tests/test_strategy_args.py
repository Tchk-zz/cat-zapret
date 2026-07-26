"""Strategy argument parsing, Roblox profile and custom strategy saving."""
import json
from pathlib import Path
import tempfile
import unittest
from app.strategy_manager import _clean_token, _tokenize_args, combine_with_roblox


class StrategyArgsTests(unittest.TestCase):

    def test_tokenize_keeps_quoted_paths(self):
        args = _tokenize_args('--wf-tcp=443 --hostlist="lists/list general.txt" --dpi-desync=fake')
        self.assertEqual(args, ['--wf-tcp=443', '--hostlist=lists/list general.txt', '--dpi-desync=fake'])

    def test_clean_unknown_placeholder(self):
        self.assertEqual(_clean_token('%UNKNOWN%,'), '')

    def test_combine_with_roblox_unions_wf_ports(self):
        combined = combine_with_roblox(
            ['--wf-tcp=443', '--filter-tcp=443', '--dpi-desync=fake'],
            ['--wf-udp=443,49152-65535', '--filter-udp=49152-65535', '--dpi-desync=fake'],
        )
        self.assertIn('--wf-tcp=443', combined)
        self.assertIn('--wf-udp=443,49152-65535', combined)
        self.assertIn('--new', combined)

    def test_save_custom_resolves_placeholders(self):
        """A custom strategy pasted with %BIN%/%LISTS% must be saved with
        placeholders resolved so winws.exe doesn't crash at launch."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'bin').mkdir()
            (root / 'bin' / 'winws.exe').write_bytes(b'')
            (root / 'lists').mkdir()
            from app.strategy_manager import StrategyManager
            mgr = StrategyManager(root)
            saved = mgr.save_custom(
                'MyTest',
                '--wf-tcp=443 --hostlist="%LISTS%list-general.txt" --dpi-desync=fake',
            )
            joined = ' '.join(saved.args)
            self.assertNotIn('%LISTS%', joined)
            self.assertIn('list-general.txt', joined)

    # --- tg-ws-proxy integration tests (embedded engine, no subprocess) ---

    def test_roblox_profile_public_constant_exists(self):
        """``ROBLOX_FIX_ARGS`` (no underscore) must be importable as a
        public API. Previously only ``_ROBLOX_FIX_ARGS`` (private) existed,
        forcing callers to reach into bootstrap's privates."""
        from app import bootstrap
        self.assertTrue(hasattr(bootstrap, "ROBLOX_FIX_ARGS"))
        self.assertTrue(bootstrap.ROBLOX_FIX_ARGS)
        # The private alias must still exist for backwards-compat.
        self.assertTrue(hasattr(bootstrap, "_ROBLOX_FIX_ARGS"))
        # Both must point at the same string.
        self.assertEqual(bootstrap.ROBLOX_FIX_ARGS, bootstrap._ROBLOX_FIX_ARGS)

    def test_load_roblox_profile_returns_args_and_description(self):
        """load_roblox_profile() must return a non-empty (args, description)
        tuple. The args must contain the Roblox UDP port range so the
        bypass actually applies to game traffic."""
        from app.bootstrap import load_roblox_profile
        args, desc = load_roblox_profile()
        self.assertIsInstance(args, str)
        self.assertIsInstance(desc, str)
        self.assertTrue(args.strip(), "Roblox args must not be empty")
        self.assertTrue(desc.strip(), "Roblox description must not be empty")
        # Critical markers that must be present in any Roblox profile.
        self.assertIn("--filter-udp=49152-65535", args)
        self.assertIn("--ipset-ip=", args)
        self.assertIn("roblox.com", args)

    def test_load_roblox_profile_falls_back_on_missing_json(self):
        """If the JSON file is missing (e.g. an older install was upgraded
        in place), load_roblox_profile() must fall back to the hardcoded
        ROBLOX_FIX_ARGS string instead of raising."""
        from app import bootstrap
        # Force the path lookup to fail.
        orig = bootstrap._roblox_profile_path
        try:
            bootstrap._roblox_profile_path = lambda: None
            args, desc = bootstrap.load_roblox_profile()
            self.assertEqual(args, bootstrap.ROBLOX_FIX_ARGS)
            self.assertTrue(desc)
        finally:
            bootstrap._roblox_profile_path = orig

    def test_load_roblox_profile_falls_back_on_corrupt_json(self):
        """A corrupt or hand-edited-but-broken JSON must NOT crash the
        loader — it falls back to the hardcoded constant."""
        from app import bootstrap
        orig = bootstrap._roblox_profile_path
        try:
            # Simulate a corrupt JSON file by returning a path to a temp
            # file containing garbage.
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as f:
                f.write("this is not json {{{ ,,, ")
                bad_path = Path(f.name)
            bootstrap._roblox_profile_path = lambda: bad_path
            args, desc = bootstrap.load_roblox_profile()
            self.assertEqual(args, bootstrap.ROBLOX_FIX_ARGS)
            self.assertTrue(desc)
        finally:
            bootstrap._roblox_profile_path = orig
            try:
                bad_path.unlink()
            except OSError:
                pass

    def test_roblox_profile_json_file_is_valid(self):
        """The shipped ``roblox_profile.json`` at the project root must be
        valid JSON with at least an ``args`` field."""
        from app.bootstrap import _roblox_profile_path
        p = _roblox_profile_path()
        self.assertIsNotNone(p, "roblox_profile.json must exist at project root")
        if p is not None:
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertIn("args", data)
            self.assertIsInstance(data["args"], str)
            self.assertTrue(data["args"].strip())

    # --- Dynamic User-Agent ---
