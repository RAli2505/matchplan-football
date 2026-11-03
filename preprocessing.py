"""Strict, auditable input checks. Never invent xG or silently clip coordinates."""
from copy import deepcopy
from datetime import date
import math

VERSION = '2.0-validation'


class DataQualityError(ValueError):
    pass


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def prepare_events(raw):
    if not isinstance(raw, list): raise DataQualityError('События должны быть списком JSON.')
    cleaned, seen = [], {}
    report = {'version': VERSION, 'raw_events': len(raw), 'accepted_events': 0,
              'exact_duplicates_removed': 0, 'spatial_bounds_warnings': 0, 'shots': 0,
              'missing_optional_duration': 0}
    for ordinal, e in enumerate(raw):
        where = f'Событие {e.get("id", ordinal) if isinstance(e, dict) else ordinal}'
        if not isinstance(e, dict): raise DataQualityError(where + ': ожидается объект.')
        ident = e.get('id')
        if not isinstance(ident, str) or not ident: raise DataQualityError(where + ': отсутствует ID.')
        if ident in seen:
            if e == seen[ident]:
                report['exact_duplicates_removed'] += 1
                continue
            raise DataQualityError(where + ': конфликтующие записи с одинаковым ID.')
        if not isinstance(e.get('type', {}).get('name'), str): raise DataQualityError(where + ': неизвестен тип.')
        if e.get('period') not in (1, 2, 3, 4, 5): raise DataQualityError(where + ': неверный период.')
        try:
            h, m, s = e['timestamp'].split(':')
            if int(h) < 0 or not 0 <= int(m) < 60 or not 0 <= float(s) < 60:
                raise ValueError('clock')
        except (KeyError, ValueError, TypeError):
            raise DataQualityError(where + ': неверное локальное время.')
        kind = e['type']['name']
        if kind in ('Pass', 'Carry', 'Shot'):
            coordinates = [e.get('location')]
            if kind in ('Pass', 'Carry'):
                coordinates.append(e.get(kind.lower(), {}).get('end_location'))
            for xy in coordinates:
                if not isinstance(xy, list) or len(xy) < 2 or not all(_finite(x) for x in xy[:2]):
                    raise DataQualityError(where + ': отсутствуют конечные числовые координаты.')
                if not (0 <= xy[0] <= 120 and 0 <= xy[1] <= 80):
                    # Out-of-bounds ball positions may be meaningful; never silently winsorize.
                    report['spatial_bounds_warnings'] += 1
        if kind == 'Shot':
            xg = e.get('shot', {}).get('statsbomb_xg')
            if not _finite(xg) or not 0 <= xg <= 1:
                raise DataQualityError(where + ': xG отсутствует или вне [0,1]; подстановка нуля запрещена.')
            report['shots'] += 1
        if 'duration' not in e: report['missing_optional_duration'] += 1
        seen[ident] = e
        cleaned.append(deepcopy(e))
    report['accepted_events'] = len(cleaned)
    return cleaned, report


def validate_lineups(lineups):
    if not isinstance(lineups, list) or len(lineups) != 2:
        raise DataQualityError('Ожидаются заявки двух команд.')
    team_ids = [x['team_id'] for x in lineups]
    if len(set(team_ids)) != 2: raise DataQualityError('Команды в заявках повторяются.')
    all_ids = []
    for team in lineups:
        ids = [p['player_id'] for p in team['lineup']]
        if len(ids) != len(set(ids)): raise DataQualityError('Повторяющийся игрок в заявке.')
        all_ids += ids
    if len(all_ids) != len(set(all_ids)): raise DataQualityError('Игрок одновременно в двух заявках.')


def validate_matches(games):
    ids = set()
    for game in games:
        if game['match_id'] in ids: raise DataQualityError('Повторяющийся match_id.')
        ids.add(game['match_id'])
        date.fromisoformat(game['match_date'])
        for field in ('home_score', 'away_score'):
            if not isinstance(game[field], int) or game[field] < 0: raise DataQualityError('Некорректный счёт.')
        if game['home_team']['home_team_id'] == game['away_team']['away_team_id']:
            raise DataQualityError('Команда не может играть сама с собой.')
