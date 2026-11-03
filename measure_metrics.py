"""All-split metrics from fixed, trained weights. No refitting or model selection."""
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (accuracy_score, average_precision_score, cohen_kappa_score,
                             confusion_matrix, log_loss, matthews_corrcoef,
                             precision_recall_fscore_support, roc_auc_score)
from ml_data import BASE_FEATURES, LABELS

ROOT = Path(__file__).parent


def extended_metrics(y, p):
    raw_p = np.asarray(p, dtype=float)
    if not np.allclose(raw_p.sum(1), 1., atol=1e-5):
        raise ValueError('Probabilities do not sum to one.')
    p = np.clip(raw_p, 1e-6, 1-1e-6)
    p /= p.sum(1, keepdims=True)
    predicted = p.argmax(1)
    onehot = np.eye(3)[y]
    result = {'accuracy': float(accuracy_score(y, predicted)),
              'log_loss': float(log_loss(y, p, labels=[0, 1, 2])),
              'brier_multiclass': float(np.mean(np.sum((p-onehot)**2, axis=1))),
              'mcc': float(matthews_corrcoef(y, predicted)), 'cohen_kappa': float(cohen_kappa_score(y, predicted)),
              'roc_auc_macro_ovr': float(roc_auc_score(y, raw_p, multi_class='ovr', average='macro')),
              'pr_auc_macro_average_precision': float(average_precision_score(onehot, raw_p, average='macro')),
              'confusion_matrix': confusion_matrix(y, predicted, labels=[0, 1, 2]).tolist()}
    for average in ('macro', 'weighted'):
        precision, recall, f1, _ = precision_recall_fscore_support(y, predicted, average=average, zero_division=0)
        result.update({f'precision_{average}': float(precision), f'recall_{average}': float(recall), f'f1_{average}': float(f1)})
    prec, rec, f1, support = precision_recall_fscore_support(y, predicted, labels=[0, 1, 2], zero_division=0)
    result['per_class'] = {label: {'precision': float(prec[i]), 'recall': float(rec[i]), 'f1': float(f1[i]),
                                 'support': int(support[i]), 'roc_auc': float(roc_auc_score(y == i, raw_p[:, i])),
                                 'average_precision': float(average_precision_score(y == i, raw_p[:, i]))} for i, label in enumerate(LABELS)}
    confidence = p.max(1)
    correct = predicted == y
    bins, ece = [], 0.
    for j in range(10):
        lo, hi = j/10, (j+1)/10
        mask = (confidence >= lo) & ((confidence < hi) if j < 9 else (confidence <= hi))
        if mask.any():
            c, a = float(confidence[mask].mean()), float(correct[mask].mean())
            ece += mask.mean() * abs(a-c)
            bins.append({'lower': lo, 'upper': hi, 'count': int(mask.sum()), 'confidence': c, 'accuracy': a})
    result['ece_top_label_10_bins'] = float(ece)
    result['confidence_bins'] = bins
    return result


def main():
    from ml_runtime import load_models
    from train_models import standardized, neural_predict
    report = json.loads((ROOT / 'reports/ml_results.json').read_text(encoding='utf-8'))
    manifest, scaler, models = load_models()
    import joblib
    models['Score/time baseline'] = joblib.load(ROOT / 'models/baseline.joblib')
    with np.load(ROOT / 'models/dataset.npz') as z: dataset = dict(z)
    data = standardized(dataset['sequences'], dataset['lengths'], scaler)
    current = data[np.arange(len(data)), dataset['lengths']-1]
    result, rows = {}, []
    for name, model in models.items():
        result[name] = {}
        for split, info in report['splits'].items():
            ix = np.flatnonzero(np.isin(dataset['ids'], info['match_ids']))
            start = time.perf_counter()
            if name in ('MLP', 'Transformer', 'LSTM'):
                prob = neural_predict(model, data[ix], dataset['lengths'][ix])
            else:
                X = current[ix, :BASE_FEATURES] if name == 'Score/time baseline' else current[ix]
                prob = model.predict_proba(X)
            elapsed = time.perf_counter()-start
            metrics = extended_metrics(dataset['y'][ix], prob)
            metrics['inference_milliseconds_per_state'] = elapsed / len(ix) * 1000
            result[name][split] = metrics
            row = {'model': name, 'split': split, **{k: v for k, v in metrics.items() if isinstance(v, (int, float))}}
            rows.append(row)
            if name in report['models']:
                report['models'][name].setdefault(split, {}).update(metrics)
        print(f'Measured train/validation/test: {name}', flush=True)
    details = {'models': result, 'definitions': {'pr_auc': 'Macro average precision (step-integral PR AUC), not trapezoidal interpolation.',
               'ece': 'Top-label ECE with 10 equal-width confidence bins. Lower is better.',
               'brier': 'Mean sum of squared errors over 3 outcome probabilities; range 0 to 2.',
               'timing': 'One CPU inference pass per split, excludes loading and feature extraction; indicative, not a benchmark.'},
               'integrity': 'Metrics computed from fixed saved weights. No training or reselection in this script.'}
    (ROOT / 'reports/all_metrics.json').write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding='utf-8')
    pd.DataFrame(rows).to_csv(ROOT / 'reports/all_metrics.csv', index=False)
    (ROOT / 'reports/ml_results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    from render_report import render
    render(report)
    print(pd.DataFrame(rows)[['model', 'split', 'accuracy', 'f1_macro', 'roc_auc_macro_ovr', 'ece_top_label_10_bins']].to_string(index=False))


if __name__ == '__main__': main()
