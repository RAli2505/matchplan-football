"""Audit local portrait files by club squad membership in the actual match dataset."""
import json
import zipfile
from PIL import Image
from build_player_photos import ROOT


def main():
    path=ROOT/'reports/player_photos.json'
    report=json.loads(path.read_text(encoding='utf-8'))
    clubs={}
    with zipfile.ZipFile(ROOT.parent/'open-data-master.zip') as z:
        prefix=next(n for n in z.namelist() if n.endswith('/data/matches/2/27.json')).split('/data/matches/')[0]
        for g in json.loads(z.read(prefix+'/data/matches/2/27.json')):
            for team in json.loads(z.read(prefix+f'/data/lineups/{g["match_id"]}.json')):
                clubs.setdefault(team['team_name'],set()).update(p['player_id'] for p in team['lineup'])
    valid=set(); errors=[]
    for pid,record in report['portraits'].items():
        if not record.get('downloaded'): continue
        try:
            with Image.open(ROOT/record['file']) as image: image.verify()
            valid.add(int(pid))
        except Exception as exc: errors.append({'player_id':pid,'error':str(exc)})
    coverage=[{'Команда':name,'Игроков в заявках':len(ids),'С фото':len(ids & valid),
               'Без фото':len(ids-valid),'Покрытие':round(len(ids & valid)/len(ids)*100,1)}
              for name,ids in sorted(clubs.items())]
    result={'league':'Premier League 2015/16','valid_portraits':len(valid),'teams':coverage,
            'file_errors':errors,'missing':[{'player_id':pid,'name':record['name'],'reason':record.get('error','not downloaded')}
             for pid,record in report['portraits'].items() if int(pid) not in valid] + report['unmatched']}
    (ROOT/'reports/photo_coverage.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
