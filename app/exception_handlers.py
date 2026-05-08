# app/exception_handlers.py
from fastapi import Request
from fastapi.responses import JSONResponse

from app.models.exceptions import FeatureNotFoundError, InvalidBoundingBoxError


async def feature_not_found_handler(request: Request, exc: FeatureNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def bad_request_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


EXCEPTION_HANDLERS = {
    FeatureNotFoundError: feature_not_found_handler,
    InvalidBoundingBoxError: bad_request_handler,
}
