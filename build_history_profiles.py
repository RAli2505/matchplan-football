"""Summarize player evidence from the 69 earlier La Liga matches in this archive."""
import json
from pathlib import Path
from core import matches, match_data, historical_roles, historical_profiles


def main():
    games = sorted([g for season in (25, 26) for g in matches(11, season)],
                   key=lambda g: (g['match_date'], g['match_id']))
    roles, profiles = {}, {}
    for index, game in enumerate(games):
        events, _ = match_data(game['match_id'])
        roles.update(historical_roles([events]))
        for pid, values in historical_profiles([events]).items():
            total = profiles.setdefault(pid, dict.fromkeys(values, 0))
            for key, value in values.items():
                total[key] += value
        if (index + 1) % 20 == 0:
            print(f'Historical profiles: {index+1}/{len(games)}', flush=True)
    result = {'source': 'La Liga 2013/14 and 2014/15; selected-team archive coverage',
              'matches': len(games), 'latest_date': max(g['match_date'] for g in games),
              'roles': roles, 'profiles': profiles}
    (Path(__file__).parent / 'reports' / 'history_profiles.json').write_text(
        json.dumps(result, ensure_ascii=False), encoding='utf-8')
    print(f'Saved {len(profiles)} player histories; latest date {result["latest_date"]}')


if __name__ == '__main__':
    main()
