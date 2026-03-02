"""
scienti_upb_crawler.py
Crawler que busca todos los grupos de la UPB Bucaramanga en ScienTI/MinCiencias
y descarga cada GrupLAC individual usando gruplac_scraper.py.

Uso:
  python -m scrapers.scienti_upb_crawler --only-list
  python -m scrapers.scienti_upb_crawler --scrape-all
  python -m scrapers.scienti_upb_crawler --scrape-all --delay-min 3.0 --delay-max 6.0
  python -m scrapers.scienti_upb_crawler --only-list --ciudad MEDELLIN --departamento ANTIOQUIA
"""

import argparse
import json
import logging
import math
import os
import re
import sys
import time
import random
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Path setup: permite importar gruplac_scraper desde cualquier directorio
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent   # scrapers/
_ROOT = _HERE.parent                       # raiz del proyecto
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scrapers.gruplac_scraper import extract_group_data  # noqa: E402

# ---------------------------------------------------------------------------
# Logging: consola UTF-8 + archivo crawler.log
# ---------------------------------------------------------------------------
_LOG_FILE = _ROOT / "crawler.log"

_stream_handler = logging.StreamHandler(
    stream=open(sys.stdout.fileno(), mode="w", encoding="utf-8",
                buffering=1, closefd=False)
)
_stream_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)

_file_handler = logging.FileHandler(str(_LOG_FILE), encoding="utf-8")
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)

logging.root.setLevel(logging.INFO)
logging.root.addHandler(_stream_handler)
logging.root.addHandler(_file_handler)

logger = logging.getLogger("scienti_upb_crawler")

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
_BASE = "https://scienti.minciencias.gov.co/ciencia-war"

# GET inicial: inicializa la sesion Struts y muestra el formulario vacio
INIT_URL = f"{_BASE}/busquedaAvanzadaGrupos.do?buscar=sinBuscar"

# POST de busqueda con resultados
SEARCH_URL = f"{_BASE}/busquedaAvanzadaGrupos.do?buscar=buscar"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.7",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://scienti.minciencias.gov.co",
    "Referer": INIT_URL,
}

# Valores por defecto para UPB Bucaramanga
DEFAULT_INSTITUTION = "UNIVERSIDAD PONTIFICIA BOLIVARIANA"
DEFAULT_CITY        = "BUCARAMANGA"
DEFAULT_DEPARTMENT  = "SANTANDER"
DEFAULT_COUNTRY     = "COL"
DEFAULT_MAX_ROWS    = 50   # 15 | 50 | 100


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def cod_to_nro(cod_grupo: str) -> str:
    """
    Convierte COL0027699 a 00000000027699 (14 digitos con ceros a la izquierda).
    Acepta COL..., solo digitos, o cualquier mezcla.
    """
    digits = re.sub(r'^[A-Za-z]+', '', cod_grupo)
    return digits.zfill(14)


def build_gruplac_url(nro: str) -> str:
    """URL publica de GrupLAC para el nro de 14 digitos."""
    return (
        "https://scienti.minciencias.gov.co/gruplac/jsp/visualiza/"
        f"visualizagr.jsp?nro={nro}"
    )


def _random_delay(min_s: float = 2.0, max_s: float = 4.5) -> None:
    """Pausa aleatoria para respetar el rate limiting del servidor."""
    delay = random.uniform(min_s, max_s)
    logger.debug(f"Esperando {delay:.2f}s...")
    time.sleep(delay)


# ---------------------------------------------------------------------------
# Payload de busqueda
# ---------------------------------------------------------------------------

def _build_payload(page: int, max_rows: int,
                   institution: str, city: str,
                   department: str, country: str) -> dict:
    """
    Parametros completos del formulario de busqueda de ScienTI.
    Usados tanto para el GET inicial como para los GET de paginacion.

    La pagina usa un <form> sin atributo method (defaultea a GET) y
    onInvokeAction() envia TODOS los campos con el numero de pagina actualizado.
    Si falta cualquier campo de filtro el servidor ignora la paginacion.
    """
    return {
        "codIdGrupo":      "",
        "nmeGrupo":        "",
        "nmeLider":        "",
        "areaConocimiento": "",
        "annoCreacion":    "",
        "nmeInstitucion":  institution,
        "ciuInst":         city,
        "depInst":         department,
        "integrantes":     "",
        "proyectos":       "",
        "productos":       "",
        "genLider":        "",
        "status":          "",
        "progNacional":    "",
        "progNacionalSec": "",
        "filtrar":         "",
        "buscar":          "buscar",
        "grupos_tr_":      "true",
        "grupos_p_":       str(page),
        "grupos_mr_":      str(max_rows),
    }


