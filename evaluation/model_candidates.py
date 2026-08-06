import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from evaluation.evaluation_config import PROJECT_CLASSES

MAXIMUM_CANDIDATES = 3
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ModelCandidateError(ValueError):
    """Raised when the predeclared model shortlist is invalid."""


@dataclass(frozen=True)
class SourceReportedMetrics:
    evaluation_partition: str
    map50: float
    map50_95: float
    precision: float
    recall: float


@dataclass(frozen=True)
class ModelCandidate:
    candidate_id: str
    name: str
    selection_role: str
    framework: str
    training_dataset: str
    repository_id: str
    repository_revision: str
    source_url: str
    weights_filename: str
    weights_url: str
    weights_sha256: str
    weights_size_bytes: int
    license_id: str
    license_url: str
    parameters_millions: float
    source_classes: tuple[str, ...]
    class_mapping: tuple[tuple[str, str], ...]
    excluded_source_classes: tuple[str, ...]
    source_reported_metrics: SourceReportedMetrics

    def map_class(self, source_class: str) -> str | None:
        return dict(self.class_mapping).get(source_class)


@dataclass(frozen=True)
class ModelCandidateSelection:
    schema_version: int
    selection_name: str
    selection_date: date
    protocol_version: str
    dataset_role: str
    maximum_candidates: int
    candidates: tuple[ModelCandidate, ...]


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelCandidateError(f"{field} must be a JSON object")
    return value


def _fields(values: dict[str, Any], field: str, required: set[str]) -> None:
    missing = required - set(values)
    unknown = set(values) - required
    if missing:
        raise ModelCandidateError(
            f"{field} is missing required fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise ModelCandidateError(
            f"{field} contains unknown fields: {', '.join(sorted(unknown))}"
        )


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelCandidateError(f"{field} must be a non-empty string")
    return value


