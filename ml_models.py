"""Small real PyTorch networks for short historical match sequences."""
import torch
from torch import nn


class MatchNetwork(nn.Module):
    def __init__(self, kind, features=20, sequence_length=6):
        super().__init__()
        self.kind = kind
        if kind == 'MLP':
            self.net = nn.Sequential(nn.Linear(features, 32), nn.ReLU(), nn.Dropout(.15),
                                     nn.Linear(32, 16), nn.ReLU(), nn.Linear(16, 3))
        elif kind == 'LSTM':
            self.recurrent = nn.LSTM(features, 24, batch_first=True)
            self.head = nn.Linear(24, 3)
        elif kind == 'Transformer':
            self.project = nn.Linear(features, 24)
            self.position = nn.Parameter(torch.zeros(1, sequence_length, 24))
            layer = nn.TransformerEncoderLayer(d_model=24, nhead=2, dim_feedforward=48,
                                                dropout=.15, batch_first=True)
            self.encoder = nn.TransformerEncoder(layer, num_layers=1, enable_nested_tensor=False)
            self.head = nn.Linear(24, 3)
        else:
            raise ValueError(kind)

    def forward(self, x, lengths):
        if self.kind == 'MLP':
            return self.net(x[torch.arange(len(x), device=x.device), lengths-1])
        if self.kind == 'LSTM':
            packed = nn.utils.rnn.pack_padded_sequence(x, lengths.cpu(), batch_first=True, enforce_sorted=False)
            _, (hidden, _) = self.recurrent(packed)
            return self.head(hidden[-1])
        mask = torch.arange(x.shape[1], device=x.device)[None, :] >= lengths[:, None]
        encoded = self.encoder(self.project(x) + self.position[:, :x.shape[1]], src_key_padding_mask=mask)
        return self.head(encoded[torch.arange(len(x), device=x.device), lengths-1])
