# coding: utf-8
"""Stitching and Retargeting Networks (S, R) for LivePortrait.

- Stitching module: pastes animated portrait back into original image
  space without pixel misalignment.
- Eye retargeting module: handles incomplete eye closure during
  cross-id reenactment.
- Lip retargeting module: normalizes lip state for better animation.
"""

from torch import nn


class StitchingRetargetingNetwork(nn.Module):
    def __init__(self, input_size, hidden_sizes, output_size):
        super().__init__()
        layers = []
        for i in range(len(hidden_sizes)):
            if i == 0:
                layers.append(nn.Linear(input_size, hidden_sizes[i]))
            else:
                layers.append(nn.Linear(hidden_sizes[i - 1], hidden_sizes[i]))
            layers.append(nn.ReLU(inplace=True))
        layers.append(nn.Linear(hidden_sizes[-1], output_size))
        self.mlp = nn.Sequential(*layers)

    def initialize_weights_to_zero(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.zeros_(m.weight)
                nn.init.zeros_(m.bias)

    def forward(self, x):
        return self.mlp(x)
