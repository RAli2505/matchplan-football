"""Chronological train-only xT surfaces; never touch the six outcome models."""
import hashlib
import json
import logging
import time
import zipfile
from datetime import datetime,timezone
from itertools import groupby
from core import ARCHIVE
from preprocessing import prepare_events
from expected_threat import ROOT,VERSION,L,W,empty_counts,add_events,solve


def train():
    start=time.perf_counter(); run=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    logdir=ROOT/'reports/logs'; logdir.mkdir(parents=True,exist_ok=True)
    logger=logging.getLogger('xt-'+run); logger.setLevel(logging.INFO)
    for h in (logging.StreamHandler(),logging.FileHandler(logdir/f'xt_{run}.log',encoding='utf-8')):
        h.setFormatter(logging.Formatter('%(asctime)s %(message)s')); logger.addHandler(h)
    logger.info('START stage=load CPU deterministic counts, seed=none grid=%dx%d ETA=unknown',L,W)
    report_bytes=(ROOT/'reports/ml_results.json').read_bytes(); report=json.loads(report_bytes)
    ids=set(report['splits']['train']['match_ids'])
    others=set(report['splits']['validation']['match_ids'])|set(report['splits']['test']['match_ids'])
    assert not ids&others
    counts=empty_counts(); surfaces=[]; seen=[]; crc=[]; accepted=0
    try:
        with zipfile.ZipFile(ARCHIVE) as z:
            name=next(n for n in z.namelist() if n.endswith('/data/matches/2/27.json'))
            prefix=name.split('/data/matches/')[0]
            games=sorted([g for g in json.loads(z.read(name)) if g['match_id'] in ids],key=lambda g:(g['match_date'],g['match_id']))
            assert {g['match_id'] for g in games}==ids
            for date,group in groupby(games,key=lambda g:g['match_date']):
                for game in group:
                    eventpath=prefix+f'/data/events/{game["match_id"]}.json'
                    info=z.getinfo(eventpath); crc.append([eventpath,info.CRC,info.file_size])
                    events,_=prepare_events(json.loads(z.read(eventpath)))
                    accepted+=add_events(counts,events); seen.append(game['match_id'])
                if len(seen)>=20:
                    values,stats=solve(counts,progress=lambda epoch,residual:logger.info('stage=solve through=%s epoch=%d residual=%.9f',date,epoch,residual))
                    surfaces.append({'through_date':date,'matches':len(seen),'values':values.tolist(),**stats})
                elapsed=time.perf_counter()-start; rate=len(seen)/elapsed
                logger.info('stage=counts done=%d/%d accepted_actions=%d throughput=%.2f matches/s measured_ETA=%.1fs',len(seen),len(ids),accepted,rate,(len(ids)-len(seen))/rate)
        m={'version':VERSION,'run':run,'competition_id':2,'season_id':27,'grid':[L,W],
           'match_ids':sorted(ids),'validation_test_matches_used':0,'minimum_training_matches':20,
           'split_report_sha256':hashlib.sha256(report_bytes).hexdigest(),
           'source_crc_sha256':hashlib.sha256(json.dumps(crc).encode()).hexdigest(),
           'archive_size':ARCHIVE.stat().st_size,'archive_mtime_ns':ARCHIVE.stat().st_mtime_ns,
           'policy':'Only train partition; surface date strictly before query date; open-play Pass/Carry/Shot, failed moves retained; empirical goals, not supplied xG; no smoothing',
           'accepted_actions':accepted,'shots':int(counts['shots'].sum()),'goals':int(counts['goals'].sum()),
           'device':'CPU','seed':None,'elapsed_seconds':time.perf_counter()-start}
        result={'manifest':m,'surfaces':surfaces}
        path=ROOT/'models/expected_threat.json'; tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(path)
        logger.info('COMPLETE surfaces=%d elapsed=%.2fs output=%s',len(surfaces),m['elapsed_seconds'],path)
        return result
    except BaseException:
        logger.exception('FAILED elapsed=%.2fs',time.perf_counter()-start); raise


if __name__=='__main__': train()
