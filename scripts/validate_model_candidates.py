import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.model_candidates import load_model_candidate_selection


def main() -> None:
    path = Path("configs/evaluation/aerial_model_candidates.json")
    selection = load_model_candidate_selection(path)

    print(f"Candidate selection: {selection.selection_name}")
    print(f"Dataset role: {selection.dataset_role}")
    print(f"Selected candidates: {len(selection.candidates)}")
    for candidate in selection.candidates:
        print(
            f"- {candidate.candidate_id}: {candidate.repository_id} "
            f"@ {candidate.repository_revision}"
        )
    print("Candidate configuration validation: PASS")


if __name__ == "__main__":
    main()
