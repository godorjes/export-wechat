"""Repeatable Windows packaging; optional ASR is excluded only in the core profile."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUST_URL = 'https://github.com/Wangnov/rust-silk/releases/download/v0.1.3/rust-silk-x86_64-pc-windows-msvc.zip'
RUST_SHA256 = '44a01bc0f3ec3ec6f6044b656869b0dd7c298329d12f07c7f7a846be72a89504'


def prepare_decoder():
    tools = ROOT / 'tools'
    tools.mkdir(exist_ok=True)
    # Always verify the archive; an existing unverified executable is never reused.
    archive = tools / 'rust-silk-v0.1.3.zip'
    if not archive.is_file():
        urllib.request.urlretrieve(RUST_URL, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != RUST_SHA256:
        raise RuntimeError('rust-silk archive SHA256 mismatch')
    with zipfile.ZipFile(archive) as z:
        matches = [n for n in z.namelist() if n.endswith('/rust-silk.exe') or n == 'rust-silk.exe']
        if len(matches) != 1:
            raise RuntimeError('Invalid rust-silk release contents')
        (tools / 'rust-silk.exe').write_bytes(z.read(matches[0]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--profile', choices=('core', 'full'), default='core')
    p.add_argument('--layout', choices=('onefile', 'onedir'), default='onefile')
    p.add_argument('--distdir', default='dist')
    a = p.parse_args()
    prepare_decoder()
    name = 'Export-WeChat-V1' + ('-Full' if a.profile == 'full' else '')
    dist = (ROOT / a.distdir).resolve()
    dist.mkdir(parents=True, exist_ok=True)
    work = ROOT / 'build' / f'{a.profile}-{a.layout}'
    work.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
           '--' + a.layout, '--windowed', '--name', name, '--icon', str(ROOT / 'assets/app.ico'),
           '--distpath', str(dist), '--workpath', str(work), '--specpath', str(work),
           '--add-data', str(ROOT / 'assets') + ';assets']
    modules = ['wechatauto', 'winsdk', 'uiautomation', 'comtypes', 'imageio_ffmpeg']
    if a.profile == 'full':
        modules += ['sherpa_onnx', 'soundfile']
    else:
        for module in ('sherpa_onnx', 'sherpa_onnx_core', 'soundfile', '_soundfile_data'):
            cmd += ['--exclude-module', module]
    for module in modules:
        cmd += ['--collect-all', module]
    cmd += ['--hidden-import', 'win32timezone', '--add-binary', str(ROOT / 'tools/rust-silk.exe') + ';tools', str(ROOT / 'app.py')]
    started = time.perf_counter()
    log_path = dist / f'{name}-{a.layout}-build.log'
    with log_path.open('w', encoding='utf8') as log:
        completed = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    if completed.returncode:
        print(log_path.read_text(encoding='utf8', errors='replace')[-5000:])
        raise SystemExit(completed.returncode)
    package = dist / (name + '.exe' if a.layout == 'onefile' else name)
    license_files = ['LICENSE', 'THIRD_PARTY_NOTICES.md', 'README.md',
                     'docs/ACCEPTANCE.md', 'docs/CODE_AUDIT.md']
    if (ROOT / 'docs/DELIVERY.md').is_file():
        license_files.append('docs/DELIVERY.md')
    if (ROOT / 'docs/UI_ACCOUNT_FOLDED.md').is_file():
        license_files.append('docs/UI_ACCOUNT_FOLDED.md')
    archive = dist / f'{name}-{a.layout}-Windows.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        files = [package] if package.is_file() else package.rglob('*')
        for f in files:
            if f.is_file():
                z.write(f, f.relative_to(dist))
        for f in license_files:
            z.write(ROOT / f, f)
    size = package.stat().st_size if package.is_file() else sum(f.stat().st_size for f in package.rglob('*') if f.is_file())
    report = {'profile': a.profile, 'layout': a.layout, 'package_bytes': size,
              'zip_bytes': archive.stat().st_size, 'build_seconds': round(time.perf_counter()-started, 2),
              'sha256': hashlib.sha256(package.read_bytes()).hexdigest() if package.is_file() else None}
    (dist / f'{name}-{a.layout}-build.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
