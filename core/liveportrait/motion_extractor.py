# coding: utf-8
"""Motion Extractor (M) for LivePortrait.

Predicts canonical keypoints, head pose, and expression
deformation from an input face image using ConvNeXtV2.
"""

from torch import nn

from .convnextv2 import convnextv2_tiny
from .util import filter_state_dict

_model_dict = {
    'convnextv2_tiny': convnextv2_tiny,
}


class MotionExtractor(nn.Module):
    def __init__(self, **kwargs):
        super().__init__()
        backbone = kwargs.get('backbone', 'convnextv2_tiny')
        self.detector = _model_dict.get(backbone)(**kwargs)

    def forward(self, x):
        out = self.detector(x)
        return out
