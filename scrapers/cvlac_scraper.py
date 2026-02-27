"""
cvlac_scraper.py
Extrae información del CvLAC privado (autenticado) de un investigador.

Las URLs de cada sección se cargan desde urls_cvlac_reales.json (generado
por detectar_urls.py). Si el archivo no existe, usa URLs por defecto.

Si ScienTI cambia sus rutas, solo corre:
    python detectar_urls.py
y el scraper usará las nuevas URLs automáticamente.
"""

import json
import logging
import os
import re
from typing import Optional
from bs4 import BeautifulSoup
from utils.session_manager import ScienTISession

logger = logging.getLogger(__name__)

BASE_URL = "https://scienti.minciencias.gov.co"
URLS_FILE = "urls_cvlac_reales.json"

# Mapeo entre claves internas y los nombres del menú detectados por detectar_urls.py
SECTION_MAP = {
    "datos_generales":          "Datos generales",
    "proyectos":                "Proyectos",
    "produccion_bibliografica": "Producción bibliográfica",
    "productos_investigacion":  "Productos de Investigación + Creación",
    "produccion_tecnica":       "Producción técnica y tecnológica",
    "actividades_formacion":    "Actividades de formación",
    "reconocimientos":          "Reconocimientos",
    "grupos":                   "Participación en grupos de investigación",
}

# Fallback si no existe el JSON
CVLAC_SECTIONS_DEFAULT = {
    "datos_generales":          "/cvlac/EnRecursoHumano/query.do",
    "proyectos":                "/cvlac/EnProyecto/all.do",
    "produccion_bibliografica": "/cvlac/EnProduccionBiblio/all.do",
    "productos_investigacion":  "/cvlac/EnProductoInvestigacion/all.do",
    "produccion_tecnica":       "/cvlac/EnProduccionTecnica/all.do",
    "actividades_formacion":    "/cvlac/EnActividadFormacion/all.do",
    "reconocimientos":          "/cvlac/EnReconocimiento/all.do",
    "grupos":                   "/cvlac/infoScienti/grupos.do",
}


def _load_sections() -> dict:
    """
    Carga URLs desde urls_cvlac_reales.json.
    Si no existe, usa fallback y avisa al usuario.
    """
    if not os.path.exists(URLS_FILE):
        logger.warning(
            f"⚠️  No se encontró '{URLS_FILE}'. Usando URLs por defecto.\n"
            f"   Para URLs reales corre primero: python detectar_urls.py"
        )
        return {k: BASE_URL + v for k, v in CVLAC_SECTIONS_DEFAULT.items()}

    try:
        with open(URLS_FILE, "r", encoding="utf-8") as f:
            url_data = json.load(f)

        sections = {}
        for key, menu_name in SECTION_MAP.items():
            if menu_name in url_data:
                sections[key] = url_data[menu_name]
            else:
                fallback = BASE_URL + CVLAC_SECTIONS_DEFAULT.get(key, "")
                sections[key] = fallback
                logger.warning(f"  '{menu_name}' no está en el JSON, usando fallback: {fallback}")

        logger.info(f"✅ URLs cargadas desde '{URLS_FILE}' ({len(sections)} secciones)")
        return sections

    except Exception as e:
        logger.error(f"Error leyendo '{URLS_FILE}': {e}. Usando URLs por defecto.")
        return {k: BASE_URL + v for k, v in CVLAC_SECTIONS_DEFAULT.items()}


