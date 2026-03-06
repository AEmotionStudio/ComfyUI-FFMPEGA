# coding: utf-8
"""Dense motion network for LivePortrait.

Predicts dense motion from sparse keypoint representations
using an hourglass architecture with deformable features.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

from .util import Hourglass, make_coordinate_grid, kp2gaussian


class DenseMotionNetwork(nn.Module):
    def __init__(self, block_expansion, num_blocks, max_features,
                 num_kp, feature_channel, reshape_depth, compress,
                 estimate_occlusion_map=True):
        super().__init__()
        self.hourglass = Hourglass(
            block_expansion=block_expansion,
            in_features=(num_kp + 1) * (compress + 1),
            max_features=max_features,
            num_blocks=num_blocks,
        )
        self.mask = nn.Conv3d(
            self.hourglass.out_filters, num_kp + 1,
            kernel_size=7, padding=3,
        )
        self.compress = nn.Conv3d(feature_channel, compress, kernel_size=1)
        self.norm = nn.BatchNorm3d(compress, affine=True)
        self.num_kp = num_kp
        self.flag_estimate_occlusion_map = estimate_occlusion_map

        if self.flag_estimate_occlusion_map:
            self.occlusion = nn.Conv2d(
                self.hourglass.out_filters * reshape_depth, 1,
                kernel_size=7, padding=3,
            )
        else:
            self.occlusion = None

    def create_sparse_motions(self, feature, kp_driving, kp_source):
        bs, _, d, h, w = feature.shape
        identity_grid = make_coordinate_grid((d, h, w), ref=kp_source)
        identity_grid = identity_grid.view(1, 1, d, h, w, 3)
        coordinate_grid = (
            identity_grid
            - kp_driving.view(bs, self.num_kp, 1, 1, 1, 3)
        )

        driving_to_source = (
            coordinate_grid
            + kp_source.view(bs, self.num_kp, 1, 1, 1, 3)
        )

        identity_grid = identity_grid.repeat(bs, 1, 1, 1, 1, 1)
        sparse_motions = torch.cat(
            [identity_grid, driving_to_source], dim=1)
        return sparse_motions

    def create_deformed_feature(self, feature, sparse_motions):
        bs, _, d, h, w = feature.shape
        feature_repeat = (
            feature.unsqueeze(1).unsqueeze(1)
            .repeat(1, self.num_kp + 1, 1, 1, 1, 1, 1)
        )
        feature_repeat = feature_repeat.view(
            bs * (self.num_kp + 1), -1, d, h, w)
        sparse_motions = sparse_motions.view(
            bs * (self.num_kp + 1), d, h, w, -1)
        sparse_deformed = F.grid_sample(
            feature_repeat, sparse_motions, align_corners=False)
        sparse_deformed = sparse_deformed.view(
            bs, self.num_kp + 1, -1, d, h, w)
        return sparse_deformed

    def create_heatmap_representations(self, feature, kp_driving, kp_source):
        spatial_size = feature.shape[3:]
        gaussian_driving = kp2gaussian(
            kp_driving, spatial_size=spatial_size, kp_variance=0.01)
        gaussian_source = kp2gaussian(
            kp_source, spatial_size=spatial_size, kp_variance=0.01)
        heatmap = gaussian_driving - gaussian_source

        zeros = torch.zeros(
            heatmap.shape[0], 1,
            spatial_size[0], spatial_size[1], spatial_size[2],
        ).type(heatmap.dtype).to(heatmap.device)
        heatmap = torch.cat([zeros, heatmap], dim=1)
        heatmap = heatmap.unsqueeze(2)
        return heatmap

    def forward(self, feature, kp_driving, kp_source):
        bs, _, d, h, w = feature.shape

        feature = self.compress(feature)
        feature = self.norm(feature)
        feature = F.relu(feature)

        out_dict = {}

        sparse_motion = self.create_sparse_motions(
            feature, kp_driving, kp_source)
        deformed_feature = self.create_deformed_feature(
            feature, sparse_motion)

        heatmap = self.create_heatmap_representations(
            deformed_feature, kp_driving, kp_source)

        input = torch.cat([heatmap, deformed_feature], dim=2)
        input = input.view(bs, -1, d, h, w)

        prediction = self.hourglass(input)

        mask = self.mask(prediction)
        mask = F.softmax(mask, dim=1)
        out_dict['mask'] = mask
        mask = mask.unsqueeze(2)
        sparse_motion = sparse_motion.permute(0, 1, 5, 2, 3, 4)
        deformation = (sparse_motion * mask).sum(dim=1)
        deformation = deformation.permute(0, 2, 3, 4, 1)

        out_dict['deformation'] = deformation

        if self.flag_estimate_occlusion_map:
            bs, _, d, h, w = prediction.shape
            prediction_reshape = prediction.view(bs, -1, h, w)
            occlusion_map = torch.sigmoid(
                self.occlusion(prediction_reshape))
            out_dict['occlusion_map'] = occlusion_map

        return out_dict
