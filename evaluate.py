"""Descriptive policy comparison, not a causal win-rate evaluation."""
import json
from collections import Counter
from pathlib import Path
from core import TEAM_ID, match_data, matches, recommend, seconds, snapshot, timeline


def evaluate():
    counts = {'matches': 0, 'checkpoints': 0, 'target_changes_plan': 0,
              'differs_from_score_time_baseline': 0, 'max_players': 0, 'squad_violations': 0}
    cases = []
    for m in matches():
        es, ls = match_data(m['match_id'])
        counts['matches'] += 1
        for minute in (0, 15, 30, 45, 60, 75, 85):
            # Query by period-local time, not ambiguous global match minute.
            period = 1 if minute < 45 else 2
            local = minute * 60 if period == 1 else (minute-45)*60
            candidates = [t for t, e in timeline(es) if e['period'] == period and
                          seconds(e) <= local]
            if not candidates: continue
            s = snapshot(es, ls, max(candidates))
            win, draw = recommend(s, TEAM_ID, 'win'), recommend(s, TEAM_ID, 'draw')
            counts['checkpoints'] += 1
            if win['plan'] != draw['plan']:
                counts['target_changes_plan'] += 1
                if len(cases) < 8:
                    cases.append({'match_id': m['match_id'], 'minute': minute,
                                  'win': win['plan'], 'avoid_defeat': draw['plan']})
            # Ablation: identical state with recent statistics and red-card feature removed.
            baseline = dict(s)
            baseline['visible'] = []
            baseline['red'] = Counter()
            if win['plan'] != recommend(baseline, TEAM_ID, 'win')['plan']:
                counts['differs_from_score_time_baseline'] += 1
            for tid, players in s['players'].items():
                counts['max_players'] = max(counts['max_players'], len(players))
                counts['squad_violations'] += int(len(players) > 11 or bool(set(players) & set(s['bench'][tid])) or bool(set(players) & s['removed']))
    result = {'description': 'Descriptive rule-policy audit on Bayer Leverkusen Bundesliga 2023/24; no causal outcome claims.',
              **counts, 'example_target_comparisons': cases,
              'limitations': 'All matches used for descriptive audit. No trained model, held-out performance or validated tactical uplift. Rules are author assumptions.'}
    folder = Path(__file__).parent / 'reports'
    folder.mkdir(exist_ok=True)
    (folder / 'evaluation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': evaluate()
