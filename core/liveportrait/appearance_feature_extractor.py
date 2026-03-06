# coding: utf-8
"""Appearance Feature Extractor (F) for LivePortrait.

Maps a source image to a 3D appearance feature volume.
"""

import torch
from torch import nn

from .util import SameBlock2d, DownBlock2d, ResBlock3d


class AppearanceFeatureExtractor(nn.Module):
    def __init__(self, image_channel, block_expansion, num_down_blocks,
                 max_features, reshape_channel, reshape_depth, num_resblocks):
        super().__init__()
        self.image_channel = image_channel
        self.block_expansion = block_expansion
        self.num_down_blocks = num_down_blocks
        self.max_features = max_features
        self.reshape_channel = reshape_channel
        self.reshape_depth = reshape_depth

        self.first = SameBlock2d(
            image_channel, block_expansion,
            kernel_size=(3, 3), padding=(1, 1),
        )

        down_blocks = []
        out_features = block_expansion
        for i in range(num_down_blocks):
            in_features = min(max_features, block_expansion * (2 ** i))
            out_features = min(max_features, block_expansion * (2 ** (i + 1)))
            down_blocks.append(DownBlock2d(
                in_features, out_features,
                kernel_size=(3, 3), padding=(1, 1),
            ))
        self.down_blocks = nn.ModuleList(down_blocks)

        self.second = nn.Conv2d(
            in_channels=out_features, out_channels=max_features,
            kernel_size=1, stride=1,
        )

        self.resblocks_3d = nn.Sequential()
        for i in range(num_resblocks):
            self.resblocks_3d.add_module(
                '3dr' + str(i),
                ResBlock3d(reshape_channel, kernel_size=3, padding=1),
            )

    def forward(self, source_image):
        out = self.first(source_image)

        for i in range(len(self.down_blocks)):
            out = self.down_blocks[i](out)
        out = self.second(out)
        bs, c, h, w = out.shape

        f_s = out.view(
            bs, self.reshape_channel, self.reshape_depth, h, w)
        f_s = self.resblocks_3d(f_s)
        return f_s