# ---------------------------------------------------------------------------
# Parseo de la tabla de resultados
# ---------------------------------------------------------------------------

def _parse_grupos_table(soup: BeautifulSoup) -> list[dict]:
    """
    Extrae grupos de la tabla de ScienTI.

    Estructura real del HTML: una sola <tr> con TODAS las celdas aplanadas.
    Cada grupo ocupa 8 celdas consecutivas tras el encabezado:
      [0] numero de fila  [1] cod_grupo (COLxxxx)  [2] nombre  [3] lider
      [4] "Ver Perfiles"  [5] avalado   [6] estado  [7] clasificacion
    """
    grupos = []

    target_table = None
    for table in soup.find_all("table"):
        if "Cod grupo" in table.get_text():
            target_table = table
            break

    if not target_table:
        logger.debug("No se encontro la tabla de resultados en la pagina.")
        return grupos

    all_cells = target_table.find_all("td")
    texts = [c.get_text(strip=True) for c in all_cells]

    try:
        header_idx = texts.index("Cod grupo")
    except ValueError:
        logger.warning("No se encontro cabecera 'Cod grupo' en la tabla.")
        return grupos

    data_start = header_idx + 7   # 7 columnas de encabezado
    data_cells = all_cells[data_start:]
    data_texts = texts[data_start:]

    i = 0
    while i < len(data_texts) - 7:
        first  = data_texts[i]
        second = data_texts[i + 1] if i + 1 < len(data_texts) else ""

        if first.isdigit() and re.match(r'^COL\d+$', second):
            cod_grupo = second
            nro       = cod_to_nro(cod_grupo)
            nombre    = data_texts[i + 2] if i + 2 < len(data_texts) else None
            lider     = data_texts[i + 3] if i + 3 < len(data_texts) else None
            # [i+4] = "Ver Perfiles" (se ignora)
            avalado   = data_texts[i + 5] if i + 5 < len(data_texts) else None
            estado    = data_texts[i + 6] if i + 6 < len(data_texts) else None
            clasif    = data_texts[i + 7] if i + 7 < len(data_texts) else None

            # Refinar nro desde el href del link si esta disponible
            cod_cell = data_cells[i + 1] if i + 1 < len(data_cells) else None
            if cod_cell:
                lnk = cod_cell.find("a", href=re.compile(r"visualizagr\.jsp"))
                if lnk:
                    m = re.search(r"nro=(\d+)", lnk["href"])
                    if m:
                        nro = m.group(1).zfill(14)

            grupos.append({
                "cod_grupo":     cod_grupo,
                "nro":           nro,
                "nombre":        nombre,
                "lider":         lider,
                "avalado_por":   avalado,
                "estado":        estado,
                "clasificacion": clasif,
                "gruplac_url":   build_gruplac_url(nro) if nro else None,
            })
            i += 8
        else:
            i += 1

    return grupos


def _parse_total_groups(soup: BeautifulSoup) -> Optional[int]:
    """
    Extrae el total de grupos del pie de tabla.
    ScienTI muestra: "Resultados 1 - 50 de 267."
    """
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Resultados\s+\d+\s*-\s*\d+\s+de\s+(\d+)", text)
    if m:
        return int(m.group(1))
    m2 = re.search(r"de\s+(\d{2,})", text)
    if m2:
        return int(m2.group(1))
    return None


# ---------------------------------------------------------------------------
# Inicializacion de sesion Struts
# ---------------------------------------------------------------------------

def _init_session(session: requests.Session) -> None:
    """
    GET a la raiz + GET al formulario vacio para crear la sesion Struts.
    Sin esto el POST devuelve 500.
    """
    try:
        session.get(f"{_BASE}/", headers=HEADERS, timeout=15)
        session.get(INIT_URL,    headers=HEADERS, timeout=15)
    except requests.RequestException as e:
        logger.warning(f"Advertencia al inicializar sesion: {e}")


# ---------------------------------------------------------------------------
# Fetch de una pagina via requests (POST)
# ---------------------------------------------------------------------------

