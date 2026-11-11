#!/usr/bin/env python3
"""Install only the reviewed direct F-admin webview page and its existing GO icon."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import socket
import stat
import struct
import sys
import tempfile
import time
import urllib.request
import uuid

ROOT = Path('/home/fasakha/public_html')
SITE_USER = 'fasakha'
HOSTNAME = 'srv1836524'
RELEASE = 'f-admin-webview-direct-20261111'
REPOSITORY = 'https://raw.githubusercontent.com/omarmakramelbaz-hub/F-admin'
PREFIX = 'deployment/webview-direct-20261111'
HTML_SOURCE = 'web-preview/index.html'
HTML_TARGET = 'public/f-admin-webview.html'
ICON_SOURCE = 'assets/dashboard-icon.png'
ICON_TARGET = 'public/f-admin-dashboard-icon.png'
ICON_SHA256 = 'f006ba15ad15de9f51c7179e4556b3ac750cd758a033fa9328a155f7e00e3168'
MAPPINGS = {HTML_SOURCE: HTML_TARGET, ICON_SOURCE: ICON_TARGET}
TARGETS = frozenset(MAPPINGS.values())
BASELINES = {HTML_TARGET: 'b0b75f380fbdedea2a75d4c70388614ef56bee6d8f0a0fcd9c87458cf65288a0', ICON_TARGET: None}
BACKUPS = Path('/root/fasakhansta-f-admin-direct-webview-backups')
# Share the previous opening installer's lock: both releases replace this HTML.
LOCK = Path('/var/lock/fasakhansta-f-admin-webview-opening.lock')
MAX_HTML = 256 * 1024
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 20 * 1024 * 1024
SHA256 = re.compile(r'^[a-f0-9]{64}$')
REVISION = re.compile(r'^[a-f0-9]{40}$')
ORIGIN = 'https://fasakhaninja.com'
LOGIN_PATH = '/admin/login'


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_manifest(payload):
    need(isinstance(payload, list) and len(payload) == 2, 'Exactly two manifest entries are required')
    sources, targets = set(), set()
    for entry in payload:
        need(isinstance(entry, dict) and set(entry) == {'source_path', 'target_path', 'sha256', 'baseline_sha256'}, 'Invalid manifest entry')
        source, target = entry['source_path'], entry['target_path']
        need(isinstance(source, str) and source in MAPPINGS and MAPPINGS[source] == target
             and source not in sources and target not in targets, 'Manifest mapping is not uniquely allowlisted')
        for path in (source, target):
            parts = PurePosixPath(path)
            need(not parts.is_absolute() and '..' not in parts.parts and str(parts) == path, 'Unsafe manifest path')
        need(isinstance(entry['sha256'], str) and SHA256.fullmatch(entry['sha256']), 'Invalid source SHA256')
        if target == ICON_TARGET:
            need(entry['sha256'] == ICON_SHA256, 'Reviewed existing GO icon hash mismatch')
        need(entry['baseline_sha256'] == BASELINES[target], 'Unexpected destination baseline: ' + target)
        sources.add(source); targets.add(target)
    need(sources == set(MAPPINGS) and targets == TARGETS, 'The manifest must contain the reviewed direct page and GO PNG only')
    return payload


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        raise RuntimeError('Unexpected HTTP redirect')


HTTP = urllib.request.build_opener(NoRedirect())


def download(url, limit, content_type=None):
    need(url.startswith('https://'), 'HTTPS is required')
    request = urllib.request.Request(url, headers={'User-Agent': 'F-admin-Direct-Webview-Installer', 'Accept': '*/*'})
    with HTTP.open(request, timeout=45) as response:
        need(response.status == 200 and response.geturl() == url, 'Unexpected download response')
        if content_type is not None:
            need(response.headers.get_content_type() == content_type, 'Unexpected public content type')
        data = response.read(limit + 1)
    need(len(data) <= limit, 'Download exceeds reviewed size limit')
    return data


class PageMarkers(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.release = False
        self.frames = []
        self.retry = False
        self.loading = False
        self.loading_hidden = False
        self.fallback = False
        self.base = False
        self.opening = False
        self.headers = False
        self.icons = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.release |= tag == 'body' and attrs.get('data-release') == RELEASE
        self.opening |= tag in ('video', 'audio', 'source') or attrs.get('id') == 'opening' or 'opening' in attrs.get('class', '').split() or any(key.startswith('data-opening') for key in attrs)
        if tag == 'img':
            self.opening |= attrs.get('src', '').lower().split('?', 1)[0].endswith('.gif')
        if tag == 'link' and attrs.get('rel') in ('icon', 'apple-touch-icon'):
            self.icons.append(attrs)
        if tag == 'header':
            self.headers = True
        if tag == 'base':
            self.base = True
        if tag == 'iframe':
            self.frames.append(attrs)
        if tag == 'button' and attrs.get('id') == 'retry' and attrs.get('type') == 'button':
            self.retry = True
        if attrs.get('id') == 'loading':
            self.loading = True
            self.loading_hidden = 'hidden' in attrs
        if tag == 'a' and attrs.get('href') == LOGIN_PATH and attrs.get('target') == '_top':
            self.fallback = True


def validate_page(data):
    need(len(data) <= MAX_HTML, 'HTML exceeds reviewed size limit')
    page = PageMarkers()
    page.feed(data.decode('utf-8'))
    need(page.release and not page.base, 'Missing release marker or unexpected base URL')
    need(len(page.frames) == 1, 'Exactly one dashboard iframe is required')
    frame = page.frames[0]
    need(frame.get('id') == 'dashboard' and frame.get('src') == LOGIN_PATH
         and 'sandbox' not in frame and 'srcdoc' not in frame, 'The dashboard iframe must preserve its same-origin context')
    policy = {}
    for directive in frame.get('allow', '').split(';'):
        parts = directive.split()
        if parts:
            policy[parts[0]] = parts[1:]
    need(all(name in policy and (not policy[name] or "'self'" in policy[name]) for name in ('camera', 'microphone', 'geolocation')),
         'Same-origin camera/microphone/geolocation delegation is missing')
    need(page.retry and page.loading and page.fallback, 'Loading, retry and same-origin direct fallback controls are required')
    need(page.loading_hidden, 'The direct webview must keep its error overlay hidden initially')
    need(not page.opening, 'The direct webview must not contain video, GIF, or an opening screen')
    need(not page.headers, 'The removed top header must not return')
    need(len(page.icons) == 2 and {icon.get('rel') for icon in page.icons} == {'icon', 'apple-touch-icon'}
         and all(icon.get('href') == '/' + ICON_TARGET[len('public/'):] for icon in page.icons)
         and next(icon for icon in page.icons if icon.get('rel') == 'icon').get('type') == 'image/png',
         'Both favicon links must use the reviewed same-origin GO PNG')
    return page


def validate_assets(files):
    need(set(files) == TARGETS, 'Unexpected release roster')
    validate_page(files[HTML_TARGET])
    icon = files[ICON_TARGET]
    need(33 <= len(icon) <= MAX_FILE and icon[:8] == b'\x89PNG\r\n\x1a\n'
         and icon[8:16] == b'\x00\x00\x00\rIHDR', 'Expected a bounded PNG icon')
    width, height = struct.unpack_from('>II', icon, 16)
    need((width, height) == (1024, 1024) and digest(icon) == ICON_SHA256,
         'Expected the exact reviewed 1024x1024 existing GO icon')


def read_release(revision, manifest_hash):
    manifest_bytes = download(f'{REPOSITORY}/{revision}/{PREFIX}/manifest.json', 16 * 1024)
    need(digest(manifest_bytes) == manifest_hash, 'Pinned manifest hash mismatch')
    entries = validate_manifest(json.loads(manifest_bytes.decode('utf-8')))
    files, total = {}, len(manifest_bytes)
    for entry in entries:
        source = entry['source_path']
        data = download(f'{REPOSITORY}/{revision}/{source}', MAX_HTML if source == HTML_SOURCE else MAX_FILE)
        total += len(data)
        need(total <= MAX_TOTAL and digest(data) == entry['sha256'], 'Release file hash/total size mismatch: ' + source)
        files[entry['target_path']] = data
    validate_assets(files)
    return entries, files


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def directory_identity(info):
    return identity(info)[:5]


class Target:
    """Hold directory descriptors so writes never follow an application symlink."""
    def __init__(self, relative, user, stack):
        need(relative in TARGETS, 'Unexpected destination path')
        self.relative = relative
        self.path = ROOT / relative
        self.user = user
        self.published = None
        self.chain = []
        need(ROOT.resolve() == ROOT, 'Application root must not traverse symlinks')
        root_info = ROOT.lstat()
        need(stat.S_ISDIR(root_info.st_mode) and root_info.st_uid == user.pw_uid, 'Unexpected application root owner')
        self.root_identity = directory_identity(root_info)
        fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, fd)
        need(directory_identity(os.fstat(fd)) == self.root_identity, 'Application root changed')
        for name in PurePosixPath(relative).parts[:-1]:
            before = os.stat(name, dir_fd=fd, follow_symlinks=False)
            need(stat.S_ISDIR(before.st_mode) and before.st_uid in (0, user.pw_uid)
                 and not before.st_mode & 0o002, 'Unsafe application parent: ' + relative)
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            stack.callback(os.close, child)
            need(directory_identity(os.fstat(child)) == directory_identity(before), 'Application parent changed')
            self.chain.append((fd, name, child, directory_identity(before)))
            fd = child
        self.fd = fd
        self.name = PurePosixPath(relative).name
        self.check()

    def check(self):
        need(directory_identity(ROOT.lstat()) == self.root_identity, 'Application root changed')
        for parent, name, child, expected in self.chain:
            need(directory_identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected
                 and directory_identity(os.fstat(child)) == expected, 'Application parent changed')

    def read(self):
        self.check()
        try:
            before = os.stat(self.name, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        need(stat.S_ISREG(before.st_mode) and before.st_uid in (0, self.user.pw_uid)
             and before.st_nlink == 1 and not before.st_mode & 0o002 and before.st_size <= MAX_FILE,
             'Unsafe application file: ' + self.relative)
        fd = os.open(self.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            need(identity(os.fstat(fd)) == identity(before), 'Application file changed')
            data = bytearray()
            while len(data) <= before.st_size:
                part = os.read(fd, min(65536, before.st_size + 1 - len(data)))
                if not part:
                    break
                data.extend(part)
            need(len(data) == before.st_size and identity(os.fstat(fd)) == identity(before), 'Application file changed')
        finally:
            os.close(fd)
        return {'identity': identity(before), 'data': bytes(data), 'mode': stat.S_IMODE(before.st_mode),
                'uid': before.st_uid, 'gid': before.st_gid}

    def write(self, data, expected, original=None):
        self.check()
        need(self.read() == expected, 'Concurrent application change: ' + self.relative)
        name = '.f-admin-direct-webview-' + uuid.uuid4().hex
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            os.fchown(fd, original['uid'] if original else self.user.pw_uid, original['gid'] if original else self.user.pw_gid)
            os.fchmod(fd, original['mode'] if original else 0o644)
            with os.fdopen(fd, 'wb', closefd=False) as output:
                output.write(data)
                output.flush()
            os.fsync(fd)
            self.check()
            need(self.read() == expected, 'Concurrent application change: ' + self.relative)
            os.replace(name, self.name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            published = os.fstat(fd)
            self.published = {'identity': identity(published), 'data': data,
                              'mode': stat.S_IMODE(published.st_mode),
                              'uid': published.st_uid, 'gid': published.st_gid}
            os.fsync(self.fd)
        finally:
            os.close(fd)
            try:
                os.unlink(name, dir_fd=self.fd)
            except FileNotFoundError:
                pass
        current = self.read()
        need(current == self.published, 'Atomic write verification failed')
        return current

    def remove(self, expected):
        self.check()
        need(self.read() == expected, 'Concurrent application change during rollback')
        os.unlink(self.name, dir_fd=self.fd)
        os.fsync(self.fd)


def check_login_capability(revision):
    url = ORIGIN + LOGIN_PATH + '?f_admin_direct_webview_verify=' + revision
    request = urllib.request.Request(url, headers={'User-Agent': 'F-admin-Direct-Webview-Installer', 'Accept': 'text/html'})
    with HTTP.open(request, timeout=30) as response:
        need(response.status == 200 and response.geturl() == url, 'The existing login page is not available')
        for value in response.headers.get_all('X-Frame-Options', []):
            need(all(token.strip().upper() == 'SAMEORIGIN' for token in value.split(',')), 'The login page denies same-origin framing')
        for policy in response.headers.get_all('Content-Security-Policy', []):
            for directive in policy.split(';'):
                parts = directive.split()
                if parts and parts[0].lower() == 'frame-ancestors':
                    allowed = {"'self'", ORIGIN, ORIGIN + '/', 'https:', '*'}
                    need("'none'" not in parts[1:] and bool(allowed.intersection(parts[1:])), 'The login page CSP denies same-origin framing')
        need(b'<html' in response.read(4096).lower(), 'The existing login endpoint did not return HTML')


def smoke(revision, files):
    for target, data in files.items():
        url = ORIGIN + '/' + target[len('public/'):] + '?direct_webview_verify=' + revision
        served = download(url, MAX_HTML if target == HTML_TARGET else MAX_FILE,
                          'text/html' if target == HTML_TARGET else 'image/png')
        need(digest(served) == digest(data), 'The reviewed webview release is not served: ' + target)
    validate_assets(files)
    check_login_capability(revision)


def installation_order(changed):
    need(set(changed) <= TARGETS, 'Unexpected publication target')
    return [target for target in (ICON_TARGET, HTML_TARGET) if target in changed]


def preflight(entries, files, user, stack):
    targets = {entry['target_path']: Target(entry['target_path'], user, stack) for entry in entries}
    before = {path: target.read() for path, target in targets.items()}
    changed = []
    for entry in entries:
        path, prior = entry['target_path'], before[entry['target_path']]
        if prior is not None and digest(prior['data']) == entry['sha256']:
            continue
        baseline = entry['baseline_sha256']
        need(prior is None and baseline is None or prior is not None and baseline is not None
             and digest(prior['data']) == baseline, 'Existing destination differs from reviewed baseline: ' + path)
        changed.append(path)
    return targets, before, changed


def rollback(written, targets, before):
    complete = True
    for path in reversed(list(written)):
        try:
            published = written[path] or targets[path].published
            if published is not None:
                prior = before[path]
                if prior is None:
                    targets[path].remove(published)
                else:
                    targets[path].write(prior['data'], published, prior)
        except Exception:
            complete = False
    return complete


def verify_private_directory(path):
    if not path.exists():
        path.mkdir(mode=0o700)
    info = path.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700
         and path.resolve() == path, 'Backup directory must be private and root-owned')


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as output:
            output.write(data)
            output.flush()
        os.fsync(fd)
    finally:
        os.close(fd)


def install(revision, manifest_hash):
    need(os.geteuid() == 0 and socket.gethostname().split('.')[0] == HOSTNAME, 'Fixed production identity required')
    os.umask(0o077)
    user = pwd.getpwnam(SITE_USER)
    entries, files = read_release(revision, manifest_hash)
    lock_fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(lock_fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
             and not stat.S_IMODE(info.st_mode) & 0o077, 'Unsafe production lock')
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        with ExitStack() as stack:
            targets, before, changed = preflight(entries, files, user, stack)
            verify_private_directory(BACKUPS)
            backup = Path(tempfile.mkdtemp(prefix=revision[:12] + '-', dir=BACKUPS))
            os.chmod(backup, 0o700)
            record = {'release': RELEASE, 'revision': revision, 'created_at': datetime.now(timezone.utc).isoformat(), 'files': {}}
            for path in changed:
                prior = before[path]
                record['files'][path] = None if prior is None else {key: prior[key] for key in ('mode', 'uid', 'gid')}
                if prior is not None:
                    saved = backup / path
                    saved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    private_write(saved, prior['data'])
            private_write(backup / 'manifest.json', json.dumps(record, indent=2).encode('utf-8'))
            written = {}
            try:
                for path in installation_order(changed):
                    written[path] = None
                    written[path] = targets[path].write(files[path], before[path], before[path])
                for attempt in range(3):
                    try:
                        smoke(revision, files)
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        time.sleep(2)
                print(json.dumps({'status': 'F_ADMIN_DIRECT_WEBVIEW_READY', 'revision': revision,
                                  'url': ORIGIN + '/f-admin-webview.html',
                                  'changed_files': len(written), 'backup': str(backup), 'database_writes': 0}))
            except BaseException:
                complete = rollback(written, targets, before)
                print('F_ADMIN_DIRECT_WEBVIEW_ROLLBACK_' + ('RESTORED' if complete else 'NEEDS_REVIEW'), file=sys.stderr)
                raise
    finally:
        os.close(lock_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--check-local', type=Path)
    args = parser.parse_args()
    need(REVISION.fullmatch(args.revision), 'Pinned 40-character revision required')
    if args.check_local is not None:
        root = args.check_local.resolve()
        manifest = (root / PREFIX / 'manifest.json').read_bytes()
        entries = validate_manifest(json.loads(manifest.decode('utf-8')))
        files, total = {}, len(manifest)
        for entry in entries:
            path = root / entry['source_path']
            need(root in path.resolve().parents and path.is_file() and not path.is_symlink(), 'Unsafe local release source')
            limit = MAX_HTML if entry['target_path'] == HTML_TARGET else MAX_FILE
            need(path.stat().st_size <= limit, 'Local source exceeds reviewed size limit')
            data = path.read_bytes(); total += len(data)
            need(total <= MAX_TOTAL and digest(data) == entry['sha256'], 'Local source hash/total size mismatch')
            files[entry['target_path']] = data
        validate_assets(files)
        print('F_ADMIN_DIRECT_WEBVIEW_LOCAL_MANIFEST_OK')
        return
    need(isinstance(args.manifest_sha256, str) and SHA256.fullmatch(args.manifest_sha256), 'Pinned manifest SHA256 required')
    install(args.revision, args.manifest_sha256)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('F_ADMIN_DIRECT_WEBVIEW_FAILED: ' + str(error), file=sys.stderr)
        sys.exit(1)
