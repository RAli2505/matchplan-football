"""Create auditable identity mapping and local portraits; FIFA ratings are unused."""
import csv
import io
import json
import unicodedata
import zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from functools import lru_cache
from threading import Event

ROOT = Path(__file__).resolve().parent

@lru_cache(maxsize=60000)
def normalize(name):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', name).casefold()
                            if not unicodedata.combining(c) and (c.isalpha() or c.isspace())).split())

def choose(name, rows):
    n = normalize(name)
    exact = [r for r in rows if n in (normalize(r['long_name']), normalize(r['short_name']))]
    if len(exact) == 1:
        return exact[0], 'exact_name'
    # Full multi-token names only; never match a surname or approximate spelling alone.
    tokens = set(n.split())
    candidates = [r for r in rows if len(tokens) >= 2 and tokens <= set(normalize(r['long_name']).split())]
    return (candidates[0], 'unique_full_name_subset') if len(candidates) == 1 else (None, 'unmatched_or_ambiguous')

def main():
    with zipfile.ZipFile(ROOT.parent / 'archive (3).zip') as z:
        rows = list(csv.DictReader(io.TextIOWrapper(z.open('players_16.csv'), encoding='utf-8-sig')))
    identities = {}
    with zipfile.ZipFile(ROOT.parent / 'open-data-master.zip') as z:
        names = z.namelist()
        prefix = next(n for n in names if n.endswith('/data/matches/2/27.json')).split('data/matches')[0]
        games = json.loads(z.read(prefix + 'data/matches/2/27.json'))
        for g in games:
            for team in json.loads(z.read(prefix + f'data/lineups/{g["match_id"]}.json')):
                for p in team['lineup']:
                    identities[p['player_id']] = p['player_name']
    directory = ROOT / 'assets' / 'players'
    directory.mkdir(parents=True, exist_ok=True)
    manifest, missing = {}, []
    for pid, name in identities.items():
        row, method = choose(name, rows)
        if row is None:
            missing.append({'player_id': pid, 'name': name, 'reason': method})
            continue
        manifest[str(pid)] = {'name': name, 'fifa_name': row['long_name'], 'sofifa_id': row['sofifa_id'],
            'url': row['player_face_url'], 'source': 'FIFA 16 CSV / SoFIFA', 'match_method': method,
            'file': f'assets/players/{pid}.png', 'downloaded': False}
        manifest[str(pid)]['attributes'] = {k: row[k] for k in (
            'player_positions', 'overall', 'preferred_foot', 'pace', 'shooting', 'passing',
            'dribbling', 'defending', 'physic', 'power_stamina', 'attacking_crossing',
            'skill_fk_accuracy', 'mentality_penalties')}
    network_failed = Event()
    def download(item):
        pid, record = item
        path = ROOT / record['file']
        if network_failed.is_set() and not path.exists():
            record['error'] = 'Download skipped after source connection failure'
            return
        try:
            if not path.exists():
                with urlopen(Request(record['url'], headers={'User-Agent': 'MatchPlan educational project'}), timeout=15) as response:
                    data = response.read(2_000_000)
                if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('not PNG')
                path.write_bytes(data)
            record['downloaded'] = True
        except Exception as exc:
            record['error'] = type(exc).__name__ + ': ' + str(exc)
            network_failed.set()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(download, manifest.items()))
    report = {'dataset': 'players_16.csv', 'players': len(identities), 'matched': len(manifest),
              'downloaded': sum(r['downloaded'] for r in manifest.values()),
              'unmatched': missing, 'portraits': manifest,
              'note': 'Identity matches, not manual verification. Photos are display-only; source image rights remain with their owners.'}
    (ROOT / 'reports' / 'player_photos.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print({k: report[k] for k in ('players', 'matched', 'downloaded')})

if __name__ == '__main__':
    main()
