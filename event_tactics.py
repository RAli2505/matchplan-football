"""Transparent event-based tactical signals. Thresholds are expert rules, not learned effects."""
from collections import Counter
from core import clock_label
from field_views import field, point


def indicators(state, tid, window=900):
    result = Counter()
    evidence = []
    for tick, e in state['visible']:
        if not max(0, state['cutoff']-window) <= tick <= state['cutoff'] or e.get('team', {}).get('id') != tid:
            continue
        kind, loc = e['type']['name'], e.get('location', [])
        tag = None
        if kind == 'Pass':
            p, end = e.get('pass', {}), e.get('pass', {}).get('end_location', [])
            complete = not p.get('outcome')
            if loc and end and loc[0] < 40 and end[0]-loc[0] >= 30:
                result['long_exits'] += 1
            if loc and loc[0] < 40:
                result['deep_passes'] += 1
                if not complete:
                    result['deep_failed'] += 1; tag = 'Неточная передача в своей трети'
            if p.get('cross'):
                result['crosses'] += 1
                result['crosses_complete'] += int(complete)
                tag = 'Подача: ' + ('успешная' if complete else 'неточная')
            if complete and loc and end and loc[0] < 80 <= end[0]:
                result['final_third_entries'] += 1
            if p.get('type', {}).get('name') == 'Free Kick':
                result['free_kicks'] += 1; tag = 'Штрафной розыгрыш'
        if kind in ('Miscontrol', 'Dispossessed') and loc and loc[0] < 40:
            result['deep_losses'] += 1; tag = 'Потеря в своей трети'
        if kind == 'Shot':
            result['shots'] += 1
            result['xg'] += e.get('shot', {}).get('statsbomb_xg', 0)
            if loc and loc[0] < 102:
                result['outside_shots'] += 1
            tag = 'Удар'
        if kind == 'Foul Committed':
            result['fouls'] += 1
            if loc and loc[0] < 40:
                result['deep_fouls'] += 1; tag = 'Фол в своей трети'
        if tag:
            evidence.append({'Время': clock_label(e), 'Игрок': e.get('player', {}).get('name', '—'),
                             'Наблюдение': tag})
    return dict(result), evidence[-8:]


