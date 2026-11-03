"""Past training-match analogues. Query features never use future actions or outcomes."""
import hashlib
import json
import logging
import time
import zipfile
from datetime import datetime,timezone
from pathlib import Path
from core import ARCHIVE,snapshot,timeline,seconds,metrics,clock_label,competition_rules
from preprocessing import prepare_events,validate_lineups

ROOT=Path(__file__).resolve().parent
FEATURE_VERSION='decision-analogues-v1'


def context_features(state,tid):
    opp=next(t for t in state['players'] if t!=tid)
    ours,theirs=metrics(state,tid),metrics(state,opp)
    return {'minute':state['last'].get('minute',0),'score_diff':state['goals'][tid]-state['goals'][opp],
            'man_diff':len(state['players'][tid])-len(state['players'][opp]),
            'xg_delta':ours['xg']-theirs['xg'],'entries_delta':ours['box_entries']-theirs['box_entries']}


def find_similar(rows,query,date,match_id,limit=5):
    if query['minute']<10 or limit<=0: return []
    candidates=[]
    for row in rows:
        f=row['features']
        if row['date']>=date or row['match_id']==match_id: continue
        if f['score_diff']!=query['score_diff'] or f['man_diff']!=query['man_diff']: continue
        if abs(f['minute']-query['minute'])>15: continue
        distance=abs(f['minute']-query['minute'])/15+abs(f['xg_delta']-query['xg_delta'])/.5+abs(f['entries_delta']-query['entries_delta'])/5
        candidates.append(dict(row,distance=round(distance,4)))
    candidates.sort(key=lambda r:(r['distance'],r['date'],r['match_id'],r['team_id']))
    found=[]; seen=set()
    for row in candidates:
        if row['match_id'] in seen: continue
        seen.add(row['match_id']); found.append(row)
        if len(found)>=limit: break
    return found


def load_index():
    path=ROOT/'reports/decision_history.json'
    if not path.exists(): raise ValueError('Индекс исторических ситуаций ещё не построен.')
    data=json.loads(path.read_text(encoding='utf-8'))
    manifest=data['manifest']; stat=ARCHIVE.stat()
    report=(ROOT/'reports/ml_results.json').read_bytes()
    if manifest['feature_version']!=FEATURE_VERSION or manifest['archive_size']!=stat.st_size or manifest['archive_mtime_ns']!=stat.st_mtime_ns:
        raise ValueError('Индекс не соответствует текущим данным; его нужно перестроить.')
    if manifest['ml_report_sha256']!=hashlib.sha256(report).hexdigest():
        raise ValueError('Изменилось разделение моделей: индекс нужно перестроить.')
    return data


