"""
gruplac_scraper.py
Extrae información pública de páginas GrupLAC de MinCiencias.
No requiere autenticación.
"""

import requests
import logging
import time
import re
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_GRUPLAC_URL = "https://scienti.minciencias.gov.co/gruplac/jsp/visualiza/visualizagr.jsp"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def get_group_page(nro_grupo: str, delay: float = 1.0) -> Optional[BeautifulSoup]:
    """
    Obtiene y parsea la página pública de un grupo GrupLAC.

    Args:
        nro_grupo: Código numérico del grupo (ej: '00000000000890')
        delay: Segundos de espera antes de la petición (rate limiting)

    Returns:
        BeautifulSoup parseado o None si falló
    """
    time.sleep(delay)
    url = BASE_GRUPLAC_URL
    params = {"nro": nro_grupo.zfill(14)}  # Asegura 14 dígitos con ceros a la izquierda

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        # ScienTI usa Latin-1 / ISO-8859-1 en muchas páginas
        resp.encoding = resp.apparent_encoding or "latin-1"
        return BeautifulSoup(resp.text, "html.parser")

    except requests.RequestException as e:
        logger.error(f"Error al obtener GrupLAC {nro_grupo}: {e}")
        return None


def extract_group_data(nro_grupo: str) -> Optional[dict]:
    """
    Extrae toda la información disponible de un grupo GrupLAC.

    Args:
        nro_grupo: Código del grupo

    Returns:
        Diccionario con los datos del grupo o None si falló
    """
    soup = get_group_page(nro_grupo)
    if not soup:
        return None

    data = {
        "nro_grupo": nro_grupo,
        "nombre": None,
        "datos_basicos": {},
        "instituciones": [],
        "lineas_investigacion": [],
        "integrantes": [],
        "productos": {
            "articulos": [],
            "libros": [],
            "capitulos": [],
            "proyectos": [],
            "otros": [],
        },
    }

    # --- Nombre del grupo (título de la página) ---
    titulo = soup.find("div", id="titulo") or soup.find("h1") or soup.find("b")
    if titulo:
        data["nombre"] = titulo.get_text(strip=True)
    else:
        # Alternativa: buscar en el primer <b> o <strong> de la página
        first_bold = soup.find("b")
        if first_bold:
            data["nombre"] = first_bold.get_text(strip=True)

    # --- Todas las tablas de la página ---
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        # Detectar tabla de "Datos básicos" por encabezado
        header_text = table.get_text(" ", strip=True).lower()

        # Tabla de datos básicos (2 columnas: label | valor)
        if any(kw in header_text for kw in ["año y mes", "lider", "clasificación", "área de conocimiento"]):
            for row in rows:
                cells = row.find_all("td")
                if len(cells) == 2:
                    key = cells[0].get_text(strip=True)
                    val = cells[1].get_text(strip=True)
                    if key:
                        data["datos_basicos"][key] = val

        # Tabla de integrantes
        elif "integrantes del grupo" in header_text or ("nombre" in header_text and "vinculación" in header_text):
            for row in rows[1:]:  # Skip header row
                cells = row.find_all("td")
                if len(cells) >= 2:
                    link = cells[0].find("a")
                    integrante = {
                        "nombre": cells[0].get_text(strip=True),
                        "cvlac_url": link["href"] if link and link.get("href") else None,
                        "cod_rh": _extract_cod_rh(link["href"]) if link and link.get("href") else None,
                        "vinculacion": cells[1].get_text(strip=True) if len(cells) > 1 else None,
                        "horas_dedicacion": cells[2].get_text(strip=True) if len(cells) > 2 else None,
                    }
                    if integrante["nombre"]:
                        data["integrantes"].append(integrante)

        # Tabla de instituciones
        elif "instituciones" in header_text:
            for row in rows:
                text = row.get_text(strip=True)
                if text and text not in ["Instituciones", ""]:
                    data["instituciones"].append(text)

    # --- Líneas de investigación (lista de ítems) ---
    # Buscar sección por texto
    lineas_section = _find_section_by_title(soup, "líneas de investigación")
    if lineas_section:
        items = lineas_section.find_all("li") or lineas_section.find_next("ul")
        if items:
            for item in (items if isinstance(items, list) else items.find_all("li")):
                text = item.get_text(strip=True)
                if text:
                    data["lineas_investigacion"].append(text)
        else:
            # A veces están como texto numerado (1.- CiberSeguridad)
            text_block = lineas_section.get_text("\n", strip=True)
            lineas = re.findall(r'\d+\.-\s*(.+)', text_block)
            data["lineas_investigacion"] = lineas

    logger.info(
        f"Grupo {nro_grupo} extraído: {len(data['integrantes'])} integrantes, "
        f"{len(data['lineas_investigacion'])} líneas"
    )
    return data


def _find_section_by_title(soup: BeautifulSoup, title_keyword: str) -> Optional[BeautifulSoup]:
    """Busca una sección en la página por palabra clave en el título."""
    for tag in soup.find_all(["h2", "h3", "h4", "b", "strong", "td"]):
        if title_keyword.lower() in tag.get_text(strip=True).lower():
            # Retorna el contenedor padre o el siguiente elemento
            parent = tag.find_parent("table") or tag.find_parent("div")
            return parent or tag
    return None


def _extract_cod_rh(url: str) -> Optional[str]:
    """Extrae el cod_rh de una URL de CvLAC."""
    if not url:
        return None
    match = re.search(r'cod_rh=(\d+)', url)
    return match.group(1) if match else None


def scrape_multiple_groups(nro_list: list, delay: float = 2.0) -> list[dict]:
    """
    Extrae datos de múltiples grupos con rate limiting.

    Args:
        nro_list: Lista de códigos de grupos
        delay: Segundos entre peticiones

    Returns:
        Lista de diccionarios con datos de cada grupo
    """
    results = []
    total = len(nro_list)

    for i, nro in enumerate(nro_list, 1):
        logger.info(f"Procesando grupo {i}/{total}: {nro}")
        data = extract_group_data(nro)
        if data:
            results.append(data)
        else:
            logger.warning(f"No se pudo extraer datos del grupo: {nro}")

        time.sleep(delay)  # Rate limiting entre grupos

    logger.info(f"Scraping completado: {len(results)}/{total} grupos extraídos exitosamente")
    return results
