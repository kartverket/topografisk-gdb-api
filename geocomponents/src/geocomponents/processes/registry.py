"""The set of processes a dataset may declare.

Maps a process id (used in ``DatasetDef.processes``) to the dotted path of its
pygeoapi processor. Values are plain strings, so this module imports no pygeoapi
and can be used by the loader for validation without pulling in the API stack.
"""

from __future__ import annotations

PROCESS_REGISTRY: dict[str, str] = {
    "hello": "geocomponents.processes.placeholder.PlaceholderProcessor",
    "export-feature": "geocomponents.processes.export_feature.ExportFeatureProcessor",
}


def known_process_ids() -> set[str]:
    """Ids a dataset may declare in ``processes``."""
    return set(PROCESS_REGISTRY)
