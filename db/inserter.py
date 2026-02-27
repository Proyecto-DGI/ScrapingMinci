"""
inserter.py
Inserta y actualiza datos en PostgreSQL usando lógica UPSERT.

UPSERT = INSERT si no existe, UPDATE si cambió, ignorar si es igual.
Esto garantiza que la BD siempre tenga la info más reciente sin duplicados.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.database import (
    GrupoInvestigacion, Investigador,
    Proyecto, ProduccionBibliografica, LogEjecucion
)

logger = logging.getLogger(__name__)


class ScienTIInserter:
    """
    Maneja la inserción y actualización de datos de ScienTI en PostgreSQL.
    Lleva conteo de registros nuevos, actualizados e ignorados.
    """

    def __init__(self, session: Session):
        self.session = session
        self.stats = {
            "nuevos": 0,
            "actualizados": 0,
            "ignorados": 0,
            "errores": 0,
        }

    # -----------------------------------------------------------------------
    # Grupos
    # -----------------------------------------------------------------------

    def upsert_grupo(self, grupo: dict) -> str:
        """
        Inserta o actualiza un grupo de investigación.
        Retorna: 'nuevo', 'actualizado', 'ignorado'
        """
        nro = grupo.get("nro_gruplac")
        if not nro:
            logger.warning("Grupo sin nro_gruplac, ignorando")
            self.stats["ignorados"] += 1
            return "ignorado"

        try:
            existente = (
                self.session.query(GrupoInvestigacion)
                .filter_by(nro_gruplac=nro)
                .first()
            )

            datos = {
                "nro_gruplac":          nro,
                "nombre_grupo":         grupo.get("nombre_grupo"),
                "clasificacion":        grupo.get("clasificacion"),
                "area_conocimiento":    grupo.get("area_conocimiento"),
                "departamento":         grupo.get("departamento"),
                "ciudad":               grupo.get("ciudad"),
                "nombre_lider":         grupo.get("nombre_lider"),
                "email_grupo":          grupo.get("email_grupo"),
                "lineas_investigacion": json.dumps(grupo.get("lineas_investigacion", []), ensure_ascii=False),
                "instituciones":        json.dumps(grupo.get("instituciones", []), ensure_ascii=False),
            }

            if not existente:
                # INSERT
                nuevo = GrupoInvestigacion(**datos)
                self.session.add(nuevo)
                self.session.flush()
                logger.info(f"  ➕ Nuevo grupo: {grupo.get('nombre_grupo')}")
                self.stats["nuevos"] += 1
                return "nuevo"

            elif self._grupo_cambio(existente, datos):
                # UPDATE
                for key, val in datos.items():
                    setattr(existente, key, val)
                existente.fecha_actualizacion = datetime.utcnow()
                self.session.flush()
                logger.info(f"  🔄 Actualizado grupo: {grupo.get('nombre_grupo')}")
                self.stats["actualizados"] += 1
                return "actualizado"

            else:
                # Sin cambios
                self.stats["ignorados"] += 1
                return "ignorado"

        except Exception as e:
            logger.error(f"Error insertando grupo {nro}: {e}")
            self.session.rollback()
            self.stats["errores"] += 1
            return "error"

    # -----------------------------------------------------------------------
    # Investigadores
    # -----------------------------------------------------------------------

    def upsert_investigador(self, inv: dict) -> str:
        """Inserta o actualiza un investigador."""
        identificacion = inv.get("identificacion")
        if not identificacion:
            self.stats["ignorados"] += 1
            return "ignorado"

        try:
            existente = (
                self.session.query(Investigador)
                .filter_by(identificacion=str(identificacion))
                .first()
            )

            datos = {
                "identificacion": str(identificacion),
                "cod_rh":         inv.get("cod_rh"),
                "nombre":         inv.get("nombre"),
                "institucion":    inv.get("institucion"),
                "categoria":      inv.get("categoria"),
                "nro_gruplac":    inv.get("nro_gruplac"),
            }

            if not existente:
                nuevo = Investigador(**datos)
                self.session.add(nuevo)
                self.session.flush()
                logger.info(f"  ➕ Nuevo investigador: {inv.get('nombre')}")
                self.stats["nuevos"] += 1
                return "nuevo"

            elif self._dict_cambio(existente, datos):
                for key, val in datos.items():
                    setattr(existente, key, val)
                existente.fecha_actualizacion = datetime.utcnow()
                self.session.flush()
                self.stats["actualizados"] += 1
                return "actualizado"

            else:
                self.stats["ignorados"] += 1
                return "ignorado"

        except Exception as e:
            logger.error(f"Error insertando investigador {identificacion}: {e}")
            self.session.rollback()
            self.stats["errores"] += 1
            return "error"

    # -----------------------------------------------------------------------
    # Proyectos
    # -----------------------------------------------------------------------

    def upsert_proyecto(self, proyecto: dict, cod_rh: str = None, nro_gruplac: str = None) -> str:
        """
        Inserta o actualiza un proyecto.
        El radicado es el campo de enlace con Banner/PURE.
        """
        radicado = proyecto.get("radicado")
        if not radicado or radicado == "No aplica":
            self.stats["ignorados"] += 1
            return "ignorado"

        try:
            existente = (
                self.session.query(Proyecto)
                .filter_by(radicado=radicado, cod_rh=cod_rh)
                .first()
            )

            datos = {
                "radicado":     radicado,
                "radicado_raw": proyecto.get("radicado_raw"),
                "titulo":       proyecto.get("titulo"),
                "anio_inicio":  proyecto.get("anio_inicio"),
                "anio_fin":     proyecto.get("anio_fin"),
                "rol":          proyecto.get("rol"),
                "estado":       proyecto.get("estado"),
                "cod_rh":       cod_rh,
                "nro_gruplac":  nro_gruplac,
            }

            if not existente:
                nuevo = Proyecto(**datos)
                self.session.add(nuevo)
                self.session.flush()
                self.stats["nuevos"] += 1
                return "nuevo"

            elif self._dict_cambio(existente, datos):
                for key, val in datos.items():
                    setattr(existente, key, val)
                existente.fecha_actualizacion = datetime.utcnow()
                self.session.flush()
                self.stats["actualizados"] += 1
                return "actualizado"

            else:
                self.stats["ignorados"] += 1
                return "ignorado"

        except Exception as e:
            logger.error(f"Error insertando proyecto {radicado}: {e}")
            self.session.rollback()
            self.stats["errores"] += 1
            return "error"

    # -----------------------------------------------------------------------
    # Producción bibliográfica
    # -----------------------------------------------------------------------

    def upsert_produccion(self, prod: dict, cod_rh: str = None) -> str:
        """Inserta o actualiza un ítem de producción bibliográfica."""
        titulo = prod.get("titulo")
        if not titulo:
            self.stats["ignorados"] += 1
            return "ignorado"

        try:
            existente = (
                self.session.query(ProduccionBibliografica)
                .filter_by(titulo=titulo, cod_rh=cod_rh, anio=prod.get("anio"))
                .first()
            )

            datos = {
                "tipo":     prod.get("tipo"),
                "titulo":   titulo,
                "autores":  prod.get("autores"),
                "anio":     prod.get("anio"),
                "detalles": prod.get("detalles"),
                "cod_rh":   cod_rh,
            }

            if not existente:
                nuevo = ProduccionBibliografica(**datos)
                self.session.add(nuevo)
                self.session.flush()
                self.stats["nuevos"] += 1
                return "nuevo"

            elif self._dict_cambio(existente, datos):
                for key, val in datos.items():
                    setattr(existente, key, val)
                existente.fecha_actualizacion = datetime.utcnow()
                self.session.flush()
                self.stats["actualizados"] += 1
                return "actualizado"

            else:
                self.stats["ignorados"] += 1
                return "ignorado"

        except Exception as e:
            logger.error(f"Error insertando producción '{titulo[:50]}': {e}")
            self.session.rollback()
            self.stats["errores"] += 1
            return "error"

    # -----------------------------------------------------------------------
    # Inserción completa de un investigador con toda su data
    # -----------------------------------------------------------------------

    def insert_full_researcher(self, mapped_data: dict, nro_gruplac: str = None):
        """
        Inserta el perfil completo de un investigador:
        datos personales + proyectos + producción bibliográfica.
        """
        cod_rh = mapped_data.get("cod_rh")

        # 1. Investigador
        mapped_data["nro_gruplac"] = nro_gruplac
        self.upsert_investigador(mapped_data)

        # 2. Proyectos
        for proyecto in mapped_data.get("proyectos", []):
            self.upsert_proyecto(proyecto, cod_rh=cod_rh, nro_gruplac=nro_gruplac)

        # 3. Producción bibliográfica
        for prod in mapped_data.get("produccion_bibliografica", []):
            self.upsert_produccion(prod, cod_rh=cod_rh)

        self.session.commit()

    # -----------------------------------------------------------------------
    # Log de ejecución
    # -----------------------------------------------------------------------

    def save_log(self, modo: str, fecha_inicio: datetime, detalle: str = ""):
        """Guarda un registro de la ejecución en la tabla de logs."""
        estado = "ERROR" if self.stats["errores"] > 0 else "OK"

        log = LogEjecucion(
            fecha_inicio=fecha_inicio,
            fecha_fin=datetime.utcnow(),
            modo=modo,
            registros_nuevos=self.stats["nuevos"],
            registros_actualizados=self.stats["actualizados"],
            errores=self.stats["errores"],
            estado=estado,
            detalle=detalle,
        )
        self.session.add(log)
        self.session.commit()

        logger.info(
            f"\n📊 Resumen ejecución:\n"
            f"   ➕ Nuevos:       {self.stats['nuevos']}\n"
            f"   🔄 Actualizados: {self.stats['actualizados']}\n"
            f"   ⏭️  Ignorados:    {self.stats['ignorados']}\n"
            f"   ❌ Errores:      {self.stats['errores']}\n"
            f"   Estado: {estado}"
        )

    # -----------------------------------------------------------------------
    # Helpers de comparación
    # -----------------------------------------------------------------------

    def _grupo_cambio(self, existente: GrupoInvestigacion, nuevos: dict) -> bool:
        campos = ["nombre_grupo", "clasificacion", "nombre_lider", "email_grupo"]
        return any(getattr(existente, c) != nuevos.get(c) for c in campos)

    def _dict_cambio(self, existente, nuevos: dict) -> bool:
        return any(
            getattr(existente, k, None) != v
            for k, v in nuevos.items()
            if k not in ("fecha_extraccion", "fecha_actualizacion")
        )
