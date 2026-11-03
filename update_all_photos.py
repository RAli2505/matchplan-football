"""Resolve cross-edition FIFA identities and download official EA portraits for every club."""
import csv
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.request import urlopen
from PIL import Image
from build_player_photos import ROOT,normalize

EA16='https://fifa15.content.easports.com/fifa/fltOnlineAssets/B488919F-23B5-497F-9FC0-CACFB38863D0/2016/fut/items/images/players/html5/120x120/{}.png'
EA23='https://media.contentapi.ea.com/content/dam/ea/fifa/fifa-23/ratings/common/player-headshots/{}.png'

def club_key(name):
    return ' '.join(t for t in normalize(name).split() if t not in ('fc','afc','hotspur'))

def main():
    path=ROOT/'reports/player_photos.json'
    report=json.loads(path.read_text(encoding='utf-8'))
    exact={}; by_id={}; clubs={}
    with zipfile.ZipFile(ROOT.parent/'archive (3).zip') as z:
        for year in (16,15,17,18,19,20,21,22):
            for row in csv.DictReader(io.TextIOWrapper(z.open(f'players_{year}.csv'),encoding='utf-8-sig')):
                fid=row['sofifa_id']; by_id.setdefault(fid,row)
                clubs.setdefault(fid,set()).add(club_key(row['club_name']))
                for name in (row['long_name'],row['short_name'],row['long_name'].replace('-',' '),row['short_name'].replace('-',' ')):
                    exact.setdefault(normalize(name),set()).add(fid)
    player_clubs={}
    with zipfile.ZipFile(ROOT.parent/'open-data-master.zip') as z:
        prefix=next(n for n in z.namelist() if n.endswith('/data/matches/2/27.json')).split('/data/matches/')[0]
        for game in json.loads(z.read(prefix+'/data/matches/2/27.json')):
            for team in json.loads(z.read(prefix+f'/data/lineups/{game["match_id"]}.json')):
                for player in team['lineup']:
                    player_clubs.setdefault(player['player_id'],set()).add(club_key(team['team_name']))
    remaining=[]
    for identity in report['unmatched']:
        name=normalize(identity['name'])
        found=exact.get(name,set())
        method='unique_exact_name_across_FIFA_15_22'
        reviewed_aliases={'Sandro Ranieri Guimarães Cordeiro':'Sandro Raniere Guimarães Cordeiro',
                          'Jake-Liam Clarke-Salter':'Jake Clarke-Salter', 'Tony Andreu':'Anthony Andreu',
                          'Josh Vickers':'Joshua Anthony Vickers'}
        if not found and identity['name'] in reviewed_aliases:
            found=exact.get(normalize(reviewed_aliases[identity['name']]),set())
            method='reviewed_full_name_alias'
        if not found:
            tokens=set(name.split())
            found={fid for candidate,ids in exact.items() if len(tokens)>=2 and len(candidate.split())>=2
                   and (tokens<=set(candidate.split()) or set(candidate.split())<=tokens)
                   for fid in ids}
            method='unique_full_name_subset_across_FIFA_15_22'
        if len(found)>1:
            found={fid for fid in found if clubs[fid] & player_clubs.get(identity['player_id'],set())}
            method+=' plus_club'
        if not found:
            aliases={'John Michael Nchekwube Obinna':'John Obi Mikel','Sung-Yeung Ki':'Ki Sung Yueng',
                     'Chung-Yong Lee':'Lee Chung Yong','Heung-Min Son':'Son Heung Min',
                     'Sandro Ranieri Guimarães Cordeiro':'Sandro'}
            alias=aliases.get(identity['name'],identity['name']).replace('-',' ')
            words=alias.split()
            original=identity['name'].replace('-',' ').split()
            variants={normalize(alias)} | {normalize(words[0][0]+' '+word) for word in words[1:]}
            variants |= {normalize(original[0][0]+' '+word) for word in original[1:]}
            found={fid for variant in variants for fid in exact.get(variant,set())
                   if clubs[fid] & player_clubs.get(identity['player_id'],set())}
            method='unique_alias_or_initial_surname_with_club_verification'
        if len(found)!=1:
            remaining.append(identity); continue
        fid=next(iter(found)); row=by_id[fid]; pid=str(identity['player_id'])
        report['portraits'][pid]=dict(name=identity['name'],fifa_name=row['long_name'],sofifa_id=fid,
            source='FIFA 15–22 identity reference only',match_method=method,
            file=f'assets/players/{pid}.png',downloaded=False,attributes={})
    report['unmatched']=remaining
    def save():
        report['matched']=len(report['portraits'])
        report['downloaded']=sum(p.get('downloaded',False) for p in report['portraits'].values())
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save(); print(f'Identified {report["matched"]}/{report["players"]}',flush=True)
    def download(item):
        pid,record=item
        # Keep already verified local images.
        target=ROOT/record['file']
        if record.get('downloaded') and target.exists(): return
        for edition,url in (('FIFA 16 / EA',EA16.format(record['sofifa_id'])),('FIFA 23 / EA',EA23.format(record['sofifa_id']))):
            try:
                with urlopen(url,timeout=10) as response: data=response.read(2_000_000)
                with Image.open(io.BytesIO(data)) as picture:
                    if picture.width<30 or picture.height<30: raise ValueError('Invalid portrait dimensions')
                    picture.thumbnail((180,180)); picture.convert('RGBA').save(target,'PNG')
                record.update(downloaded=True,portrait_source=edition,portrait_url=url)
                record.pop('error',None); return
            except Exception as exc: record['error']=type(exc).__name__+': '+str(exc)
    jobs=[item for item in report['portraits'].items() if not item[1].get('downloaded')]
    with ThreadPoolExecutor(max_workers=6) as pool:
        tasks=[pool.submit(download,item) for item in jobs]
        for count,task in enumerate(as_completed(tasks),1):
            task.result()
            if count%50==0: save(); print(f'Checked {count}/{len(jobs)}; portraits {report["downloaded"]}',flush=True)
    save(); print(f'DONE: {report["downloaded"]}/{report["players"]} portraits',flush=True)

if __name__=='__main__':main()
