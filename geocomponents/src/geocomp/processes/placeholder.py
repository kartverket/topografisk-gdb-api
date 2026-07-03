"""A trivial OGC API - Processes processor.

Its only job is to prove the Processes plumbing is live per dataset. Real
processes will be backed by generated DB functions (the same pattern as the
``geocomp.ogc_*`` dispatch layer), but this one just echoes its input so the
``/processes`` surface works end to end.
"""

from __future__ import annotations

from pygeoapi.process.base import BaseProcessor

PROCESS_METADATA = {
    "version": "0.1.0",
    "id": "hello",
    "title": {"en": "Hello"},
    "description": {"en": "Placeholder process: echoes a name back."},
    "jobControlOptions": ["sync-execute"],
    "keywords": ["example", "placeholder"],
    "links": [],
    "inputs": {
        "name": {
            "title": "Name",
            "description": "Name to echo back.",
            "schema": {"type": "string"},
            "minOccurs": 1,
            "maxOccurs": 1,
        }
    },
    "outputs": {
        "echo": {
            "title": "Echo",
            "description": "The greeting.",
            "schema": {"type": "string"},
        }
    },
    "example": {"inputs": {"name": "world"}},
}


class PlaceholderProcessor(BaseProcessor):
    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)

    def execute(self, data, outputs=None):
        name = data.get("name", "world")
        return "application/json", {"echo": f"Dataset echoes: {name}"}

    def __repr__(self):
        return "<PlaceholderProcessor>"
