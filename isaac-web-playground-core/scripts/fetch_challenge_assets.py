"""Fetch pinned simulation assets into ignored uploads; never touches user assets."""
import hashlib, json, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'uploads' / 'challenges'
CHECKS = json.loads((ROOT / 'configs' / 'challenge-assets.lock.json').read_text(encoding='utf-8'))
DUCK = 'a2e7f327344eda402467af83053f6e33ca6bcdb7'
POLICIES = '590b986bd8c0d50ae02cb3ea2f59c463b6828168'

def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    expected = CHECKS.get(dest.relative_to(OUT).as_posix())
    if dest.exists():
        if expected and hashlib.sha256(dest.read_bytes()).hexdigest() != expected:
            raise ValueError('Existing asset checksum mismatch: ' + str(dest))
        return
    data = urllib.request.urlopen(url, timeout=120).read()
    if expected and hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Download checksum mismatch: ' + url)
    tmp = dest.with_suffix(dest.suffix + '.part')
    tmp.write_bytes(data)
    tmp.replace(dest)
    print(dest.relative_to(ROOT), len(data), flush=True)

def main():
    api = 'https://api.github.com/repos/osrbot/microduck-ros2-isaac/git/trees/' + DUCK + '?recursive=1'
    tree = json.load(urllib.request.urlopen(api, timeout=60))['tree']
    prefix = 'assets/isaac/robot_allcollisions/'
    for item in tree:
        name = item['path']
        if item['type'] == 'blob' and name.startswith(prefix):
            dest = OUT / 'microduck' / name[len(prefix):]
            download('https://raw.githubusercontent.com/osrbot/microduck-ros2-isaac/' + DUCK + '/' + name, dest)
            data = dest.read_bytes()
            blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if blob != item['sha']: raise ValueError('Asset checksum mismatch: ' + name)
    for name in ['alpha_stand', 'alpha_walking', 'alpha_sitstand', 'roulade', 'ball_kick_right']:
        download(f'https://raw.githubusercontent.com/pollen-robotics/microduck/{POLICIES}/policies/{name}.onnx', OUT / 'microduck' / 'policies' / (name + '.onnx'))
    download('https://github.com/jixinyan/OpenSO-101/releases/download/v0.1.0/SO-ARM101-USD.usd', OUT / 'so101' / 'SO-ARM101-USD.usd')
    download('https://raw.githubusercontent.com/osrbot/microduck-ros2-isaac/' + DUCK + '/NOTICE-MICRODUCK.md', OUT / 'microduck' / 'NOTICE-MICRODUCK.md')
    manifest = {p.relative_to(OUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and p.name != 'sha256.json'}
    (OUT / 'sha256.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
if __name__ == '__main__': main()
