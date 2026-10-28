#!/usr/bin/env python3
"""Local V-JEPA 2-AC prediction and optional CEM smoke check.

Derived from facebookresearch/vjepa2 commit
204698b45b3712590f06245fbfba32d3be539812, especially
notebooks/energy_landscape_example.ipynb and src/hub/backbones.py.
No network requests, simulator, or robot connection are used by this script.
"""

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


EXPECTED_REVISION = "204698b45b3712590f06245fbfba32d3be539812"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--precision", choices=("fp32", "bf16"), default="fp32")
    parser.add_argument("--mode", choices=("predict", "plan"), default="predict")
    parser.add_argument("--samples", type=int, default=25)
    parser.add_argument("--topk", type=int, default=10)
    parser.add_argument("--cem-steps", type=int, default=2)
    parser.add_argument("--rollout", type=int, default=2)
    parser.add_argument("--maxnorm", type=float, default=0.075)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    checkpoint_path = args.checkpoint.expanduser().resolve()
    trajectory_path = (args.trajectory or repo / "notebooks/franka_example_traj.npz").expanduser().resolve()
    if not (repo / "src/hub/backbones.py").is_file():
        parser.error(f"Not a V-JEPA 2 checkout: {repo}")
    if not checkpoint_path.is_file() or checkpoint_path.stat().st_size == 0:
        parser.error(f"Missing or empty AC checkpoint: {checkpoint_path}")
    if not trajectory_path.is_file():
        parser.error(f"Missing trajectory: {trajectory_path}")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("--output-dir must be fresh or empty")
    if not (2 <= args.topk <= args.samples and args.cem_steps > 0 and args.rollout > 0 and args.maxnorm > 0):
        parser.error("Require samples >= topk >= 2 and positive cem-steps, rollout, maxnorm")
    revision = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != EXPECTED_REVISION:
        parser.error(f"Expected repository commit {EXPECTED_REVISION}; found {revision}")
    if args.rollout > 32:
        parser.error("--rollout exceeds the official model's 32-tubelet context capacity")

    # The official package contains top-level src/app modules and notebook utils.
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(repo / "notebooks"))
    import numpy as np
    import torch
    from torch.nn import functional as F
    from app.vjepa_droid.transforms import make_transforms
    from src.hub.backbones import _clean_backbone_key, vjepa2_ac_vit_giant
    from utils.mpc_utils import poses_to_diff
    from utils.world_model_wrapper import WorldModel

    device = torch.device(args.device)
    if device.type not in {"cuda", "cpu"}:
        parser.error("This check supports --device cpu or cuda:N")
    if device.type == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA unavailable; check AC interpreter, GPU driver, and CUDA PyTorch build")
    if args.precision == "bf16" and (device.type != "cuda" or not torch.cuda.is_bf16_supported()):
        parser.error("bf16 mode requires a CUDA device with BF16 support; use fp32 otherwise")
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Repository: {revision}", flush=True)
    print(f"Torch: {torch.__version__}; CUDA runtime: {torch.version.cuda}; device: {device}", flush=True)
    print("Building AC encoder and predictor from local source...", flush=True)
    # Critical: pretrained=False bypasses the upstream localhost:8300 URL.
    encoder, predictor = vjepa2_ac_vit_giant(pretrained=False)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False, mmap=True)
    if not isinstance(checkpoint, dict) or not {"encoder", "predictor"} <= checkpoint.keys():
        raise ValueError("Expected AC checkpoint containing encoder and predictor; policy/visual-only weights differ")
    encoder_load = encoder.load_state_dict(_clean_backbone_key(dict(checkpoint["encoder"])), strict=False)
    if encoder_load.missing_keys or set(encoder_load.unexpected_keys) - {"pos_embed"}:
        raise ValueError(f"Unexpected encoder checkpoint mismatch: {encoder_load}")
    predictor.load_state_dict(_clean_backbone_key(dict(checkpoint["predictor"])), strict=True)
    del checkpoint
    encoder = encoder.to(device).eval()
    predictor = predictor.to(device).eval()
    transform = make_transforms(
        random_horizontal_flip=False,
        random_resize_aspect_ratio=(1.0, 1.0),
        random_resize_scale=(1.0, 1.0),
        reprob=0.0,
        auto_augment=False,
        motion_shift=False,
        crop_size=256,
    )
    tokens_per_frame = (256 // encoder.patch_size) ** 2
    world_model = WorldModel(
        encoder=encoder,
        predictor=predictor,
        tokens_per_frame=tokens_per_frame,
        transform=transform,
        normalize_reps=True,
        device=str(device),
        mpc_args={
            "rollout": args.rollout,
            "samples": args.samples,
            "topk": args.topk,
            "cem_steps": args.cem_steps,
            "momentum_mean": 0.15,
            "momentum_mean_gripper": 0.15,
            "momentum_std": 0.75,
            "momentum_std_gripper": 0.15,
            "maxnorm": args.maxnorm,
            "verbose": True,
        },
    )
    with np.load(trajectory_path, allow_pickle=False) as trajectory:
        observations = np.asarray(trajectory["observations"])
        states = np.asarray(trajectory["states"])
    if observations.ndim != 5 or observations.shape[1] < 2 or observations.shape[-1] != 3:
        raise ValueError(f"Expected observations [B,T>=2,H,W,3], found {observations.shape}")
    if states.ndim != 3 or states.shape[1] < 2 or states.shape[-1] != 7:
        raise ValueError(f"Expected states [B,T>=2,7], found {states.shape}")
    state = torch.as_tensor(states[0:1, 0:1], dtype=torch.float32, device=device)
    observed_action = poses_to_diff(states[0, 0], states[0, 1]).to(device=device, dtype=torch.float32)[None, None]
    precision_context = torch.autocast("cuda", dtype=torch.bfloat16) if args.precision == "bf16" else nullcontext()
    print("Running encoder and one-step action-conditioned prediction...", flush=True)
    with torch.inference_mode(), precision_context:
        current = world_model.encode(observations[0, 0])
        target = world_model.encode(observations[0, 1])
        predicted = predictor(current, observed_action, state)[:, -tokens_per_frame:]
        predicted = F.layer_norm(predicted, (predicted.size(-1),))
        if not torch.isfinite(predicted).all():
            raise RuntimeError("Nonfinite predicted latent")
        error = F.l1_loss(predicted.float(), target.float()).item()
        plan = None
        if args.mode == "plan":
            print("Planning with CEM...", flush=True)
            plan = world_model.infer_next_action(current[:, None], state, target[:, None])
            if tuple(plan.shape) != (args.rollout, 7) or not torch.isfinite(plan).all():
                raise RuntimeError(f"Invalid plan shape or values: {tuple(plan.shape)}")
    result = {
        "smoke_passed": True,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_revision": revision,
        "checkpoint": str(checkpoint_path),
        "trajectory": str(trajectory_path),
        "trajectory_frames_used": [0, 1],
        "torch_version": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "device": str(device),
        "precision": args.precision,
        "mode": args.mode,
        "context_latent_shape": list(current.shape),
        "prediction_latent_shape": list(predicted.shape),
        "one_step_jepa_l1": error,
        "encoder_unexpected_keys": list(encoder_load.unexpected_keys),
        "observed_action": observed_action[0, 0].cpu().tolist(),
        "planned_actions": None if plan is None else plan.float().cpu().tolist(),
        "parameters": {key: getattr(args, key) for key in ("samples", "topk", "cem_steps", "rollout", "maxnorm", "seed")},
    }
    if device.type == "cuda":
        result["peak_allocated_cuda_gib"] = torch.cuda.max_memory_allocated(device) / 1024**3
    (args.output_dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    print(f"AC smoke passed; result: {args.output_dir / 'result.json'}", flush=True)


if __name__ == "__main__":
    main()