def _integer(value: Any, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ModelCandidateError(f"{field} must be an integer >= {minimum}")
    return value


def _positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ModelCandidateError(f"{field} must be a positive number")
    return float(value)


def _probability(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelCandidateError(f"{field} must be a number between 0 and 1")
    number = float(value)
    if not 0 <= number <= 1:
        raise ModelCandidateError(f"{field} must be a number between 0 and 1")
    return number


def _url(value: Any, field: str) -> str:
    url = _string(value, field)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ModelCandidateError(f"{field} must be a valid HTTPS URL")
    return url


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ModelCandidateError(f"{field} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise ModelCandidateError(f"{field} must not contain duplicates")
    return tuple(value)


def _parse_metrics(values: dict[str, Any], field: str) -> SourceReportedMetrics:
    required = {"evaluation_partition", "map50", "map50_95", "precision", "recall"}
    _fields(values, field, required)
    return SourceReportedMetrics(
        evaluation_partition=_string(
            values["evaluation_partition"], f"{field}.evaluation_partition"
        ),
        map50=_probability(values["map50"], f"{field}.map50"),
        map50_95=_probability(values["map50_95"], f"{field}.map50_95"),
        precision=_probability(values["precision"], f"{field}.precision"),
        recall=_probability(values["recall"], f"{field}.recall"),
    )


def _parse_mapping(value: Any, field: str) -> tuple[tuple[str, str], ...]:
    values = _object(value, field)
    if not values:
        raise ModelCandidateError(f"{field} must not be empty")

    entries = []
    for source_class, project_class in values.items():
        source = _string(source_class, f"{field} source class")
        if project_class not in PROJECT_CLASSES:
            raise ModelCandidateError(
                f"{field} contains unknown project class: {project_class!r}"
            )
        entries.append((source, project_class))

    mapped_classes = {project_class for _, project_class in entries}
    missing_classes = set(PROJECT_CLASSES) - mapped_classes
    if missing_classes:
        raise ModelCandidateError(
            f"{field} does not cover project classes: "
            f"{', '.join(sorted(missing_classes))}"
        )
    return tuple(sorted(entries))


def _parse_candidate(values: dict[str, Any], index: int) -> ModelCandidate:
    field = f"candidates[{index}]"
    required = {
        "candidate_id",
        "name",
        "selection_role",
        "framework",
        "training_dataset",
        "repository_id",
        "repository_revision",
        "source_url",
        "weights_filename",
        "weights_url",
        "weights_sha256",
        "weights_size_bytes",
        "license_id",
        "license_url",
        "parameters_millions",
        "source_classes",
        "class_mapping",
        "excluded_source_classes",
        "source_reported_metrics",
    }
    _fields(values, field, required)

    candidate_id = _string(values["candidate_id"], f"{field}.candidate_id")
    if not NAME_PATTERN.fullmatch(candidate_id):
        raise ModelCandidateError(
            f"{field}.candidate_id must contain lowercase words separated by hyphens"
        )

    revision = _string(values["repository_revision"], f"{field}.repository_revision")
    if not REVISION_PATTERN.fullmatch(revision):
        raise ModelCandidateError(f"{field}.repository_revision must be a Git SHA")

    weights_sha256 = _string(values["weights_sha256"], f"{field}.weights_sha256")
    if not SHA256_PATTERN.fullmatch(weights_sha256):
        raise ModelCandidateError(f"{field}.weights_sha256 must be a SHA-256 digest")

    weights_filename = _string(values["weights_filename"], f"{field}.weights_filename")
    if Path(weights_filename).name != weights_filename:
        raise ModelCandidateError(f"{field}.weights_filename must be a file name")

    repository_id = _string(values["repository_id"], f"{field}.repository_id")
    weights_url = _url(values["weights_url"], f"{field}.weights_url")
    expected_url = (
        f"https://huggingface.co/{repository_id}/resolve/{revision}/{weights_filename}"
    )
    if weights_url != expected_url:
        raise ModelCandidateError(
            f"{field}.weights_url must pin the repository revision and file name"
        )

    mapping = _parse_mapping(values["class_mapping"], f"{field}.class_mapping")
    source_classes = _string_list(values["source_classes"], f"{field}.source_classes")
    excluded = _string_list(
        values["excluded_source_classes"], f"{field}.excluded_source_classes"
    )
    if set(excluded) & {source for source, _ in mapping}:
        raise ModelCandidateError(
            f"{field}.excluded_source_classes overlaps the class mapping"
        )
    declared_classes = {source for source, _ in mapping} | set(excluded)
    if declared_classes != set(source_classes):
        raise ModelCandidateError(
            f"{field}.source_classes must match the mapped and excluded classes"
        )

    return ModelCandidate(
        candidate_id=candidate_id,
        name=_string(values["name"], f"{field}.name"),
        selection_role=_string(values["selection_role"], f"{field}.selection_role"),
        framework=_string(values["framework"], f"{field}.framework"),
        training_dataset=_string(
            values["training_dataset"], f"{field}.training_dataset"
        ),
        repository_id=repository_id,
        repository_revision=revision,
        source_url=_url(values["source_url"], f"{field}.source_url"),
        weights_filename=weights_filename,
        weights_url=weights_url,
        weights_sha256=weights_sha256,
        weights_size_bytes=_integer(
            values["weights_size_bytes"], f"{field}.weights_size_bytes", 1
        ),
        license_id=_string(values["license_id"], f"{field}.license_id"),
        license_url=_url(values["license_url"], f"{field}.license_url"),
        parameters_millions=_positive_number(
            values["parameters_millions"], f"{field}.parameters_millions"
        ),
        source_classes=source_classes,
        class_mapping=mapping,
        excluded_source_classes=excluded,
        source_reported_metrics=_parse_metrics(
            _object(
                values["source_reported_metrics"],
                f"{field}.source_reported_metrics",
            ),
            f"{field}.source_reported_metrics",
        ),
    )


def parse_model_candidate_selection(values: dict[str, Any]) -> ModelCandidateSelection:
    required = {
        "schema_version",
        "selection_name",
        "selection_date",
        "protocol_version",
        "dataset_role",
        "maximum_candidates",
        "candidates",
    }
    _fields(values, "candidate selection", required)

    schema_version = _integer(values["schema_version"], "schema_version", 1)
    if schema_version != 1:
        raise ModelCandidateError("schema_version must be 1")

    selection_name = _string(values["selection_name"], "selection_name")
    if not NAME_PATTERN.fullmatch(selection_name):
        raise ModelCandidateError(
            "selection_name must contain lowercase words separated by hyphens"
        )

    maximum_candidates = _integer(values["maximum_candidates"], "maximum_candidates", 1)
    if maximum_candidates != MAXIMUM_CANDIDATES:
        raise ModelCandidateError(
            f"maximum_candidates must match the protocol limit of {MAXIMUM_CANDIDATES}"
        )

    raw_candidates = values["candidates"]
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ModelCandidateError("candidates must be a non-empty list")
    if len(raw_candidates) > maximum_candidates:
        raise ModelCandidateError(
            f"candidates must contain no more than {maximum_candidates} entries"
        )
    candidates = tuple(
        _parse_candidate(_object(candidate, f"candidates[{index}]"), index)
        for index, candidate in enumerate(raw_candidates)
    )
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    repository_ids = [candidate.repository_id for candidate in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ModelCandidateError("candidate_id values must be unique")
    if len(repository_ids) != len(set(repository_ids)):
        raise ModelCandidateError("repository_id values must be unique")

    dataset_role = _string(values["dataset_role"], "dataset_role")
    if dataset_role != "validation":
        raise ModelCandidateError(
            "dataset_role must be validation during model selection"
        )

    try:
        selected_on = date.fromisoformat(
            _string(values["selection_date"], "selection_date")
        )
    except ValueError as error:
        raise ModelCandidateError("selection_date must use YYYY-MM-DD") from error

    return ModelCandidateSelection(
        schema_version=schema_version,
        selection_name=selection_name,
        selection_date=selected_on,
        protocol_version=_string(values["protocol_version"], "protocol_version"),
        dataset_role=dataset_role,
        maximum_candidates=maximum_candidates,
        candidates=candidates,
    )


def load_model_candidate_selection(path: Path) -> ModelCandidateSelection:
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ModelCandidateError(f"Candidate file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ModelCandidateError(
            f"Candidate file is not valid JSON: {path}: {error.msg}"
        ) from error
    return parse_model_candidate_selection(_object(values, "candidate selection"))
