"""EI material-simulation scorers S1-S6 for validator v4.12."""

from .dispatcher import score_simulation
from .gap import _gap_s2, _gap_s3, _gap_wide_contract
from .material import _maximum_material_match

__all__ = ["score_simulation"]
