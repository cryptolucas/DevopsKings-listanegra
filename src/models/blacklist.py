"""Modelo de la lista negra global de emails."""

from datetime import datetime, timezone

from src.extensions import db


def _utcnow() -> datetime:
    """Fecha/hora actual en UTC (naive, para almacenar en TIMESTAMP)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Blacklist(db.Model):
    """Registro de un email agregado a la lista negra global.

    Campos solicitados por el enunciado:
      * ``email``           email del cliente a bloquear (obligatorio).
      * ``app_uuid``        UUID de la app cliente que solicita el bloqueo
                            (obligatorio).
      * ``blocked_reason``  motivo del bloqueo (opcional, maximo 255 chars).

    Campos que el microservicio registra internamente:
      * ``ip_address``      IP desde donde se hizo la solicitud.
      * ``created_at``      fecha/hora (UTC) en la que se realizo la solicitud.
    """

    __tablename__ = "blacklist"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(254), nullable=False, index=True)
    app_uuid = db.Column(db.String(36), nullable=False, index=True)
    blocked_reason = db.Column(db.String(255), nullable=True)

    # Registrados internamente por el microservicio.
    # 45 caracteres para soportar tambien direcciones IPv6.
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        # Un mismo email no se agrega dos veces a la lista negra global.
        db.UniqueConstraint("email", name="uq_blacklist_email"),
    )

    def __repr__(self) -> str:  # pragma: no cover - utilidad de depuracion
        return f"<Blacklist {self.email}>"
