"""
scienti_mapper.py
Normaliza los datos extraídos de ScienTI al esquema interno del proyecto UPB.
Este mapper conecta la Fase 3 con la DB existente de las fases 1 y 2.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mapeo de campos: ScienTI → Schema interno UPB
# ---------------------------------------------------------------------------

# Mapeo de claves de datos básicos de GrupLAC a nombres normalizados
GRUPLAC_FIELD_MAP = {
    "Año y mes de formación":                    "anio_formacion",
    "Departamento - Ciudad":                     "departamento_ciudad",
    "Líder":                                     "lider",
    "Clasificación":                             "clasificacion_minciencias",
    "Área de conocimiento":                      "area_conocimiento",
    "Programa nacional de ciencia y tecnología": "programa_nacional_cyt",
    "E-mail":                                    "email",
    "Página web":                                "pagina_web",
}

# Mapeo de categorías de MinCiencias a categorías internas UPB
CLASIFICACION_MAP = {
    "A1": "A1",
    "A":  "A",
    "B":  "B",
    "C":  "C",
    "D":  "D",
    "Reconocido": "Reconocido",
}

# Tipos de producción bibliográfica normalizados
TIPO_PRODUCCION_MAP = {
    "artículo": "ARTICULO",
    "libro": "LIBRO",
    "capítulo": "CAPITULO_LIBRO",
    "tesis": "TESIS",
    "ponencia": "PONENCIA",
    "trabajo": "TRABAJO",
    "documento": "DOCUMENTO",
}


def map_group(raw_group: dict) -> dict:
    """
    Normaliza los datos crudos de un grupo GrupLAC al schema interno.

    Args:
        raw_group: Diccionario salida de gruplac_scraper.extract_group_data()

    Returns:
        Diccionario normalizado listo para insertar en DB
    """
    datos = raw_group.get("datos_basicos", {})

    grupo = {
        # Identificadores
        "nro_gruplac":           raw_group.get("nro_grupo"),
        "nombre_grupo":          _clean_text(raw_group.get("nombre")),

        # Datos básicos normalizados
        "anio_formacion":        _map_field(datos, "Año y mes de formación"),
        "departamento":          _parse_departamento(datos.get("Departamento - Ciudad", "")),
        "ciudad":                _parse_ciudad(datos.get("Departamento - Ciudad", "")),
        "nombre_lider":          _clean_text(_map_field(datos, "Líder")),
        "clasificacion":         _normalize_clasificacion(_map_field(datos, "Clasificación")),
        "area_conocimiento":     _clean_text(_map_field(datos, "Área de conocimiento")),
        "programa_nacional_cyt": _clean_text(_map_field(datos, "Programa nacional de ciencia y tecnología")),
        "email_grupo":           _map_field(datos, "E-mail"),
        "pagina_web":            _map_field(datos, "Página web"),

        # Listas
        "instituciones":         raw_group.get("instituciones", []),
        "lineas_investigacion":  raw_group.get("lineas_investigacion", []),

        # Integrantes mapeados
        "integrantes":           [map_integrante(m) for m in raw_group.get("integrantes", [])],

        # Fuente para trazabilidad
        "_fuente": "SCIENTI_GRUPLAC",
    }

    return grupo


def map_integrante(raw: dict) -> dict:
    """Normaliza un integrante del grupo."""
    return {
        "nombre":          _clean_text(raw.get("nombre")),
        "cod_rh":          raw.get("cod_rh"),
        "cvlac_url":       raw.get("cvlac_url"),
        "vinculacion":     raw.get("vinculacion"),
        "horas_dedicacion": _safe_int(raw.get("horas_dedicacion")),
        "_fuente":         "SCIENTI_GRUPLAC",
    }


def map_researcher(raw_cvlac: dict, cod_rh: str = None) -> dict:
    """
    Normaliza datos crudos del CvLAC autenticado al schema interno.

    Args:
        raw_cvlac: Diccionario salida de cvlac_scraper.extract_researcher_data()
        cod_rh: Código del investigador en ScienTI

    Returns:
        Diccionario normalizado
    """
    datos_generales = raw_cvlac.get("datos_generales", {})

    investigador = {
        "cod_rh":           cod_rh,
        "nombre":           _clean_text(datos_generales.get("Nombre") or datos_generales.get("nombre")),
        "identificacion":   datos_generales.get("Identificación") or datos_generales.get("identificacion"),
        "institucion":      datos_generales.get("Institución") or datos_generales.get("institucion"),
        "categoria":        datos_generales.get("Categoría") or datos_generales.get("categoria"),

        # Producción
        "proyectos":                [map_proyecto(p) for p in raw_cvlac.get("proyectos", [])],
        "produccion_bibliografica": [map_produccion(p) for p in raw_cvlac.get("produccion_bibliografica", [])],
        "productos_investigacion":  raw_cvlac.get("productos_investigacion", []),
        "produccion_tecnica":       raw_cvlac.get("produccion_tecnica", []),

        "_fuente": "SCIENTI_CVLAC",
    }

    return investigador


def map_proyecto(raw: dict) -> dict:
    """
    Normaliza un proyecto del CvLAC.
    El campo 'radicado' es el campo de enlace con la DB interna (Banner/PURE).
    """
    radicado_raw = raw.get("radicado", "")

    return {
        "titulo":         _clean_text(raw.get("titulo")),
        "radicado":       _normalize_radicado(radicado_raw),  # Campo de enlace principal
        "radicado_raw":   radicado_raw,                        # Valor original para auditoría
        "anio_inicio":    _safe_int(raw.get("anio_inicio")),
        "anio_fin":       _safe_int(raw.get("anio_fin")),
        "rol":            raw.get("rol"),
        "estado":         raw.get("estado"),
        "_fuente":        "SCIENTI_CVLAC",
    }


def map_produccion(raw: dict) -> dict:
    """Normaliza un ítem de producción bibliográfica."""
    return {
        "tipo":    _normalize_tipo_produccion(raw.get("tipo", "")),
        "titulo":  _clean_text(raw.get("titulo")),
        "autores": raw.get("autores"),
        "anio":    raw.get("anio"),
        "detalles": raw.get("detalles"),
        "_fuente": "SCIENTI_CVLAC",
    }


# ---------------------------------------------------------------------------
# Helpers de normalización
# ---------------------------------------------------------------------------

def _normalize_radicado(raw: str) -> Optional[str]:
    """
    Normaliza el radicado para que sea comparable con Banner y PURE.
    Elimina espacios, guiones extra y estandariza formato.
    Ejemplo: "PI2023-001" → "PI2023001"
    """
    if not raw:
        return None
    # Eliminar espacios y convertir a mayúsculas
    cleaned = raw.strip().upper()
    # Eliminar guiones para comparación (ajustar según tu estándar)
    # cleaned = re.sub(r'[-\s]', '', cleaned)
    return cleaned


def _normalize_clasificacion(raw: Optional[str]) -> Optional[str]:
    """Extrae la categoría de clasificación (A1, A, B, C, D) del texto."""
    if not raw:
        return None
    # Buscar patrón de clasificación al inicio del texto
    match = re.match(r'^(A1|A|B|C|D|Reconocido)', raw.strip())
    return match.group(1) if match else raw[:10]


def _normalize_tipo_produccion(tipo: str) -> str:
    """Normaliza el tipo de producción bibliográfica."""
    tipo_lower = tipo.lower()
    for keyword, normalized in TIPO_PRODUCCION_MAP.items():
        if keyword in tipo_lower:
            return normalized
    return tipo.upper().replace(" ", "_")[:50]


def _map_field(datos: dict, original_key: str) -> Optional[str]:
    """Busca un campo en el diccionario con tolerancia a variaciones de nombre."""
    # Búsqueda exacta
    if original_key in datos:
        return datos[original_key]
    # Búsqueda case-insensitive
    for key, val in datos.items():
        if key.strip().lower() == original_key.lower():
            return val
    return None


def _parse_departamento(dep_ciudad: str) -> Optional[str]:
    """Extrae el departamento de 'DEPARTAMENTO - CIUDAD'."""
    if " - " in dep_ciudad:
        return dep_ciudad.split(" - ")[0].strip().title()
    return dep_ciudad.strip().title() or None


def _parse_ciudad(dep_ciudad: str) -> Optional[str]:
    """Extrae la ciudad de 'DEPARTAMENTO - CIUDAD'."""
    if " - " in dep_ciudad:
        return dep_ciudad.split(" - ")[1].strip().title()
    return None


def _clean_text(text: Optional[str]) -> Optional[str]:
    """Limpia texto: strip, colapsa espacios múltiples."""
    if not text:
        return None
    return re.sub(r'\s+', ' ', text.strip())


def _safe_int(val: Optional[str]) -> Optional[int]:
    """Convierte a int de forma segura."""
    if val is None:
        return None
    try:
        digits = re.sub(r'\D', '', str(val))
        return int(digits) if digits else None
    except (ValueError, TypeError):
        return None
