from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = BASE_DIR / "data" / "input"
OUTPUT_DIR = BASE_DIR / "data" / "output"

MODEL_PATH = BASE_DIR / "models" / "yolo26n.pt"

# Selected validation baseline from Issue #44. These are application defaults,
# not a claim that the current model has passed the quality gate.
DEFAULT_DETECTION_CONFIDENCE = 0.25
DEFAULT_INFERENCE_IMAGE_SIZE = 1280
DEFAULT_PREPROCESSING_SCALE_FACTOR = 2
DEFAULT_MAX_DETECTIONS = 300

SAMPLE_IMAGE_PATH = INPUT_DIR / "sample_image.jpg"
SAMPLE_OUTPUT_PATH = OUTPUT_DIR / "sample_detected.jpg"
