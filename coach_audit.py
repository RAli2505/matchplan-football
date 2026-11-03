"""Descriptive comparison of pre-substitution suggestions with recorded choices."""
from core import recommend, snapshot, timeline


def audit_substitutions(events, lineups, team_id, roles, rules, goal='win', cutoff=None):
    rows = []
    for tick, event in timeline(events):
        if cutoff is not None and tick > cutoff:
            continue
        if event['type']['name'] != 'Substitution' or event.get('team', {}).get('id') != team_id:
            continue
        before = snapshot(events, lineups, max(0., tick - .01), rules=rules)
        if before['last'].get('minute', 0) < 60:
            continue
        options = recommend(before, team_id, goal, roles)['sub_options']
        suggestion = options[0] if options else None
        actual_out = event.get('player', {}).get('id')
        actual_in = event.get('substitution', {}).get('replacement', {}).get('id')
        rows.append({
            'time': f"{event.get('minute', '?')}′",
            'actual_out': event.get('player', {}).get('name', '—'),
            'actual_in': event.get('substitution', {}).get('replacement', {}).get('name', '—'),
            'suggestion': suggestion,
            'exact_match': bool(suggestion and suggestion['out_id'] == actual_out and suggestion['in_id'] == actual_in),
            'top3_match': any(s['out_id'] == actual_out and s['in_id'] == actual_in for s in options),
        })
    covered = [row for row in rows if row['suggestion']]
    return {
        'rows': rows,
        'actual_count': len(rows),
        'covered_count': len(covered),
        'exact_count': sum(row['exact_match'] for row in covered),
        'top3_count': sum(row['top3_match'] for row in covered),
        'coverage': len(covered) / len(rows) if rows else None,
        'agreement_when_suggested': sum(row['exact_match'] for row in covered) / len(covered) if covered else None,
    }


def audit_formations(events, lineups, team_id, roles, profiles, rules, goal='win', cutoff=None):
    from coaching import formation_choice
    rows = []
    for tick, event in timeline(events):
        if cutoff is not None and tick > cutoff:
            continue
        if event['type']['name'] != 'Tactical Shift' or event.get('team', {}).get('id') != team_id:
            continue
        before = snapshot(events, lineups, max(0., tick - .01), rules=rules)
        current = str(before['formation'].get(team_id, ''))
        actual = str(event['tactics']['formation'])
        if actual == current:
            continue
        choice = formation_choice(before, team_id, roles, profiles, goal)
        proposed = ''.join(c for c in choice['formation'] if c.isdigit()) if choice else None
        rows.append({'time': f"{event.get('minute', '?')}′", 'before': current, 'actual': actual,
                     'suggestion': proposed, 'exact_match': proposed == actual if proposed else False})
    covered = [row for row in rows if row['suggestion']]
    return {'rows': rows, 'actual_count': len(rows), 'covered_count': len(covered),
            'exact_count': sum(row['exact_match'] for row in covered)}
