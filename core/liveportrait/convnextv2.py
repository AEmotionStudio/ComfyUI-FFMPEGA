# coding: utf-8
"""ConvNeXt V2 backbone adapted for LivePortrait motion extraction.

Extracts implicit keypoints, head pose (pitch/yaw/roll), translation,
scale, and expression deformation from an input face image.

Vendored from LivePortrait, with timm imports replaced by local util.
"""

import torch
import torch.nn as nn

from .util import LayerNorm, DropPath, trunc_normal_, GRN

__all__ = ['convnextv2_tiny']


class Block(nn.Module):
    """ConvNeXtV2 Block.

    Args:
        dim: Number of input channels.
        drop_path: Stochastic depth rate.
    """

    def __init__(self, dim, drop_path=0.):
        super().__init__()
        self.dwconv = nn.Conv2d(dim, dim, kernel_size=7, padding=3, groups=dim)
        self.norm = LayerNorm(dim, eps=1e-6)
        self.pwconv1 = nn.Linear(dim, 4 * dim)
        self.act = nn.GELU()
        self.grn = GRN(4 * dim)
        self.pwconv2 = nn.Linear(4 * dim, dim)
        self.drop_path = DropPath(drop_path) if drop_path > 0. else nn.Identity()

    def forward(self, x):
        input = x
        x = self.dwconv(x)
        x = x.permute(0, 2, 3, 1)  # (N, C, H, W) -> (N, H, W, C)
        x = self.norm(x)
        x = self.pwconv1(x)
        x = self.act(x)
        x = self.grn(x)
        x = self.pwconv2(x)
        x = x.permute(0, 3, 1, 2)  # (N, H, W, C) -> (N, C, H, W)
        x = input + self.drop_path(x)
        return x


class ConvNeXtV2(nn.Module):
    """ConvNeXt V2 with LivePortrait output heads.

    Args:
        in_chans: Number of input image channels.
        depths: Number of blocks at each stage.
        dims: Feature dimension at each stage.
        drop_path_rate: Stochastic depth rate.
    """

    def __init__(self, in_chans=3, depths=[3, 3, 9, 3],
                 dims=[96, 192, 384, 768], drop_path_rate=0., **kwargs):
        super().__init__()
        self.depths = depths
        self.downsample_layers = nn.ModuleList()

        # Stem
        stem = nn.Sequential(
            nn.Conv2d(in_chans, dims[0], kernel_size=4, stride=4),
            LayerNorm(dims[0], eps=1e-6, data_format="channels_first"),
        )
        self.downsample_layers.append(stem)

        # Intermediate downsampling layers
        for i in range(3):
            downsample_layer = nn.Sequential(
                LayerNorm(dims[i], eps=1e-6, data_format="channels_first"),
                nn.Conv2d(dims[i], dims[i + 1], kernel_size=2, stride=2),
            )
            self.downsample_layers.append(downsample_layer)

        # Feature resolution stages
        self.stages = nn.ModuleList()
        dp_rates = [
            x.item()
            for x in torch.linspace(0, drop_path_rate, sum(depths))
        ]
        cur = 0
        for i in range(4):
            stage = nn.Sequential(
                *[Block(dim=dims[i], drop_path=dp_rates[cur + j])
                  for j in range(depths[i])]
            )
            self.stages.append(stage)
            cur += depths[i]

        self.norm = nn.LayerNorm(dims[-1], eps=1e-6)

        # LivePortrait output heads
        num_bins = kwargs.get('num_bins', 66)
        num_kp = kwargs.get('num_kp', 24)
        self.fc_kp = nn.Linear(dims[-1], 3 * num_kp)
        self.fc_scale = nn.Linear(dims[-1], 1)
        self.fc_pitch = nn.Linear(dims[-1], num_bins)
        self.fc_yaw = nn.Linear(dims[-1], num_bins)
        self.fc_roll = nn.Linear(dims[-1], num_bins)
        self.fc_t = nn.Linear(dims[-1], 3)
        self.fc_exp = nn.Linear(dims[-1], 3 * num_kp)

    def _init_weights(self, m):
        if isinstance(m, (nn.Conv2d, nn.Linear)):
            trunc_normal_(m.weight, std=.02)
            nn.init.constant_(m.bias, 0)

    def forward_features(self, x):
        for i in range(4):
            x = self.downsample_layers[i](x)
            x = self.stages[i](x)
        return self.norm(x.mean([-2, -1]))

    def forward(self, x):
        x = self.forward_features(x)

        kp = self.fc_kp(x)
        pitch = self.fc_pitch(x)
        yaw = self.fc_yaw(x)
        roll = self.fc_roll(x)
        t = self.fc_t(x)
        exp = self.fc_exp(x)
        scale = self.fc_scale(x)

        return {
            'pitch': pitch,
            'yaw': yaw,
            'roll': roll,
            't': t,
            'exp': exp,
            'scale': scale,
            'kp': kp,
        }


def convnextv2_tiny(**kwargs):
    return ConvNeXtV2(
        depths=[3, 3, 9, 3], dims=[96, 192, 384, 768], **kwargs)
