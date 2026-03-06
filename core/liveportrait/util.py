# coding: utf-8
"""Neural network building blocks for LivePortrait.

Contains convolutional blocks, residual blocks, normalizations,
spatial transformation helpers, and the Hourglass architecture.

Vendored from LivePortrait with timm dependency removed
(trunc_normal_, DropPath, LayerNorm, GRN are inlined).
"""

import collections.abc
import math
import warnings
from itertools import repeat

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.nn.utils.spectral_norm as spectral_norm


# ---------------------------------------------------------------------------
#  Spatial transformation helpers
# ---------------------------------------------------------------------------


def kp2gaussian(kp, spatial_size, kp_variance):
    """Transform a keypoint into gaussian-like representation."""
    mean = kp
    coordinate_grid = make_coordinate_grid(spatial_size, mean)
    number_of_leading_dimensions = len(mean.shape) - 1
    shape = (1,) * number_of_leading_dimensions + coordinate_grid.shape
    coordinate_grid = coordinate_grid.view(*shape)
    repeats = mean.shape[:number_of_leading_dimensions] + (1, 1, 1, 1)
    coordinate_grid = coordinate_grid.repeat(*repeats)

    shape = mean.shape[:number_of_leading_dimensions] + (1, 1, 1, 3)
    mean = mean.view(*shape)
    mean_sub = coordinate_grid - mean
    out = torch.exp(-0.5 * (mean_sub ** 2).sum(-1) / kp_variance)
    return out


def make_coordinate_grid(spatial_size, ref, **kwargs):
    d, h, w = spatial_size
    x = torch.arange(w).type(ref.dtype).to(ref.device)
    y = torch.arange(h).type(ref.dtype).to(ref.device)
    z = torch.arange(d).type(ref.dtype).to(ref.device)

    x = 2 * (x / (w - 1)) - 1
    y = 2 * (y / (h - 1)) - 1
    z = 2 * (z / (d - 1)) - 1

    yy = y.view(1, -1, 1).repeat(d, 1, w)
    xx = x.view(1, 1, -1).repeat(d, h, 1)
    zz = z.view(-1, 1, 1).repeat(1, h, w)

    meshed = torch.cat([
        xx.unsqueeze_(3), yy.unsqueeze_(3), zz.unsqueeze_(3)
    ], 3)
    return meshed


# ---------------------------------------------------------------------------
#  Convolutional blocks
# ---------------------------------------------------------------------------


class ConvT2d(nn.Module):
    """Upsampling block for use in decoder."""

    def __init__(self, in_features, out_features, kernel_size=3,
                 stride=2, padding=1, output_padding=1):
        super().__init__()
        self.convT = nn.ConvTranspose2d(
            in_features, out_features,
            kernel_size=kernel_size, stride=stride,
            padding=padding, output_padding=output_padding,
        )
        self.norm = nn.InstanceNorm2d(out_features)

    def forward(self, x):
        out = self.convT(x)
        out = self.norm(out)
        out = F.leaky_relu(out)
        return out


class ResBlock3d(nn.Module):
    """3D residual block, preserves spatial resolution."""

    def __init__(self, in_features, kernel_size, padding):
        super().__init__()
        self.conv1 = nn.Conv3d(in_features, in_features,
                               kernel_size=kernel_size, padding=padding)
        self.conv2 = nn.Conv3d(in_features, in_features,
                               kernel_size=kernel_size, padding=padding)
        self.norm1 = nn.BatchNorm3d(in_features, affine=True)
        self.norm2 = nn.BatchNorm3d(in_features, affine=True)

    def forward(self, x):
        out = self.norm1(x)
        out = F.relu(out)
        out = self.conv1(out)
        out = self.norm2(out)
        out = F.relu(out)
        out = self.conv2(out)
        out += x
        return out


