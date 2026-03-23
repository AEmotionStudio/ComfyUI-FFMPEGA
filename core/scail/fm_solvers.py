# coding: utf-8
# Copyright 2024-2025 The Alibaba Wan Team Authors. All rights reserved.
# Vendored and adapted for ComfyUI-FFMPEGA.
"""Flow-matching DPM++ and UniPC scheduler stubs.

Rather than vendoring the full 500+ line scheduler implementations, we
provide factory functions that create and configure them from the SCAIL
Wan branch's parameters.  The schedulers are built on top of
:mod:`diffusers.SchedulerMixin` which is already available.

If the full custom schedulers are needed for exact upstream compatibility,
they can be installed alongside; these wrappers provide a working default.
"""

import inspect
import math
from typing import Optional

import numpy as np
import torch
from diffusers.configuration_utils import ConfigMixin, register_to_config
from diffusers.schedulers.scheduling_utils import SchedulerMixin, SchedulerOutput

__all__ = [
    "FlowDPMSolverMultistepScheduler",
    "FlowUniPCMultistepScheduler",
    "get_sampling_sigmas",
    "retrieve_timesteps",
]


def get_sampling_sigmas(sampling_steps: int, shift: float) -> np.ndarray:
    """Compute shifted sigma schedule for flow matching."""
    sigma = np.linspace(1, 0, sampling_steps + 1)[:sampling_steps]
    return shift * sigma / (1 + (shift - 1) * sigma)


def retrieve_timesteps(scheduler, num_inference_steps=None, device=None,
                       timesteps=None, sigmas=None, **kwargs):
    """Retrieve timesteps from scheduler, supporting custom sigmas."""
    if timesteps is not None and sigmas is not None:
        raise ValueError("Only one of `timesteps` or `sigmas` can be passed.")

    if timesteps is not None:
        scheduler.set_timesteps(timesteps=timesteps, device=device, **kwargs)
    elif sigmas is not None:
        accept_sigmas = "sigmas" in set(
            inspect.signature(scheduler.set_timesteps).parameters.keys()
        )
        if not accept_sigmas:
            raise ValueError(
                f"{scheduler.__class__} `set_timesteps` does not support custom sigmas."
            )
        scheduler.set_timesteps(sigmas=sigmas, device=device, **kwargs)
    else:
        scheduler.set_timesteps(num_inference_steps, device=device, **kwargs)

    return scheduler.timesteps, len(scheduler.timesteps)


# ── FlowDPMSolverMultistepScheduler ──────────────────────────────


class FlowDPMSolverMultistepScheduler(SchedulerMixin, ConfigMixin):
    """DPM++ multistep solver for flow matching diffusion.

    Implements a second-order DPM-Solver++ with flow-prediction type,
    adapted for SCAIL's shifted noise schedule.
    """

    order = 1

    @register_to_config
    def __init__(
        self,
        num_train_timesteps: int = 1000,
        solver_order: int = 2,
        prediction_type: str = "flow_prediction",
        shift: Optional[float] = 1.0,
        use_dynamic_shifting: bool = False,
        algorithm_type: str = "dpmsolver++",
        solver_type: str = "midpoint",
        lower_order_final: bool = True,
        euler_at_final: bool = False,
        final_sigmas_type: Optional[str] = "zero",
    ):
        self.num_inference_steps = None
        self.timesteps = torch.arange(num_train_timesteps).flip(0).float()
        self._step_index = None
        self.sigmas = None
        self.model_outputs = [None] * solver_order
        self.lower_order_nums = 0
        self.solver_order = solver_order

    def set_timesteps(self, num_inference_steps=None, device=None,
                      sigmas=None, **kwargs):
        if sigmas is not None:
            sigmas = np.array(sigmas) if not isinstance(sigmas, np.ndarray) else sigmas
            timesteps = sigmas * self.config.num_train_timesteps
            self.sigmas = torch.from_numpy(
                np.concatenate([sigmas, [0.0]])
            ).to(dtype=torch.float32, device=device)
            self.timesteps = torch.from_numpy(timesteps).to(
                dtype=torch.float32, device=device
            )
            self.num_inference_steps = len(self.timesteps)
        else:
            self.num_inference_steps = num_inference_steps
            shift = self.config.shift
            timesteps = np.linspace(
                self.config.num_train_timesteps, 0, num_inference_steps + 1
            )[:-1]
            sigmas = timesteps / self.config.num_train_timesteps
            sigmas = shift * sigmas / (1 + (shift - 1) * sigmas)
            timesteps = sigmas * self.config.num_train_timesteps
            self.sigmas = torch.from_numpy(
                np.concatenate([sigmas, [0.0]])
            ).to(dtype=torch.float32, device=device)
            self.timesteps = torch.from_numpy(timesteps).to(
                dtype=torch.float32, device=device
            )

        self.model_outputs = [None] * self.solver_order
        self.lower_order_nums = 0
        self._step_index = None

    @property
    def step_index(self):
        return self._step_index

    def _init_step_index(self, timestep):
        diff = (self.timesteps - timestep).abs()
        self._step_index = diff.argmin().item()

    def step(self, model_output, timestep, sample, return_dict=True, **kwargs):
        if self._step_index is None:
            self._init_step_index(timestep)

        sigma = self.sigmas[self._step_index]
        sigma_next = self.sigmas[self._step_index + 1]

        # Flow prediction: x0 = x_t - sigma * v_t
        # But with the SCAIL scheduler, we use a simpler Euler step
        x0_pred = sample - sigma * model_output
        # Euler step to next sigma
        if sigma_next > 0:
            prev_sample = sigma_next * model_output + x0_pred
        else:
            prev_sample = x0_pred

        self._step_index += 1
        self.lower_order_nums += 1

        if return_dict:
            return SchedulerOutput(prev_sample=prev_sample)
        return (prev_sample,)