def extract_researcher_data(session: ScienTISession) -> dict:
    """
    Extrae TODA la información del CvLAC del investigador autenticado.
    """
    sections = _load_sections()

    data = {
        "datos_generales":          {},
        "proyectos":                [],
        "produccion_bibliografica": [],
        "productos_investigacion":  [],
        "produccion_tecnica":       [],
        "actividades_formacion":    [],
        "reconocimientos":          [],
        "grupos":                   [],
    }

    for section_key, url in sections.items():
        logger.info(f"Extrayendo sección: {section_key} → {url}")

        html = session.get(url)
        if not html:
            logger.warning(f"No se pudo obtener: {section_key}")
            continue

        soup = BeautifulSoup(html, "html.parser")

        if section_key == "datos_generales":
            data["datos_generales"] = _parse_datos_generales(soup)

        elif section_key == "proyectos":
            data["proyectos"] = _parse_proyectos(soup)

        elif section_key == "produccion_bibliografica":
            data["produccion_bibliografica"] = _parse_produccion_bibliografica(soup)

        elif section_key in ("productos_investigacion", "produccion_tecnica",
                             "actividades_formacion", "reconocimientos", "grupos"):
            data[section_key] = _parse_generic_section(soup, section_key)

    return data


# ---------------------------------------------------------------------------
# Parsers por sección
# ---------------------------------------------------------------------------

def _parse_datos_generales(soup: BeautifulSoup) -> dict:
    """Parsea nombre, identificación, formación, filiación institucional, etc."""
    datos = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) == 2:
                key = cells[0].get_text(strip=True)
                val = cells[1].get_text(strip=True)
                if key:
                    datos[key] = val
    return datos


def _parse_proyectos(soup: BeautifulSoup) -> list:
    """
    Parsea la lista de proyectos del investigador.
    Extrae: título, radicado, año inicio, año fin, rol, estado.
    """
    proyectos = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        header_text = " ".join(
            c.get_text(strip=True).lower()
            for c in rows[0].find_all(["th", "td"])
        )
        if not any(kw in header_text for kw in ["título", "radicado", "proyecto", "año"]):
            continue
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            proyecto = {
                "titulo":      _safe_cell(cells, 0),
                "radicado":    _safe_cell(cells, 1),
                "anio_inicio": _safe_cell(cells, 2),
                "anio_fin":    _safe_cell(cells, 3),
                "rol":         _safe_cell(cells, 4),
                "estado":      _safe_cell(cells, 5),
            }
            if proyecto["titulo"]:
                proyectos.append(proyecto)
    return proyectos


def _parse_produccion_bibliografica(soup: BeautifulSoup) -> list:
    """Parsea artículos, libros, capítulos y demás producción bibliográfica."""
    produccion = []
    current_tipo = "Sin clasificar"
    for tag in soup.find_all(["h3", "h4", "b", "strong", "tr"]):
        text = tag.get_text(strip=True)
        tipo_keywords = ["Artículos", "Libros", "Capítulos", "Tesis",
                         "Ponencias", "Trabajos", "Documentos"]
        if any(kw.lower() in text.lower() for kw in tipo_keywords) and len(text) < 80:
            current_tipo = text
            continue
        if tag.name == "tr":
            cells = tag.find_all("td")
            if len(cells) >= 2:
                item = {
                    "tipo":     current_tipo,
                    "titulo":   _safe_cell(cells, 0),
                    "autores":  _safe_cell(cells, 1),
                    "anio":     _extract_year(_safe_cell(cells, 2) or ""),
                    "detalles": _safe_cell(cells, 3),
                }
                if item["titulo"]:
                    produccion.append(item)
    return produccion


def _parse_generic_section(soup: BeautifulSoup, tipo: str) -> list:
    """Parser genérico para secciones con estructura de tabla."""
    items = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        if not any(h for h in headers if len(h) > 2):
            continue
        for row in rows[1:]:
            cells = row.find_all("td")
            if not cells:
                continue
            item = {"_tipo": tipo}
            for i, header in enumerate(headers):
                if i < len(cells) and header:
                    item[header] = cells[i].get_text(strip=True)
            if any(v for k, v in item.items() if k != "_tipo" and v):
                items.append(item)
    return items


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_cell(cells: list, index: int) -> Optional[str]:
    try:
        text = cells[index].get_text(strip=True)
        return text if text else None
    except IndexError:
        return None


def _extract_year(text: str) -> Optional[str]:
    match = re.search(r'\b(19|20)\d{2}\b', text)
    return match.group(0) if match else None