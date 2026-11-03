"""Download verified portraits using public TheSportsDB identities and FIFA dates of birth."""
import csv
import io
import json
import zipfile
import time
import argparse
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlparse
from urllib.request import urlopen
from PIL import Image
from build_player_photos import ROOT, normalize


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--club', default='Chelsea')
    parser.add_argument('--limit',type=int,default=30)
    args=parser.parse_args()
    path = ROOT / 'reports/player_photos.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    with zipfile.ZipFile(ROOT.parent / 'archive (3).zip') as z:
        data = {r['sofifa_id']: r for r in csv.DictReader(io.TextIOWrapper(z.open('players_16.csv'), encoding='utf-8-sig'))}
    def fetch(item):
        pid, record = item
        target = ROOT / record['file']
        if record.get('downloaded') and target.exists(): return True
        row = data[record['sofifa_id']]
        slug = urlparse(row['player_url']).path.split('/')[3].replace('-', ' ')
        aliases = {'Radamel Falcao García Zárate':'Radamel Falcao', 'Francesc Fàbregas i Soler':'Cesc Fabregas',
                   'César Azpilicueta Tanco':'Cesar Azpilicueta', 'Pedro Eliezer Rodríguez Ledesma':'Pedro Rodriguez',
                   'Ramires Santos do Nascimento':'Ramires', 'Oscar dos Santos Emboaba Júnior':'Oscar'}
        slug = aliases.get(record['name'], slug)
        try:
            with urlopen('https://www.thesportsdb.com/api/v1/json/123/searchplayers.php?p='+quote(slug), timeout=12) as response:
                candidates = json.load(response).get('player') or []
            candidates = [p for p in candidates if p.get('strSport') == 'Soccer' and p.get('dateBorn') == row['dob']]
            if len(candidates) != 1:
                record['error'] = 'No unique football identity with matching date of birth'; return False
            person = candidates[0]
            url = person.get('strCutout') or person.get('strThumb')
            if not url: record['error'] = 'Verified identity has no portrait'; return False
            with urlopen(url, timeout=12) as response: image = response.read(3_000_000)
            with Image.open(io.BytesIO(image)) as picture:
                picture.thumbnail((180,180))
                picture.convert('RGBA').save(target, 'PNG')
            record.update(downloaded=True, portrait_source='TheSportsDB', portrait_url=url,
                          sportsdb_id=person['idPlayer'], verified_dob=row['dob'],
                          portrait_name=person['strPlayer'])
            record.pop('error',None)
            return True
        except HTTPError as exc:
            record['error'] = 'HTTPError: '+str(exc.code)
            if exc.code==429: raise
            return False
        except Exception as exc:
            record['error'] = type(exc).__name__ + ': ' + str(exc); return False
    def save():
        report['downloaded'] = sum(p.get('downloaded',False) for p in report['portraits'].values())
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    items=[item for item in report['portraits'].items() if not item[1].get('downloaded')]
    items.sort(key=lambda item: (args.club.lower() not in data[item[1]['sofifa_id']]['club_name'].lower(),int(item[0])))
    for count,item in enumerate(items[:args.limit],1):
        try: fetch(item)
        except HTTPError:
            save(); print('Rate limit reached; stopped without further requests',flush=True); break
        save()
        print(f'Checked {count}; downloaded {report["downloaded"]}',flush=True)
        time.sleep(3)
    save(); print(f'DONE: {report["downloaded"]} portraits',flush=True)

if __name__=='__main__': main()
