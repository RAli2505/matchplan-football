"""Short coaching plans and observable follow-up, never causal-effect estimates."""
from core import metrics, snapshot, card, clock_label
from tactics import family, formation_options
from tactical_playbook import extended_options, detailed_instructions
from event_tactics import event_options, indicators
from deep_tactics import deep_options, diagnose


def formation_choice(state, tid, roles, profiles, goal='win'):
    if len(state['players'][tid]) != 11:
        return None
    # Rearrange only players already on the pitch; substitutions are separate decisions.
    observed_roles = dict(roles)
    observed_roles.update({pid: p['position'] for pid, p in state['players'][tid].items()})
    ranked = formation_options(state, tid, observed_roles, profiles, tuple(state['bench'][tid]), goal)
    opp = next(x for x in state['players'] if x != tid)
    diff = state['goals'][tid] - state['goals'][opp]
    need_goal = diff < 0 or diff == 0 and goal == 'win'
    minute = state['last'].get('minute', 0)
    for candidate in ranked:
        bonus = 3 if minute >= 60 and (
            need_goal and candidate['formation'] in ('4-3-3', '4-4-2') or
            not need_goal and candidate['formation'] in ('4-1-4-1', '4-2-3-1')) else 0
        candidate['score'] += bonus
        if bonus:
            candidate['rationale'] += ' Экспертная поправка +3 за соответствие цели после 60-й минуты.'
    ranked.sort(key=lambda r: (r['gaps'], -r['score'], r['formation']))
    complete = [r for r in ranked if r['gaps'] == 0]
    if not complete:
        return None
    current = next((r for r in complete if r['formation'].startswith('Объявленная ')), None)
    best = complete[0]
    if current and best['score'] - current['score'] < 2:
        best = current
    return best


def tactical_options(state, tid, goal):
    opp = next(x for x in state['players'] if x != tid)
    a, b = metrics(state, tid), metrics(state, opp)
    diff = state['goals'][tid] - state['goals'][opp]
    need_goal = diff < 0 or diff == 0 and goal == 'win'
    short = len(state['players'][tid]) < len(state['players'][opp])
    types = {family(p['position']) for p in state['players'][tid].values()}
    total = b['left'] + b['center'] + b['right']
    side = max(('left', 'center', 'right'), key=lambda x: b[x])
    names = {'left': 'нашу правую сторону', 'right': 'нашу левую сторону', 'center': 'центр'}
    concentrated = total >= 5 and b[side] / total >= .45
    pressure = b['xg'] - a['xg'] >= .35 or b['box_entries'] - a['box_entries'] >= 3
    def option(key, title, available, why, tasks, risk, check, roles):
        return dict(key=key, title=title, available=available, why=why, tasks=tasks,
                    risk=risk, check=check, roles=roles)
    return [
        option('center', 'Защитить центр', True,
               f'Входы соперника в штрафную за 15 минут: {b["box_entries"]}; xG: {b["xg"]:.2f}.',
               ['Ближайший центральный полузащитник закрывает передачу между линиями.',
                'Защитники сохраняют взаимную страховку; не выходят одновременно на одного игрока.'],
               'Соперник может получить больше свободы на флангах.', 'Сравнить частоту входов соперника в штрафную.',
               'Центральные защитники и центральные полузащитники'),
        option('flank', 'Закрыть активную зону соперника', concentrated,
               f'{b[side]} из {total} передач соперника в финальную треть направлены через {names[side]}. '
               + ('Наблюдений достаточно для локальной задачи.' if concentrated else 'Устойчивой концентрации пока нет.'),
               [f'Сместить ближайшего полузащитника на {names[side]}, не освобождая центр.',
                'Крайний защитник встречает игрока с мячом, партнёр страхует передачу за спину.'],
               'При чрезмерном смещении откроется противоположный фланг.', 'Сравнить частоту входов соперника в штрафную.',
               'Ближайший к зоне полузащитник и защитник'),
        option('width', 'Атаковать шире', need_goal and bool(types & {'wide', 'full_back'}),
               f'Нужен гол: {"да" if need_goal else "нет"}. Доступны фланговые роли: '
               f'{"да" if types & {"wide", "full_back"} else "не подтверждены"}.',
               ['Растянуть линию соперника широким расположением флангового игрока.',
                'Подключать одного партнёра; противоположный край сохраняет страховку.'],
               'Потеря мяча за спиной подключившегося защитника.', 'Проверить появление ударов и входов в штрафную.',
               'Фланговый игрок, крайний защитник и центральный нападающий'),
        option('transition', 'Быстрый выход из обороны', (short or pressure) and 'striker' in types,
               f'Меньшинство: {"да" if short else "нет"}; выраженное давление: {"да" if pressure else "нет"}.',
               ['После отбора искать доступного нападающего первым надёжным пасом.',
                'Поддерживать выход поочерёдно; не отправлять весь центр вперёд.'],
               'При неточном первом пасе давление возобновится.', 'Проверить удары своей команды и входы соперника.',
               'Нападающий и ближайший полузащитник'),
        option('press', 'Прессинг по сигналу', need_goal and not short,
               'Нужен гол и нет численного меньшинства.' if need_goal and not short else
               'Для текущей цели или численности высокий риск прессинга не обоснован.',
               ['Начинать согласованное давление только после обратного паса или плохого приёма соперника.',
                'Если первая линия пройдена, вернуться в средний блок; центр сохраняет страховку.'],
               'Соперник может пройти первую линию и атаковать свободное пространство.',
               'Проверить удары своей команды и входы соперника.', 'Нападающие и центральные полузащитники'),
        option('control', 'Контролировать преимущество', diff > 0 or diff == 0 and goal != 'win',
               f'Счёт {state["goals"][tid]}:{state["goals"][opp]}; цель — '
               + ('победить.' if goal == 'win' else 'не проиграть.'),
               ['Сохранять выход для первого паса после отбора; не прижиматься всей командой к воротам.',
                'Подключать только одного игрока за линию мяча при надёжной страховке.'],
               'Слишком пассивная игра может увеличить давление соперника.',
               'Сравнить частоту входов соперника в штрафную.', 'Опорная зона и крайние защитники')] + extended_options(state, tid, goal) + event_options(state, tid, goal) + deep_options(state, tid, goal)


