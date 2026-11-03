"""Deterministic match replay and explainable decision support. No future events."""
from __future__ import annotations

import json
import zipfile
from collections import Counter
from pathlib import Path
from preprocessing import prepare_events, validate_lineups, validate_matches

ARCHIVE = Path(__file__).resolve().parents[1] / 'open-data-master.zip'
TEAM_ID = 904
PLANS = {'cautious': 'Осторожный', 'balanced': 'Сбалансированный', 'attacking': 'Атакующий'}


def competition_rules(competition_id, season_id):
    if (competition_id, season_id) == (2, 27):
        return {'sub_limit': 3, 'window_limit': None, 'label': 'Premier League 2015/16'}
    if (competition_id, season_id) == (9, 281):
        return {'sub_limit': 5, 'window_limit': 3, 'label': 'Bundesliga 2023/24'}
    raise ValueError('Регламент замен для этого соревнования и сезона не настроен.')


def read_json(relative, archive=ARCHIVE):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        name = next((n for n in names if n.endswith('/data/' + relative)), None)
        if name is None:
            raise ValueError(f'В архиве отсутствует data/{relative}')
        return json.loads(z.read(name))


def matches(competition_id=9, season_id=281):
    games = read_json(f'matches/{competition_id}/{season_id}.json')
    validate_matches(games)
    return sorted(games, key=lambda m: (m['match_date'], m.get('kick_off', ''), m['match_id']))


def match_data(match_id):
    events, _ = prepare_events(read_json(f'events/{match_id}.json'))
    lineups = read_json(f'lineups/{match_id}.json')
    validate_lineups(lineups)
    return events, lineups


def seconds(event):
    h, m, s = event.get('timestamp', '00:00:00').split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def timeline(events):
    """Sequential period clocks preserve first-half stoppage before second half."""
    durations = {}
    for e in events:
        if e.get('period', 1) <= 2:
            p = e.get('period', 1)
            durations[p] = max(durations.get(p, 0), seconds(e))
    offsets = {1: 0, 2: durations.get(1, 2700) + 1}
    return [(offsets[e['period']] + seconds(e), e) for e in events if e.get('period') in offsets]


def clock_label(event):
    p = event.get('period', 1)
    base = 0 if p == 1 else 45
    sec = int(seconds(event))
    mm, ss = divmod(sec, 60)
    label = f'{base + mm:02}:{ss:02}' if mm < 45 else f'{base + 45}+{mm - 45:02}:{ss:02}'
    return f'{label} · {p}-й тайм'


def card(event):
    for field in ('foul_committed', 'bad_behaviour'):
        value = event.get(field, {}).get('card', {}).get('name')
        if value:
            return value
    return None


