"""
database.py
Conexión y esquema de base de datos PostgreSQL para el proyecto UPB.
Crea las tablas automáticamente si no existen.
"""

import os
import logging
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, Integer, Text,
    DateTime, UniqueConstraint, text
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------

def get_engine():
    """Crea el engine de conexión a PostgreSQL desde variables de entorno."""
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        # Construir URL desde variables individuales
        host     = os.getenv("DB_HOST", "localhost")
        port     = os.getenv("DB_PORT", "5432")
        name     = os.getenv("DB_NAME", "upb_investigacion")
        user     = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{name}"

    return create_engine(db_url, echo=False)


# ---------------------------------------------------------------------------
# Modelos (tablas)
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class GrupoInvestigacion(Base):
    """Grupos de investigación extraídos de GrupLAC."""
    __tablename__ = "grupos_investigacion"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    nro_gruplac          = Column(String(20), unique=True, nullable=False)
    nombre_grupo         = Column(String(300))
    clasificacion        = Column(String(10))   # A1, A, B, C, D
    area_conocimiento    = Column(Text)
    departamento         = Column(String(100))
    ciudad               = Column(String(100))
    nombre_lider         = Column(String(200))
    email_grupo          = Column(String(200))
    lineas_investigacion = Column(Text)          # JSON string
    instituciones        = Column(Text)          # JSON string
    fuente               = Column(String(50), default="SCIENTI_GRUPLAC")
    fecha_extraccion     = Column(DateTime, default=datetime.utcnow)
    fecha_actualizacion  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("nro_gruplac", name="uq_grupo_nro"),
    )


class Investigador(Base):
    """Investigadores extraídos de CvLAC."""
    __tablename__ = "investigadores"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    cod_rh         = Column(String(20))
    nombre         = Column(String(300))
    identificacion = Column(String(20), unique=True, nullable=False)
    institucion    = Column(String(300))
    categoria      = Column(String(100))
    nro_gruplac    = Column(String(20))          # Relación con grupo
    fuente         = Column(String(50), default="SCIENTI_CVLAC")
    fecha_extraccion    = Column(DateTime, default=datetime.utcnow)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Proyecto(Base):
    """Proyectos de investigación — campo de enlace con Banner/PURE."""
    __tablename__ = "proyectos"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    radicado     = Column(String(50))            # Campo de enlace con Banner/PURE
    radicado_raw = Column(String(100))           # Valor original sin normalizar
    titulo       = Column(Text)
    anio_inicio  = Column(Integer)
    anio_fin     = Column(Integer)
    rol          = Column(String(100))
    estado       = Column(String(100))
    cod_rh       = Column(String(20))            # Investigador dueño
    nro_gruplac  = Column(String(20))            # Grupo al que pertenece
    fuente       = Column(String(50), default="SCIENTI_CVLAC")
    fecha_extraccion    = Column(DateTime, default=datetime.utcnow)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("radicado", "cod_rh", name="uq_proyecto_radicado_investigador"),
    )


class ProduccionBibliografica(Base):
    """Producción bibliográfica extraída de CvLAC."""
    __tablename__ = "produccion_bibliografica"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    tipo     = Column(String(100))
    titulo   = Column(Text)
    autores  = Column(Text)
    anio     = Column(Integer)
    detalles = Column(Text)
    cod_rh   = Column(String(20))
    fuente   = Column(String(50), default="SCIENTI_CVLAC")
    fecha_extraccion    = Column(DateTime, default=datetime.utcnow)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("titulo", "cod_rh", "anio", name="uq_produccion_titulo_autor_anio"),
    )


class LogEjecucion(Base):
    """
    Registro de cada ejecución del scraper.
    Permite auditar qué cambió en cada corrida.
    """
    __tablename__ = "log_ejecuciones"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    fecha_inicio     = Column(DateTime, default=datetime.utcnow)
    fecha_fin        = Column(DateTime)
    modo             = Column(String(20))        # gruplac, cvlac, both
    grupos_procesados = Column(Integer, default=0)
    registros_nuevos  = Column(Integer, default=0)
    registros_actualizados = Column(Integer, default=0)
    errores          = Column(Integer, default=0)
    estado           = Column(String(20))        # OK, ERROR, PARCIAL
    detalle          = Column(Text)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def init_db():
    """Crea todas las tablas si no existen."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("✅ Base de datos inicializada correctamente")
    return engine


def get_session(engine=None):
    """Retorna una sesión de SQLAlchemy."""
    if engine is None:
        engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()
