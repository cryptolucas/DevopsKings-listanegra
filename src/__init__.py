"""Microservicio de lista negra global de emails.

Paquete principal de la aplicacion Flask.
"""

from src.app import create_app

__all__ = ["create_app"]
