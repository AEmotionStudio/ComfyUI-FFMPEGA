# coding: utf-8
# Vendored from kijai/ComfyUI-SCAIL-Pose/render_3d/render_torch.py
"""PyTorch-based 3D cylinder renderer using ray marching.

This replaces the taichi-based renderer, using pure PyTorch operations
for GPU-accelerated rendering. Renders 3D skeleton cylinders with
Blinn-Phong shading and depth-based attenuation.
"""

import math
import random

import numpy as np
import torch


def flatten_specs(specs_list):
    """Flatten cylinder specs into batched numpy arrays.

    Returns:
        starts: (N, 3) float32  — cylinder start positions
        ends:   (N, 3) float32  — cylinder end positions
        colors: (N, 4) float32  — RGBA colors
        frame_offset: (num_frames,) int32
        frame_count:  (num_frames,) int32
    """
    starts, ends, colors = [], [], []
    frame_offset, frame_count = [], []
    offset = 0
    for specs in specs_list:
        frame_offset.append(offset)
        frame_count.append(len(specs))
        for s, e, c in specs:
            starts.append(s)
            ends.append(e)
            colors.append(c)
        offset += len(specs)

    if len(starts) == 0:
        return (
            np.zeros((0, 3), dtype=np.float32),
            np.zeros((0, 3), dtype=np.float32),
            np.zeros((0, 4), dtype=np.float32),
            np.array(frame_offset, dtype=np.int32),
            np.array(frame_count, dtype=np.int32),
        )

    return (
        np.array(starts, dtype=np.float32),
        np.array(ends, dtype=np.float32),
        np.array(colors, dtype=np.float32),
        np.array(frame_offset, dtype=np.int32),
        np.array(frame_count, dtype=np.int32),
    )