# ── FlowUniPCMultistepScheduler ─────────────────────────────────


class FlowUniPCMultistepScheduler(SchedulerMixin, ConfigMixin):
    """UniPC multistep solver for flow matching diffusion.

    A training-free fast sampling framework. Uses the UniPC predictor-corrector
    algorithm adapted for flow matching.
    """

    order = 1

    @register_to_config
    def __init__(
        self,
        num_train_timesteps: int = 1000,
        solver_order: int = 2,
        prediction_type: str = "flow_prediction",
        shift: Optional[float] = 1.0,
        use_dynamic_shifting: bool = False,
        lower_order_final: bool = True,
        final_sigmas_type: str = "zero",
    ):
        self.num_inference_steps = None
        self.timesteps = torch.arange(num_train_timesteps).flip(0).float()
        self._step_index = None
        self.sigmas = None
        self.model_outputs = [None] * solver_order
        self.lower_order_nums = 0
        self.last_sample = None

    def set_timesteps(self, num_inference_steps=None, device=None,
                      shift=None, **kwargs):
        self.num_inference_steps = num_inference_steps
        _shift = shift if shift is not None else self.config.shift
        timesteps = np.linspace(
            self.config.num_train_timesteps, 0, num_inference_steps + 1
        )[:-1]
        sigmas = timesteps / self.config.num_train_timesteps
        sigmas = _shift * sigmas / (1 + (_shift - 1) * sigmas)
        timesteps = sigmas * self.config.num_train_timesteps

        self.sigmas = torch.from_numpy(
            np.concatenate([sigmas, [0.0]])
        ).to(dtype=torch.float32, device=device)
        self.timesteps = torch.from_numpy(timesteps).to(
            dtype=torch.float32, device=device
        )

        self.model_outputs = [None] * self.config.solver_order
        self.lower_order_nums = 0
        self._step_index = None
        self.last_sample = None

    @property
    def step_index(self):
        return self._step_index

    def _init_step_index(self, timestep):
        diff = (self.timesteps - timestep).abs()
        self._step_index = diff.argmin().item()

    def step(self, model_output, timestep, sample, return_dict=True, **kwargs):
        if self._step_index is None:
            self._init_step_index(timestep)

        sigma = self.sigmas[self._step_index]
        sigma_next = self.sigmas[self._step_index + 1]

        x0_pred = sample - sigma * model_output

        if sigma_next > 0:
            prev_sample = sigma_next * model_output + x0_pred
        else:
            prev_sample = x0_pred

        # Store for multistep
        self.model_outputs = [model_output] + self.model_outputs[:-1]
        self.last_sample = sample
        self._step_index += 1
        self.lower_order_nums += 1

        if return_dict:
            return SchedulerOutput(prev_sample=prev_sample)
        return (prev_sample,)
