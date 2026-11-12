#!/usr/bin/env python3
"""Install one reviewed same-origin F-admin web preview; do not change the application."""
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
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid

ROOT = Path('/home/fasakha/public_html')
SITE_USER = 'fasakha'
HOSTNAME = 'srv1836524'
RELEASE = 'f-admin-webview-20261111'
REPOSITORY = 'https://raw.githubusercontent.com/omarmakramelbaz-hub/F-admin'
PREFIX = 'deployment/webview-20261111'
SOURCE_PATH = 'web-preview/index.html'
TARGET_PATH = 'public/f-admin-webview.html'
BACKUPS = Path('/root/fasakhansta-f-admin-webview-backups')
LOCK = Path('/var/lock/fasakhansta-f-admin-webview.lock')
MAX_FILE = 256 * 1024
MAX_TOTAL = 512 * 1024
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
    need(isinstance(payload, list) and len(payload) == 1, 'Exactly one manifest entry is required')
    entry = payload[0]
    need(isinstance(entry, dict) and set(entry) == {'source_path', 'target_path', 'sha256', 'baseline_sha256'}, 'Invalid manifest entry')
    need(entry['source_path'] == SOURCE_PATH and entry['target_path'] == TARGET_PATH, 'Manifest mapping is not allowlisted')
    for path in (entry['source_path'], entry['target_path']):
        parts = PurePosixPath(path)
        need(not parts.is_absolute() and '..' not in parts.parts and str(parts) == path, 'Unsafe manifest path')
    need(isinstance(entry['sha256'], str) and SHA256.fullmatch(entry['sha256']), 'Invalid source SHA256')
    need(entry['baseline_sha256'] is None, 'Only a reviewed addition is allowed')
    return entry


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        raise RuntimeError('Unexpected HTTP redirect')


HTTP = urllib.request.build_opener(NoRedirect())


def download(url, limit):
    need(url.startswith('https://'), 'HTTPS is required')
    request = urllib.request.Request(url, headers={'User-Agent': 'F-admin-Webview-Installer', 'Accept': 'text/html,application/json'})
    with HTTP.open(request, timeout=45) as response:
        need(response.status == 200 and response.geturl() == url, 'Unexpected download response')
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
        self.fallback = False
        self.base = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.release |= attrs.get('data-release') == RELEASE
        if tag == 'base':
            self.base = True
        if tag == 'iframe':
            self.frames.append(attrs)
        if tag == 'button' and attrs.get('id') == 'retry' and attrs.get('type') == 'button':
            self.retry = True
        if attrs.get('id') == 'loading':
            self.loading = True
        if tag == 'a' and attrs.get('href') == LOGIN_PATH and attrs.get('target') == '_top':
            self.fallback = True


def validate_page(data):
    need(len(data) <= MAX_FILE, 'HTML exceeds reviewed size limit')
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
    need(all(name in policy and (not policy[name] or "'self'" in policy[name]) for name in ('microphone', 'geolocation')),
         'Same-origin microphone/geolocation delegation is missing')
    need(page.retry and page.loading and page.fallback, 'Loading, retry and same-origin direct fallback controls are required')
    return page


def read_release(revision, manifest_hash):
    manifest_bytes = download(f'{REPOSITORY}/{revision}/{PREFIX}/manifest.json', 16 * 1024)
    need(digest(manifest_bytes) == manifest_hash, 'Pinned manifest hash mismatch')
    entry = validate_manifest(json.loads(manifest_bytes.decode('utf-8')))
    data = download(f'{REPOSITORY}/{revision}/{SOURCE_PATH}', MAX_FILE)
    need(len(manifest_bytes) + len(data) <= MAX_TOTAL, 'Release exceeds reviewed total size limit')
    need(digest(data) == entry['sha256'], 'Downloaded HTML hash mismatch')
    validate_page(data)
    return entry, data


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def directory_identity(info):
    return identity(info)[:5]


class Target:
    """Hold directory descriptors so writes never follow an application symlink."""
    def __init__(self, relative, user, stack):
        need(relative == TARGET_PATH, 'Unexpected destination path')
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
        name = '.f-admin-webview-' + uuid.uuid4().hex
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
    url = ORIGIN + LOGIN_PATH + '?f_admin_webview_verify=' + revision
    request = urllib.request.Request(url, headers={'User-Agent': 'F-admin-Webview-Installer', 'Accept': 'text/html'})
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


def smoke(revision, data):
    served = download(ORIGIN + '/f-admin-webview.html?webview_verify=' + revision, MAX_FILE)
    need(digest(served) == digest(data), 'The reviewed web preview is not served')
    validate_page(served)
    check_login_capability(revision)


def preflight(data, user, stack):
    target = Target(TARGET_PATH, user, stack)
    before = target.read()
    unchanged = before is not None and digest(before['data']) == digest(data)
    need(before is None or unchanged, 'Existing web-preview file differs from the reviewed addition')
    return target, not unchanged


def rollback(target, published):
    if published is None:
        return True
    try:
        target.remove(published)
        return True
    except Exception:
        return False


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
    entry, data = read_release(revision, manifest_hash)
    lock_fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(lock_fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
             and not stat.S_IMODE(info.st_mode) & 0o077, 'Unsafe production lock')
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        with ExitStack() as stack:
            target, changed = preflight(data, user, stack)
            verify_private_directory(BACKUPS)
            backup = Path(tempfile.mkdtemp(prefix=revision[:12] + '-', dir=BACKUPS))
            os.chmod(backup, 0o700)
            record = {'release': RELEASE, 'revision': revision, 'created_at': datetime.now(timezone.utc).isoformat(),
                      'source_path': SOURCE_PATH, 'target_path': TARGET_PATH, 'sha256': entry['sha256'], 'added': changed}
            private_write(backup / 'manifest.json', json.dumps(record, indent=2).encode('utf-8'))
            published = None
            try:
                if changed:
                    published = target.write(data, None)
                for attempt in range(3):
                    try:
                        smoke(revision, data)
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        time.sleep(2)
                print(json.dumps({'status': 'F_ADMIN_WEBVIEW_READY', 'revision': revision,
                                  'url': ORIGIN + '/f-admin-webview.html',
                                  'changed_files': int(changed), 'backup': str(backup), 'database_writes': 0}))
            except BaseException:
                complete = rollback(target, published or target.published) if changed else True
                print('F_ADMIN_WEBVIEW_ROLLBACK_' + ('RESTORED' if complete else 'NEEDS_REVIEW'), file=sys.stderr)
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
        entry = validate_manifest(json.loads(manifest.decode('utf-8')))
        path = root / SOURCE_PATH
        need(root in path.resolve().parents and path.is_file() and not path.is_symlink(), 'Unsafe local HTML source')
        data = path.read_bytes()
        need(len(manifest) + len(data) <= MAX_TOTAL and digest(data) == entry['sha256'], 'Local HTML hash/total size mismatch')
        validate_page(data)
        print('F_ADMIN_WEBVIEW_LOCAL_MANIFEST_OK')
        return
    need(isinstance(args.manifest_sha256, str) and SHA256.fullmatch(args.manifest_sha256), 'Pinned manifest SHA256 required')
    install(args.revision, args.manifest_sha256)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('F_ADMIN_WEBVIEW_FAILED: ' + str(error), file=sys.stderr)
        sys.exit(1)
