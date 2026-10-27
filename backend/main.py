"""Compatibility entry point for ``uvicorn backend.main:app``."""

from .api.app import app

__all__ = ['app']
