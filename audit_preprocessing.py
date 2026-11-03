"""Audit the full season once using a single archive handle; no model refitting."""
import json
import zipfile
from collections import Counter
from pathlib import Path
from core import ARCHIVE
from preprocessing import VERSION, prepare_events, validate_lineups, validate_matches


def main():
    totals, warnings, errors, changed = Counter(), [], [], []
    with zipfile.ZipFile(ARCHIVE) as z:
        prefix = next(n[:-len('competitions.json')] for n in z.namelist() if n.endswith('/data/competitions.json'))
        games = json.loads(z.read(prefix+'matches/2/27.json'))
        validate_matches(games)
        for i, game in enumerate(games):
            mid = game['match_id']
            try:
                raw = json.loads(z.read(prefix+f'events/{mid}.json'))
                clean, report = prepare_events(raw)
                validate_lineups(json.loads(z.read(prefix+f'lineups/{mid}.json')))
                totals.update({k: v for k, v in report.items() if isinstance(v, int)})
                if clean != raw: changed.append(mid)
                if report['spatial_bounds_warnings']: warnings.append({'match_id': mid, 'spatial_bounds': report['spatial_bounds_warnings']})
            except (ValueError, KeyError) as exc:
                errors.append({'match_id': mid, 'error': str(exc)})
            if (i+1) % 50 == 0: print(f'Preprocessing audit: {i+1}/{len(games)}', flush=True)
    result = {'version': VERSION, 'matches': len(games), 'totals': dict(totals), 'errors': errors,
              'warnings': warnings, 'matches_with_semantic_changes': changed,
              'existing_experiment_inputs_unchanged': not changed and not errors,
              'policy': 'Exact duplicates logged; conflicting IDs, missing xG and non-finite coordinates rejected. No imputation or clipping. Source order preserved.'}
    path = Path(__file__).parent / 'reports/preprocessing_audit.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors or changed: raise SystemExit(1)


if __name__ == '__main__': main()
