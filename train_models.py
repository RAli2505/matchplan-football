"""Reproducible six-model experiment; model selection uses validation, never test."""
import copy
import hashlib
import json
import random
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import log_loss, accuracy_score, confusion_matrix, roc_auc_score

from core import ARCHIVE, matches
from ml_data import BASE_FEATURES, FEATURES, LABELS, SEQUENCE_LENGTH, build_dataset, temporal_split
from ml_models import MatchNetwork

ROOT = Path(__file__).parent
MODELS = ROOT / 'models'
REPORTS = ROOT / 'reports'
SEED = 42


def measure(y, p):
    p = np.clip(p, 1e-6, 1-1e-6)
    p = p / p.sum(axis=1, keepdims=True)
    onehot = np.eye(3)[y]
    result = {'log_loss': float(log_loss(y, p, labels=[0, 1, 2])),
            'brier_multiclass': float(np.mean(np.sum((p-onehot)**2, axis=1))),
            'accuracy': float(accuracy_score(y, p.argmax(1))),
            'confusion_matrix': confusion_matrix(y, p.argmax(1), labels=[0, 1, 2]).tolist()}
    if len(np.unique(y)) == 3:
        result['roc_auc_macro_ovr'] = float(roc_auc_score(y, p, multi_class='ovr', average='macro'))
        result['roc_auc_per_class'] = {LABELS[i]: float(roc_auc_score((y == i).astype(int), p[:, i])) for i in range(3)}
    return result


def standardized(sequences, lengths, scaler):
    data = scaler.transform(sequences.reshape(-1, sequences.shape[-1])).reshape(sequences.shape).astype(np.float32)
    for i, length in enumerate(lengths): data[i, length:] = 0
    return data


def neural_predict(model, data, lengths):
    model.eval()
    with torch.no_grad():
        parts = []
        for i in range(0, len(data), 512):
            logits = model(torch.from_numpy(data[i:i+512]), torch.as_tensor(lengths[i:i+512], dtype=torch.long))
            parts.append(logits.softmax(1).numpy())
    return np.concatenate(parts)


def fit_neural(kind, data, lengths, y, train, validation):
    torch.manual_seed(SEED)
    model = MatchNetwork(kind, len(FEATURES), SEQUENCE_LENGTH)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.002, weight_decay=.03)
    criterion = torch.nn.CrossEntropyLoss()
    best, best_epoch, best_weights, stale = float('inf'), 0, None, 0
    history = []
    generator = np.random.default_rng(SEED)
    for epoch in range(1, 121):
        model.train()
        for batch in np.array_split(generator.permutation(train), max(1, int(np.ceil(len(train)/256)))):
            x = torch.from_numpy(data[batch])
            lens = torch.as_tensor(lengths[batch], dtype=torch.long)
            target = torch.as_tensor(y[batch], dtype=torch.long)
            optimizer.zero_grad()
            loss = criterion(model(x, lens), target)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
            optimizer.step()
        val = measure(y[validation], neural_predict(model, data[validation], lengths[validation]))['log_loss']
        history.append({'epoch': epoch, 'validation_log_loss': val})
        if val < best - 1e-5:
            best, best_epoch, best_weights, stale = val, epoch, copy.deepcopy(model.state_dict()), 0
        else: stale += 1
        if stale >= 18: break
    model.load_state_dict(best_weights)
    return model, {'best_epoch': best_epoch, 'epochs_run': epoch, 'validation_curve': history,
                   'parameters': sum(p.numel() for p in model.parameters())}


def calibration(y, p):
    rows = []
    for label in range(3):
        for lo in np.arange(0, 1, .2):
            mask = (p[:, label] >= lo) & (p[:, label] < lo+.2+1e-9)
            if mask.any():
                rows.append({'class': LABELS[label], 'bin': round(float(lo), 1), 'count': int(mask.sum()),
                             'predicted': float(p[mask, label].mean()), 'observed': float((y[mask] == label).mean())})
    return rows


