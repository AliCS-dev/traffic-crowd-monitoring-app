import importlib
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from evaluation.crowd_counting import (
    CrowdCandidateSettings,
    CrowdCountExample,
    CrowdCountingError,
    CrowdCountObservation,
    CrowdInferenceSettings,
    sha256_file,
)


def iter_image_tiles(image: Image.Image, tile_size: int) -> Iterator[Image.Image]:
    if tile_size < 1:
        raise ValueError("Tile size must be positive")
    width, height = image.size
    for top in range(0, height, tile_size):
        for left in range(0, width, tile_size):
            yield image.crop(
                (left, top, min(left + tile_size, width), min(top + tile_size, height))
            )


class P2PNetAdapter:
    def __init__(
        self,
        repository_root: Path,
        candidate: CrowdCandidateSettings,
        inference: CrowdInferenceSettings,
    ) -> None:
        try:
            import torch
            from torchvision.transforms import functional as transform
        except ImportError as error:
            raise CrowdCountingError(
                "P2PNet evaluation requires torch and torchvision"
            ) from error

        self.torch = torch
        self.transform = transform
        self.device = torch.device(inference.device)
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise CrowdCountingError("CUDA was configured but is unavailable")

        source_directory = repository_root / inference.source_directory
        weights_path = repository_root / candidate.weights_path
        self._verify_candidate(source_directory, weights_path, candidate)
        self.model = self._load_model(source_directory, weights_path)
        self.confidence = inference.operating_confidence
        self.tile_size = inference.tile_size

    @staticmethod
    def _verify_candidate(
        source_directory: Path,
        weights_path: Path,
        candidate: CrowdCandidateSettings,
    ) -> None:
        if not source_directory.is_dir():
            raise CrowdCountingError(
                f"P2PNet source directory is missing: {source_directory}"
            )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=source_directory,
            check=False,
            capture_output=True,
            text=True,
        )
        if (
            result.returncode != 0
            or result.stdout.strip() != candidate.repository_revision
        ):
            raise CrowdCountingError(
                "P2PNet source revision does not match the protocol"
            )
        try:
            size = weights_path.stat().st_size
        except OSError as error:
            raise CrowdCountingError(
                f"P2PNet checkpoint is missing: {weights_path}"
            ) from error
        if size != candidate.weights_size_bytes:
            raise CrowdCountingError(
                "P2PNet checkpoint size does not match the protocol"
            )
        if sha256_file(weights_path) != candidate.weights_sha256:
            raise CrowdCountingError(
                "P2PNet checkpoint hash does not match the protocol"
            )

    def _load_model(self, source_directory: Path, weights_path: Path):
        import torchvision

        collisions = set(sys.modules) & {"models", "util"}
        if collisions:
            raise CrowdCountingError(
                "Cannot import P2PNet after top-level modules are loaded: "
                + ", ".join(sorted(collisions))
            )
        sys.path.insert(0, str(source_directory))
        torchvision_version = torchvision.__version__
        try:
            # Upstream parses 0.27 as decimal 0.2 and imports a removed 0.5 API.
            torchvision.__version__ = "1.0"
            models = importlib.import_module("models")
            upstream_vgg = importlib.import_module("models.vgg_")
            original_vgg16_bn = upstream_vgg.vgg16_bn

            def without_private_pretraining(*args, **kwargs):
                kwargs["pretrained"] = False
                return original_vgg16_bn(*args, **kwargs)

            upstream_vgg.vgg16_bn = without_private_pretraining
            model = models.build_model(
                SimpleNamespace(backbone="vgg16_bn", row=2, line=2)
            )
        finally:
            torchvision.__version__ = torchvision_version
            sys.path.remove(str(source_directory))

        checkpoint = self.torch.load(
            weights_path, map_location="cpu", weights_only=True
        )
        model.load_state_dict(checkpoint["model"], strict=True)
        model.to(self.device)
        model.eval()
        return model

    def _tensor(self, tile: Image.Image):
        tensor = self.transform.to_tensor(tile)
        tensor = self.transform.normalize(
            tensor,
            mean=(0.485, 0.456, 0.406),
            std=(0.229, 0.224, 0.225),
        )
        return tensor.unsqueeze(0).to(self.device)

    def count_tile(self, tile: Image.Image) -> int:
        width, height = tile.size
        padded_width = ((width + 15) // 16) * 16
        padded_height = ((height + 15) // 16) * 16
        padded = tile
        if (padded_width, padded_height) != tile.size:
            padded = Image.new("RGB", (padded_width, padded_height))
            padded.paste(tile, (0, 0))
        with self.torch.inference_mode():
            output = self.model(self._tensor(padded))
            scores = self.torch.nn.functional.softmax(output["pred_logits"], dim=-1)[
                0, :, 1
            ]
            selected = scores > self.confidence
            if padded.size != tile.size:
                points = output["pred_points"][0]
                selected &= (
                    (points[:, 0] >= 0)
                    & (points[:, 0] < width)
                    & (points[:, 1] >= 0)
                    & (points[:, 1] < height)
                )
            return int(selected.sum().item())

    def warm_up(self, image_path: Path, repetitions: int) -> None:
        if repetitions == 0:
            return
        with Image.open(image_path) as image:
            tile = next(iter_image_tiles(image.convert("RGB"), self.tile_size))
            for _ in range(repetitions):
                self.count_tile(tile)
        self.synchronize()

    def synchronize(self) -> None:
        if self.device.type == "cuda":
            self.torch.cuda.synchronize(self.device)

    def reset_peak_memory(self) -> None:
        if self.device.type == "cuda":
            self.torch.cuda.reset_peak_memory_stats(self.device)

    def peak_memory_bytes(self) -> int | None:
        if self.device.type != "cuda":
            return None
        return int(self.torch.cuda.max_memory_allocated(self.device))

    def evaluate(self, example: CrowdCountExample) -> CrowdCountObservation:
        with Image.open(example.asset.image_path) as image:
            rgb_image = image.convert("RGB")
            tiles = tuple(iter_image_tiles(rgb_image, self.tile_size))
            self.synchronize()
            started = time.perf_counter()
            predicted_count = sum(self.count_tile(tile) for tile in tiles)
            self.synchronize()
            elapsed = time.perf_counter() - started
        return CrowdCountObservation(
            asset_id=example.asset.asset_id,
            reference_count=example.reference_count,
            predicted_count=predicted_count,
            width=example.asset.width,
            height=example.asset.height,
            elapsed_seconds=elapsed,
            tile_count=len(tiles),
        )
