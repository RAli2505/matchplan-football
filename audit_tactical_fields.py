"""Audit actual availability of tactical event fields across the PL dataset."""
import json
import zipfile
from collections import Counter
from pathlib import Path
from core import ARCHIVE


def main():
    counts=Counter(); kinds=Counter(); games_with=Counter()
    with zipfile.ZipFile(ARCHIVE) as z:
        path=next(n for n in z.namelist() if n.endswith('/data/matches/2/27.json'))
        prefix=path.split('/data/matches/')[0]
        games=json.loads(z.read(path))
        for game in games:
            present=set()
            for event in json.loads(z.read(prefix+f'/data/events/{game["match_id"]}.json')):
                kinds[event['type']['name']]+=1
                values={'under_pressure':event.get('under_pressure') is True,
                    'pass_cut_back':event.get('pass',{}).get('cut_back') is True,
                    'pass_through_ball':event.get('pass',{}).get('through_ball') is True,
                    'pass_assisted_shot_id':bool(event.get('pass',{}).get('assisted_shot_id')),
                    'dribble_outcome':bool(event.get('dribble',{}).get('outcome')),
                    'counterpress':event.get('counterpress') is True,
                    'shot_key_pass_id':bool(event.get('shot',{}).get('key_pass_id'))}
                for key,exists in values.items():
                    if exists: counts[key]+=1; present.add(key)
            games_with.update(present)
    result={'competition':'Premier League 2015/16','matches':len(games),'events':sum(kinds.values()),
            'event_types':dict(kinds),'fields':{key:{'events':value,'matches':games_with[key]} for key,value in counts.items()},
            'interpretation':'Counts are explicit flags/links in source, not tracking coverage. Absence of under_pressure does not prove absence of pressure.'}
    (Path(__file__).parent/'reports/tactical_field_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('matches','events','fields')},indent=2))

if __name__=='__main__':main()
