"""The set of processes a dataset may declare.

Maps a process id (used in ``DatasetDef.processes``) to the dotted path of its
pygeoapi processor. Values are plain strings, so this module imports no pygeoapi
and can be used by the loader for validation without pulling in the API stack.
"""

from __future__ import annotations

PROCESS_REGISTRY: dict[str, str] = {
    "hello": "geocomp.processes.placeholder.PlaceholderProcessor",
}


def known_process_ids() -> set[str]:
    return set(PROCESS_REGISTRY)
