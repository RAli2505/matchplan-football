"""Add ROC-AUC to the frozen experiment. Does not train or select any model."""
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from ml_data import BASE_FEATURES, LABELS
from render_report import render

ROOT = Path(__file__).parent


def auc_values(y, p):
    return {'roc_auc_macro_ovr': float(roc_auc_score(y, p, multi_class='ovr', average='macro')),
            'roc_auc_per_class': {LABELS[i]: float(roc_auc_score((y == i).astype(int), p[:, i])) for i in range(3)}}


def auc_interval(y, p, ids):
    rng = np.random.default_rng(42)
    unique = np.unique(ids)
    blocks = {mid: np.flatnonzero(ids == mid) for mid in unique}
    scores = []
    for _ in range(200):
        chosen = np.concatenate([blocks[mid] for mid in rng.choice(unique, len(unique), replace=True)])
        if len(np.unique(y[chosen])) == 3:
            scores.append(auc_values(y[chosen], p[chosen])['roc_auc_macro_ovr'])
    return [float(np.quantile(scores, .025)), float(np.quantile(scores, .975))]


def main():
    path = ROOT / 'reports/ml_results.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    frame = pd.read_csv(ROOT / 'reports/test_predictions.csv')
    for name, subset in frame.groupby('model', sort=False):
        p = subset[['p_loss', 'p_draw', 'p_win']].to_numpy()
        y = subset['actual'].to_numpy()
        report['models'][name]['test'].update(auc_values(y, p))
        report['models'][name]['test']['roc_auc_macro_match_bootstrap_95'] = auc_interval(y, p, subset.match_id.to_numpy())
        report['models'][name]['auc_by_minute'] = [
            {'minute': int(minute), **auc_values(g.actual.to_numpy(), g[['p_loss', 'p_draw', 'p_win']].to_numpy())}
            for minute, g in subset.groupby('minute')]
    with np.load(ROOT / 'models/dataset.npz') as dataset:
        mask = np.isin(dataset['ids'], report['splits']['test']['match_ids'])
        current = dataset['sequences'][np.arange(len(dataset['y'])), dataset['lengths']-1][mask]
        y = dataset['y'][mask]
        X = joblib.load(ROOT / 'models/scaler.joblib').transform(current)
        base_p = joblib.load(ROOT / 'models/baseline.joblib').predict_proba(X[:, :BASE_FEATURES])
        report['baseline_score_time'].update(auc_values(y, base_p))
    report['auc_note'] = 'Macro one-vs-rest ROC-AUC across three final-outcome classes, over all test time slices. '
    report['auc_note'] += 'Confidence intervals resample entire matches. Minute-level AUC is shown separately. Added after training without refitting or model reselection.'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    render(report)
    print(json.dumps({name: result['test']['roc_auc_macro_ovr'] for name, result in report['models'].items()}, indent=2))
    print('Baseline AUC:', report['baseline_score_time']['roc_auc_macro_ovr'])


if __name__ == '__main__': main()