def render_whole(
    specs_list, H=480, W=640, fx=500, fy=500, cx=240, cy=320, radius=21.5, device=None
):
    """Render cylinders using PyTorch ray marching.

    Args:
        specs_list: List of frame specs, each a list of (start, end, color) tuples.
        H, W: Output image dimensions.
        fx, fy: Camera focal lengths.
        cx, cy: Camera principal point.
        radius: Cylinder radius in world units.
        device: PyTorch device (default: CUDA if available).

    Returns:
        List of (H, W, 4) uint8 RGBA numpy arrays, one per frame.
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    starts_np, ends_np, colors_np, frame_offset_np, frame_count_np = flatten_specs(
        specs_list
    )

    if len(starts_np) == 0:
        return [np.zeros((H, W, 4), dtype=np.uint8) for _ in range(len(specs_list))]

    all_starts = torch.from_numpy(starts_np).to(device).float()
    all_ends = torch.from_numpy(ends_np).to(device).float()
    all_colors = torch.from_numpy(colors_np).to(device).float()

    z_min_val = min(starts_np[:, 2].min(), ends_np[:, 2].min())
    z_max_val = max(starts_np[:, 2].max(), ends_np[:, 2].max())

    znear = 0.1
    zfar = max(min(z_max_val, 25000), 10000)

    y_coords, x_coords = torch.meshgrid(
        torch.arange(H, device=device).float(),
        torch.arange(W, device=device).float(),
        indexing="ij",
    )

    u = (x_coords - cx) / fx
    v = (y_coords - cy) / fy
    z = torch.ones_like(u)

    ray_dirs = torch.stack([u, v, z], dim=-1)
    ray_dirs = ray_dirs / torch.norm(ray_dirs, dim=-1, keepdim=True)
    ray_origins = torch.zeros((H, W, 3), device=device)
    light_dir = torch.tensor([0.0, 0.0, 1.0], device=device)

    MAX_STEPS = 100
    EPSILON = 1e-3

    rendered_frames = []

    for i in range(len(specs_list)):
        start_idx = frame_offset_np[i]
        count = frame_count_np[i]

        if count == 0:
            rendered_frames.append(np.zeros((H, W, 4), dtype=np.uint8))
            continue

        curr_starts = all_starts[start_idx:start_idx + count]
        curr_ends = all_ends[start_idx:start_idx + count]
        curr_colors = all_colors[start_idx:start_idx + count]

        ba = curr_ends - curr_starts
        ba_len = torch.sqrt((ba * ba).sum(dim=1))
        ba_norm = ba / ba_len.unsqueeze(1)

        flat_ray_dirs = ray_dirs.view(-1, 3)
        flat_ray_origins = ray_origins.view(-1, 3)

        pixels_n = H * W
        flat_t = torch.ones(pixels_n, device=device) * znear
        flat_active = torch.ones(pixels_n, dtype=torch.bool, device=device)
        flat_hit = torch.zeros(pixels_n, dtype=torch.bool, device=device)
        flat_hit_color = torch.zeros((pixels_n, 4), device=device)
        flat_hit_pos = torch.zeros((pixels_n, 3), device=device)

        depth_near = max(z_min_val, 0.1)
        depth_far = min(z_max_val + 6000, 20000)

        for step in range(MAX_STEPS):
            if not flat_active.any():
                break

            p = flat_ray_origins + flat_ray_dirs * flat_t.unsqueeze(1)
            active_indices = torch.nonzero(flat_active).squeeze()
            if active_indices.numel() == 0:
                break

            p_active = p[active_indices]

            pa = p_active.unsqueeze(1) - curr_starts.unsqueeze(0)
            proj = (pa * ba_norm.unsqueeze(0)).sum(dim=-1)
            proj_clamped = proj.clamp(min=0.0).min(ba_len.unsqueeze(0))
            closest_on_axis = curr_starts.unsqueeze(0) + proj_clamped.unsqueeze(-1) * ba_norm.unsqueeze(0)
            dist_vec = p_active.unsqueeze(1) - closest_on_axis
            dist_euc = torch.norm(dist_vec, dim=-1)
            sdf = dist_euc - radius

            min_sdf, min_idx = sdf.min(dim=1)
            current_t_vals = flat_t[active_indices]

            hit_cond = min_sdf < EPSILON
            miss_cond = current_t_vals > zfar
            new_hits = hit_cond & (~miss_cond)

            hit_global_idx = active_indices[new_hits]
            if hit_global_idx.numel() > 0:
                flat_hit[hit_global_idx] = True
                flat_active[hit_global_idx] = False
                flat_hit_pos[hit_global_idx] = p_active[new_hits]
                closest_cyl_idx = min_idx[new_hits]
                flat_hit_color[hit_global_idx] = curr_colors[closest_cyl_idx]

            miss_global_idx = active_indices[miss_cond]
            if miss_global_idx.numel() > 0:
                flat_active[miss_global_idx] = False

            still_active_local = ~(hit_cond | miss_cond)
            if still_active_local.any():
                step_dist = min_sdf[still_active_local]
                step_dist = torch.max(step_dist, torch.tensor(1e-4, device=device))
                active_global_idx = active_indices[still_active_local]
                flat_t[active_global_idx] += step_dist

        # ── Blinn-Phong shading ──
        hit_indices = torch.nonzero(flat_hit).squeeze()

        if hit_indices.numel() > 0:
            p_hit = flat_hit_pos[hit_indices]
            hit_cols = flat_hit_color[hit_indices]

            e = 1e-3

            def get_sdf_batch(points):
                pa = points.unsqueeze(1) - curr_starts.unsqueeze(0)
                proj = (pa * ba_norm.unsqueeze(0)).sum(dim=-1)
                proj_clamped = proj.clamp(min=0.0).min(ba_len.unsqueeze(0))
                closest = curr_starts.unsqueeze(0) + proj_clamped.unsqueeze(-1) * ba_norm.unsqueeze(0)
                dist = torch.norm(points.unsqueeze(1) - closest, dim=-1)
                sdf = dist - radius
                return sdf.min(dim=1)[0]

            def get_normal_batch(points):
                dx = get_sdf_batch(points + torch.tensor([e, 0, 0], device=device)) - get_sdf_batch(points - torch.tensor([e, 0, 0], device=device))
                dy = get_sdf_batch(points + torch.tensor([0, e, 0], device=device)) - get_sdf_batch(points - torch.tensor([0, e, 0], device=device))
                dz = get_sdf_batch(points + torch.tensor([0, 0, e], device=device)) - get_sdf_batch(points - torch.tensor([0, 0, e], device=device))
                n = torch.stack([dx, dy, dz], dim=-1)
                return n / (torch.norm(n, dim=-1, keepdim=True) + 1e-8)

            normals = get_normal_batch(p_hit)
            view_dir = -flat_ray_dirs[hit_indices]
            view_dir = view_dir / torch.norm(view_dir, dim=-1, keepdim=True)

            diff = torch.clamp((normals * (-light_dir)).sum(dim=-1), min=0.0)

            half_dir = (view_dir + (-light_dir)).float()
            half_dir = half_dir / (torch.norm(half_dir, dim=-1, keepdim=True) + 1e-8)
            spec = torch.clamp((normals * half_dir).sum(dim=-1), min=0.0)
            spec = spec ** 32

            z_vals = p_hit[:, 2]
            depth_factor = 1.0 - (z_vals - depth_near) / (depth_far - znear)
            depth_factor = depth_factor.clamp(0.0, 1.0)

            diffuse_term = 0.3 + 0.7 * diff
            base_rgb = hit_cols[:, :3] * diffuse_term.unsqueeze(-1) * depth_factor.unsqueeze(-1)
            highlight = (
                torch.tensor([1.0, 1.0, 1.0], device=device)
                * (0.5 * spec.unsqueeze(-1))
                * depth_factor.unsqueeze(-1)
            )
            final_rgb = base_rgb + highlight

            flat_hit_color[hit_indices, :3] = final_rgb
            flat_hit_color[hit_indices, 3] = hit_cols[:, 3]

        frame_img = flat_hit_color.view(H, W, 4)
        frame_np = (frame_img.clamp(0, 1) * 255).byte().cpu().numpy()
        rendered_frames.append(frame_np)

    return rendered_frames
