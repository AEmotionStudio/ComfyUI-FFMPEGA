# coding: utf-8
"""Vendored from Pulse-of-Motion (Apache 2.0) — src/models/autoencoder.py

Base AutoencoderKL — pytorch_lightning stripped → pure torch.nn.Module.
Training methods (training_step, validation_step, configure_optimizers) removed.
"""

import torch
import torch.nn as nn
from einops import rearrange

from .ae_modules import Encoder, Decoder
from .distributions import DiagonalGaussianDistribution


class AutoencoderKL(nn.Module):
    def __init__(
        self,
        ddconfig,
        lossconfig,
        embed_dim,
        use_quant_conv=True,
        ckpt_path=None,
        ignore_keys=[],
        image_key="image",
        colorize_nlabels=None,
        monitor=None,
        test=False,
        logdir=None,
        input_dim=4,
        test_args=None,
    ):
        super().__init__()
        self.image_key = image_key
        self.encoder = Encoder(**ddconfig)
        self.decoder = Decoder(**ddconfig)
        # lossconfig is a dummy (torch.nn.Identity) — no loss instantiation needed
        assert ddconfig["double_z"]

        if use_quant_conv:
            self.quant_conv = torch.nn.Conv2d(
                2 * ddconfig["z_channels"], 2 * embed_dim, 1
            )
            self.post_quant_conv = torch.nn.Conv2d(embed_dim, ddconfig["z_channels"], 1)
            self.embed_dim = embed_dim

        self.use_quant_conv = use_quant_conv
        self.input_dim = input_dim
        self.test = test

        if ckpt_path is not None:
            self.init_from_ckpt(ckpt_path, ignore_keys=ignore_keys)

    def init_from_ckpt(self, path, ignore_keys=list()):
        sd = torch.load(path, map_location="cpu", weights_only=True)
        try:
            sd = sd["state_dict"]
        except (KeyError, TypeError):
            pass
        keys = list(sd.keys())
        for k in keys:
            for ik in ignore_keys:
                if k.startswith(ik):
                    del sd[k]
        self.load_state_dict(sd, strict=False)

    def encode(self, x, **kwargs):
        h = self.encoder(x)
        moments = h
        if self.use_quant_conv:
            moments = self.quant_conv(h)
        posterior = DiagonalGaussianDistribution(moments)
        return posterior

    def decode(self, z, **kwargs):
        if self.use_quant_conv:
            z = self.post_quant_conv(z)
        dec = self.decoder(z)
        return dec

    def forward(self, input, sample_posterior=True):
        posterior = self.encode(input)
        if sample_posterior:
            z = posterior.sample()
        else:
            z = posterior.mode()
        dec = self.decode(z)
        return dec, posterior

    def get_last_layer(self):
        return self.decoder.conv_out.weight

    def freeze(self):
        """Freeze all parameters (replaces pl.LightningModule.freeze)."""
        for param in self.parameters():
            param.requires_grad = False
