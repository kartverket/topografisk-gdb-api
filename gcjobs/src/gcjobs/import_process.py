from __future__ import annotations

from copy import deepcopy

from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

IMPORT_PROCESS_ID = "import"

PROCESS_METADATA = {
    "version": "0.1.0",
    "id": IMPORT_PROCESS_ID,
    "title": {"en": "Dataset import"},
    "description": {
        "en": "Asynchronously import a multipart upload into this dataset."
    },
    "jobControlOptions": ["async-execute"],
    "keywords": ["import", "dataset", "jobs"],
    "links": [],
    "inputs": {},
    "outputs": {
        "jobID": {
            "title": "Job ID",
            "description": "Identifier of the accepted import job.",
            "schema": {"type": "string"},
        }
    },
}


class ImportProcessProcessor(BaseProcessor):
    def __init__(self, processor_def):
        metadata = deepcopy(PROCESS_METADATA)
        dataset_title = processor_def.get("dataset_title") or "dataset"
        metadata["title"] = {"en": f"Import {dataset_title}"}
        metadata["description"] = {
            "en": f"Asynchronously import a multipart upload into the {dataset_title} dataset."
        }
        super().__init__(processor_def, metadata)

    def execute(self, data, outputs=None):
        raise ProcessorExecuteError(
            "gcjobs handles multipart import execution through the dataset-scoped execution route"
        )

    def __repr__(self):
        return "<ImportProcessProcessor>"
