"""Public RunSelector implementation."""

from .service import SelectionError, SelectorSpec, load_selector, record_from_run, select_runs

__all__ = [
    "SelectionError", "SelectorSpec", "load_selector", "record_from_run", "select_runs"
]
