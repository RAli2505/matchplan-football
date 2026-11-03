"""Role assignment and opponent analysis; all inputs must precede the target match."""
from copy import deepcopy
from core import clock_label, metrics, snapshot, timeline, role_group

FORMATIONS = {
    '4-3-3': ['Goalkeeper', 'Right Back', 'Right Center Back', 'Left Center Back', 'Left Back',
              'Center Defensive Midfield', 'Right Center Midfield', 'Left Center Midfield',
              'Right Wing', 'Left Wing', 'Center Forward'],
    '4-2-3-1': ['Goalkeeper', 'Right Back', 'Right Center Back', 'Left Center Back', 'Left Back',
                'Right Defensive Midfield', 'Left Defensive Midfield', 'Right Attacking Midfield',
                'Center Attacking Midfield', 'Left Attacking Midfield', 'Center Forward'],
    '3-4-2-1': ['Goalkeeper', 'Right Center Back', 'Center Back', 'Left Center Back',
                'Right Wing Back', 'Left Wing Back', 'Right Center Midfield', 'Left Center Midfield',
              'Right Attacking Midfield', 'Left Attacking Midfield', 'Center Forward'],
    '4-4-2': ['Goalkeeper', 'Right Back', 'Right Center Back', 'Left Center Back', 'Left Back',
              'Right Midfield', 'Right Center Midfield', 'Left Center Midfield', 'Left Midfield',
              'Right Center Forward', 'Left Center Forward'],
    '4-1-4-1': ['Goalkeeper', 'Right Back', 'Right Center Back', 'Left Center Back', 'Left Back',
                'Center Defensive Midfield', 'Right Midfield', 'Right Center Midfield',
                'Left Center Midfield', 'Left Midfield', 'Center Forward'],
    '3-5-2': ['Goalkeeper', 'Right Center Back', 'Center Back', 'Left Center Back',
              'Right Wing Back', 'Left Wing Back', 'Center Defensive Midfield',
              'Right Center Midfield', 'Left Center Midfield', 'Right Center Forward', 'Left Center Forward'],
    '3-4-3': ['Goalkeeper', 'Right Center Back', 'Center Back', 'Left Center Back',
              'Right Wing Back', 'Left Wing Back', 'Right Center Midfield', 'Left Center Midfield',
              'Right Wing', 'Left Wing', 'Center Forward'],
    '4-5-1': ['Goalkeeper', 'Right Back', 'Right Center Back', 'Left Center Back', 'Left Back',
              'Right Midfield', 'Right Center Midfield', 'Center Midfield', 'Left Center Midfield',
              'Left Midfield', 'Center Forward'],
    '5-4-1': ['Goalkeeper', 'Right Wing Back', 'Right Center Back', 'Center Back', 'Left Center Back',
              'Left Wing Back', 'Right Midfield', 'Right Center Midfield', 'Left Center Midfield',
              'Left Midfield', 'Center Forward'],
    '4-3-1-2': ['Goalkeeper', 'Right Back', 'Right Center Back', 'Left Center Back', 'Left Back',
               'Center Defensive Midfield', 'Right Center Midfield', 'Left Center Midfield',
               'Center Attacking Midfield', 'Right Center Forward', 'Left Center Forward'],
    '4-3-2-1': ['Goalkeeper', 'Right Back', 'Right Center Back', 'Left Center Back', 'Left Back',
               'Center Defensive Midfield', 'Right Center Midfield', 'Left Center Midfield',
               'Right Attacking Midfield', 'Left Attacking Midfield', 'Center Forward'],
    '5-3-2': ['Goalkeeper', 'Right Wing Back', 'Right Center Back', 'Center Back', 'Left Center Back',
             'Left Wing Back', 'Center Defensive Midfield', 'Right Center Midfield', 'Left Center Midfield',
             'Right Center Forward', 'Left Center Forward'],
    '4-2-2-2': ['Goalkeeper','Right Back','Right Center Back','Left Center Back','Left Back',
               'Right Defensive Midfield','Left Defensive Midfield','Right Attacking Midfield',
               'Left Attacking Midfield','Right Center Forward','Left Center Forward'],
    '3-4-1-2': ['Goalkeeper','Right Center Back','Center Back','Left Center Back','Right Wing Back',
               'Left Wing Back','Right Center Midfield','Left Center Midfield','Center Attacking Midfield',
               'Right Center Forward','Left Center Forward']}


