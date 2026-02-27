"""
credentials.py
Carga segura de credenciales para ScienTI.

Orden de prioridad:
  1. Archivo .env (recomendado para desarrollo local)
  2. Variables de entorno del sistema (recomendado para producción/CI)
  3. Input interactivo como fallback (nunca guarda nada)

NUNCA hardcodear credenciales en el código.
"""

import os
import logging
from getpass import getpass
from dataclasses import dataclass
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


@dataclass
class ScienTICredentials:
    nombre: str
    identificacion: str
    contrasena: str
    nacionalidad: str = "C"


def load_credentials() -> ScienTICredentials:
    """
    Carga las credenciales de ScienTI de forma segura.

    Busca en este orden:
      1. Archivo .env en el directorio del proyecto
      2. Variables de entorno del sistema operativo
      3. Input interactivo si no se encontró nada

    Returns:
        ScienTICredentials con los datos de acceso
    """
    # Cargar .env si existe (sin sobrescribir variables del sistema)
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path, override=False)
        logger.info("Credenciales cargadas desde .env")
    else:
        logger.info("No se encontró .env — usando variables de entorno del sistema")

    nombre         = os.getenv("SCIENTI_NOMBRE")
    identificacion = os.getenv("SCIENTI_IDENTIFICACION")
    contrasena     = os.getenv("SCIENTI_CONTRASENA")
    nacionalidad   = os.getenv("SCIENTI_NACIONALIDAD", "C")

    # Fallback interactivo para lo que falte
    # getpass() no muestra lo que se escribe en consola
    if not nombre:
        nombre = input("Nombre CvLAC: ").strip()

    if not identificacion:
        identificacion = input("Documento de identificación: ").strip()

    if not contrasena:
        contrasena = getpass("Contraseña CvLAC: ")

    # Validación mínima
    if not all([nombre, identificacion, contrasena]):
        raise ValueError("Faltan credenciales. Completa el archivo .env o las variables de entorno.")

    return ScienTICredentials(
        nombre=nombre,
        identificacion=identificacion,
        contrasena=contrasena,
        nacionalidad=nacionalidad,
    )


def load_grupos() -> list[str]:
    """
    Carga la lista de códigos de grupos GrupLAC desde .env o variable de entorno.

    Returns:
        Lista de códigos de grupos
    """
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path, override=False)

    grupos_raw = os.getenv("SCIENTI_GRUPOS", "")
    if not grupos_raw:
        return []

    return [g.strip() for g in grupos_raw.split(",") if g.strip()]
