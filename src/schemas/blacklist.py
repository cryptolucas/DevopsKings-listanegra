"""Esquemas Marshmallow para la lista negra global.

Se usan tanto para validar la entrada del POST como para serializar las
respuestas del API.
"""

import uuid

from marshmallow import EXCLUDE, Schema, ValidationError, fields, pre_load, validate

from src.extensions import ma
from src.models.blacklist import Blacklist


def validate_uuid(value: str) -> None:
    """Valida que ``value`` sea un UUID valido.

    El enunciado exige que ``app_uuid`` sea un UUID obligatorio.
    """
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValidationError("app_uuid debe ser un UUID valido.") from exc


class BlacklistCreateSchema(Schema):
    """Valida el cuerpo del POST /blacklists."""

    class Meta:
        unknown = EXCLUDE

    email = fields.Email(
        required=True,
        validate=validate.Length(
            min=3, max=254, error="El campo email debe tener entre 3 y 254 caracteres."
        ),
        error_messages={
            "required": "El campo email es obligatorio.",
            "invalid": "El campo email no tiene un formato valido.",
            "null": "El campo email no puede ser nulo.",
        },
    )
    app_uuid = fields.String(
        required=True,
        validate=validate_uuid,
        error_messages={
            "required": "El campo app_uuid es obligatorio.",
            "null": "El campo app_uuid no puede ser nulo.",
        },
    )
    blocked_reason = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(
            max=255,
            error="El campo blocked_reason admite maximo 255 caracteres.",
        ),
    )

    @pre_load
    def normalize(self, data, **kwargs):
        """Normaliza el email (minusculas / sin espacios) antes de validar."""
        if not isinstance(data, dict):
            raise ValidationError("El cuerpo de la solicitud debe ser un objeto JSON.")
        cleaned = dict(data)
        if isinstance(cleaned.get("email"), str):
            cleaned["email"] = cleaned["email"].strip().lower()
        if isinstance(cleaned.get("app_uuid"), str):
            cleaned["app_uuid"] = cleaned["app_uuid"].strip()
        reason = cleaned.get("blocked_reason")
        if isinstance(reason, str):
            reason = reason.strip()
            cleaned["blocked_reason"] = reason or None
        return cleaned


class BlacklistSchema(ma.SQLAlchemyAutoSchema):
    """Serializa un registro completo de la lista negra."""

    class Meta:
        model = Blacklist
        load_instance = False
        ordered = True

    created_at = fields.DateTime(format="iso", dump_only=True)


class BlacklistStatusSchema(Schema):
    """Respuesta del GET /blacklists/<email>."""

    class Meta:
        ordered = True

    email = fields.String(required=True)
    blacklisted = fields.Boolean(required=True)
    blocked_reason = fields.String(allow_none=True)
