from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = BASE_DIR / "data" / "input"
OUTPUT_DIR = BASE_DIR / "data" / "output"

RUNTIME_MODEL_PROFILE_PATH = BASE_DIR / "configs" / "runtime" / "yolo26m_visdrone.json"

SAMPLE_IMAGE_PATH = INPUT_DIR / "sample_image.jpg"
SAMPLE_OUTPUT_PATH = OUTPUT_DIR / "sample_detected.jpg"
