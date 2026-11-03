import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class NetworkTests(unittest.TestCase):
    def test_padding_never_changes_prediction(self):
        import torch
        from ml_models import MatchNetwork
        torch.manual_seed(42)
        for kind in ('MLP', 'Transformer', 'LSTM'):
            with self.subTest(model=kind):
                model = MatchNetwork(kind).eval()
                x = torch.randn(2, 6, 20)
                lengths = torch.tensor([2, 4])
                modified = x.clone()
                for i, length in enumerate(lengths): modified[i, length:] = 1000
                with torch.no_grad():
                    a, b = model(x, lengths), model(modified, lengths)
                    self.assertTrue(torch.allclose(a, b, atol=1e-5))
                    self.assertTrue(torch.allclose(a.softmax(1).sum(1), torch.ones(2)))


if __name__ == '__main__': unittest.main()
