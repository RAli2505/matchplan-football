"""Inference from locally generated trusted model artifacts."""
import json
from functools import lru_cache
from pathlib import Path
import joblib
import numpy as np
import torch
from ml_data import FEATURES, make_sequence
from ml_models import MatchNetwork
from train_models import standardized

ROOT = Path(__file__).parent


@lru_cache(maxsize=1)
def load_models():
    folder = ROOT / 'models'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['features'] != FEATURES: raise ValueError('Версия признаков отличается от обученных моделей. Повторите обучение.')
    scaler = joblib.load(folder / 'scaler.joblib')
    estimators = {}
    for name in ('Logistic Regression', 'Gaussian Naive Bayes', 'k-NN'):
        estimators[name] = joblib.load(folder / (name.replace(' ', '_')+'.joblib'))
    for name in ('MLP', 'Transformer', 'LSTM'):
        model = MatchNetwork(name, len(FEATURES), manifest['sequence_length'])
        model.load_state_dict(torch.load(folder / (name+'.pt'), map_location='cpu', weights_only=True))
        model.eval()
        estimators[name] = model
    torch.set_num_threads(2)
    return manifest, scaler, estimators


def predict_all(events, lineups, cutoff, tid, home_tid, current_state=None):
    manifest, scaler, models = load_models()
    seq, length = make_sequence(events, lineups, cutoff, tid, home_tid, current_state)
    data = standardized(seq[None], np.array([length]), scaler)
    current = data[:, length-1]
    results = {}
    for name, model in models.items():
        if name in ('MLP', 'LSTM', 'Transformer'):
            with torch.no_grad(): p = model(torch.from_numpy(data), torch.tensor([length])).softmax(1).numpy()[0]
        else: p = model.predict_proba(current)[0]
        p = np.clip(p, 1e-6, 1.)
        results[name] = (p / p.sum()).tolist()
    return manifest['selected_by_validation'], results
