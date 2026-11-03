"""Separate chronological transfer experiment. Never replaces published weights."""
import json
from pathlib import Path
import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from core import matches
from ml_data import build_dataset, temporal_split
from train_models import measure

ROOT = Path(__file__).parent


def main():
    original = dict(np.load(ROOT / 'models' / 'dataset.npz'))
    train, validation, test = temporal_split(original['ids'], original['dates'])
    start = str(min(original['dates']))
    games = sorted([g for season in (25, 26) for g in matches(11, season)
                    if g['match_date'] < start], key=lambda g: (g['match_date'], g['match_id']))
    cache = ROOT / 'models' / 'history_69.npz'
    if cache.exists():
        extra = dict(np.load(cache))
    else:
        extra = build_dataset(games=games)
        np.savez_compressed(cache, **extra)
    assert set(extra['ids']).isdisjoint(original['ids'])
    assert max(extra['dates']) < min(original['dates'])
    def current(d):
        return d['sequences'][np.arange(len(d['y'])), d['lengths'] - 1]
    x, hx = current(original), current(extra)
    results = {}
    for name, xx, yy in [('PL train only', x[train], original['y'][train]),
                         ('PL train + earlier La Liga', np.concatenate([x[train], hx]),
                          np.concatenate([original['y'][train], extra['y']]))]:
        model = make_pipeline(StandardScaler(), LogisticRegression(C=.5, max_iter=1500, random_state=42))
        model.fit(xx, yy)
        results[name] = {part: measure(original['y'][indices], model.predict_proba(x[indices]))
                         for part, indices in [('validation', validation), ('test', test)]}
    selected = min(results, key=lambda n: results[n]['validation']['log_loss'])
    report = {'purpose': 'Earlier-season transfer experiment; independent from published six-model results',
              'historical_league': 'La Liga', 'historical_seasons': ['2013/14', '2014/15'],
              'historical_matches': len(set(extra['ids'])), 'historical_last_date': str(max(extra['dates'])),
              'pl_train_matches': len(set(original['ids'][train])), 'pl_validation_matches': len(set(original['ids'][validation])),
              'pl_test_matches': len(set(original['ids'][test])), 'results': results,
              'selected_by_validation': selected, 'deployed': False,
              'limitations': ['Historical seasons cover selected teams, not full leagues.',
                              'Transfer across leagues can reduce quality; test never selects deployment.']}
    target = ROOT / 'reports' / 'history_experiment.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