def event_options(state, tid, goal):
    a, evidence = indicators(state, tid)
    opp = next(x for x in state['players'] if x != tid)
    b, _ = indicators(state, opp)
    short = len(state['players'][tid]) < len(state['players'][opp])
    def row(key, title, available, priority, why, tasks, risk, check, groups):
        relevant_tags = {'safe_exit': ('Неточная', 'Потеря'), 'cutback': ('Подача',),
                         'shot_selection': ('Удар',), 'foul_discipline': ('Фол',)}.get(key)
        supporting = [e for e in evidence if relevant_tags is None or e['Наблюдение'].startswith(relevant_tags)]
        return dict(key=key, title=title, available=available, priority=priority,
                    why=why, tasks=tasks, risk=risk, check=check,
                    roles='Игроки подтверждённых ролей; распределение ниже',
                    role_groups=groups, event_evidence=supporting,
                    sample_note='Окно — последние 15 минут или весь доступный отрезок, если он короче. Порог — экспертное правило.')
    return [
        row('safe_exit', 'Снизить риск при выходе из своей трети',
            a.get('deep_failed', 0)+a.get('deep_losses', 0) >= 3, 90,
            f'В своей трети: неточных передач {a.get("deep_failed", 0)} из {a.get("deep_passes", 0)}, '
            f'потерь контроля/при отборе {a.get("deep_losses", 0)}.',
            ['Перед первым пасом предложить короткий и дальний выход; не ставить всех адресатов на одну линию.',
             'Опорный открывается под защитника, второй полузащитник остаётся следующей линией.',
             'Если короткие адресаты закрыты — сыграть в доступного нападающего со страховкой подбора.'],
            'Повторять короткий выход под закрытые линии опасно; длинный пас тоже может вернуть владение сопернику.',
            'Проверить число неточных передач и потерь в своей трети за следующие 5–10 минут.',
            ['keeper', 'center_back', 'central', 'striker']),
        row('cutback', 'Заменить неподготовленные навесы проходом и пасом назад',
            a.get('crosses', 0) >= 4 and a.get('crosses_complete', 0)/max(1,a.get('crosses', 0)) < .25, 75,
            f'Подачи: {a.get("crosses_complete", 0)} успешных из {a.get("crosses", 0)}. Низкая точность не доказывает причину неудач.',
            ['Фланговый игрок проверяет возможность продвижения к лицевой вместо ранней подачи.',
             'Нападающий занимает линию завершения, второй адресат открывается под передачу назад.',
             'Опорный сохраняет подбор; не выполнять прострел при закрытой линии.'],
            'Продвижение может закончиться потерей; свободный коридор нужно подтвердить на поле.',
            'Сравнить точность подач, удары и средний xG удара; без ударов среднее не рассчитывать.',
            ['wide', 'full_back', 'striker', 'creator', 'central']),
        row('shot_selection', 'Готовить более качественное завершение',
            a.get('shots', 0) >= 3 and a.get('xg', 0)/max(1,a.get('shots', 0)) < .08, 70,
            f'Ударов {a.get("shots", 0)}, суммарный xG {a.get("xg", 0):.2f}; '
            f'ударов до линии штрафной {a.get("outside_shots", 0)}.',
            ['Перед ударом проверить открытого партнёра ближе к воротам.',
             'Создать поддержку под скидку и обратную передачу, сохранив страховку.',
             'Не запрещать удар категорически: при закрытом пасе решение остаётся у игрока.'],
            'Лишняя передача может привести к потере хорошего момента.',
            'Проверить xG на удар и число ударов; меньше ударов само по себе не является улучшением.',
            ['striker', 'creator', 'wide', 'central']),
        row('progression', 'Связать середину поля с финальной третью',
            a.get('deep_passes', 0) >= 10 and a.get('final_third_entries', 0) <= 1, 65,
            f'Передач из своей трети {a.get("deep_passes", 0)}, успешных входов передачей в финальную треть {a.get("final_third_entries", 0)}.',
            ['Разнести центральных полузащитников по высоте для следующей передачи.',
             'Игрок между линиями открывается под третьего; фланг сохраняет ширину.',
             'Защитник продвигает мяч только при открытой линии и страховке.'],
            'Количество передач не измеряет владение и не доказывает блокировку центра.',
            'Проверить успешные передачи в финальную треть и потери в своей трети.',
            ['center_back', 'central', 'creator', 'wide']),
        row('foul_discipline', 'Снизить число опасных фолов', a.get('deep_fouls', 0) >= 2, 85,
            f'Фолов в своей трети {a.get("deep_fouls", 0)}; всего фолов {a.get("fouls", 0)}.',
            ['Встречать соперника с сохранением позиции, не бросаться в отбор без страховки.',
             'Игрок с карточкой передаёт давление партнёру, когда это возможно.',
             'После свистка сразу распределить стенку, опеку и подбор.'],
            'Пассивное сопровождение тоже позволяет продвижение; задача не означает отказ от единоборств.',
            'Проверить новые фолы в своей трети, карточки и удары со стандартов.',
            ['center_back', 'full_back', 'central']),
        row('second_ball', 'Согласовать первый контакт и подбор после длинной передачи',
            not short and b.get('long_exits', 0) >= 4, 60,
            f'У соперника {b.get("long_exits", 0)} передач из своей трети с продвижением минимум на 30 единиц поля.',
            ['Перед длинной передачей соперника согласовать, кто идёт на первый контакт.',
             'Полузащитник занимает зону подбора, сосед страхует передачу за спину.',
             'После подбора первым надёжным пасом закрепить владение.'],
            'Направление мяча и реальную плотность игроков нужно оценивать визуально.',
            'Разобрать следующие длинные передачи и первые действия после подбора; по одному эпизоду вывод не делать.',
            ['center_back', 'central', 'full_back'])]