class UpBlock3d(nn.Module):
    """3D upsampling block for use in decoder."""

    def __init__(self, in_features, out_features, kernel_size=3,
                 padding=1, groups=1):
        super().__init__()
        self.conv = nn.Conv3d(in_features, out_features,
                              kernel_size=kernel_size, padding=padding,
                              groups=groups)
        self.norm = nn.BatchNorm3d(out_features, affine=True)

    def forward(self, x):
        out = F.interpolate(x, scale_factor=(1, 2, 2))
        out = self.conv(out)
        out = self.norm(out)
        out = F.relu(out)
        return out


class DownBlock2d(nn.Module):
    """2D downsampling block for use in encoder."""

    def __init__(self, in_features, out_features, kernel_size=3,
                 padding=1, groups=1):
        super().__init__()
        self.conv = nn.Conv2d(in_features, out_features,
                              kernel_size=kernel_size, padding=padding,
                              groups=groups)
        self.norm = nn.BatchNorm2d(out_features, affine=True)
        self.pool = nn.AvgPool2d(kernel_size=(2, 2))

    def forward(self, x):
        out = self.conv(x)
        out = self.norm(out)
        out = F.relu(out)
        out = self.pool(out)
        return out


class DownBlock3d(nn.Module):
    """3D downsampling block for use in encoder."""

    def __init__(self, in_features, out_features, kernel_size=3,
                 padding=1, groups=1):
        super().__init__()
        self.conv = nn.Conv3d(in_features, out_features,
                              kernel_size=kernel_size, padding=padding,
                              groups=groups)
        self.norm = nn.BatchNorm3d(out_features, affine=True)
        self.pool = nn.AvgPool3d(kernel_size=(1, 2, 2))

    def forward(self, x):
        out = self.conv(x)
        out = self.norm(out)
        out = F.relu(out)
        out = self.pool(out)
        return out


class SameBlock2d(nn.Module):
    """2D block that preserves spatial resolution."""

    def __init__(self, in_features, out_features, groups=1,
                 kernel_size=3, padding=1, lrelu=False):
        super().__init__()
        self.conv = nn.Conv2d(in_features, out_features,
                              kernel_size=kernel_size, padding=padding,
                              groups=groups)
        self.norm = nn.BatchNorm2d(out_features, affine=True)
        if lrelu:
            self.ac = nn.LeakyReLU()
        else:
            self.ac = nn.ReLU()

    def forward(self, x):
        out = self.conv(x)
        out = self.norm(out)
        out = self.ac(out)
        return out


# ---------------------------------------------------------------------------
#  Hourglass architecture
# ---------------------------------------------------------------------------


class Encoder(nn.Module):
    """Hourglass encoder."""

    def __init__(self, block_expansion, in_features, num_blocks=3,
                 max_features=256):
        super().__init__()
        down_blocks = []
        for i in range(num_blocks):
            in_f = in_features if i == 0 else min(
                max_features, block_expansion * (2 ** i))
            out_f = min(max_features, block_expansion * (2 ** (i + 1)))
            down_blocks.append(DownBlock3d(in_f, out_f,
                                           kernel_size=3, padding=1))
        self.down_blocks = nn.ModuleList(down_blocks)

    def forward(self, x):
        outs = [x]
        for down_block in self.down_blocks:
            outs.append(down_block(outs[-1]))
        return outs


class Decoder(nn.Module):
    """Hourglass decoder."""

    def __init__(self, block_expansion, in_features, num_blocks=3,
                 max_features=256):
        super().__init__()
        up_blocks = []
        for i in range(num_blocks)[::-1]:
            in_filters = (
                (1 if i == num_blocks - 1 else 2)
                * min(max_features, block_expansion * (2 ** (i + 1)))
            )
            out_filters = min(max_features, block_expansion * (2 ** i))
            up_blocks.append(UpBlock3d(in_filters, out_filters,
                                       kernel_size=3, padding=1))
        self.up_blocks = nn.ModuleList(up_blocks)
        self.out_filters = block_expansion + in_features

        self.conv = nn.Conv3d(self.out_filters, self.out_filters,
                              kernel_size=3, padding=1)
        self.norm = nn.BatchNorm3d(self.out_filters, affine=True)

    def forward(self, x):
        out = x.pop()
        for up_block in self.up_blocks:
            out = up_block(out)
            skip = x.pop()
            out = torch.cat([out, skip], dim=1)
        out = self.conv(out)
        out = self.norm(out)
        out = F.relu(out)
        return out


