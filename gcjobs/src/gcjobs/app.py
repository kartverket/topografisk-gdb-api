from __future__ import annotations

import httpx2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gcjobs import config, routing, service, storage
from gcjobs.datasets import DescriptionError, load_dataset_descriptions
from gcjobs.pubsub import ImportEventListener

db = storage.db
_declared_content_length = service._declared_content_length


def create_app(
    *,
    event_listener: ImportEventListener | None = None,
    import_client: httpx2.AsyncClient | None = None,
) -> FastAPI:
    try:
        datasets = load_dataset_descriptions(
            config.descriptions_dir(),
            supported_import_profiles=config.SUPPORTED_IMPORT_PROFILES,
        )
    except DescriptionError as err:
        raise RuntimeError(f"invalid shared descriptions for gcjobs: {err}") from err

    application = FastAPI(
        title="gcjobs",
        version="0.1.0",
        lifespan=service.build_lifespan(
            event_listener=event_listener,
            import_client=import_client,
        ),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.state.proxy_tasks = set()

    mounts: list[routing.DatasetMount] = []
    for dataset in datasets:
        path = routing.mount_path(dataset.name)
        api_url = f"{config.api_base_url()}{path}"
        application.mount(
            path,
            routing.build_dataset_app(
                application,
                dataset,
                api_url,
                queue_import_request=service.queue_import_request,
            ),
        )
        mounts.append(routing.DatasetMount(dataset, path, api_url))

    routing.register_routes(application, mounts)

    return application


app = create_app()
