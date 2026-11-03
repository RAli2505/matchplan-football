"""Reviewable coaching packages, evidence sufficiency and manual execution records."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from core import recommend, metrics, PLANS
from coaching import tactical_options, freeze_plan
from tactics import formation_options

POLICIES = {
    'balanced': {'title':'Сохранить структуру','intent':'Сохранить баланс и подключать игроков поочерёдно.',
                 'keys':{'center','central_build','progression','pressure_support','dribble_support','creator_watch'},
                 'shapes':{'4-2-3-1','4-3-3','4-4-2'}},
    'attacking': {'title':'Усилить атаку','intent':'Добавить адресатов впереди при сохранённой страховке.',
                 'keys':{'width','shot_selection','cutback','press','progression','central_build','dribble_support'},
                 'shapes':{'4-3-3','4-4-2','4-2-2-2','3-4-1-2'}},
    'cautious': {'title':'Снизить риск','intent':'Укрепить центральную страховку и сохранить выход после отбора.',
                'keys':{'center','control','safe_exit','deep_block','through_defence','cutback_defence','rest_defence','pressure_support','foul_discipline'},
                'shapes':{'4-1-4-1','4-2-3-1','5-4-1','5-3-2'}}}


def compare_plans(state,tid,goal,roles):
    opponent=next(t for t in state['players'] if t!=tid)
    need=state['goals'][tid]<state['goals'][opponent] or state['goals'][tid]==state['goals'][opponent] and goal=='win'
    rows=[]
    for key,policy in POLICIES.items():
        rec=recommend(state,tid,goal,roles,plan_override=key)
        caution=[]
        if key=='cautious' and need: caution.append('Нужен гол: снижение риска может уменьшить число атакующих адресатов.')
        if key=='attacking' and len(state['players'][tid])<len(state['players'][opponent]):
            caution.append('Меньшинство: высокий прессинг и массовые подключения не включаются в пакет.')
        rows.append({'key':key,'title':policy['title'],'intent':policy['intent'],'risk':rec['risk'],
                     'expert_score':rec['scores'][key],'evidence':rec['evidence'],'cautions':caution,
                     'sub_options':rec['sub_options'],'finished':rec['finished']})
    return rows


def evidence_support(state,tid,task):
    opponent=next(t for t in state['players'] if t!=tid)
    window=min(900,state['cutoff'])
    visible=[e for t,e in state['visible'] if max(0,state['cutoff']-900)<=t<=state['cutoff']]
    meaningful=[e for e in visible if e['type']['name'] in ('Pass','Carry','Shot','Dribble','Miscontrol','Dispossessed','Pressure')]
    direct=len(task.get('event_evidence',[]))
    # An explicit sufficiency description, never a calibrated probability of success.
    if window<300 or not task['available']:
        level='Недостаточно оснований для уверенного совета'
    elif direct>=3:
        level='Есть несколько записанных оснований; нужна проверка тренером'
    else:
        level='Основания ограничены; используйте как рабочую гипотезу'
    unknown=[p['name'] for p in state['players'][tid].values() if p['position']=='Позиция не подтверждена']
    return {'level':level,'observed_seconds':window,'events':len(meaningful),'direct_examples':direct,
            'available':task['available'],'unknown_roles':unknown,
            'observations':[task['why'],f'Численность: {len(state["players"][tid])}:{len(state["players"][opponent])}.'],
            'limits':['Нет измерения физической готовности и непрерывного трекинга.',
                      'Число примеров не является вероятностью успеха совета.',
                      'Причинный эффект выбранного действия не измерен.'],
            'recheck':'После гола, удаления, замены, смены схемы или через 5 игровых минут.'}


def build_package(state,tid,goal,roles,profiles,policy='balanced',sub_index=None,horizon=5):
    if policy not in POLICIES: raise ValueError('Unknown policy')
    if horizon not in (5,10): raise ValueError('Horizon must be 5 or 10 minutes')
    original=recommend(state,tid,goal,roles,plan_override=policy)
    if original['finished']: raise ValueError('Матч завершён: можно анализировать решения, но новый игровой пакет не создаётся.')
    local=deepcopy(state); substitution=None
    if sub_index is not None:
        if not isinstance(sub_index,int) or not 0<=sub_index<len(original['sub_options']):
            raise ValueError('Выбранная замена не входит в допустимые варианты.')
        substitution=original['sub_options'][sub_index]
        outgoing,incoming=substitution['out_id'],substitution['in_id']
        if not original['subs_allowed'] or outgoing not in local['players'][tid] or incoming not in local['bench'][tid]:
            raise ValueError('Замена сейчас недоступна.')
        local['players'][tid].pop(outgoing)
        player=local['bench'][tid].pop(incoming)
        local['players'][tid][incoming]=dict(player,position=substitution['position'])
        local['entered'][incoming]=state['cutoff']
    observed=dict(roles)
    observed.update({pid:p['position'] for pid,p in local['players'][tid].items()})
    shape=None
    if len(local['players'][tid])==11:
        candidates=formation_options(local,tid,observed,profiles,tuple(local['bench'][tid]),goal)
        complete=[c for c in candidates if not c['gaps']]
        for candidate in complete:
            candidate['package_bonus']=2 if candidate['formation'] in POLICIES[policy]['shapes'] else 0
        if complete:
            shape=max(complete,key=lambda c:(c['fit']+c['package_bonus'],c['formation']))
            if {p['id'] for p in shape['lineup']}!=set(local['players'][tid]):
                raise ValueError('Расстановка изменила состав без разрешённой замены.')
            local['players'][tid]={p['id']:dict(p) for p in shape['lineup']}
    allowed=POLICIES[policy]['keys']
    options=tactical_options(local,tid,goal)
    compatible=[o for o in options if o['available'] and o['key'] in allowed]
    if not compatible: compatible=[o for o in options if o['key']=='center' and o['available']]
    task=max(compatible,key=lambda o:(o.get('priority',40),o['key']))
    # Measure baseline from the actual state; only role assignment uses the hypothetical package.
    frozen=freeze_plan(state,tid,goal,task,horizon)
    from tactical_playbook import detailed_instructions
    frozen['details']=detailed_instructions(local,tid,task)
    package={'policy':policy,'title':POLICIES[policy]['title'],'intent':POLICIES[policy]['intent'],
             'substitution':substitution,'formation':shape,'task':task,'plan':frozen,
             'support':evidence_support(state,tid,task),
             'roster':sorted(local['players'][tid]),'origin_roster':sorted(state['players'][tid]),
             'origin_score':dict(state['goals']),'origin_formation':state['formation'].get(tid),
             'origin_period':state['last'].get('period',1),'goal':goal,
             'note':'Единый план-кандидат: одна основная задача. Смена ролей и замена ещё не выполнены в записи.'}
    identity=[tid,state['cutoff'],goal,policy,horizon,sorted(state['players'][tid]),dict(state['goals']),substitution,shape['formation'] if shape else None,task['key']]
    package['id']=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
    return package


def package_changes(package,state,tid,goal=None):
    reasons=[]
    if goal is not None and package['goal']!=goal: reasons.append('Изменилась цель на матч.')
    if state['cutoff']<package['plan']['origin']: reasons.append('Запись перемотана до момента создания пакета.')
    if state['cutoff']-package['plan']['origin']>=300: reasons.append('Прошло не менее 5 игровых минут.')
    if sorted(state['players'][tid])!=package['origin_roster']: reasons.append('Изменился фактический состав.')
    if dict(state['goals'])!={int(k):v for k,v in package['origin_score'].items()}: reasons.append('Изменился счёт.')
    if state['formation'].get(tid)!=package['origin_formation']: reasons.append('Изменилась фактическая схема.')
    if state['last'].get('period',1)!=package['origin_period']: reasons.append('Начался другой тайм.')
    return reasons


def checklist_items(package):
    items=[{'id':f'task_{i}','text':text} for i,text in enumerate(package['task']['tasks'])]
    if package['substitution']:
        sub=package['substitution']; items.insert(0,{'id':'sub','text':f'Проверить и согласовать замену: {sub["out"]} → {sub["in"]}.'})
    if package['formation']:
        items.insert(0,{'id':'shape','text':'Согласовать роли в схеме '+package['formation']['formation']+'.'})
    return items


def save_execution(package,mid,tid,statuses,note,root=None):
    valid={'Не начато','Выполняется','Выполнено','Отменено'}
    keys={item['id'] for item in checklist_items(package)}
    if set(statuses)!=keys or any(value not in valid for value in statuses.values()):
        raise ValueError('Недопустимые отметки выполнения.')
    root=Path(root) if root is not None else Path(os.environ.get('MATCHPLAN_SESSION_DIR',str(Path(__file__).parent/'reports/coach_sessions')))
    root.mkdir(parents=True,exist_ok=True)
    path=root/f'{int(mid)}_{int(tid)}.json'
    existing=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'match_id':int(mid),'team_id':int(tid),'decisions':{}}
    existing['decisions'][package['id']]={'package':package,'statuses':dict(statuses),'note':str(note),
        'source':'Ручные отметки тренера. Выполнение не подтверждено событиями StatsBomb.'}
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(existing,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)
    return existing


def load_execution(mid,tid,root=None):
    root=Path(root) if root is not None else Path(os.environ.get('MATCHPLAN_SESSION_DIR',str(Path(__file__).parent/'reports/coach_sessions')))
    path=root/f'{int(mid)}_{int(tid)}.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'decisions':{}}
