"""The set of processes a dataset may declare.

Maps a process id (used in ``DatasetDef.processes``) to the dotted path of its
pygeoapi processor. Values are plain strings, so this module imports no pygeoapi
and can be used by the loader for validation without pulling in the API stack.

Note that external processes (like ``import``) are not implemented in geocomponents, but are
declared here so that datasets can declare them in ``processes`` and the API can expose
their metadata. The API will route execution of these processes to the appropriate external service (gcjobs) instead of trying to execute them in geocomponents.
This is an ad hoc implementation for POC purposes, and may be replaced by a more general solution in the future.

"""

from __future__ import annotations

PROCESS_REGISTRY: dict[str, str] = {
    "hello": "geocomponents.processes.placeholder.PlaceholderProcessor",
    "upsert-batch": "geocomponents.processes.upsert_batch.UpsertBatchProcessor",
    "transaction-batch-upsert": "geocomponents.processes.transaction_batch_upsert.TransactionBatchUpsertProcessor",
    "import": "geocomponents.processes.external.import_process.ImportProcessor",
}


def known_process_ids() -> set[str]:
    """Ids a dataset may declare in ``processes``."""
    return set(PROCESS_REGISTRY)