def snapshot(events, lineups, cutoff, rules=None):
    timed = timeline(events)
    visible = [(t, e) for t, e in timed if t <= cutoff]
    state = {'players': {}, 'bench': {}, 'removed': set(), 'yellow': set(),
             'rules': dict(rules) if rules is not None else competition_rules(9, 281),
             'red': Counter(), 'goals': Counter(), 'subs': Counter(), 'windows': {},
             'formation': {}, 'visible': visible, 'cutoff': cutoff, 'entered': {},
             'last': visible[-1][1] if visible else {'period': 1, 'timestamp': '00:00:00', 'minute': 0}}
    # Only identities and squad membership from lineups: never read future cards/positions.
    for team in lineups:
        tid = team['team_id']
        state['players'][tid] = {}
        state['bench'][tid] = {p['player_id']: {'id': p['player_id'], 'name': p['player_name'],
            'number': p['jersey_number'], 'position': 'Позиция не подтверждена'} for p in team['lineup']}
        state['windows'][tid] = set()
    play_sequence = 0
    for t, e in visible:
        tid = e.get('team', {}).get('id')
        kind = e['type']['name']
        if kind in ('Pass', 'Carry', 'Shot', 'Duel', 'Dribble', 'Pressure', 'Ball Receipt*', 'Clearance', 'Ball Recovery'):
            play_sequence += 1
        if kind in ('Starting XI', 'Tactical Shift'):
            state['formation'][tid] = str(e['tactics']['formation'])
            for item in e['tactics']['lineup']:
                pid = item['player']['id']
                if pid in state['removed']:
                    continue  # Some source tactical shifts contain previously sent-off players.
                player = {'id': pid, 'name': item['player']['name'], 'number': item['jersey_number'],
                          'position': item['position']['name']}
                state['players'][tid][pid] = player
                state['bench'][tid].pop(pid, None)
                state['entered'].setdefault(pid, t if kind == 'Starting XI' else 0)
        if kind == 'Substitution':
            out = e['player']['id']
            replacement = e['substitution']['replacement']
            pid = replacement['id']
            old = state['players'][tid].pop(out, {})
            new = state['bench'][tid].pop(pid, {'id': pid, 'name': replacement['name'], 'number': '?'})
            new['position'] = old.get('position', e.get('position', {}).get('name', 'Unknown'))
            state['players'][tid][pid] = new
            state['removed'].add(out)
            state['entered'][pid] = t
            state['subs'][tid] += 1
            # Interval substitutions do not consume an in-play window.
            if not (e['period'] == 2 and seconds(e) == 0):
                state['windows'][tid].add((e['period'], play_sequence))
        c = card(e)
        if c and 'player' in e:
            pid = e['player']['id']
            if c == 'Yellow Card':
                state['yellow'].add(pid)
            elif c in ('Red Card', 'Second Yellow'):
                if pid in state['players'].get(tid, {}):
                    state['red'][tid] += 1
                state['players'][tid].pop(pid, None)
                state['bench'][tid].pop(pid, None)
                state['removed'].add(pid)
        if kind == 'Shot' and e.get('shot', {}).get('outcome', {}).get('name') == 'Goal':
            state['goals'][tid] += 1
        if kind == 'Own Goal Against':
            other = next(k for k in state['players'] if k != tid)
            state['goals'][other] += 1
    return state


def metrics(state, tid, window=900):
    result = {'shots': 0, 'xg': 0., 'box_entries': 0, 'passes': 0, 'left': 0, 'right': 0, 'center': 0}
    start = state['cutoff'] - window if window else -1
    for t, e in state['visible']:
        if t < start or e.get('team', {}).get('id') != tid:
            continue
        kind = e['type']['name']
        if kind == 'Shot':
            result['shots'] += 1
            result['xg'] += e['shot'].get('statsbomb_xg', 0)
        if kind == 'Pass':
            result['passes'] += 1
            pas = e.get('pass', {})
            if 'outcome' not in pas:
                loc = e.get('location', [0, 40])
                end = pas.get('end_location', loc)
                if end[0] >= 102 and 18 <= end[1] <= 62 and not (loc[0] >= 102 and 18 <= loc[1] <= 62):
                    result['box_entries'] += 1
                if end[0] >= 80:
                    result['left' if end[1] < 27 else 'right' if end[1] > 53 else 'center'] += 1
        if kind == 'Carry':
            loc = e.get('location', [0, 40])
            end = e.get('carry', {}).get('end_location', loc)
            if end[0] >= 102 and 18 <= end[1] <= 62 and not (loc[0] >= 102 and 18 <= loc[1] <= 62):
                result['box_entries'] += 1
    return result


def role_group(position):
    if position == 'Goalkeeper': return 'GK'
    if 'Back' in position: return 'DEF'
    if 'Defensive Midfield' in position or 'Center Midfield' in position: return 'MID'
    if 'Midfield' in position or 'Forward' in position or 'Wing' in position: return 'ATT'
    return 'UNK'


def historical_roles(previous_events):
    """Position priors from strictly earlier matches, never the current lineup's future."""
    counts = {}
    for events in previous_events:
        for e in events:
            if e['type']['name'] == 'Starting XI':
                for item in e['tactics']['lineup']:
                    counts.setdefault(item['player']['id'], Counter())[item['position']['name']] += 1
            elif 'player' in e and 'position' in e:
                counts.setdefault(e['player']['id'], Counter())[e['position']['name']] += 1
    return {pid: counter.most_common(1)[0][0] for pid, counter in counts.items()}


