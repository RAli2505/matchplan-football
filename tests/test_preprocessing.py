import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class PreprocessingTests(unittest.TestCase):
    def test_exact_duplicate_removed_with_audit(self):
        from preprocessing import prepare_events
        from test_core import event
        e = event('Pass', 10, id='abc', index=1, location=[50, 40], **{'pass': {'end_location': [70, 40]}})
        cleaned, report = prepare_events([e, copy.deepcopy(e)])
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(report['exact_duplicates_removed'], 1)

    def test_conflicting_ids_never_silently_deduplicated(self):
        from preprocessing import prepare_events, DataQualityError
        from test_core import event
        a = event('Pass', 10, id='abc', location=[50, 40], **{'pass': {'end_location': [70, 40]}})
        b = copy.deepcopy(a); b['location'] = [90, 40]
        with self.assertRaises(DataQualityError): prepare_events([a, b])

    def test_missing_xg_not_imputed_as_zero(self):
        from preprocessing import prepare_events, DataQualityError
        from test_core import event
        with self.assertRaises(DataQualityError):
            prepare_events([event('Shot', 10, id='s', location=[100, 40], shot={'outcome': {'name': 'Saved'}})])

    def test_nonfinite_coordinate_rejected(self):
        from preprocessing import prepare_events, DataQualityError
        from test_core import event
        with self.assertRaises(DataQualityError):
            prepare_events([event('Pass', 10, id='p', location=[float('nan'), 40], **{'pass': {'end_location': [70, 40]}})])

    def test_raw_object_not_modified(self):
        from preprocessing import prepare_events
        from test_core import event
        raw = [event('Shot', 10, id='s', location=[100, 40], shot={'statsbomb_xg': .2})]
        original = copy.deepcopy(raw)
        clean, report = prepare_events(raw)
        self.assertEqual(raw, original)
        self.assertEqual(raw, clean)


if __name__ == '__main__': unittest.main()
