import logging
import numpy as np
import torch
import tyro

from examples.libero import serve_policy as stock

OriginalPolicy = stock.VJEPAPolicyServing

CAMERAS = {
    "observation/image": "observation.images.image",
    "observation/wrist_image": "observation.images.wrist_image",
    "observation/image_past": "observation.images.image_past",
    "observation/wrist_image_past": "observation.images.wrist_image_past",
}

class LiberoCompatiblePolicy(OriginalPolicy):
    def infer(self, obs):
        # Preserve native serving inputs unchanged.
        if "observation/image" not in obs:
            return super().infer(obs)

        converted = {}

        for source, target in CAMERAS.items():
            image = np.asarray(obs[source])

            if image.ndim != 3 or image.shape[-1] != 3:
                raise ValueError(
                    f"Invalid image shape for {source}: {image.shape}"
                )
            if image.dtype != np.uint8:
                raise ValueError(
                    f"Expected uint8 image for {source}, got {image.dtype}"
                )

            # HWC uint8 -> CHW float32 [0, 1]
            converted[target] = (
                torch.from_numpy(np.ascontiguousarray(image))
                .permute(2, 0, 1)
                .float()
                .div_(255.0)
            )

        converted["observation.state"] = torch.as_tensor(
            obs["observation/state"], dtype=torch.float32
        )
        converted["task"] = [str(obs["prompt"])]

        return super().infer(converted)

stock.VJEPAPolicyServing = LiberoCompatiblePolicy

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, force=True)
    stock.main(tyro.cli(stock.Args))
