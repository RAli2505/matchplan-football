"""Verify match coverage, event-score agreement and source missingness."""
import json
from pathlib import Path
from core import matches, match_data, snapshot, timeline


def main():
    games = matches(2, 27)
    teams, mismatches, violations = set(), [], []
    events_total, shots_total, shots_missing_xg = 0, 0, 0
    missing_locations = 0
    for i, game in enumerate(games):
        es, ls = match_data(game['match_id'])
        events_total += len(es)
        teams.update([game['home_team']['home_team_id'], game['away_team']['away_team_id']])
        for e in es:
            if e['type']['name'] == 'Shot':
                shots_total += 1
                shots_missing_xg += int('statsbomb_xg' not in e['shot'])
            if e['type']['name'] in ('Pass', 'Carry', 'Shot') and 'location' not in e:
                missing_locations += 1
        end = max(t for t, _ in timeline(es)) + 1
        state = snapshot(es, ls, end)
        scores = [state['goals'][game['home_team']['home_team_id']], state['goals'][game['away_team']['away_team_id']]]
        if scores != [game['home_score'], game['away_score']]: mismatches.append(game['match_id'])
        for tid, players in state['players'].items():
            if len(players) > 11 or set(players) & state['removed'] or set(players) & set(state['bench'][tid]):
                violations.append({'match': game['match_id'], 'team': tid})
        if (i+1) % 50 == 0: print(f'Audit: {i+1}/{len(games)}', flush=True)
    result = {'competition': 'Premier League 2015/2016', 'matches': len(games), 'teams': len(teams),
              'events': events_total, 'shots': shots_total, 'shots_missing_xg': shots_missing_xg,
              'pass_carry_shot_missing_location': missing_locations, 'score_mismatches': mismatches,
              'final_squad_violations': violations,
              'duplicate_match_ids': len(games)-len(set(m['match_id'] for m in games)),
              'note': 'Audit of source consistency, not validation of tactical effectiveness.'}
    (Path(__file__).parent / 'reports/data_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if mismatches or violations: raise SystemExit(1)


if __name__ == '__main__': main()
