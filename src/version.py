"""Version desplegada del microservicio.

Unica fuente de la version. Vive en codigo (y no en una variable de entorno)
porque cambiar una environment property en Elastic Beanstalk dispara un
"configuration update" y no un "application deployment": para medir las
deployment policies hay que subir un bundle nuevo con esta constante cambiada.
"""

APP_VERSION = "1.0.0"