def build_index():
    start=time.perf_counter()
    run=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    logs=ROOT/'reports/logs'; logs.mkdir(parents=True,exist_ok=True)
    logger=logging.getLogger('decision-history-'+run); logger.setLevel(logging.INFO)
    format_=logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    for handler in (logging.StreamHandler(),logging.FileHandler(logs/f'decision_history_{run}.log',encoding='utf-8')):
        handler.setFormatter(format_); logger.addHandler(handler)
    logger.info('START run=%s stage=load mode=CPU seed=none frozen_models=unchanged ETA=unknown',run)
    report_bytes=(ROOT/'reports/ml_results.json').read_bytes(); report=json.loads(report_bytes)
    train=set(report['splits']['train']['match_ids'])
    samples=(15,30,45,60,75); rows=[]; crc=[]
    try:
        with zipfile.ZipFile(ARCHIVE) as z:
            source=next(n for n in z.namelist() if n.endswith('/data/matches/2/27.json'))
            prefix=source.split('/data/matches/')[0]
            games=sorted((g for g in json.loads(z.read(source)) if g['match_id'] in train),key=lambda g:(g['match_date'],g['match_id']))
            rules=competition_rules(2,27)
            logger.info('LOAD complete matches=%d split=train only sample_minutes=%s stage=index ETA=unknown',len(games),samples)
            for number,game in enumerate(games,1):
                mid=game['match_id']; ep=prefix+f'/data/events/{mid}.json'; lp=prefix+f'/data/lineups/{mid}.json'
                for name in (ep,lp):
                    info=z.getinfo(name); crc.append([name,info.CRC,info.file_size])
                events,_=prepare_events(json.loads(z.read(ep))); lineups=json.loads(z.read(lp)); validate_lineups(lineups)
                timed=timeline(events); final=snapshot(events,lineups,max(t for t,e in timed),rules)
                names={lineup['team_id']:lineup['team_name'] for lineup in lineups}
                for minute in samples:
                    period,local=(1,minute*60) if minute<45 else (2,(minute-45)*60)
                    cutoff=max((t for t,e in timed if e['period']==period and seconds(e)<=local),default=None)
                    if cutoff is None: continue
                    state=snapshot(events,lineups,cutoff,rules)
                    future=[(t,e) for t,e in timed if cutoff<t<=cutoff+600]
                    follow=dict(state,cutoff=cutoff+600,visible=future)
                    for tid in names:
                        opp=next(t for t in names if t!=tid)
                        actions=[]
                        for tick,e in future:
                            if e.get('team',{}).get('id')!=tid: continue
                            if e['type']['name']=='Substitution':
                                actions.append(clock_label(e)+': '+e['player']['name']+' → '+e['substitution']['replacement']['name'])
                            if e['type']['name']=='Tactical Shift':
                                shape=str(e.get('tactics',{}).get('formation','?'))
                                if shape!=state['formation'].get(tid): actions.append(clock_label(e)+': схема '+shape)
                        diff=final['goals'][tid]-final['goals'][opp]
                        rows.append({'match_id':mid,'date':game['match_date'],'team_id':tid,'team':names[tid],'opponent':names[opp],
                            'clock':clock_label(state['last']),'features':context_features(state,tid),
                            'score':f'{state["goals"][tid]}:{state["goals"][opp]}','formation':state['formation'].get(tid,'?'),
                            'recorded_next_10_minutes':actions,'following_ours':metrics(follow,tid,0),
                            'following_opponent':metrics(follow,opp,0),
                            'result':'Победа' if diff>0 else 'Ничья' if diff==0 else 'Поражение',
                            'final_score':f'{final["goals"][tid]}:{final["goals"][opp]}'})
                if number%10==0 or number==len(games):
                    elapsed=time.perf_counter()-start; rate=number/elapsed
                    logger.info('stage=index done=%d/%d rows=%d elapsed=%.1fs throughput=%.2f matches/s stage_ETA=%.1fs',
                                number,len(games),len(rows),elapsed,rate,(len(games)-number)/rate)
        stat=ARCHIVE.stat()
        data={'manifest':{'run':run,'feature_version':FEATURE_VERSION,'competition_id':2,'season_id':27,
            'pool':'train matches only','match_ids':sorted(train),'sample_minutes':samples,
            'archive_size':stat.st_size,'archive_mtime_ns':stat.st_mtime_ns,
            'source_crc_sha256':hashlib.sha256(json.dumps(crc,sort_keys=True).encode()).hexdigest(),
            'ml_report_sha256':hashlib.sha256(report_bytes).hexdigest(),
            'distance':'same score_diff and man_diff; |minute delta|/15 + |xG delta|/.5 + |entries delta|/5; one row per match',
            'query_policy':'strictly earlier date, different match, minute difference <=15; future fields are display-only',
            'device':'CPU','seed':None,'elapsed_seconds':time.perf_counter()-start},'rows':rows}
        path=ROOT/'reports/decision_history.json'; temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); temp.replace(path)
        logger.info('COMPLETE stage=save rows=%d elapsed=%.1fs path=%s',len(rows),time.perf_counter()-start,path)
        return data
    except BaseException:
        logger.exception('FAILED run=%s elapsed=%.1fs',run,time.perf_counter()-start); raise


if __name__=='__main__':build_index()