class Hourglass(nn.Module):
    """Hourglass architecture (encoder-decoder with skip connections)."""

    def __init__(self, block_expansion, in_features, num_blocks=3,
                 max_features=256):
        super().__init__()
        self.encoder = Encoder(block_expansion, in_features,
                               num_blocks, max_features)
        self.decoder = Decoder(block_expansion, in_features,
                               num_blocks, max_features)
        self.out_filters = self.decoder.out_filters

    def forward(self, x):
        return self.decoder(self.encoder(x))


# ---------------------------------------------------------------------------
#  SPADE normalization
# ---------------------------------------------------------------------------


class SPADE(nn.Module):
    def __init__(self, norm_nc, label_nc):
        super().__init__()
        self.param_free_norm = nn.InstanceNorm2d(norm_nc, affine=False)
        nhidden = 128
        self.mlp_shared = nn.Sequential(
            nn.Conv2d(label_nc, nhidden, kernel_size=3, padding=1),
            nn.ReLU(),
        )
        self.mlp_gamma = nn.Conv2d(nhidden, norm_nc, kernel_size=3, padding=1)
        self.mlp_beta = nn.Conv2d(nhidden, norm_nc, kernel_size=3, padding=1)

    def forward(self, x, segmap):
        normalized = self.param_free_norm(x)
        segmap = F.interpolate(segmap, size=x.size()[2:], mode='nearest')
        actv = self.mlp_shared(segmap)
        gamma = self.mlp_gamma(actv)
        beta = self.mlp_beta(actv)
        out = normalized * (1 + gamma) + beta
        return out


class SPADEResnetBlock(nn.Module):
    def __init__(self, fin, fout, norm_G, label_nc, use_se=False, dilation=1):
        super().__init__()
        self.learned_shortcut = (fin != fout)
        fmiddle = min(fin, fout)
        self.use_se = use_se

        self.conv_0 = nn.Conv2d(fin, fmiddle, kernel_size=3,
                                padding=dilation, dilation=dilation)
        self.conv_1 = nn.Conv2d(fmiddle, fout, kernel_size=3,
                                padding=dilation, dilation=dilation)
        if self.learned_shortcut:
            self.conv_s = nn.Conv2d(fin, fout, kernel_size=1, bias=False)

        if 'spectral' in norm_G:
            self.conv_0 = spectral_norm(self.conv_0)
            self.conv_1 = spectral_norm(self.conv_1)
            if self.learned_shortcut:
                self.conv_s = spectral_norm(self.conv_s)

        self.norm_0 = SPADE(fin, label_nc)
        self.norm_1 = SPADE(fmiddle, label_nc)
        if self.learned_shortcut:
            self.norm_s = SPADE(fin, label_nc)

    def forward(self, x, seg1):
        x_s = self.shortcut(x, seg1)
        dx = self.conv_0(self.actvn(self.norm_0(x, seg1)))
        dx = self.conv_1(self.actvn(self.norm_1(dx, seg1)))
        out = x_s + dx
        return out

    def shortcut(self, x, seg1):
        if self.learned_shortcut:
            x_s = self.conv_s(self.norm_s(x, seg1))
        else:
            x_s = x
        return x_s

    def actvn(self, x):
        return F.leaky_relu(x, 2e-1)


# ---------------------------------------------------------------------------
#  Utility functions (inlined from timm to avoid dependency)
# ---------------------------------------------------------------------------


