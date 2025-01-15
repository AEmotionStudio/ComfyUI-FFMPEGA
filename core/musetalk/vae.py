"""VAE wrapper for MuseTalk — encode/decode face crops in latent space.

Adapted from MuseTalk (MIT License).
Uses ``diffusers.AutoencoderKL`` (already installed in ComfyUI).
"""

import cv2
import numpy as np
import torch
import torchvision.transforms as transforms
from diffusers import AutoencoderKL


class VAE:
    """Wraps a Stable Diffusion VAE for face image encoding/decoding."""

    def __init__(
        self,
        model_path: str = "stabilityai/sd-vae-ft-mse",
        resized_img: int = 256,
        use_float16: bool = False,
        device: torch.device | None = None,
    ):
        self.model_path = model_path
        self.vae = AutoencoderKL.from_pretrained(model_path)

        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self.vae.to(self.device)

        if use_float16:
            self.vae = self.vae.half()
            self._use_float16 = True
        else:
            self._use_float16 = False

        self.scaling_factor = self.vae.config.scaling_factor
        self.transform = transforms.Normalize(
            mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]
        )
        self._resized_img = resized_img
        self._mask_tensor = self._get_mask_tensor()

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------

    def _get_mask_tensor(self) -> torch.Tensor:
        """Create a mask: 1 for upper half, 0 for lower half."""
        mask = torch.zeros((self._resized_img, self._resized_img))
        mask[: self._resized_img // 2, :] = 1.0
        return mask

    def preprocess_img(
        self,
        img: np.ndarray | str,
        half_mask: bool = False,
    ) -> torch.Tensor:
        """Preprocess a face image for VAE encoding.

        Args:
            img: BGR numpy array (from cv2) or file path.
            half_mask: If True, zero out the lower half (mouth area).

        Returns:
            Tensor of shape ``[1, 3, 256, 256]``.
        """
        if isinstance(img, str):
            img = cv2.imread(img)

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_rgb = cv2.resize(
            img_rgb,
            (self._resized_img, self._resized_img),
            interpolation=cv2.INTER_LANCZOS4,
        )

        x = np.asarray(img_rgb, dtype=np.float32) / 255.0
        x = np.transpose(x, (2, 0, 1))  # HWC → CHW
        x = torch.FloatTensor(x)

        if half_mask:
            x = x * (self._mask_tensor > 0.5)

        x = self.transform(x)
        x = x.unsqueeze(0).to(self.device)
        return x

    def encode_latents(self, image: torch.Tensor) -> torch.Tensor:
        """Encode image tensor to latent space.

        Args:
            image: ``[B, 3, 256, 256]`` tensor.

        Returns:
            Latent tensor ``[B, 4, 32, 32]``.
        """
        with torch.no_grad():
            dist = self.vae.encode(image.to(self.vae.dtype)).latent_dist
        return self.scaling_factor * dist.sample()

    def decode_latents(self, latents: torch.Tensor) -> np.ndarray:
        """Decode latents back to BGR uint8 images.

        Args:
            latents: ``[B, 4, 32, 32]`` tensor.

        Returns:
            ``[B, H, W, 3]`` BGR uint8 numpy array.
        """
        latents = (1.0 / self.scaling_factor) * latents
        image = self.vae.decode(latents.to(self.vae.dtype)).sample
        image = (image / 2.0 + 0.5).clamp(0, 1)
        image = image.detach().cpu().permute(0, 2, 3, 1).float().numpy()
        image = (image * 255).round().astype("uint8")
        image = image[..., ::-1]  # RGB → BGR
        return image

    def get_latents_for_unet(self, img: np.ndarray) -> torch.Tensor:
        """Prepare concatenated latents for UNet input.

        Encodes both a masked (lower-half zeroed) and full reference
        version of the face, concatenating them along the channel dim.

        Args:
            img: BGR numpy array of face crop.

        Returns:
            ``[1, 8, 32, 32]`` tensor (masked + reference latents).
        """
        masked = self.preprocess_img(img, half_mask=True)
        masked_latents = self.encode_latents(masked)

        ref = self.preprocess_img(img, half_mask=False)
        ref_latents = self.encode_latents(ref)

        return torch.cat([masked_latents, ref_latents], dim=1)
