from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from gccore import config, db

app = FastAPI(title="gccore", version="0.1.0")


@app.get("/")
def root() -> dict[str, str]:
    return {"service": config.SERVICE_NAME, "schema": config.DB_SCHEMA}


@app.get("/healthz")
def healthz() -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "ok",
        "service": config.SERVICE_NAME,
        "schema": config.DB_SCHEMA,
    }
    try:
        payload.update(db.health_status())
    except RuntimeError as err:
        payload["status"] = "misconfigured"
        payload["detail"] = str(err)
        return JSONResponse(payload, status_code=503)
    except Exception:
        payload["status"] = "unavailable"
        return JSONResponse(payload, status_code=503)
    return payload