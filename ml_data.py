"""Causal feature extraction. Labels are final scores; inputs stop at the cutoff."""
from collections import OrderedDict
import numpy as np
from core import match_data, matches, metrics, seconds, snapshot, timeline

SEQUENCE_LENGTH = 6
SAMPLE_MINUTES = list(range(0, 90, 5))
FEATURES = ['minute_fraction', 'goal_difference', 'player_difference', 'home',
            'score_time_interaction', 'remaining_fraction', 'xg_recent_for', 'xg_recent_against',
            'shots_recent_for', 'shots_recent_against', 'entries_recent_for', 'entries_recent_against',
            'xg_total_for', 'xg_total_against', 'shots_total_for', 'shots_total_against',
            'subs_used', 'subs_opponent', 'yellow_on_pitch', 'yellow_opponent']
BASE_FEATURES = 6
LABELS = ['Поражение', 'Ничья', 'Победа']


def features(state, tid, home_tid):
    other = next(x for x in state['players'] if x != tid)
    minute = min(100, state['last'].get('minute', 0)) / 100
    diff = state['goals'][tid] - state['goals'][other]
    a, b = metrics(state, tid), metrics(state, other)
    aa, bb = metrics(state, tid, 0), metrics(state, other, 0)
    return np.array([minute, diff, len(state['players'][tid]) - len(state['players'][other]), int(tid == home_tid),
                     diff * minute, 1-minute, a['xg'], b['xg'], a['shots'], b['shots'], a['box_entries'], b['box_entries'],
                     aa['xg'], bb['xg'], aa['shots'], bb['shots'], state['subs'][tid], state['subs'][other],
                     len(set(state['players'][tid]) & state['yellow']),
                     len(set(state['players'][other]) & state['yellow'])], dtype=np.float32)


def make_sequence(events, lineups, cutoff, tid, home_tid, current_state=None):
    timed = timeline(events)
    scheduled = []
    for minute in SAMPLE_MINUTES:
        period, local = (1, minute*60) if minute < 45 else (2, (minute-45)*60)
        point = max((t for t, e in timed if e['period'] == period and seconds(e) <= local), default=None)
        if point is not None and point < cutoff:
            scheduled.append(point)
    points = scheduled[-(SEQUENCE_LENGTH-1):] + [cutoff]
    sequence = np.zeros((SEQUENCE_LENGTH, len(FEATURES)), dtype=np.float32)
    for i, point in enumerate(points):
        s = current_state if point == cutoff and current_state is not None else snapshot(events, lineups, point)
        sequence[i] = features(s, tid, home_tid)
    return sequence, len(points)


def temporal_split(ids, dates=None):
    unique = list(dict.fromkeys(ids))
    if dates is None:
        train_end, val_end = int(len(unique)*.70), int(len(unique)*.85)
        train_ids, val_ids = set(unique[:train_end]), set(unique[train_end:val_end])
    else:
        # Keep all games on the same date together. No tuning on simultaneously played games.
        day_by_id = dict(zip(ids, dates))
        days = sorted(set(dates))
        # Boundaries target match counts, then move to complete date boundaries.
        a = day_by_id[unique[int(len(unique)*.70)]]
        b = day_by_id[unique[int(len(unique)*.85)]]
        train_ids = {mid for mid in unique if day_by_id[mid] < a}
        val_ids = {mid for mid in unique if a <= day_by_id[mid] < b}
    parts = [[], [], []]
    for i, mid in enumerate(ids):
        parts[0 if mid in train_ids else 1 if mid in val_ids else 2].append(i)
    return tuple(np.asarray(p, dtype=int) for p in parts)


def build_dataset(progress=print, games=None):
    games = matches(2, 27) if games is None else games
    sequences, lengths, labels, ids, dates, minutes, tids = [], [], [], [], [], [], []
    for index, game in enumerate(games):
        es, ls = match_data(game['match_id'])
        timed = timeline(es)
        home, away = game['home_team']['home_team_id'], game['away_team']['away_team_id']
        histories = {home: [], away: []}
        for minute in SAMPLE_MINUTES:
            period, local = (1, minute*60) if minute < 45 else (2, (minute-45)*60)
            cutoff = max((t for t, e in timed if e['period'] == period and seconds(e) <= local), default=None)
            if cutoff is None: continue
            state = snapshot(es, ls, cutoff)
            for tid in (home, away):
                histories[tid].append(features(state, tid, home))
                seq = np.zeros((SEQUENCE_LENGTH, len(FEATURES)), dtype=np.float32)
                window = histories[tid][-SEQUENCE_LENGTH:]
                seq[:len(window)] = window
                diff = (game['home_score']-game['away_score']) * (1 if tid == home else -1)
                sequences.append(seq); lengths.append(len(window)); labels.append(2 if diff > 0 else 0 if diff < 0 else 1)
                ids.append(game['match_id']); dates.append(game['match_date']); minutes.append(minute); tids.append(tid)
        if (index+1) % 20 == 0: progress(f'Dataset: {index+1}/{len(games)} matches', flush=True)
    return {'sequences': np.asarray(sequences), 'lengths': np.asarray(lengths), 'y': np.asarray(labels),
            'ids': np.asarray(ids), 'dates': np.asarray(dates), 'minutes': np.asarray(minutes), 'teams': np.asarray(tids)}
