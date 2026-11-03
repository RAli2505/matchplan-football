# MatchPlan

An adaptive football coaching decision support system for a single match. MatchPlan helps select a lineup, compare tactical plans and adjust decisions as the score, time, available players and opponent actions change. The coach can target a win or avoid defeat.

## Features

- Compare 14 formations and assign players using confirmed positional roles.
- Explore cautious, balanced and attacking plans with explicit risks.
- Use 24 tactical tasks: observed events → role instructions → review after 5–10 minutes.
- Compare legal substitutions and view a player board with optional local portraits.
- Inspect xG zones, scoring and conceding maps, passing networks and attacking sequences.
- Compare adjacent match periods and evaluate ball progression with expected threat (xT).
- Retrieve similar situations from earlier matches.
- Review win, draw and loss probabilities and model evaluation metrics.
- Record coaching notes, track task status and export decisions as JSON or HTML.

## Installation

Requires Python 3.10 or later.

```bash
python -m venv .venv
```

Activate the environment on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies and start the application:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open http://localhost:8501.

## Data and local artifacts

The primary dataset is [StatsBomb Open Data](https://github.com/statsbomb/open-data), covering 380 Premier League matches from 2015/16. Download the archive and place it next to the project folder as `../open-data-master.zip`.

Datasets, player photographs, trained weights, experiment reports and presentations are excluded from this repository. Full prediction functionality requires local model artifacts under `models/`. Model preparation is implemented in `train_models.py`; inspect its options using `python train_models.py --help`. `decision_history.py` builds the historical index, while `train_expected_threat.py` prepares xT surfaces. Optional portrait preparation scripts require their own source files.

For a standalone example without the dataset or external packages:

```bash
python -S demo_decisions.py
```

This generates a local HTML report under `reports/demo/` using explicitly synthetic events.

## Models and evaluation

The outcome models are Logistic Regression, Gaussian Naive Bayes, k-NN, MLP, Transformer and LSTM. The baseline is logistic regression using six features. Predictions describe win, draw and loss probabilities rather than exact final scores.

Matches are split chronologically as complete groups: 266 training, 57 validation and 57 test matches (70/15/15). Recommendations use only events available at the selected time. Transformer was selected among the six models by validation Log Loss. The baseline performed better on the test set; this experiment did not establish an advantage for neural models.

Transformer test AUC in the local experiment: **0.8406** for wins, **0.7237** for draws and **0.8343** for losses. These values belong to the specific historical split; experiment artifacts are not included in this source repository.

Tactical recommendations combine expert rules with observed events. Their causal effect on match outcomes has not been established. Event data does not measure player fitness or reconstruct actual off-ball movement.

## Code structure

| Modules | Purpose |
| --- | --- |
| `app.py`, `decision_workspace_ui.py` | Coaching interface |
| `core.py`, `preprocessing.py`, `event_adapter.py` | Event processing |
| `tactics.py`, `tactical_playbook.py`, `decision_support.py` | Tactical recommendations |
| `decision_history.py`, `player_insights.py` | Historical situations and player analysis |
| `goal_pitch.py`, `match_lab.py`, `attack_chains.py` | Match visualizations |
| `ml_data.py`, `ml_models.py`, `train_models.py` | Outcome model training |
| `expected_threat.py`, `train_expected_threat.py` | Ball progression valuation |
| `tests/` | Automated checks |
