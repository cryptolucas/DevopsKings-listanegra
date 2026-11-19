"""Recursos REST (Flask-RESTful) del microservicio."""

from src.resources.auth import TokenResource
from src.resources.blacklist import BlacklistEmailResource, BlacklistResource
from src.resources.debug import DebugErrorResource, DebugSlowDbResource, DebugSlowResource
from src.resources.health import HealthResource, RootResource

__all__ = [
    "BlacklistResource",
    "BlacklistEmailResource",
    "DebugErrorResource",
    "DebugSlowDbResource",
    "DebugSlowResource",
    "HealthResource",
    "RootResource",
    "TokenResource",
]
