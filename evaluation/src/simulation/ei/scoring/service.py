"""Stable scoring service; implementation remains in core during rule migration."""

from simulation.ei.core.engine import (
    assemble_component_result,
    score_components,
    score_run,
)

__all__ = ["assemble_component_result", "score_components", "score_run"]
