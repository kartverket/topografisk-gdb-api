# app/exception_handlers.py
from fastapi import Request
from fastapi.responses import JSONResponse

from app.models.exceptions import FeatureNotFoundError


async def feature_not_found_handler(request: Request, exc: FeatureNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


EXCEPTION_HANDLERS = {FeatureNotFoundError: feature_not_found_handler}
