"""Optional simulation-game reference, never real historical match measurements."""
from field_views import photo_manifest

WEIGHTS = {
    'attacking': {'shooting': .35, 'passing': .25, 'dribbling': .2, 'pace': .2},
    'balanced': {'passing': .35, 'defending': .25, 'dribbling': .2, 'physic': .2},
    'cautious': {'defending': .5, 'physic': .3, 'passing': .2}}

def compare_substitutions(options, plan):
    rows = []
    data = photo_manifest()
    weights = WEIGHTS[plan]
    for sub in options:
        before = data.get(str(sub['out_id']), {}).get('attributes', {})
        after = data.get(str(sub['in_id']), {}).get('attributes', {})
        def score(attributes):
            try:
                return sum(float(attributes[k]) * w for k, w in weights.items())
            except (KeyError, ValueError, TypeError):
                return None
        a, b = score(before), score(after)
        rows.append({'Уходит': sub['out'], 'Выходит': sub['in'],
                     'Позиции FIFA 16': after.get('player_positions', 'нет данных'),
                     'Рабочая нога': after.get('preferred_foot', 'нет данных'),
                     'Игровой индекс уходит': round(a, 1) if a is not None else None,
                     'Игровой индекс выходит': round(b, 1) if b is not None else None,
                     'Разница индекса': round(b-a, 1) if a is not None and b is not None else None})
    return sorted(rows, key=lambda r: (r['Разница индекса'] is not None, r['Разница индекса'] or 0), reverse=True)
