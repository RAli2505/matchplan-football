"""Tactical diagnosis from explicit StatsBomb flags and links, limited to visible events."""
from collections import Counter
from core import clock_label
from tactics import family
from field_views import field,point


def diagnose(state,tid,window=900):
    visible=[(t,e) for t,e in state['visible'] if max(0,state['cutoff']-window)<=t<=state['cutoff']]
    ids={e.get('id'):(t,e) for t,e in visible if e.get('id')}
    counts=Counter(); creators=Counter(); names={}; evidence=[]; locations=[]
    for tick,e in visible:
        if e.get('team',{}).get('id')!=tid: continue
        kind=e['type']['name']; tags=[]
        if kind=='Pass':
            p=e.get('pass',{}); complete=not p.get('outcome')
            if e.get('under_pressure') is True:
                counts['pressured_passes']+=1
                counts['pressured_complete']+=int(complete)
                tags.append('Передача под отмеченным давлением')
            if p.get('cut_back') is True:
                counts['cutbacks']+=1; counts['cutbacks_complete']+=int(complete)
                tags.append('Пас назад от лицевой')
            if p.get('through_ball') is True:
                counts['through_balls']+=1; counts['through_complete']+=int(complete)
                tags.append('Разрезающая передача')
            linked=ids.get(p.get('assisted_shot_id'))
            if linked and linked[0]>=tick and linked[1]['type']['name']=='Shot' and linked[1].get('team',{}).get('id')==tid:
                pid=e.get('player',{}).get('id')
                if pid is not None:
                    creators[pid]+=1; names[pid]=e['player']['name']
                counts['shot_assists']+=1; tags.append('Передача с подтверждённым последующим ударом')
        if kind=='Dribble':
            outcome=e.get('dribble',{}).get('outcome',{}).get('name')
            if outcome in ('Complete','Incomplete'):
                counts['dribbles']+=1; counts['dribbles_failed']+=int(outcome=='Incomplete')
                tags.append('Обводка: '+('успешная' if outcome=='Complete' else 'неудачная'))
        for tag in tags:
            evidence.append({'Время':clock_label(e),'Игрок':e.get('player',{}).get('name','—'),'Событие':tag})
            if e.get('location'):
                locations.append({'location':e['location'][:2],'tag':tag,'name':e.get('player',{}).get('name','—')})
    # A shot following a recorded loss is an observed sequence, not a causal attribution.
    used_shots=set(); episodes=[]
    for i,(tick,e) in enumerate(visible):
        if e.get('team',{}).get('id')!=tid or e['type']['name'] not in ('Miscontrol','Dispossessed'): continue
        for j,(later,event) in enumerate(visible[i+1:],i+1):
            if later-tick>12 or event.get('period')!=e.get('period'): break
            ours=event.get('team',{}).get('id')==tid
            kind=event['type']['name']
            if kind in ('Half End','Half Start','Foul Committed','Foul Won','Ball Out'): break
            if ours and (kind in ('Carry','Ball Recovery') or kind=='Pass' and not event.get('pass',{}).get('outcome')): break
            if not ours and kind=='Shot':
                shot_id=event.get('id',j)
                if shot_id not in used_shots:
                    used_shots.add(shot_id)
                    counts['shots_after_loss']+=1
                    counts['xg_after_loss']+=event.get('shot',{}).get('statsbomb_xg',0)
                    episodes.append({'Потеря':clock_label(e),'Игрок':e.get('player',{}).get('name','—'),
                                     'Удар соперника':clock_label(event),'Через секунд':round(later-tick,1),
                                     'xG удара':round(event.get('shot',{}).get('statsbomb_xg',0),3)})
                break
    leaders=[{'Игрок':names[pid],'Передач под удар':count} for pid,count in creators.most_common(3)]
    return {'counts':dict(counts),'creators':leaders,'evidence':evidence[-12:],'locations':locations,
            'episodes':episodes,'window_seconds':min(window,state['cutoff'])}


