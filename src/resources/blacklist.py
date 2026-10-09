"""Recursos REST de la lista negra global de emails."""

import logging

from flask import request
from flask_restful import Resource
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.extensions import db
from src.models.blacklist import Blacklist
from src.schemas.blacklist import (
    BlacklistCreateSchema,
    BlacklistSchema,
    BlacklistStatusSchema,
)
from src.security import token_required
from src.utils import get_client_ip

logger = logging.getLogger(__name__)

create_schema = BlacklistCreateSchema()
blacklist_schema = BlacklistSchema()
status_schema = BlacklistStatusSchema()


class BlacklistResource(Resource):
    """``/blacklists`` - agrega un email a la lista negra global."""

    method_decorators = [token_required]

    def post(self):
        payload = request.get_json(silent=True)
        if payload is None:
            return {
                "message": "El cuerpo de la solicitud debe ser JSON valido.",
                "created": False,
            }, 400

        try:
            data = create_schema.load(payload)
        except ValidationError as err:
            return {
                "message": "Los datos enviados no son validos.",
                "created": False,
                "errors": err.messages,
            }, 400

        email = data["email"]

        existing = db.session.query(Blacklist).filter(Blacklist.email == email).first()
        if existing is not None:
            return {
                "message": f"El email {email} ya se encuentra en la lista negra global.",
                "created": False,
                "blacklist": blacklist_schema.dump(existing),
            }, 409

        record = Blacklist(
            email=email,
            app_uuid=data["app_uuid"],
            blocked_reason=data.get("blocked_reason"),
            ip_address=get_client_ip(),
        )

        try:
            db.session.add(record)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return {
                "message": f"El email {email} ya se encuentra en la lista negra global.",
                "created": False,
            }, 409
        except SQLAlchemyError:
            db.session.rollback()
            logger.exception("Error persistiendo el email en la lista negra")
            return {
                "message": "No fue posible agregar el email a la lista negra global.",
                "created": False,
            }, 500

        return {
            "message": f"El email {email} fue agregado a la lista negra global.",
            "created": True,
            "blacklist": blacklist_schema.dump(record),
        }, 201


class BlacklistEmailResource(Resource):
    """``/blacklists/<string:email>`` - consulta si un email esta bloqueado."""

    method_decorators = [token_required]

    def get(self, email: str):
        normalized = (email or "").strip().lower()
        if not normalized:
            return {"message": "Debe indicar un email en la ruta."}, 400

        record = (
            db.session.query(Blacklist).filter(Blacklist.email == normalized).first()
        )

        result = {
            "email": normalized,
            "blacklisted": record is not None,
            "blocked_reason": record.blocked_reason if record is not None else None,
        }
        return status_schema.dump(result), 200