def family(position):
    if position == 'Goalkeeper': return 'keeper'
    if 'Center Back' in position: return 'center_back'
    if 'Back' in position: return 'full_back'
    if 'Defensive Midfield' in position or 'Center Midfield' in position: return 'central'
    if 'Wing' in position or position in ('Left Midfield', 'Right Midfield'): return 'wide'
    if 'Attacking Midfield' in position or 'Secondary' in position: return 'creator'
    if 'Forward' in position: return 'striker'
    return 'unknown'


def fit_score(source, target):
    if source == target: return 5.
    a, b = family(source), family(target)
    if a == 'unknown' or b == 'unknown': return None
    if a == b: return 3.
    if {a, b} in ({'wide', 'creator'}, {'creator', 'striker'}): return 1.
    return None


def assign_roles(scores, slots):
    """Exact dynamic programming: maximize filled slots, then fit; no repeated player."""
    dp = {0: (0., [None] * slots)}
    for pid, row in sorted(scores.items()):
        updated = dict(dp)
        for mask, (total, assignment) in dp.items():
            for j, score in enumerate(row):
                if score is None or mask & (1 << j): continue
                newmask = mask | (1 << j)
                value = total + score
                if newmask not in updated or value > updated[newmask][0]:
                    order = assignment.copy()
                    order[j] = pid
                    updated[newmask] = (value, order)
        dp = updated
    best = max(dp, key=lambda mask: (mask.bit_count(), dp[mask][0]))
    return dp[best][1], dp[best][0]


def formation_options(initial, tid, roles, profiles, unavailable=(), goal='win', opponent=None):
    squad = {**initial['bench'][tid], **initial['players'][tid]}
    pool = {pid: p for pid, p in squad.items() if pid not in unavailable}
    templates = dict(FORMATIONS)
    actual = list(initial['players'][tid].values())
    if len(actual) == 11:
        templates['Объявленная ' + '–'.join(initial['formation'].get(tid, '?'))] = [p['position'] for p in actual]
    result = []
    for name, slots in templates.items():
        scores = {}
        for pid, p in pool.items():
            source = roles.get(pid, p['position'])
            history = profiles.get(pid, {})
            n = max(1, history.get('matches', 0))
            bonus = 2 * history.get('starts', 0) / n
            if goal == 'win':
                bonus += min(1, history.get('shots', 0) / n / 3) + min(1, history.get('progressive_passes', 0) / n / 10)
            scores[pid] = [None if fit_score(source, target) is None else fit_score(source, target) + bonus for target in slots]
        order, total = assign_roles(scores, len(slots))
        lineup = []
        for i, (pid, position) in enumerate(zip(order, slots)):
            if pid is None:
                lineup.append({'id': -i-1, 'name': 'Нет подтверждённого кандидата', 'number': '—',
                               'position': position, 'evidence': 'Не хватает доступного игрока с совместимой ролью.'})
            else:
                p = dict(pool[pid])
                p['position'] = position
                p['evidence'] = f'Роль: {roles.get(pid, pool[pid]["position"])}; прошлых матчей: {profiles.get(pid, {}).get("matches", 0)}'
                lineup.append(p)
        adjustment = 0.
        rationale = 'Оценка совместимости игроков с ролями.'
        if opponent and opponent['matches'] >= 3:
            if goal == 'win' and name == '4-3-3' and opponent['xg_against_per_match'] >= 1.3:
                adjustment = 1.
                rationale += ' Небольшой сценарный бонус атакующей ширине: соперник допускал много xG.'
            if goal != 'win' and name == '4-2-3-1' and opponent['xg_per_match'] >= 1.3:
                adjustment = 1.
                rationale += ' Небольшой сценарный бонус двум опорным: соперник создавал много xG.'
        result.append({'formation': name, 'lineup': lineup, 'fit': round(total, 2),
                       'score': round(total + adjustment, 2), 'gaps': sum(pid is None for pid in order), 'rationale': rationale})
    return sorted(result, key=lambda x: (x['gaps'], -x['score'], x['formation']))