def deep_options(state,tid,goal):
    ours=diagnose(state,tid)
    opp=next(t for t in state['players'] if t!=tid)
    theirs=diagnose(state,opp)
    a,b=ours['counts'],theirs['counts']
    roles={family(p['position']) for p in state['players'][tid].values()}
    leader=theirs['creators'][0] if theirs['creators'] else {'Игрок':'не установлен','Передач под удар':0}
    def row(key,title,condition,priority,why,tasks,risk,check,groups,source):
        available=condition and bool(roles & set(groups))
        return dict(key=key,title=title,available=available,priority=priority,why=why,tasks=tasks,risk=risk,
                    check=check,roles='Исполнители указаны ниже по подтверждённым позициям',role_groups=groups,
                    event_evidence=source['evidence'],sample_note='Последние 15 минут. Пороги экспертные; позиции и расстояния без мяча не измерены.')
    return [
        row('pressure_support','Дать поддержку при передачах под давлением',
            a.get('pressured_passes',0)>=8 and a.get('pressured_complete',0)/max(1,a.get('pressured_passes',0))<.6,88,
            f'Успешных передач с флагом давления: {a.get("pressured_complete",0)} из {a.get("pressured_passes",0)}.',
            ['До приёма предложить два разных выхода: рядом и через следующую линию.',
             'Опорный открывается под скидку, сосед сохраняет возможность обратной передачи.',
             'Если выходы закрыты, не повторять рискованный пас в центр.'],
            'Безопасная передача назад может позволить сопернику поднять блок.',
            'Сравнить точность передач под отмеченным давлением и потери в своей трети.',
            ['keeper','center_back','central','full_back'],ours),
        row('dribble_support','Поддержать игрока вместо повторных обводок',
            a.get('dribbles',0)>=4 and a.get('dribbles_failed',0)>=2,68,
            f'Неудачных обводок: {a.get("dribbles_failed",0)} из {a.get("dribbles",0)}.',
            ['Предложить короткий пас до начала обводки и открывание за ближайшим соперником.',
             'Использовать стенку, если линия ответного паса открыта.',
             'При отсутствии поддержки сохранить мяч; не запрещать обводку при свободном коридоре.'],
            'Избыточные короткие передачи могут снизить темп атаки.',
            'Проверить долю успешных обводок, потери и продвижения.', ['wide','creator','central','full_back'],ours),
        row('creator_watch','Перекрыть передачи главного созидателя соперника',leader['Передач под удар']>=2,82,
            f'{leader["Игрок"]}: {leader["Передач под удар"]} передач с подтверждённым ударом.',
            ['Ближайший полузащитник закрывает удобное направление передачи созидателю.',
             'После его приёма партнёр страхует пас в штрафную, не выходя одновременно на мяч.',
             'Не назначать постоянную персональную опеку без оценки остальных угроз.'],
            'Чрезмерное внимание одному игроку освободит партнёров.',
            'Проверить новые передачи этого игрока под удар и общее число ударов соперника.',
            ['central','full_back','center_back'],theirs),
        row('cutback_defence','Закрыть передачу назад от лицевой',b.get('cutbacks_complete',0)>=3,84,
            f'Успешных пасов соперника назад от лицевой: {b.get("cutbacks_complete",0)} из {b.get("cutbacks",0)}.',
            ['Крайний защитник сдерживает продвижение к лицевой при страховке партнёра.',
             'Опорный закрывает адресата обратной передачи, защитники сохраняют контроль перед воротами.',
             'После первого касания контролировать подбор, не бежать всем к мячу.'],
            'Ранний выход опорного может открыть центр.',
            'Сравнить новые передачи назад от лицевой и удары после них.', ['full_back','central','center_back'],theirs),
        row('through_defence','Страховать разрезающие передачи',b.get('through_complete',0)>=2,78,
            f'Успешных разрезающих передач соперника: {b.get("through_complete",0)} из {b.get("through_balls",0)}.',
            ['Полузащитник затрудняет пасующему продвижение и закрывает центральную линию.',
             'Центральные защитники согласуют выход и страховку глубины.',
             'Высоту линии выбирать по реальной ситуации; скорость защитников системой не измерена.'],
            'Чрезмерное отступление отдаст пространство перед штрафной.',
            'Проверить число успешных разрезающих передач и входы соперника в штрафную.',
            ['central','center_back','full_back'],theirs),
        row('rest_defence','Сохранить страховку после потери',a.get('shots_after_loss',0)>=2,95,
            f'После зарегистрированных потерь соперник ударил в течение 12 секунд: {a.get("shots_after_loss",0)} раз; '
            f'xG этих ударов {a.get("xg_after_loss",0):.2f}. Последовательность не доказывает причину.',
            ['При атаке заранее оставить доступную страховку за мячом.',
             'После потери ближайший игрок задерживает продвижение; остальные закрывают центр.',
             'Если мяч не возвращён сразу, восстановить блок вместо одиночного давления.'],
            'Меньше игроков впереди может снизить число адресатов в штрафной.',
            'Сравнить удары соперника в течение 12 секунд после записанных потерь.',
            ['central','center_back','full_back'],ours)]


def diagnostic_map(report,opponent=False,prefix=''):
    parts=[]
    for item in report['locations']:
        if not item['tag'].startswith(prefix): continue
        loc=item['location']; x,y=loc
        if opponent: x,y=120-x,80-y
        a,b=point([x,y]); title=item['tag']+' · '+item['name']
        import html
        parts.append(f'<circle cx="{a}" cy="{b}" r="5" fill="{"#b73a40" if opponent else "#1769aa"}" opacity=".7"><title>{html.escape(title)}</title></circle>')
    return field(''.join(parts),'Записанные эпизоды тактической диагностики',light=True)
