"""Built-in dataset import profiles."""

from collections.abc import Mapping
from types import MappingProxyType

from gcimport.profiles.bane import BANE_PROFILE
from gcimport.profiles.base import ImportProfile
from gcimport.profiles.bygning import BYGNING_PROFILE

BUILTIN_PROFILES: Mapping[str, ImportProfile] = MappingProxyType(
    {
        profile.name: profile
        for profile in (
            BANE_PROFILE,
            BYGNING_PROFILE,
        )
    }
)


def get_profile(name: str) -> ImportProfile:
    profile = BUILTIN_PROFILES.get(name.casefold())
    if profile is None:
        supported = ", ".join(sorted(BUILTIN_PROFILES))
        raise ValueError(f"unknown profile '{name}'; expected one of: {supported}")
    return profile


__all__ = [
    "BANE_PROFILE",
    "BUILTIN_PROFILES",
    "BYGNING_PROFILE",
    "ImportProfile",
    "get_profile",
]
