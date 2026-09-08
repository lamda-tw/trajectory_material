"""EI scoring orchestration and release contracts."""

from .contracts import artifact_roles_for_checks, validate_release_contracts
from .service import assemble_component_result, score_components, score_run

__all__ = [
    "artifact_roles_for_checks",
    "assemble_component_result",
    "score_components",
    "score_run",
    "validate_release_contracts",
]