def fetch_grupos_page_requests(
    session: requests.Session,
    page: int, max_rows: int,
    institution: str, city: str, department: str, country: str,
) -> Optional[BeautifulSoup]:
    """
    GET a ScienTI con todos los campos del formulario (incluyendo filtros y
    numero de pagina). El <form> del sitio no tiene atributo method, por lo que
    el navegador usa GET y envia todos los campos como query string.
    Si se omiten los campos de filtro, el servidor ignora grupos_p_ y siempre
    devuelve la primera pagina.
    """
    params = _build_payload(page, max_rows, institution, city, department, country)
    try:
        resp = session.get(
            f"{_BASE}/busquedaAvanzadaGrupos.do",
            params=params,
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        resp.encoding = "iso-8859-1"
        if "Cod grupo" not in resp.text:
            logger.warning(f"Pagina {page}: la respuesta no contiene resultados.")
            return None
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        logger.error(f"Error GET pagina {page}: {e}")
        return None


# ---------------------------------------------------------------------------
# Fallback Selenium para paginacion Struts por sesion
# ---------------------------------------------------------------------------

def fetch_grupos_page_selenium(
    page: int, max_rows: int,
    institution: str, city: str, department: str, country: str,
) -> Optional[BeautifulSoup]:
    """
    Fallback con Selenium headless Chrome para paginas > 1 cuando
    requests pierde la sesion Struts.

    Requiere: pip install selenium webdriver-manager
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        logger.error("Selenium no instalado. Ejecuta: pip install selenium webdriver-manager")
        return None

    logger.info(f"Usando Selenium para pagina {page}...")
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver  = webdriver.Chrome(service=service, options=options)
        wait    = WebDriverWait(driver, 20)

        driver.get(INIT_URL)
        time.sleep(2)

        for name, value in [("nmeInstitucion", institution),
                             ("ciuInst", city),
                             ("depInst", department)]:
            try:
                el = driver.find_element(By.NAME, name)
                el.clear()
                el.send_keys(value)
            except Exception:
                pass

        try:
            driver.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
        except Exception:
            logger.error("Selenium: no se encontro el boton de busqueda.")
            return None

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        time.sleep(1)

        for _ in range(page - 1):
            try:
                nxt = driver.find_element(
                    By.XPATH,
                    "//a[contains(text(),'Siguiente') or contains(text(),'>>')]"
                )
                nxt.click()
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
                time.sleep(1.5)
            except Exception as e:
                logger.warning(f"Selenium: no se pudo navegar a pagina {page}: {e}")
                return None

        return BeautifulSoup(driver.page_source, "html.parser")

    except Exception as e:
        logger.error(f"Error Selenium pagina {page}: {e}")
        return None
    finally:
        if driver:
            driver.quit()


# ---------------------------------------------------------------------------
# Orquestador de paginacion
# ---------------------------------------------------------------------------

def fetch_grupos_page(
    session: requests.Session,
    page: int, max_rows: int,
    institution: str, city: str, department: str, country: str,
) -> Optional[BeautifulSoup]:
    """
    Pagina 1: usa requests.
    Paginas > 1: requests primero; si devuelve 0 grupos, cae a Selenium.
    """
    soup = fetch_grupos_page_requests(
        session, page, max_rows, institution, city, department, country
    )

    if soup is not None and page > 1:
        if not _parse_grupos_table(soup):
            logger.warning(
                f"Pagina {page}: requests devolvio 0 grupos. "
                "Intentando con Selenium..."
            )
            soup = fetch_grupos_page_selenium(
                page, max_rows, institution, city, department, country
            )

    return soup


# ---------------------------------------------------------------------------
# Extractor completo via Selenium (unica sesion de browser para todas las paginas)
# ---------------------------------------------------------------------------

def fetch_all_grupos(
    institution: str = DEFAULT_INSTITUTION,
    city: str        = DEFAULT_CITY,
    department: str  = DEFAULT_DEPARTMENT,
    country: str     = DEFAULT_COUNTRY,
    delay_min: float = 2.0,
    delay_max: float = 4.5,
) -> list[dict]:
    """
    Extrae todos los grupos de ScienTI usando Selenium con una sola sesion de
    browser. La paginacion del sitio es 100% JavaScript (TableFacadeManager);
    ningun metodo HTTP con requests puede navegar a paginas > 1 porque el
    servidor ignora los parametros de pagina en peticiones directas.

    Estrategia:
      1. Abre Chrome headless, navega al formulario.
      2. Rellena los filtros y hace clic en Buscar.
      3. Parsea la pagina actual con BeautifulSoup.
      4. Hace clic en el boton de siguiente pagina y repite.
      5. Cierra el browser al terminar.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        logger.error(
            "Selenium no esta instalado. "
            "Ejecuta: pip install selenium webdriver-manager"
        )
        return []

    logger.info(
        f"Iniciando Selenium | Institucion: '{institution}' | "
        f"Ciudad: '{city}' | Departamento: '{department}'"
    )

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    driver = None
    all_grupos: list[dict] = []

    try:
        service = Service(ChromeDriverManager().install())
        driver  = webdriver.Chrome(service=service, options=options)
        wait    = WebDriverWait(driver, 20)

        # ---------------------------------------------------------------
        # 1. Abrir el formulario de busqueda
        # ---------------------------------------------------------------
        driver.get(INIT_URL)
        wait.until(EC.presence_of_element_located((By.NAME, "nmeInstitucion")))
        time.sleep(1)

        # ---------------------------------------------------------------
        # 2. Rellenar los filtros
        # ---------------------------------------------------------------
        def _fill(name: str, value: str) -> bool:
            try:
                el = driver.find_element(By.NAME, name)
                el.clear()
                el.send_keys(value)
                return True
            except Exception:
                return False

        _fill("nmeInstitucion", institution)
        _fill("ciuInst",        city)
        _fill("depInst",        department)

        # ---------------------------------------------------------------
        # 3. Hacer clic en Buscar
        # ---------------------------------------------------------------
        try:
            btn = driver.find_element(
                By.XPATH,
                "//input[@type='submit' or @type='button'] | //button[@type='submit']"
            )
            btn.click()
        except Exception:
            # Intentar por valor del boton
            driver.find_element(By.XPATH, "//input[@value='Buscar']").click()

        wait.until(EC.presence_of_element_located((By.XPATH, "//table")))
        time.sleep(1.5)

        # ---------------------------------------------------------------
        # 4. Bucle de paginacion: parsear + click siguiente
        # ---------------------------------------------------------------
        page = 1
        while True:
            soup = BeautifulSoup(driver.page_source, "html.parser")

            if page == 1:
                total = _parse_total_groups(soup)
                if total:
                    logger.info(f"Total de grupos en ScienTI: {total}")

            grupos_pagina = _parse_grupos_table(soup)
            logger.info(f"  -> {len(grupos_pagina)} grupos en pagina {page}")

            if not grupos_pagina:
                logger.info("Sin mas grupos. Fin de paginacion.")
                break

            all_grupos.extend(grupos_pagina)

            # Buscar enlace de siguiente pagina
            try:
                next_btn = driver.find_element(
                    By.XPATH,
                    "//a[contains(text(),'Siguiente') or contains(text(),'>>') "
                    "or contains(@href,\"setPageToLimit\")]"
                    "[not(contains(text(),'Anterior')) and not(contains(text(),'<<'))]"
                )
                # Verificar que el enlace corresponde a la pagina siguiente
                href = next_btn.get_attribute("href") or ""
                onclick = next_btn.get_attribute("onclick") or ""
                target_page = str(page + 1)
                if target_page not in href and target_page not in onclick:
                    # Buscar por numero de pagina directamente
                    try:
                        next_btn = driver.find_element(
                            By.XPATH,
                            f"//a[contains(@href,\"'{target_page}'\") "
                            f"or contains(@onclick,\"'{target_page}'\")]"
                        )
                    except Exception:
                        logger.info("No se encontro el boton de pagina siguiente. Fin.")
                        break

                _random_delay(delay_min, delay_max)
                driver.execute_script("arguments[0].click();", next_btn)
                wait.until(EC.presence_of_element_located((By.XPATH, "//table")))
                time.sleep(1.5)
                page += 1

            except Exception:
                logger.info(f"Ultima pagina alcanzada (pagina {page}). Fin.")
                break

    except Exception as e:
        logger.error(f"Error inesperado en Selenium: {e}")
    finally:
        if driver:
            driver.quit()
            logger.debug("Browser cerrado.")

    # Deduplicar
    seen, unique = set(), []
    for g in all_grupos:
        key = g.get("cod_grupo") or g.get("nombre")
        if key and key not in seen:
            seen.add(key)
            unique.append(g)

    if len(unique) < len(all_grupos):
        logger.warning(f"Eliminados {len(all_grupos) - len(unique)} duplicados.")

    logger.info(f"Lista final: {len(unique)} grupos unicos.")
    return unique


# ---------------------------------------------------------------------------
# Guardar lista de grupos
# ---------------------------------------------------------------------------

def save_grupos_list(grupos: list[dict], output_path: str) -> str:
    """Guarda la lista de grupos en un JSON con formato legible."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(grupos, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"Lista guardada en: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Scraping individual de cada GrupLAC
# ---------------------------------------------------------------------------

def scrape_all_gruplac(
    grupos: list[dict],
    output_dir: str  = "gruplac_data",
    delay_min: float = 2.0,
    delay_max: float = 4.5,
) -> list[dict]:
    """
    Para cada grupo descarga su pagina GrupLAC y guarda <output_dir>/<COD>.json.
    Si el archivo ya existe lo salta (control de reanudacion automatica).
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []
    total   = len(grupos)
    skipped = 0
    failed  = 0

    logger.info(f"Iniciando scraping de {total} GrupLAC -> '{output_dir}/'")

    for i, grupo in enumerate(grupos, 1):
        cod    = grupo.get("cod_grupo") or f"grupo_{i}"
        nro    = grupo.get("nro")
        nombre = grupo.get("nombre", "N/A")
        output_file = os.path.join(output_dir, f"{cod}.json")
        prefix = f"[{i}/{total}] {cod} | {nombre[:45]}"

        if os.path.exists(output_file):
            logger.info(f"{prefix} -> ya existe, saltando.")
            skipped += 1
            try:
                with open(output_file, "r", encoding="utf-8") as f:
                    results.append(json.load(f))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"  No se pudo leer cache {output_file}: {e}")
            continue

        if not nro:
            logger.warning(f"{prefix} -> sin nro, no se puede scrapear.")
            failed += 1
            continue

        logger.info(f"{prefix} -> scrapeando...")
        data = extract_group_data(nro)

        if data:
            data["_meta"] = {
                "cod_grupo":     cod,
                "fuente":        "busquedaAvanzadaGrupos",
                "lider_crawler": grupo.get("lider"),
                "avalado_por":   grupo.get("avalado_por"),
                "estado":        grupo.get("estado"),
                "clasificacion": grupo.get("clasificacion"),
                "gruplac_url":   grupo.get("gruplac_url"),
            }
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            logger.info(
                f"  [OK] {output_file} | "
                f"{len(data.get('integrantes', []))} integrantes, "
                f"{len(data.get('lineas_investigacion', []))} lineas"
            )
            results.append(data)
        else:
            logger.warning(f"  [FALLO] No se pudo extraer: {cod} (nro={nro})")
            failed += 1

        _random_delay(delay_min, delay_max)

    logger.info(
        f"Scraping completado | Total: {total} | "
        f"Extraidos: {len(results) - skipped} | "
        f"Ya existian: {skipped} | Fallidos: {failed}"
    )
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ScienTI UPB Crawler - Grupos de Investigacion Bucaramanga",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python -m scrapers.scienti_upb_crawler --only-list
  python -m scrapers.scienti_upb_crawler --scrape-all
  python -m scrapers.scienti_upb_crawler --scrape-all --delay-min 3.0 --delay-max 6.0
  python -m scrapers.scienti_upb_crawler --only-list --ciudad MEDELLIN --departamento ANTIOQUIA
        """,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--only-list", action="store_true",
        help="Solo obtiene y guarda la lista de grupos.",
    )
    mode.add_argument(
        "--scrape-all", action="store_true",
        help="Lista + descarga de cada GrupLAC individual. Reanuda automaticamente.",
    )

    parser.add_argument("--institucion",  default=DEFAULT_INSTITUTION)
    parser.add_argument("--ciudad",       default=DEFAULT_CITY)
    parser.add_argument("--departamento", default=DEFAULT_DEPARTMENT)
    parser.add_argument("--pais",         default=DEFAULT_COUNTRY)
    parser.add_argument("--list-output",  default="grupos_upb_bucaramanga.json",
                        help="Ruta del JSON con la lista de grupos.")
    parser.add_argument("--output-dir",   default="gruplac_data",
                        help="Carpeta para los JSON individuales de GrupLAC.")
    parser.add_argument("--delay-min",    type=float, default=2.0)
    parser.add_argument("--delay-max",    type=float, default=4.5)
    parser.add_argument("--verbose",      action="store_true",
                        help="Mostrar mensajes DEBUG.")

    args = parser.parse_args()

    if args.verbose:
        logging.root.setLevel(logging.DEBUG)

    if args.delay_min > args.delay_max:
        parser.error("--delay-min no puede ser mayor que --delay-max")

    grupos = fetch_all_grupos(
        institution=args.institucion,
        city=args.ciudad,
        department=args.departamento,
        country=args.pais,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
    )

    if not grupos:
        logger.error("No se encontraron grupos. Verifica los parametros o la conexion.")
        sys.exit(1)

    save_grupos_list(grupos, args.list_output)

    if args.scrape_all:
        scrape_all_gruplac(
            grupos=grupos,
            output_dir=args.output_dir,
            delay_min=args.delay_min,
            delay_max=args.delay_max,
        )
        logger.info(f"Proceso completo. Datos en '{args.output_dir}/'")
    else:
        logger.info(
            f"Modo --only-list listo. {len(grupos)} grupos en '{args.list_output}'. "
            "Usa --scrape-all para descargar los GrupLAC individuales."
        )


if __name__ == "__main__":
    main()