def freeze_plan(state, tid, goal, option, horizon):
    opp = next(x for x in state['players'] if x != tid)
    window = min(horizon * 60, state['cutoff'])
    return {'team_id': tid, 'opponent_id': opp, 'goal': goal, 'origin': state['cutoff'],
            'clock': clock_label(state['last']), 'horizon': horizon, 'tactic': option,
            'details': detailed_instructions(state, tid, option),
            'baseline_tactical': indicators(state, tid, window)[0] if window else {},
            'baseline_deep': {'ours':diagnose(state,tid,window)['counts'],
                              'opponent':diagnose(state,opp,window)['counts']} if window else {},
            'baseline_seconds': window,
            'baseline_ours': metrics(state, tid, window) if window else None,
            'baseline_theirs': metrics(state, opp, window) if window else None}


def review_plan(plan, events, lineups, current_cutoff, rules):
    start, end = plan['origin'], plan['origin'] + plan['horizon'] * 60
    if current_cutoff < end:
        current = snapshot(events, lineups, current_cutoff, rules=rules)
        ended = current['last']['type']['name'] == 'Half End' and current['last']['period'] == 2
        return {'ready': False, 'remaining_seconds': int(end - current_cutoff), 'ended_early': ended}
    state = snapshot(events, lineups, end, rules=rules)
    # Strictly disjoint intervals: an event on the boundary belongs to baseline only.
    follow = dict(state, visible=[(t, e) for t, e in state['visible'] if start < t <= end])
    ours, theirs = metrics(follow, plan['team_id'], 0), metrics(follow, plan['opponent_id'], 0)
    triggers = [clock_label(e) + ' — ' + e['type']['name'] for _, e in follow['visible']
                if e['type']['name'] in ('Substitution', 'Own Goal Against') or
                e['type']['name'] == 'Shot' and e.get('shot', {}).get('outcome', {}).get('name') == 'Goal' or
                card(e) in ('Red Card', 'Second Yellow')]
    result = {'ready': True, 'ours': ours, 'theirs': theirs, 'triggers': triggers,
              'comparable': plan['baseline_seconds'] >= 300}
    measured, _ = indicators(follow, plan['team_id'], plan['horizon']*60)
    relevant = {
        'safe_exit': ['deep_failed', 'deep_losses'], 'cutback': ['crosses', 'crosses_complete', 'shots'],
        'shot_selection': ['shots', 'outside_shots'], 'progression': ['final_third_entries', 'deep_losses'],
        'foul_discipline': ['deep_fouls', 'fouls'], 'second_ball': []}.get(plan['tactic']['key'], [])
    labels = {'deep_failed': 'Неточные передачи в своей трети', 'deep_losses': 'Потери в своей трети',
              'crosses': 'Подачи', 'crosses_complete': 'Успешные подачи', 'shots': 'Удары',
              'outside_shots': 'Удары до линии штрафной', 'final_third_entries': 'Входы передачей в финальную треть',
              'deep_fouls': 'Фолы в своей трети', 'fouls': 'Все фолы'}
    result['task_metrics'] = [{'Показатель': labels[key],
        'До плана / мин': round(plan.get('baseline_tactical', {}).get(key,0)/(plan['baseline_seconds']/60),3),
        'После плана / мин': round(measured.get(key,0)/plan['horizon'],3)} for key in relevant] if result['comparable'] and 'baseline_tactical' in plan else []
    advanced = {'pressure_support':('ours',['pressured_passes','pressured_complete']),
                'dribble_support':('ours',['dribbles','dribbles_failed']),
                'creator_watch':('opponent',['shot_assists']),
                'cutback_defence':('opponent',['cutbacks_complete']),
                'through_defence':('opponent',['through_complete']),
                'rest_defence':('ours',['shots_after_loss'])}.get(plan['tactic']['key'])
    if advanced and result['comparable'] and plan.get('baseline_deep'):
        side, keys = advanced
        now = diagnose(follow,plan['team_id'] if side=='ours' else plan['opponent_id'],plan['horizon']*60)['counts']
        titles={'pressured_passes':'Наши передачи под отмеченным давлением', 'pressured_complete':'Успешные передачи под давлением',
                'dribbles':'Наши обводки','dribbles_failed':'Неудачные обводки',
                'shot_assists':'Все передачи соперника под удар', 'cutbacks_complete':'Успешные пасы соперника назад от лицевой',
                'through_complete':'Успешные разрезающие передачи соперника','shots_after_loss':'Удары соперника после наших записанных потерь'}
        result['task_metrics']=[{'Показатель':titles[key],
            'До плана / мин':round(plan['baseline_deep'][side].get(key,0)/(plan['baseline_seconds']/60),3),
            'После плана / мин':round(now.get(key,0)/plan['horizon'],3)} for key in keys]
    if result['comparable']:
        before = plan['baseline_theirs']['box_entries'] / (plan['baseline_seconds'] / 60)
        after = theirs['box_entries'] / plan['horizon']
        result.update(before_entries_per_minute=before, after_entries_per_minute=after,
                      fewer_opponent_entries=after < before, created_shot=ours['shots'] > 0)
    return result
