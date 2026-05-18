import os

os.environ.setdefault("PYGEOAPI_CONFIG", "ar5.yaml")
os.environ.setdefault("PYGEOAPI_OPENAPI", "openapi.ar5.yaml")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pygeoapi.starlette_app import APP as ar5_pygeoapi_app

app = FastAPI(title="Topografisk GDB API")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_headers=["*"], allow_methods=["*"]
)

app.mount("/ar5", ar5_pygeoapi_app)
