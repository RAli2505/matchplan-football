"""Validated event coordinates and possession motifs, inspired by kloppy.

Cell-centre correction adapted from PySport/kloppy's parse_coordinates,
Copyright (c) 2020 PySport, BSD-3-Clause; see licenses/kloppy-BSD-3-Clause.txt.
No tracking positions or provider orientation are inferred.
"""
import math


def coordinates(raw, fidelity=None):
    """StatsBomb attacking coordinates; optional explicit source fidelity 1/2.

    With unknown fidelity retain source coordinates, never guess resolution.
    """
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        x, y = float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x+y) or not (0 <= x <= 120 and 0 <= y <= 80):
        return None
    if fidelity in (1, 2):
        centre = (0.1 if fidelity == 2 else 1.0) / 2
        x, y = max(0, x-centre), max(0, y-centre)
    return x, y


def movement(event):
    kind = event.get('type', {}).get('name')
    if kind not in ('Pass', 'Carry'):
        return None
    detail = event.get(kind.lower(), {})
    start, end = coordinates(event.get('location')), coordinates(detail.get('end_location'))
    if start is None or end is None:
        return None
    return start, end, kind == 'Carry' or not detail.get('outcome')


def visible_events(state, window=0):
    lower = max(0, state['cutoff']-window) if window else 0
    return [(t,e) for t,e in state['visible'] if lower <= t <= state['cutoff']]


def possession_patterns(state, tid, window=0):
    """Recorded recovery→completed pass→shot, same known possession/period.

    Opponent controlled actions, failures and restarts break the pattern.
    """
    found=[]; active=None
    for tick,e in visible_events(state,window):
        kind=e.get('type',{}).get('name'); team=e.get('team',{}).get('id')
        key=(e.get('period'),e.get('possession'))
        if active and (key!=active['key'] or tick-active['tick']>20): active=None
        if team!=tid:
            if kind in ('Pass','Carry','Shot','Dribble','Ball Recovery','Interception'): active=None
            continue
        if kind=='Ball Recovery' and not e.get('ball_recovery',{}).get('recovery_failure') and key[1] is not None:
            active={'key':key,'tick':tick,'recovery':e,'passes':[]}
        elif active and kind=='Pass':
            if e.get('pass',{}).get('outcome'): active=None
            else: active['passes'].append(e)
        elif active and kind=='Shot':
            if active['passes']:
                found.append({'start':active['tick'],'end':tick,'recovery':active['recovery'],
                              'passes':active['passes'],'shot':e,'seconds':round(tick-active['tick'],1)})
            active=None
        elif kind in ('Foul Won','Foul Committed','Offside','Ball Out','Half End','Miscontrol','Dispossessed'):
            active=None
    return found