def filter_state_dict(state_dict, remove_name='fc'):
    new_state_dict = {}
    for key in state_dict:
        if remove_name in key:
            continue
        new_state_dict[key] = state_dict[key]
    return new_state_dict


class GRN(nn.Module):
    """Global Response Normalization layer."""

    def __init__(self, dim):
        super().__init__()
        self.gamma = nn.Parameter(torch.zeros(1, 1, 1, dim))
        self.beta = nn.Parameter(torch.zeros(1, 1, 1, dim))

    def forward(self, x):
        Gx = torch.norm(x, p=2, dim=(1, 2), keepdim=True)
        Nx = Gx / (Gx.mean(dim=-1, keepdim=True) + 1e-6)
        return self.gamma * (x * Nx) + self.beta + x


class LayerNorm(nn.Module):
    """LayerNorm supporting channels_last and channels_first formats."""

    def __init__(self, normalized_shape, eps=1e-6,
                 data_format="channels_last"):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(normalized_shape))
        self.bias = nn.Parameter(torch.zeros(normalized_shape))
        self.eps = eps
        self.data_format = data_format
        if self.data_format not in ["channels_last", "channels_first"]:
            raise NotImplementedError
        self.normalized_shape = (normalized_shape,)

    def forward(self, x):
        if self.data_format == "channels_last":
            return F.layer_norm(
                x, self.normalized_shape, self.weight, self.bias, self.eps)
        elif self.data_format == "channels_first":
            u = x.mean(1, keepdim=True)
            s = (x - u).pow(2).mean(1, keepdim=True)
            x = (x - u) / torch.sqrt(s + self.eps)
            x = self.weight[:, None, None] * x + self.bias[:, None, None]
            return x


def _no_grad_trunc_normal_(tensor, mean, std, a, b):
    """Truncated normal initialization (from PyTorch internals)."""
    def norm_cdf(x):
        return (1. + math.erf(x / math.sqrt(2.))) / 2.

    if (mean < a - 2 * std) or (mean > b + 2 * std):
        warnings.warn(
            "mean is more than 2 std from [a, b] in trunc_normal_. "
            "The distribution of values may be incorrect.",
            stacklevel=2,
        )

    with torch.no_grad():
        l = norm_cdf((a - mean) / std)
        u = norm_cdf((b - mean) / std)
        tensor.uniform_(2 * l - 1, 2 * u - 1)
        tensor.erfinv_()
        tensor.mul_(std * math.sqrt(2.))
        tensor.add_(mean)
        tensor.clamp_(min=a, max=b)
        return tensor


def trunc_normal_(tensor, mean=0., std=1., a=-2., b=2.):
    return _no_grad_trunc_normal_(tensor, mean, std, a, b)


def drop_path(x, drop_prob=0., training=False, scale_by_keep=True):
    """Drop paths (Stochastic Depth) per sample."""
    if drop_prob == 0. or not training:
        return x
    keep_prob = 1 - drop_prob
    shape = (x.shape[0],) + (1,) * (x.ndim - 1)
    random_tensor = x.new_empty(shape).bernoulli_(keep_prob)
    if keep_prob > 0.0 and scale_by_keep:
        random_tensor.div_(keep_prob)
    return x * random_tensor


class DropPath(nn.Module):
    """Drop paths (Stochastic Depth) per sample."""

    def __init__(self, drop_prob=None, scale_by_keep=True):
        super().__init__()
        self.drop_prob = drop_prob
        self.scale_by_keep = scale_by_keep

    def forward(self, x):
        return drop_path(x, self.drop_prob, self.training, self.scale_by_keep)


# From PyTorch internals
def _ntuple(n):
    def parse(x):
        if isinstance(x, collections.abc.Iterable) and not isinstance(x, str):
            return tuple(x)
        return tuple(repeat(x, n))
    return parse


to_2tuple = _ntuple(2)
