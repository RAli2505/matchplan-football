"""Event-based field views. Coordinates are nominal roles or event locations, not tracking."""
import base64
import html
import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def photo_manifest():
    path = ROOT / 'reports' / 'player_photos.json'
    return _photo_manifest(path.stat().st_mtime_ns) if path.exists() else {}

@lru_cache(maxsize=2)
def _photo_manifest(stamp):
    path = ROOT / 'reports' / 'player_photos.json'
    return json.loads(path.read_text(encoding='utf-8')).get('portraits', {})

def portrait(pid):
    path = ROOT / 'reports' / 'player_photos.json'
    return _portrait(pid, path.stat().st_mtime_ns if path.exists() else 0)

@lru_cache(maxsize=2048)
def _portrait(pid, stamp):
    record = photo_manifest().get(str(pid), {})
    path = ROOT / record.get('file', 'missing')
    if record.get('downloaded') and path.is_file():
        return 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
    return None

def field(content, label, light=False):
    background,lines,text=('#ffffff','#9caeb2','#243b4d') if light else ('#176454','#b5d2bc','white')
    return ('<svg role="img" aria-label="' + html.escape(label) + '" viewBox="0 0 600 430" width="100%" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="600" height="430" rx="14" fill="{background}"/>'
        f'<path d="M20 20H580V410H20ZM300 20V410 M20 110H110V320H20 M580 110H490V320H580" fill="none" stroke="{lines}" stroke-width="2"/>'
        f'<circle cx="300" cy="215" r="48" fill="none" stroke="{lines}" stroke-width="2"/>'
        f'<text x="300" y="425" text-anchor="middle" fill="{text}" font-size="11">Направление атаки →</text>' + content + '</svg>')

def point(location):
    return 20 + location[0] / 120 * 560, 20 + location[1] / 80 * 390

def pass_network(state, tid, window=900):
    locations, names, links = defaultdict(list), {}, Counter()
    lower = max(0, state['cutoff'] - window)
    for tick, e in state['visible']:
        if not lower <= tick <= state['cutoff'] or e.get('team', {}).get('id') != tid or e['type']['name'] != 'Pass':
            continue
        p = e.get('pass', {})
        source, target = e.get('player', {}).get('id'), p.get('recipient', {}).get('id')
        if p.get('outcome') or source is None or target is None:
            continue
        start, end = e.get('location'), p.get('end_location')
        if not start or not end:
            continue
        names[source], names[target] = e['player']['name'], p['recipient']['name']
        locations[source].append(start[:2]); locations[target].append(end[:2])
        links[source, target] += 1
    positions = {pid: point([sum(p[i] for p in locs) / len(locs) for i in (0, 1)]) for pid, locs in locations.items()}
    parts = []
    undirected = Counter()
    for (a, b), count in links.items():
        undirected[tuple(sorted((a, b)))] += count
    for (a, b), count in undirected.items():
        x, y = positions[a]; xx, yy = positions[b]
        parts.append(f'<line x1="{x}" y1="{y}" x2="{xx}" y2="{yy}" stroke="#e4c779" opacity=".65" stroke-width="{min(9, 1+count/2)}"><title>{html.escape(names[a])} ↔ {html.escape(names[b])}: {count}</title></line>')
    for pid, (x, y) in positions.items():
        name = html.escape(names[pid])
        parts.append(f'<circle cx="{x}" cy="{y}" r="12" fill="#f4f7fb"><title>{name}</title></circle><text x="{x}" y="{y+25}" text-anchor="middle" fill="white" font-size="10">{name.split()[-1]}</text>')
    rows = [{'От': names[a], 'Кому': names[b], 'Успешных передач': n} for (a, b), n in links.most_common()]
    return field(''.join(parts), 'Сеть успешных передач'), rows

def goal_map(state, tid, conceded=False):
    parts, rows, own_goals = [], [], 0
    for tick, e in state['visible']:
        if tick > state['cutoff']:
            continue
        event_team = e.get('team', {}).get('id')
        if e['type']['name'] == 'Own Goal Against':
            own_goals += int(event_team == tid if conceded else event_team != tid)
        if e['type']['name'] != 'Shot' or e.get('shot', {}).get('outcome', {}).get('name') != 'Goal':
            continue
        if (event_team != tid) != conceded:
            continue
        location = e.get('location')
        rows.append({'Минута': e.get('minute', 0), 'Игрок': e.get('player', {}).get('name', '—'),
                     'xG': round(e['shot'].get('statsbomb_xg', 0), 3),
                     'Координаты': str(location[:2]) if location else 'нет'})
        if location:
            x, y = point(location)
            color = '#ff9c91' if conceded else '#ffe17d'
            parts.append(f'<circle cx="{x}" cy="{y}" r="9" fill="{color}" stroke="white"><title>{html.escape(rows[-1]["Игрок"])} · {e.get("minute", 0)} мин</title></circle>')
    return field(''.join(parts), 'Места ударов, завершившихся голом'), rows, own_goals