def historical_profiles(previous_events):
    """Simple prior-use evidence, not a universal ability rating."""
    profiles = {}
    for events in previous_events:
        used = set()
        for e in events:
            if e['type']['name'] == 'Starting XI':
                for item in e['tactics']['lineup']:
                    pid = item['player']['id']
                    profiles.setdefault(pid, {'starts': 0, 'matches': 0, 'shots': 0, 'progressive_passes': 0})['starts'] += 1
                    used.add(pid)
            if 'player' not in e: continue
            pid = e['player']['id']
            p = profiles.setdefault(pid, {'starts': 0, 'matches': 0, 'shots': 0, 'progressive_passes': 0})
            used.add(pid)
            if e['type']['name'] == 'Shot': p['shots'] += 1
            if e['type']['name'] == 'Pass' and 'outcome' not in e.get('pass', {}):
                start = e.get('location', [0, 0])
                end = e['pass'].get('end_location', start)
                if end[0] - start[0] >= 15: p['progressive_passes'] += 1
        for pid in used:
            profiles.setdefault(pid, {'starts': 0, 'matches': 0, 'shots': 0, 'progressive_passes': 0})['matches'] += 1
    return profiles


def propose_lineup(initial, tid, roles, profiles, unavailable=(), goal='win'):
    """Greedy role assignment to the observed formation, with explicit gaps."""
    squad = {**initial['bench'][tid], **initial['players'][tid]}
    known = {pid: roles.get(pid, p['position']) for pid, p in squad.items()}
    pool = {pid: p for pid, p in squad.items() if pid not in unavailable}
    result = []
    slots = sorted(initial['players'][tid].values(), key=lambda p: (role_group(p['position']) != 'GK', p['position']))
    for slot in slots:
        position = slot['position']
        group = role_group(position)
        candidates = []
        for pid, p in pool.items():
            candidate_role = known[pid]
            if role_group(candidate_role) != group: continue
            history = profiles.get(pid, {})
            appearances = max(1, history.get('matches', 0))
            score = 4 * int(candidate_role == position) + 2 * history.get('starts', 0) / appearances
            # Small transparent preference; no inferred defensive ability without data.
            if goal == 'win' and group in ('MID', 'ATT'):
                score += min(1, history.get('shots', 0) / appearances / 3)
                score += min(1, history.get('progressive_passes', 0) / appearances / 10)
            candidates.append((score, pid))
        if candidates:
            score, pid = max(candidates)
            p = dict(pool.pop(pid))
            p['position'] = position
            p['evidence'] = f'Роль: {known[pid]}; предыдущих матчей: {profiles.get(pid, {}).get("matches", 0)}'
            result.append(p)
        else:
            result.append({'id': -len(result)-1, 'name': 'Не хватает данных / игрока', 'number': '—',
                           'position': position, 'evidence': 'Нет доступного кандидата с подтверждённой группой ролей.'})
    return result


