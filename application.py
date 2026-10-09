"""Punto de entrada WSGI.

AWS Elastic Beanstalk (plataforma Python) busca por convencion un archivo
``application.py`` en la raiz del bundle y dentro de el un callable llamado
``application``. No cambie estos nombres.

Uso local:
    python application.py
"""

import os

from dotenv import load_dotenv

# Carga el .env solo cuando existe (desarrollo local).
load_dotenv()

from src.app import create_app  # noqa: E402  (debe ir despues de load_dotenv)

application = create_app()

# Alias habitual en proyectos Flask.
app = application


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("APP_ENV", "production").lower() == "development"
    application.run(host="0.0.0.0", port=port, debug=debug)
