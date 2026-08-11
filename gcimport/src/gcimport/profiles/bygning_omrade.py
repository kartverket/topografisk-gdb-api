"""Backward-compatible exports for bygning area source objtypes."""

from gcimport.profiles.bygning import (
    _AREA_SOURCE_OBJTYPES as _SOURCE_OBJTYPES,
)
from gcimport.profiles.bygning import BYGNING_PROFILE as BYGNING_OMRADE_PROFILE

__all__ = ["BYGNING_OMRADE_PROFILE", "_SOURCE_OBJTYPES"]
