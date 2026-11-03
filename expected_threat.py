"""StatsBomb open-play grid xT, adapted from socceraction.xthreat.

Copyright (c) 2019 KU Leuven Machine Learning Research Group (MIT).
See licenses/socceraction-MIT.txt. Vectorized Bellman solver and StatsBomb
adapter replace SPADL/pandas dependencies; y is source top-to-bottom.
This is a separate descriptive action-value model, never an outcome forecast.
"""
import json
import hashlib
from pathlib import Path
import numpy as np
from event_adapter import coordinates, movement, visible_events

ROOT=Path(__file__).resolve().parent
VERSION='statsbomb-open-play-xt-v1'
L,W=12,8


def cell(point,l=L,w=W):
    return min(w-1,int(point[1]/80*w))*l+min(l-1,int(point[0]/120*l))


def safe_divide(a,b):
    # Adapted from socceraction.xthreat._safe_divide (MIT).
    return np.divide(a,b,out=np.zeros_like(a,dtype='float64'),where=b!=0,casting='unsafe')


def empty_counts(l=L,w=W):
    n=l*w
    return {'moves':np.zeros(n),'shots':np.zeros(n),'goals':np.zeros(n),'transitions':np.zeros((n,n))}


def add_events(counts, events,l=L,w=W):
    accepted=0
    for e in events:
        if e.get('period') not in (1,2): continue
        if e.get('play_pattern',{}).get('name','Regular Play') not in ('Regular Play','From Counter'): continue
        kind=e.get('type',{}).get('name'); start=coordinates(e.get('location'))
        if start is None: continue
        i=cell(start,l,w)
        if kind=='Shot' and e.get('shot',{}).get('type',{}).get('name') not in ('Penalty','Free Kick'):
            counts['shots'][i]+=1
            counts['goals'][i]+=e.get('shot',{}).get('outcome',{}).get('name')=='Goal'
            accepted+=1
        elif kind in ('Pass','Carry'):
            move=movement(e)
            # Failed passes still enter the denominator, including unknown end.
            counts['moves'][i]+=1; accepted+=1
            if move and move[2]: counts['transitions'][i,cell(move[1],l,w)]+=1
    return accepted


def solve(counts,eps=1e-7,max_iter=2000,progress=None):
    total=counts['moves']+counts['shots']
    reward=safe_divide(counts['goals'],total)
    # p(move)*P(successful destination | move); failed moves lose possession.
    transition=safe_divide(counts['transitions'],total[:,None])
    value=np.zeros_like(reward)
    for epoch in range(1,max_iter+1):
        new=reward+np.einsum('ij,j->i',transition,value)
        residual=float(np.max(np.abs(new-value))); value=new
        if progress and (epoch==1 or epoch%25==0 or residual<eps): progress(epoch,residual)
        if residual<eps: break
    else: raise RuntimeError('xT solver did not converge; artifact not saved')
    if not np.isfinite(value).all() or value.min()<0 or value.max()>1+eps:
        raise ValueError('Invalid xT surface')
    return value,{'iterations':epoch,'residual':residual,'epsilon':eps}


def load_model():
    path=ROOT/'models/expected_threat.json'
    if not path.exists(): return None
    data=json.loads(path.read_text(encoding='utf-8'))
    from core import ARCHIVE
    stat=ARCHIVE.stat(); m=data['manifest']
    if m['version']!=VERSION or m['archive_size']!=stat.st_size or m['archive_mtime_ns']!=stat.st_mtime_ns:
        raise ValueError('Модель xT не соответствует текущему архиву; запустите train_expected_threat.py.')
    report=(ROOT/'reports/ml_results.json').read_bytes()
    if hashlib.sha256(report).hexdigest()!=m['split_report_sha256']:
        raise ValueError('Изменилось разделение матчей для xT; требуется пересборка.')
    return data


def surface_for_date(data,date):
    # Same-day games are excluded irrespective of kickoff time.
    eligible=[s for s in data['surfaces'] if s['through_date']<date]
    return eligible[-1] if eligible else None


def rate_actions(state,tid,surface,window=0):
    grid=np.asarray(surface['values']); rows=[]
    for tick,e in visible_events(state,window):
        if e.get('team',{}).get('id')!=tid or e.get('period') not in (1,2): continue
        if e.get('play_pattern',{}).get('name','Regular Play') not in ('Regular Play','From Counter'): continue
        move=movement(e)
        if not move or not move[2]: continue
        a,b,_=move
        rows.append({'tick':tick,'event':e,'start':a,'end':b,'xt':float(grid[cell(b)]-grid[cell(a)])})
    return rows