def recommend(state, tid, goal='win', roles=None, plan_override=None):
    roles = roles or {}
    opponent = next(k for k in state['players'] if k != tid)
    ours, theirs = metrics(state, tid), metrics(state, opponent)
    diff = state['goals'][tid] - state['goals'][opponent]
    minute = state['last'].get('minute', 0)
    late = minute >= 60
    short = len(state['players'][tid]) < len(state['players'][opponent])
    scores = {'cautious': 0., 'balanced': 2., 'attacking': 0.}
    evidence = []
    if diff < 0:
        # The closer the end, the more the selected objective should affect risk.
        scores['attacking'] += 5 if late else 3
        evidence.append(f'Команда уступает в счёте: {state["goals"][tid]}:{state["goals"][opponent]}.')
    elif diff > 0:
        lead_weight = 4 if late else 2
        scores['cautious'] += lead_weight if goal == 'draw' else max(1, lead_weight - 1)
        evidence.append('Команда ведёт; важность сохранения преимущества зависит от выбранной цели.')
    elif goal == 'win':
        scores['attacking'] += 4 if late else 1
        evidence.append('При равном счёте цель «победить» требует поиска гола.')
    else:
        scores['cautious'] += 4 if late else 1
        evidence.append('Равный счёт соответствует цели «не проиграть».')
    if short:
        scores['cautious'] += 3
        # Preserve a route back into the game when time is running out, while
        # keeping the cost of playing a man down visible in the risk field.
        scores['attacking'] -= 1 if late and diff < 0 else 2
        evidence.append('Численное меньшинство ограничивает прессинг и выбор замен; структура требует страховки.')
    pressure = theirs['xg'] - ours['xg'] >= .35 or theirs['box_entries'] - ours['box_entries'] >= 3
    if pressure:
        scores['balanced'] += 1
        scores['cautious'] += 2 if diff >= 0 else 0
        evidence.append(f'За последние 15 минут: xG {ours["xg"]:.2f} против {theirs["xg"]:.2f}, '
                        f'входы в штрафную {ours["box_entries"]} против {theirs["box_entries"]}.')
    if minute >= 75 and ours['shots'] == 0 and (diff < 0 or goal == 'win' and diff == 0):
        scores['attacking'] += 1
        evidence.append('В последнем 15-минутном окне нет ударов; времени на гол мало.')
    ordered_scores = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    chosen = plan_override if plan_override in scores else ordered_scores[0][0]
    alternative = next(key for key, _ in ordered_scores if key != chosen)
    margin = scores[chosen] - scores[alternative]
    if margin >= 3:
        recommendation_strength = 'Выраженный перевес правил'
    elif margin >= 1:
        recommendation_strength = 'Умеренный перевес правил'
    else:
        recommendation_strength = 'Варианты близки: сравните риски перед выбором'
    plans = {
        'cautious': ('Сохранять компактность между линиями; продвигаться после надёжного первого паса.',
                     'Средний или низкий блок; выборочный прессинг после плохого приёма.',
                     'Снижение числа игроков впереди может позволить сопернику закрепиться у штрафной.'),
        'balanced': ('Сохранить текущую структуру; подключать к атаке только одного крайнего защитника.',
                     'Средний блок; прессинг по триггеру с подстраховкой центра.',
                     'Без усиления атаки может не хватить моментов для победного гола.'),
        'attacking': ('Добавить игрока между линиями; ускорить продвижение и увеличить присутствие в штрафной.',
                      'Поднимать прессинг только при сохранении страховки против контратак.',
                      'Повышается уязвимость после потери мяча; особенно опасно в меньшинстве.')}
    attack, defense, risk = plans[chosen]
    if diff > 0 and goal == 'win':
        attack = 'Сохранять контроль мяча и продолжать создавать моменты; не снижать блок чрезмерно.'
        evidence.append('Цель — победить: преимущество нужно сохранить, продолжая искать возможность увеличить счёт.')
    elif diff > 0:
        attack = 'Поддерживать владение безопасными передачами; подключать вперёд только при надёжной страховке.'
        evidence.append('Цель — не проиграть: текущий счёт уже выполняет минимальное условие цели.')
    elif diff == 0 and goal == 'draw':
        attack = 'Сохранять владение и выбирать безопасные продвижения; не открывать структуру без явного повода.'
    elif diff < 0:
        attack = 'Ускорить продвижение и чаще доводить атаки до штрафной; оставить страховку от контратаки.'
    if short:
        defense = 'Сначала восстановить компактную структуру с учётом удаления; избегать несогласованного высокого прессинга.'
    if short and chosen == 'attacking':
        attack = 'Искать быстрый выход через доступного нападающего; поддерживать его поочерёдно, сохраняя игроков за мячом.'
    if pressure:
        defense = ('Сократить расстояния между защитой и полузащитой; закрывать передачу в штрафную и подбирать отскок. '
                   'Прессинг начинать согласованно, после обратной передачи соперника.')
        if short:
            defense += ' В меньшинстве не выводить сразу нескольких игроков из блока.'
    if diff < 0:
        objective = 'Нужен гол, чтобы вернуться к целевому результату.'
    elif diff == 0 and goal == 'win':
        objective = 'Нужен победный гол; при продвижении сохраняйте страховку.'
    elif diff == 0:
        objective = 'Ничья соответствует цели. Сохраняйте баланс и используйте безопасные возможности для гола.'
    else:
        objective = 'Сохраните преимущество, продолжая выходить из-под давления.'
    actions = [attack, defense]
    if minute >= 60 and ours['shots'] == 0 and (diff < 0 or diff == 0 and goal == 'win'):
        actions.insert(0, f'За последние 15 минут нет ударов. Доводите продвижения до завершения; '
                       f'входов в штрафную за это окно: {ours["box_entries"]}.')
    review = ('Пересмотреть сразу после гола, удаления или замены; без таких событий — через 5 игровых минут. '
              'Проверить, появились ли удары и снизилось ли давление соперника.')
    sub = None
    sub_options = []
    # Rules belong to a competition-season, not to the present-day game.
    at_interval = state['last'].get('period') == 2 and seconds(state['last']) == 0
    rules = state.get('rules', competition_rules(9, 281))
    allowed = state['subs'][tid] < rules['sub_limit'] and (rules['window_limit'] is None or
              len(state['windows'][tid]) < rules['window_limit'] or at_interval)
    if minute >= 60 and allowed:
        candidates = []
        for pid, player in state['players'][tid].items():
            group = role_group(player['position'])
            if group == 'GK': continue
            priority = (2 if pid in state['yellow'] else 0) + min(100, (state['cutoff'] - state['entered'].get(pid, 0)) / 60) / 100
            target = 'ATT' if chosen == 'attacking' else 'DEF' if chosen == 'cautious' else group
            for bid, bench in state['bench'][tid].items():
                position = roles.get(bid)
                if position and role_group(position) == group and (chosen == 'balanced' or group == target):
                    # Exact known role takes priority over a broad group match.
                    compatibility = 1 if position == player['position'] else 0
                    candidates.append((priority, compatibility, pid, bid, position))
        for _, compatibility, out, incoming, position in sorted(candidates, reverse=True)[:3]:
            minutes_on_pitch = max(0, int((state['cutoff'] - state['entered'].get(out, 0)) / 60))
            sub_options.append({'out_id': out, 'in_id': incoming,
                   'out': state['players'][tid][out]['name'], 'in': state['bench'][tid][incoming]['name'],
                   'position': position, 'reason':
                   (f'У уходящего игрока жёлтая карточка; ' if out in state['yellow'] else '') +
                   f'на поле около {minutes_on_pitch} минут. ' +
                   ('Роль запасного совпадает с текущей ролью.' if compatibility else
                    'Подтверждена только общая группа ролей; точную позицию нужно согласовать.') +
                   ' Это кандидат для проверки тренером: физическая готовность и усталость не измерены.',
                   'minutes': minutes_on_pitch, 'yellow': out in state['yellow'], 'exact_role': bool(compatibility)})
        sub = sub_options[0] if sub_options else None
    return {'plan': chosen, 'scores': scores, 'evidence': evidence, 'attack': attack, 'defense': defense,
            'risk': risk, 'sub': sub, 'sub_options': sub_options, 'subs_allowed': allowed,
            'margin': margin, 'recommendation_strength': recommendation_strength,
            'alternative': alternative, 'objective': objective, 'actions': actions[:3], 'review': review,
            'finished': state['last']['type']['name'] == 'Half End' and state['last']['period'] == 2}


def decision_log(events, lineups, cutoff, tid, goal, roles=None, rules=None):
    """Replay checkpoints; switch only at >=2 point advantage, except goal/red triggers."""
    timed = timeline(events)
    points = {0., float(cutoff)}
    points.update(float(t) for t in range(300, int(cutoff) + 1, 300))
    triggers = set()
    for t, e in timed:
        if t <= cutoff and (e['type']['name'] in ('Substitution', 'Own Goal Against') or
            e['type']['name'] == 'Shot' and e.get('shot', {}).get('outcome', {}).get('name') == 'Goal' or
            card(e) in ('Red Card', 'Second Yellow')):
            points.add(t)
            triggers.add(t)
    log, previous = [], None
    for t in sorted(points):
        state = snapshot(events, lineups, t, rules=rules)
        rec = recommend(state, tid, goal, roles)
        if rec['finished']: continue
        proposal = rec['plan']
        if previous and proposal != previous and t not in triggers and rec['scores'][proposal] - rec['scores'][previous] < 2:
            proposal = previous
        if proposal != previous:
            log.append({'time': clock_label(state['last']), 'plan': PLANS[proposal],
                        'reason': ' '.join(rec['evidence']), 'key': proposal, 'cutoff': t})
            previous = proposal
    return log