def cluster_interval(y, p, ids):
    """Bootstrap whole held-out matches, not correlated time slices."""
    unique = np.unique(ids)
    rng = np.random.default_rng(SEED)
    losses = []
    grouped = {mid: np.flatnonzero(ids == mid) for mid in unique}
    for _ in range(200):
        chosen = np.concatenate([grouped[mid] for mid in rng.choice(unique, len(unique), replace=True)])
        prob = np.clip(p[chosen], 1e-6, 1-1e-6)
        prob = prob / prob.sum(axis=1, keepdims=True)
        losses.append(float(log_loss(y[chosen], prob, labels=[0, 1, 2])))
    return [float(np.quantile(losses, .025)), float(np.quantile(losses, .975))]


def main():
    start = time.time()
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED); torch.set_num_threads(2)
    MODELS.mkdir(exist_ok=True); REPORTS.mkdir(exist_ok=True)
    cache = MODELS / 'dataset.npz'
    with zipfile.ZipFile(ARCHIVE) as z:
        manifest = [(n, z.getinfo(n).CRC) for n in z.namelist() if '/data/' in n and not n.endswith('/')]
    signature = hashlib.sha256(json.dumps(manifest).encode()).hexdigest()
    signature_file = MODELS / 'dataset_signature.json'
    valid_cache = cache.exists() and signature_file.exists() and json.loads(signature_file.read_text()) == {'archive': signature, 'schema': 1}
    if valid_cache:
        with np.load(cache) as saved: dataset = dict(saved)
        print('Using verified feature cache', flush=True)
    else:
        dataset = build_dataset()
        np.savez_compressed(cache, **dataset)
        signature_file.write_text(json.dumps({'archive': signature, 'schema': 1}))
    seq, lengths, y, ids = dataset['sequences'], dataset['lengths'], dataset['y'], dataset['ids']
    train, validation, test = temporal_split(ids, dataset['dates'])
    split_sets = [set(ids[part]) for part in (train, validation, test)]
    assert not (split_sets[0] & split_sets[1] or split_sets[0] & split_sets[2] or split_sets[1] & split_sets[2])
    current = seq[np.arange(len(seq)), lengths-1]
    scaler = StandardScaler().fit(current[train])
    joblib.dump(scaler, MODELS / 'scaler.joblib')
    scaled = standardized(seq, lengths, scaler)
    X = scaled[np.arange(len(seq)), lengths-1]
    experiments = {}
    predictions = {}
    # Hyperparameters fixed before test evaluation. Best network epochs use validation only.
    for name, estimator in [
        ('Logistic Regression', LogisticRegression(C=.5, max_iter=1500, random_state=SEED)),
        ('Gaussian Naive Bayes', GaussianNB(var_smoothing=.1)),
        ('k-NN', KNeighborsClassifier(n_neighbors=51, weights='uniform'))]:
        estimator.fit(X[train], y[train])
        val = estimator.predict_proba(X[validation])
        joblib.dump(estimator, MODELS / (name.replace(' ', '_') + '.joblib'))
        predictions[name] = estimator.predict_proba(X[test])
        experiments[name] = {'validation': measure(y[validation], val), 'configuration': estimator.get_params()}
        print(f'Trained {name}: validation log loss {experiments[name]["validation"]["log_loss"]:.4f}', flush=True)
    for name in ('MLP', 'Transformer', 'LSTM'):
        model, metadata = fit_neural(name, scaled, lengths, y, train, validation)
        torch.save(model.state_dict(), MODELS / (name+'.pt'))
        val = neural_predict(model, scaled[validation], lengths[validation])
        predictions[name] = neural_predict(model, scaled[test], lengths[test])
        experiments[name] = {'validation': measure(y[validation], val), 'configuration': metadata}
        print(f'Trained {name}: validation log loss {experiments[name]["validation"]["log_loss"]:.4f}', flush=True)
    selected = min(experiments, key=lambda name: experiments[name]['validation']['log_loss'])
    baseline = LogisticRegression(C=.5, max_iter=1500, random_state=SEED).fit(X[train, :BASE_FEATURES], y[train])
    joblib.dump(baseline, MODELS / 'baseline.joblib')
    base_prob = baseline.predict_proba(X[test, :BASE_FEATURES])
    prior = np.bincount(y[train], minlength=3)/len(train)
    prior_prob = np.tile(prior, (len(test), 1))
    frames = []
    for name, result in experiments.items():
        prob = predictions[name]
        result['test'] = measure(y[test], prob)
        result['test']['log_loss_match_bootstrap_95'] = cluster_interval(y[test], prob, ids[test])
        result['calibration_test'] = calibration(y[test], prob)
        frame = pd.DataFrame({'model': name, 'match_id': ids[test], 'team_id': dataset['teams'][test],
                              'minute': dataset['minutes'][test], 'actual': y[test],
                              'p_loss': prob[:, 0], 'p_draw': prob[:, 1], 'p_win': prob[:, 2]})
        frames.append(frame)
    def split_info(part):
        return {'matches': len(set(ids[part])), 'states': len(part),
                'date_from': str(min(dataset['dates'][part])), 'date_to': str(max(dataset['dates'][part])),
                'match_ids': sorted(map(int, set(ids[part]))),
                'class_counts': np.bincount(y[part], minlength=3).tolist()}
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'seed': SEED,
              'competition': 'Premier League 2015/2016', 'competition_id': 2, 'season_id': 27,
              'archive_signature': signature, 'features': FEATURES, 'sequence_length': SEQUENCE_LENGTH,
              'labels': LABELS, 'selected_by_validation': selected,
              'splits': {'train': split_info(train), 'validation': split_info(validation), 'test': split_info(test)},
              'models': experiments, 'baseline_score_time': measure(y[test], base_prob),
              'baseline_training_class_prior': measure(y[test], prior_prob),
              'versions': {'torch': str(torch.__version__), 'sklearn': sklearn.__version__, 'numpy': np.__version__},
              'elapsed_seconds': round(time.time()-start, 1),
              'honesty': ['All states of a match and all matches on the same date share a split.',
                          'Scaler fitted on training states only. Neural checkpoints and model choice use validation only.',
                          'Test is an audit, not a model-selection target. No tactical causal effect is estimated.',
                          'Both team perspectives are correlated; confidence intervals resample whole matches.',
                          'One historical league-season; shared teams and temporal dependence remain.',
                          'No pre-match ability ratings or long-term team strength in outcome features.',
                          'Minute-zero predictions mainly reflect home advantage; lineup suggestions use a separate heuristic.',
                          'No probability calibration fit. Reliability plots report observed calibration.']}
    (REPORTS / 'ml_results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (MODELS / 'manifest.json').write_text(json.dumps({key: report[key] for key in ('selected_by_validation', 'features', 'sequence_length', 'competition_id', 'season_id', 'archive_signature', 'versions')}, ensure_ascii=False, indent=2), encoding='utf-8')
    pd.concat(frames).to_csv(REPORTS / 'test_predictions.csv', index=False)
    rows = ['# Six-model experiment', '', 'Premier League 2015/16. Selection uses validation log loss, never test.', '',
            '| Model | Validation log loss | Test log loss | Test Brier | Test accuracy |', '|---|---:|---:|---:|---:|']
    for name, result in experiments.items():
        rows.append(f'| {name} | {result["validation"]["log_loss"]:.4f} | {result["test"]["log_loss"]:.4f} | {result["test"]["brier_multiclass"]:.4f} | {result["test"]["accuracy"]:.3f} |')
    rows += ['', f'Selected: **{selected}**.', '', 'No claim of tactical uplift or guaranteed outcomes. See ml_results.json for splits, intervals and limitations.']
    (REPORTS / 'ML_REPORT.md').write_text('\n'.join(rows), encoding='utf-8')
    from render_report import render
    render(report)
    print(json.dumps({'selected': selected, 'splits': {k: {a: v for a, v in val.items() if a != 'match_ids'} for k, val in report['splits'].items()},
                      'test_log_loss': {k: v['test']['log_loss'] for k, v in experiments.items()}, 'elapsed_seconds': report['elapsed_seconds']}, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