def opponent_profile(previous_events, tid):
    samples = []
    for events in previous_events:
        starts = [e for e in events if e['type']['name'] == 'Starting XI']
        ids = [e['team']['id'] for e in starts]
        if tid not in ids or len(ids) != 2: continue
        other = next(x for x in ids if x != tid)
        end = max(t for t, _ in timeline(events)) + 1
        # metrics needs only visible events/cutoff, not future participation metadata.
        state = {'visible': timeline(events), 'cutoff': end}
        samples.append((metrics(state, tid, 0), metrics(state, other, 0)))
    samples = samples[-5:]
    n = len(samples)
    channels = {side: sum(ours[side] for ours, _ in samples) for side in ('left', 'center', 'right')}
    return {'matches': n, 'shots_per_match': sum(a['shots'] for a, _ in samples) / n if n else 0.,
            'xg_per_match': sum(a['xg'] for a, _ in samples) / n if n else 0.,
            'xg_against_per_match': sum(b['xg'] for _, b in samples) / n if n else 0.,
            'attack_channel': max(channels, key=channels.get) if sum(channels.values()) else 'unknown',
            'channels': channels}


def tactical_details(state, tid, plan, previous=None):
    opponent = next(x for x in state['players'] if x != tid)
    recent = metrics(state, opponent)
    channels = {side: recent[side] for side in ('left', 'center', 'right')}
    total = sum(channels.values())
    side = max(channels, key=channels.get)
    names = {'left': 'левый фланг соперника (наша правая сторона)',
             'right': 'правый фланг соперника (наша левая сторона)', 'center': 'центр'}
    actions = []
    recent_shots = [(tick, event) for tick, event in state['visible']
                    if tick >= state['cutoff'] - 900 and event.get('team', {}).get('id') == opponent
                    and event['type']['name'] == 'Shot']
    if recent_shots:
        tick, last_shot = recent_shots[-1]
        shooter = last_shot.get('player', {}).get('name', 'игрок соперника')
        actions.append(f'За последние 15 минут соперник нанёс {recent["shots"]} удара '
                       f'(суммарный xG {recent["xg"]:.2f}); последний — {shooter}, {clock_label(last_shot)}. '
                       'Усилить контроль подбора и не оставлять свободного игрока у штрафной.')
    if total >= 5 and channels[side] / total >= .45:
        actions.append(f'Соперник направил {channels[side]} из {total} успешных передач в финальную треть через {names[side]}. '
                       'Подстраховать эту зону ближайшим полузащитником; направление атаки не равно доказанной слабости.')
    if previous and previous['matches']:
        actions.append(f'До матча доступно {previous["matches"]} наблюдений соперника: '
                       f'xG за игру {previous["xg_per_match"]:.2f}, допущенный xG {previous["xg_against_per_match"]:.2f}. '
                       + ('Выборка мала: использовать как контекст.' if previous['matches'] < 3 else 'Учитывать ограничения доступной исторической выборки.'))
    ours = len(state['players'][tid])
    theirs = len(state['players'][opponent])
    if ours < theirs:
        shape = '4-4-1' if ours == 10 else f'Компактный блок: {ours} игроков'
        actions.append('Не предлагать схему на 11 игроков при меньшем составе. Сначала закрыть свободную роль после потери игрока.')
    else:
        actual = state.get('formation', {}).get(tid, '')
        shape = 'Сохранить текущую расстановку' + (f' ({"–".join(actual)})' if actual else '')
        actions.append('Менять задачи игроков внутри подтверждённой расстановки. '
                       'Новую схему сначала проверьте в разделе подбора состава: для неё нужны совместимые роли.')
    return {'shape_hint': shape, 'actions': actions,
            'tempo': 'Повышать при контролируемом риске' if plan == 'attacking' else 'Умеренный, без форсирования',
            'width': 'Использовать ширину и поддерживать центр' if plan == 'attacking' else 'Сохранять компактность и выходы на фланги'}


def scenario_state(state, tid, goals_for, goals_against, injured=(), unavailable_bench=(), sent_off=()):
    result = deepcopy(state)
    opponent = next(x for x in result['players'] if x != tid)
    result['goals'][tid], result['goals'][opponent] = int(goals_for), int(goals_against)
    for pid in injured:
        result['players'][tid].pop(pid, None)
        result['removed'].add(pid)
    for pid in sent_off:
        if pid in result['players'][tid]:
            result['players'][tid].pop(pid)
            result['removed'].add(pid)
            result['red'][tid] += 1
    for pid in unavailable_bench:
        result['bench'][tid].pop(pid, None)
    result['scenario'] = True
    return result
