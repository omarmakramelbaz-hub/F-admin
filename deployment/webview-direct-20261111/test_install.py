"""Run locally with unittest; production paths and network are never used."""
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location('direct_webview_install', HERE / 'install.py')
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / INSTALL.HTML_SOURCE).read_bytes()
        self.icon = (ROOT / INSTALL.ICON_SOURCE).read_bytes()
        self.files = {INSTALL.ICON_TARGET: self.icon, INSTALL.HTML_TARGET: self.html}
        self.entries = [
            {'source_path': INSTALL.ICON_SOURCE, 'target_path': INSTALL.ICON_TARGET,
             'sha256': INSTALL.digest(self.icon), 'baseline_sha256': None},
            {'source_path': INSTALL.HTML_SOURCE, 'target_path': INSTALL.HTML_TARGET,
             'sha256': INSTALL.digest(self.html), 'baseline_sha256': INSTALL.BASELINES[INSTALL.HTML_TARGET]},
        ]

    def test_reviewed_scope_and_assets(self):
        self.assertEqual(INSTALL.BASELINES[INSTALL.HTML_TARGET], 'b0b75f380fbdedea2a75d4c70388614ef56bee6d8f0a0fcd9c87458cf65288a0')
        self.assertEqual(INSTALL.MAX_HTML, 256 * 1024)
        self.assertEqual(INSTALL.MAX_FILE, 16 * 1024 * 1024)
        self.assertEqual(INSTALL.MAX_TOTAL, 20 * 1024 * 1024)
        INSTALL.validate_manifest(self.entries)
        INSTALL.validate_assets(self.files)
        self.assertEqual(INSTALL.installation_order(INSTALL.TARGETS), [INSTALL.ICON_TARGET, INSTALL.HTML_TARGET])

    def test_manifest_rejects_scope_source_and_baseline_changes(self):
        changes = [
            (0, 'source_path', 'assets/other.png'),
            (0, 'source_path', '../assets/dashboard-icon.png'),
            (0, 'baseline_sha256', '0' * 64),
            (1, 'source_path', '../web-preview/index.html'),
            (1, 'source_path', '/web-preview/index.html'),
            (1, 'target_path', 'public/../.env'),
            (1, 'target_path', '/public/f-admin-webview.html'),
            (1, 'baseline_sha256', None),
            (1, 'sha256', 'invalid'),
            (1, 'target_path', INSTALL.ICON_TARGET),
        ]
        for index, key, value in changes:
            with self.subTest(key=key, value=value):
                changed = deepcopy(self.entries)
                changed[index][key] = value
                with self.assertRaises(RuntimeError):
                    INSTALL.validate_manifest(changed)
        wrong_field = deepcopy(self.entries)
        wrong_field[0]['source_url'] = wrong_field[0].pop('source_path')
        for changed in (wrong_field, self.entries[:1], self.entries + self.entries[:1], self.entries + [{}]):
            with self.assertRaises(RuntimeError):
                INSTALL.validate_manifest(changed)

    def test_page_and_icon_guards(self):
        changes = [
            (b'src="/admin/login"', b'src="https://elsewhere.test/admin/login"'),
            (b'<iframe ', b'<iframe sandbox="allow-scripts" '),
            (b'<iframe ', b'<iframe srcdoc="unexpected" '),
            (b"microphone 'self'", b"microphone 'none'"),
            (b'<main ', b'<video src="/old.mp4"></video><main '),
            (b'<main ', b'<div id="opening"></div><main '),
            (b'<main ', b'<img src="/old.gif"><main '),
            (b'href="/f-admin-dashboard-icon.png"', b'href="https://elsewhere.test/icon.png"'),
            (b'id="loading" hidden', b'id="loading"'),
            (b'<main ', b'<header></header><main '),
        ]
        for old, new in changes:
            self.assertIn(old, self.html)
            with self.subTest(old=old), self.assertRaises(RuntimeError):
                INSTALL.validate_page(self.html.replace(old, new, 1))
        with self.assertRaises(RuntimeError):
            INSTALL.validate_page(b' ' * (INSTALL.MAX_HTML + 1))
        with self.assertRaises(RuntimeError):
            INSTALL.validate_assets({**self.files, INSTALL.ICON_TARGET: b'not a PNG'})
        with self.assertRaises(RuntimeError):
            INSTALL.validate_assets({**self.files, 'public/other': b'x'})

    def test_read_release_uses_only_pinned_sources(self):
        revision = 'a' * 40
        manifest = json.dumps(self.entries).encode()
        expected = [
            f'{INSTALL.REPOSITORY}/{revision}/{INSTALL.PREFIX}/manifest.json',
            f'{INSTALL.REPOSITORY}/{revision}/{INSTALL.ICON_SOURCE}',
            f'{INSTALL.REPOSITORY}/{revision}/{INSTALL.HTML_SOURCE}',
        ]
        responses = dict(zip(expected, (manifest, self.icon, self.html)))
        calls = []

        def download(url, limit):
            calls.append(url)
            data = responses[url]
            self.assertLessEqual(len(data), limit)
            return data

        with patch.object(INSTALL, 'download', download):
            entries, files = INSTALL.read_release(revision, INSTALL.digest(manifest))
            self.assertEqual(entries, self.entries)
            self.assertEqual(files, self.files)
            self.assertEqual(calls, expected)
            with self.assertRaises(RuntimeError):
                INSTALL.read_release(revision, '0' * 64)

    def test_smoke_requires_public_byte_hashes_and_mime_types(self):
        revision = 'b' * 40
        calls = []

        def download(url, limit, content_type=None):
            calls.append((url, content_type))
            return self.icon if '/f-admin-dashboard-icon.png?' in url else self.html

        with patch.object(INSTALL, 'download', download), patch.object(INSTALL, 'check_login_capability') as login:
            INSTALL.smoke(revision, self.files)
            login.assert_called_once_with(revision)
        self.assertEqual(calls, [
            (INSTALL.ORIGIN + '/f-admin-dashboard-icon.png?direct_webview_verify=' + revision, 'image/png'),
            (INSTALL.ORIGIN + '/f-admin-webview.html?direct_webview_verify=' + revision, 'text/html'),
        ])
        with patch.object(INSTALL, 'download', return_value=b'wrong public bytes'), self.assertRaises(RuntimeError):
            INSTALL.smoke(revision, self.files)


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / 'public').mkdir(mode=0o755)
        self.user = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
        self.root_patch = patch.object(INSTALL, 'ROOT', self.root)
        self.root_patch.start()
        self.old_html = b'original reviewed html'
        self.new_html = b'new reviewed html'
        self.new_icon = b'new reviewed icon'
        self.files = {INSTALL.ICON_TARGET: self.new_icon, INSTALL.HTML_TARGET: self.new_html}
        self.entries = [
            {'target_path': INSTALL.ICON_TARGET, 'sha256': INSTALL.digest(self.new_icon), 'baseline_sha256': None},
            {'target_path': INSTALL.HTML_TARGET, 'sha256': INSTALL.digest(self.new_html), 'baseline_sha256': INSTALL.digest(self.old_html)},
        ]
        (self.root / INSTALL.HTML_TARGET).write_bytes(self.old_html)
        (self.root / INSTALL.HTML_TARGET).chmod(0o640)

    def tearDown(self):
        self.root_patch.stop()
        self.temporary.cleanup()

    def test_publish_order_and_idempotence(self):
        with ExitStack() as stack:
            targets, before, changed = INSTALL.preflight(self.entries, self.files, self.user, stack)
            written = {}
            for target in INSTALL.installation_order(changed):
                written[target] = targets[target].write(self.files[target], before[target], before[target])
            self.assertEqual(list(written), [INSTALL.ICON_TARGET, INSTALL.HTML_TARGET])
            self.assertEqual((self.root / INSTALL.HTML_TARGET).stat().st_mode & 0o777, 0o640)
            with ExitStack() as next_stack:
                _, _, changed = INSTALL.preflight(self.entries, self.files, self.user, next_stack)
                self.assertEqual(changed, [])

    def test_rollback_restores_previous_html_and_removes_added_icon(self):
        with ExitStack() as stack:
            targets, before, changed = INSTALL.preflight(self.entries, self.files, self.user, stack)
            written = {}
            for target in INSTALL.installation_order(changed):
                written[target] = targets[target].write(self.files[target], before[target], before[target])
            self.assertTrue(INSTALL.rollback(written, targets, before))
            self.assertEqual((self.root / INSTALL.HTML_TARGET).read_bytes(), self.old_html)
            self.assertEqual((self.root / INSTALL.HTML_TARGET).stat().st_mode & 0o777, 0o640)
            self.assertFalse((self.root / INSTALL.ICON_TARGET).exists())

    def test_baseline_or_existing_addition_change_fails_closed(self):
        for target in (INSTALL.HTML_TARGET, INSTALL.ICON_TARGET):
            with self.subTest(target=target):
                path = self.root / target
                path.write_bytes(b'unreviewed data')
                with ExitStack() as stack, self.assertRaises(RuntimeError):
                    INSTALL.preflight(self.entries, self.files, self.user, stack)
                if target == INSTALL.HTML_TARGET:
                    path.write_bytes(self.old_html)

    def test_symlink_hardlink_and_world_writable_targets_rejected(self):
        path = self.root / INSTALL.ICON_TARGET
        path.symlink_to(self.root / INSTALL.HTML_TARGET)
        with ExitStack() as stack, self.assertRaises(RuntimeError):
            INSTALL.Target(INSTALL.ICON_TARGET, self.user, stack).read()
        path.unlink()
        os.link(self.root / INSTALL.HTML_TARGET, path)
        with ExitStack() as stack, self.assertRaises(RuntimeError):
            INSTALL.Target(INSTALL.ICON_TARGET, self.user, stack).read()
        path.unlink()
        path.write_bytes(b'unsafe')
        path.chmod(0o666)
        with ExitStack() as stack, self.assertRaises(RuntimeError):
            INSTALL.Target(INSTALL.ICON_TARGET, self.user, stack).read()

    def test_parent_swap_and_concurrent_file_change_rejected(self):
        with ExitStack() as stack:
            target = INSTALL.Target(INSTALL.HTML_TARGET, self.user, stack)
            before = target.read()
            (self.root / INSTALL.HTML_TARGET).write_bytes(b'concurrent change')
            with self.assertRaises(RuntimeError):
                target.write(self.new_html, before, before)
            (self.root / 'public').rename(self.root / 'saved-public')
            (self.root / 'public').symlink_to(self.root / 'saved-public', target_is_directory=True)
            with self.assertRaises(RuntimeError):
                target.read()

    def test_scope_and_rollback_do_not_overwrite_unrelated_change(self):
        with ExitStack() as stack, self.assertRaises(RuntimeError):
            INSTALL.Target('public/unapproved', self.user, stack)
        with self.assertRaises(RuntimeError):
            INSTALL.installation_order(['public/unapproved'])
        with ExitStack() as stack:
            targets, before, _ = INSTALL.preflight(self.entries, self.files, self.user, stack)
            published = targets[INSTALL.HTML_TARGET].write(self.new_html, before[INSTALL.HTML_TARGET], before[INSTALL.HTML_TARGET])
            (self.root / INSTALL.HTML_TARGET).write_bytes(b'concurrent after publication')
            self.assertFalse(INSTALL.rollback({INSTALL.HTML_TARGET: published}, targets, before))
            self.assertEqual((self.root / INSTALL.HTML_TARGET).read_bytes(), b'concurrent after publication')


if __name__ == '__main__':
    unittest.main()
