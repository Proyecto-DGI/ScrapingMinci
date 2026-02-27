"""
group_finder.py
Busca automáticamente los códigos GrupLAC (nro=XXXXXXX) a partir del
nombre de un grupo de investigación, usando la búsqueda de ScienTI.

Así no tienes que buscar manualmente los códigos en el navegador.
"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from typing import Optional

logger = logging.getLogger(__name__)

SEARCH_URL = "https://scienti.minciencias.gov.co/ciencia-war/busquedaGrupoXInstitucionGrupo.do"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Código de institución de la UPB Bucaramanga en ScienTI
# Obtenerlo entrando a la búsqueda por institución en ScienTI
UPB_COD_INST = ""  # Se intenta buscar sin filtro de institución si está vacío


def find_group_code(nombre_grupo: str, delay: float = 1.5) -> Optional[str]:
    """
    Busca el código GrupLAC (nro) de un grupo por su nombre.

    Args:
        nombre_grupo: Nombre del grupo (ej: "INTELEC")
        delay: Segundos de espera entre peticiones

    Returns:
        Código del grupo (ej: '00000000000890') o None si no se encontró
    """
    time.sleep(delay)

    # Extraer sigla o palabra clave del nombre para buscar
    # Ej: "Grupo de Investigación en Informática - INTELEC" → "INTELEC"
    keyword = _extract_keyword(nombre_grupo)
    logger.info(f"Buscando grupo: '{nombre_grupo}' → keyword: '{keyword}'")

    params = {
        "codInst":      UPB_COD_INST,
        "nombre":       keyword,
        "sglPais":      "COL",
        "maxRows":      15,
        "grupos_tr_":   "true",
        "grupos_p_":    1,
        "grupos_mr_":   15,
    }

    try:
        resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "latin-1"

        soup = BeautifulSoup(resp.text, "html.parser")
        results = _parse_search_results(soup, nombre_grupo)

        if results:
            best = results[0]
            logger.info(f"  ✅ Encontrado: '{best['nombre']}' → nro: {best['nro']}")
            return best["nro"]
        else:
            logger.warning(f"  ⚠️ No se encontró código para: '{nombre_grupo}'")
            return None

    except requests.RequestException as e:
        logger.error(f"Error buscando grupo '{nombre_grupo}': {e}")
        return None


def find_all_upb_groups(nombres_grupos: list[str], delay: float = 2.0) -> dict[str, str]:
    """
    Busca los códigos GrupLAC para una lista de nombres de grupos.

    Args:
        nombres_grupos: Lista de nombres de grupos (del Excel PURE)
        delay: Segundos entre peticiones

    Returns:
        Diccionario {nombre_grupo: nro_gruplac}
        Los grupos no encontrados tienen valor None
    """
    resultado = {}
    total = len(nombres_grupos)

    logger.info(f"Buscando códigos GrupLAC para {total} grupos...")

    for i, nombre in enumerate(nombres_grupos, 1):
        logger.info(f"[{i}/{total}] {nombre}")
        codigo = find_group_code(nombre, delay=delay)
        resultado[nombre] = codigo
        time.sleep(delay)

    encontrados = sum(1 for v in resultado.values() if v)
    logger.info(f"\nResumen búsqueda: {encontrados}/{total} grupos encontrados")

    # Mostrar los no encontrados para revisión manual
    no_encontrados = [k for k, v in resultado.items() if not v]
    if no_encontrados:
        logger.warning("Grupos no encontrados (requieren búsqueda manual):")
        for nombre in no_encontrados:
            logger.warning(f"  - {nombre}")

    return resultado


def _parse_search_results(soup: BeautifulSoup, nombre_buscado: str) -> list[dict]:
    """
    Parsea los resultados de búsqueda de GrupLAC.
    Retorna lista de {nombre, nro, url} ordenada por similitud al nombre buscado.
    """
    results = []

    # Los resultados están en links que apuntan a visualizagr.jsp
    links = soup.find_all("a", href=re.compile(r"visualizagr\.jsp\?nro="))

    for link in links:
        href = link.get("href", "")
        match = re.search(r"nro=(\d+)", href)
        if match:
            nro = match.group(1).zfill(14)
            nombre = link.get_text(strip=True)
            results.append({
                "nombre": nombre,
                "nro": nro,
                "url": href,
                "score": _similarity_score(nombre_buscado, nombre),
            })

    # Ordenar por similitud descendente
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _extract_keyword(nombre: str) -> str:
    """
    Extrae la palabra clave más útil para buscar el grupo.
    Prioriza la sigla si existe (texto entre guiones o paréntesis al final).

    Ejemplos:
        "Grupo de Investigación en Informática - INTELEC" → "INTELEC"
        "Grupo de Investigaciones Ambientales - GIA"      → "GIA"
        "Control Industrial"                               → "Control Industrial"
    """
    # Buscar sigla al final: " - SIGLA" o "(SIGLA)"
    match = re.search(r'[-–]\s*([A-Z]{2,10})\s*$', nombre.strip())
    if match:
        return match.group(1)

    match = re.search(r'\(([A-Z]{2,10})\)\s*$', nombre.strip())
    if match:
        return match.group(1)

    # Sin sigla: usar las primeras palabras significativas
    words = [w for w in nombre.split() if len(w) > 3 and w.lower() not in
             ("grupo", "investigación", "investigacion", "para", "sobre", "entre", "desarrollo")]
    return " ".join(words[:3]) if words else nombre[:30]


def _similarity_score(buscado: str, encontrado: str) -> float:
    """Score simple de similitud entre dos nombres de grupos."""
    buscado_lower = buscado.lower()
    encontrado_lower = encontrado.lower()

    # Coincidencia exacta
    if buscado_lower == encontrado_lower:
        return 1.0

    # Coincidencia por sigla
    sigla_buscado = _extract_keyword(buscado).lower()
    if sigla_buscado and sigla_buscado in encontrado_lower:
        return 0.9

    # Coincidencia parcial por palabras
    palabras_buscado = set(buscado_lower.split())
    palabras_encontrado = set(encontrado_lower.split())
    comunes = palabras_buscado & palabras_encontrado
    if palabras_buscado:
        return len(comunes) / len(palabras_buscado)

    return 0.0