def recent_changes(state, tid):
    """Two disjoint five-minute intervals; suppress incomplete comparisons."""
    if state['cutoff'] < 600:
        return []
    end = state['cutoff']
    windows = []
    for lower, upper in ((end-600, end-300), (end-300, end)):
        local = dict(state, cutoff=upper, visible=[(t,e) for t,e in state['visible'] if lower < t <= upper])
        windows.append(indicators(local, tid, 300)[0])
    labels = {'deep_failed': 'Неточные передачи в своей трети', 'deep_losses': 'Потери в своей трети',
              'final_third_entries': 'Входы передачей в финальную треть', 'shots': 'Удары', 'deep_fouls': 'Фолы в своей трети'}
    return [{'Показатель': label, 'Предыдущие 5 минут': windows[0].get(key, 0),
             'Последние 5 минут': windows[1].get(key, 0),
             'Изменение': windows[1].get(key, 0)-windows[0].get(key, 0)} for key,label in labels.items()]


def action_diagram(key):
    # Teaching diagrams, deliberately anonymous: never observed player coordinates.
    arrows = {
        'pressure_support': [(20,40,38,22),(38,22,50,40),(50,40,65,25)],
        'dribble_support': [(65,12,78,25),(78,25,85,12)],
        'creator_watch': [(42,40,55,33),(38,55,45,43)],
        'cutback_defence': [(12,12,8,24),(28,40,18,35),(30,55,22,45)],
        'through_defence': [(40,35,48,40),(25,30,18,40),(25,55,18,50)],
        'rest_defence': [(65,40,50,40),(55,20,40,30),(50,60,35,48)],
        'center': [(28,20,32,32),(28,60,32,48),(42,40,35,40)],
        'flank': [(24,20,30,12),(40,35,32,22)],
        'press': [(75,40,95,35),(65,25,82,20),(55,45,65,40)],
        'control': [(70,20,55,35),(55,35,65,60),(65,60,50,45)],
        'central_build': [(22,35,40,40),(40,40,60,25),(60,25,80,35)],
        'counterpress': [(65,30,72,38),(65,48,72,42),(50,40,58,40)],
        'deep_block': [(50,20,28,25),(50,60,28,55),(40,40,22,40)],
        'safe_exit': [(15,40,35,25),(35,25,55,40),(15,40,70,40)],
        'cutback': [(75,10,110,10),(110,10,100,35),(100,35,118,40)],
        'shot_selection': [(85,40,100,25),(100,25,108,40),(108,40,118,40)],
        'progression': [(25,40,48,25),(48,25,65,45),(65,45,90,30)],
        'foul_discipline': [(30,15,35,28),(30,65,35,52)],
        'second_ball': [(95,30,50,35),(45,25,50,35),(40,50,50,40)],
        'switch': [(65,10,55,40),(55,40,90,70)],
        'width': [(65,40,80,8),(80,8,105,15)],
        'transition': [(30,40,70,35),(55,55,85,50)],
        'attacking_corner': [(119,1,109,35),(90,50,100,45)],
        'defending_corner': [(1,1,10,35),(30,50,22,45)]}
    lines = arrows.get(key, [(40,25,55,35),(40,55,55,45),(65,40,80,40)])
    content = '<defs><marker id="tip" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0 0L6 3L0 6" fill="#ffe17d"/></marker></defs>'
    for i, (x,y,xx,yy) in enumerate(lines,1):
        a,b=point([x,y]); c,d=point([xx,yy])
        content += f'<circle cx="{a}" cy="{b}" r="10" fill="white"/><text x="{a}" y="{b+4}" text-anchor="middle" font-size="12">{i}</text><path d="M{a} {b}L{c} {d}" stroke="#ffe17d" stroke-width="3" fill="none" marker-end="url(#tip)"/>'
    return field(content, 'Учебная схема действия; стрелки не являются трекингом')
