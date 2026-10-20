"""Fetch pinned simulation assets, optionally reusing a verified local cache."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'uploads' / 'challenges'
CHECKS = json.loads((ROOT / 'configs' / 'challenge-assets.lock.json').read_text(encoding='utf-8'))
DUCK = 'a2e7f327344eda402467af83053f6e33ca6bcdb7'
POLICIES = '590b986bd8c0d50ae02cb3ea2f59c463b6828168'


def checked_file(directory, name, expected):
    base = directory.resolve()
    file = (base / name).resolve()
    if not file.is_relative_to(base):
        raise ValueError('Asset escapes source: ' + name)
    if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
        raise ValueError('Asset checksum mismatch: ' + name)
    return file


def asset_url(name):
    if name == 'so101/SO-ARM101-USD.usd':
        return 'https://github.com/jixinyan/OpenSO-101/releases/download/v0.1.0/SO-ARM101-USD.usd'
    if name.startswith('microduck/policies/'):
        return f'https://raw.githubusercontent.com/pollen-robotics/microduck/{POLICIES}/policies/' + name.removeprefix('microduck/policies/')
    if name == 'microduck/NOTICE-MICRODUCK.md':
        return f'https://raw.githubusercontent.com/osrbot/microduck-ros2-isaac/{DUCK}/NOTICE-MICRODUCK.md'
    if name.startswith('microduck/'):
        return f'https://raw.githubusercontent.com/osrbot/microduck-ros2-isaac/{DUCK}/assets/isaac/robot_allcollisions/' + name.removeprefix('microduck/')
    raise ValueError('Unknown asset: ' + name)


def fetch(cache=None):
    for name, expected in CHECKS.items():
        dest = OUT / name
        if dest.exists():
            checked_file(OUT, name, expected)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if cache is not None and (cache / name).exists():
            source = checked_file(cache, name, expected)
            data = source.read_bytes()
        else:
            data = urllib.request.urlopen(asset_url(name), timeout=120).read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Download checksum mismatch: ' + name)
        temp = dest.with_suffix(dest.suffix + '.part')
        temp.write_bytes(data)
        temp.replace(dest)
        print(name, len(data), flush=True)
    (OUT / 'sha256.json').write_text(json.dumps(CHECKS, indent=2), encoding='utf-8')


def export_cache(destination):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError('Choose a new cache directory')
    # Validate every source before creating anything, and copy only locked assets.
    sources = [(name, checked_file(OUT, name, digest)) for name, digest in CHECKS.items()]
    destination.mkdir(parents=True)
    for name, source in sources:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    print(f'Exported {len(sources)} verified assets to {destination}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--export-cache', type=Path)
    args = parser.parse_args()
    if args.export_cache:
        export_cache(args.export_cache)
    else:
        fetch(args.cache)


if __name__ == '__main__':
    main()
