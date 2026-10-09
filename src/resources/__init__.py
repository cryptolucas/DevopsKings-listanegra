"""Recursos REST (Flask-RESTful) del microservicio."""

from src.resources.auth import TokenResource
from src.resources.blacklist import BlacklistEmailResource, BlacklistResource
from src.resources.health import HealthResource, RootResource

__all__ = [
    "BlacklistResource",
    "BlacklistEmailResource",
    "HealthResource",
    "RootResource",
    "TokenResource",
]
