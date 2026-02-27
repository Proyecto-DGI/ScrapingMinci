"""
main.py
Orquestador principal del scraper ScienTI - Fase 3 del proyecto UPB.

Flujo:
  1. Login a CvLAC con credenciales del investigador
  2. Extracción de datos privados (CvLAC autenticado)
  3. Extracción de datos públicos de grupos (GrupLAC)
  4. Mapeo al schema interno
  5. Export a JSON para segunda comparación

Uso:
  python main.py --mode gruplac --grupos 00000000000890 00000000001234
  python main.py --mode cvlac
  python main.py --mode both --grupos 00000000000890
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

from scrapers.gruplac_scraper import scrape_multiple_groups
from scrapers.cvlac_scraper import extract_researcher_data
from scrapers.group_finder import find_all_upb_groups
from mappers.scienti_mapper import map_group, map_researcher
from utils.session_manager import ScienTISession
from utils.credentials import load_credentials, load_grupos

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scienti_scraper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def save_json(data: dict | list, filename: str):
    """Guarda datos en JSON con formato legible."""
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"💾 Datos guardados en: {filepath}")
    return filepath


def load_grupos_from_file(filepath: str) -> list[str]:
    """Carga lista de códigos de grupos desde un archivo de texto (uno por línea)."""
    with open(filepath, "r") as f:
        return [line.strip() for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Modos de ejecución
# ---------------------------------------------------------------------------

def run_gruplac_mode(grupos: list[str], delay: float = 2.0):
    """Extrae y mapea datos públicos de grupos GrupLAC. Guarda en JSON."""
    logger.info(f"🔍 Modo GrupLAC: {len(grupos)} grupos a procesar")

    raw_groups = scrape_multiple_groups(grupos, delay=delay)
    mapped_groups = [map_group(g) for g in raw_groups]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_json(mapped_groups, f"gruplac_data_{timestamp}.json")

    logger.info(f"✅ GrupLAC completado: {len(mapped_groups)} grupos")
    return mapped_groups


def run_cvlac_mode(delay: float = 1.5):
    """Extrae datos del CvLAC autenticado. Guarda en JSON."""
    creds = load_credentials()
    logger.info(f"🔐 Modo CvLAC autenticado: {creds.nombre}")

    session_scienti = ScienTISession(delay_between_requests=delay)

    try:
        if not session_scienti.login(
            nombre=creds.nombre,
            identificacion=creds.identificacion,
            contrasena=creds.contrasena,
            nacionalidad=creds.nacionalidad,
        ):
            logger.error("No se pudo autenticar. Verifica las credenciales en .env")
            return None

        raw_data = extract_researcher_data(session_scienti)
        mapped_data = map_researcher(raw_data)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_nombre = creds.nombre.replace(" ", "_")[:20]
        save_json(mapped_data, f"cvlac_{safe_nombre}_{timestamp}.json")

        logger.info(
            f"✅ CvLAC completado: "
            f"{len(mapped_data.get('proyectos', []))} proyectos, "
            f"{len(mapped_data.get('produccion_bibliografica', []))} productos"
        )
        return mapped_data

    finally:
        session_scienti.logout()


def run_both_mode(grupos: list[str]):
    """Extrae GrupLAC público y CvLAC autenticado. Combina en un solo JSON."""
    result = {
        "grupos": run_gruplac_mode(grupos),
        "investigador": run_cvlac_mode(),
    }
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_json(result, f"scienti_completo_{timestamp}.json")
    return result


# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------

def run_debug_login():
    """Imprime los campos reales del formulario de login de CvLAC."""
    logger.info("🔎 Inspeccionando formulario de login...")
    session = ScienTISession()
    session.debug_form_fields()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ScienTI Scraper - Fase 3 Sistema UPB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Credenciales: definir en archivo .env (ver .env.example)
  SCIENTI_NOMBRE=Elkin Albarracin
  SCIENTI_IDENTIFICACION=91284614
  SCIENTI_CONTRASENA=tu_contrasena
  SCIENTI_GRUPOS=00000000000890,00000000001234

Ejemplos:
  python main.py --mode cvlac
  python main.py --mode gruplac
  python main.py --mode both
  python main.py --mode gruplac --grupos 00000000000890 00000000001234
  python main.py --mode find-groups
  python main.py --mode debug-login
        """
    )

    parser.add_argument(
        "--mode",
        choices=["gruplac", "cvlac", "both", "debug-login", "find-groups"],
        required=True,
        help="Modo de operación"
    )
    parser.add_argument(
        "--grupos",
        nargs="+",
        help="Códigos de grupos (sobreescribe SCIENTI_GRUPOS del .env)"
    )
    parser.add_argument(
        "--grupos-file",
        help="Archivo .txt con códigos de grupos (uno por línea)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Segundos entre peticiones (default: 2.0)"
    )

    args = parser.parse_args()

    if args.mode == "debug-login":
        run_debug_login()
        return

    if args.mode == "find-groups":
        nombres_grupos = [
            "Grupo de Investigación en Informática y Telecomunicaciones - INTELEC",
            "Grupo de Investigación en Bioingeniería, Señales y Microelectrónica - BISEMIC",
            "Grupo de Investigación de Ingeniería Civil - GRINDIC",
            "Grupo de Investigación en Materiales - GIM",
            "Detección de Contaminantes y Remediación - DeCoR",
            "Control Industrial",
            "Grupo de Investigaciones en Ingeniería Sanitaria y Ambiental",
            "Grupo de Investigación en Administración",
            "Grupo de Investigación en Ciencia Política y Derecho - CIPJURIS",
            "Grupo de Investigación en Contextos para Administración de Negocios Internacionales - GRICANI",
            "Grupo de Investigación en Desarrollo Tecnológico, Mecatrónica y Agroindustria - GiDeTechMA",
            "Grupo de Investigación en Diseño e Innovación - GRIDS",
            "Grupo de Investigación en Psicología Clínica y de la Salud",
            "Grupo en Producción y Logística - PROLOG",
            "Neurociencias y Comportamiento UIS-UPB",
            "Organizaciones Sostenibilidad y Transformación Psicosocial",
            "Saber, Educación y Docencia",
            "TIC y Ciudadanía",
            "Grupo Interdisciplinario de Estudios sobre Cultura, Derechos Humanos y Muerte",
        ]
        codigos = find_all_upb_groups(nombres_grupos, delay=args.delay)
        print("\n=== CÓDIGOS ENCONTRADOS ===")
        print("Pegar en .env como SCIENTI_GRUPOS=<códigos separados por coma>\n")
        for nombre, codigo in codigos.items():
            estado = codigo if codigo else "❌ NO ENCONTRADO"
            print(f"  {nombre[:60]:60} → {estado}")
        save_json(codigos, "grupos_codigos.json")
        return

    # Resolver lista de grupos
    grupos = []
    if args.grupos:
        grupos = args.grupos
    elif args.grupos_file:
        grupos = load_grupos_from_file(args.grupos_file)
    else:
        grupos = load_grupos()

    if args.mode == "gruplac":
        if not grupos:
            parser.error("No hay grupos definidos. Usa --grupos, --grupos-file o SCIENTI_GRUPOS en .env")
        run_gruplac_mode(grupos, delay=args.delay)

    elif args.mode == "cvlac":
        run_cvlac_mode(delay=args.delay)

    elif args.mode == "both":
        if not grupos:
            parser.error("No hay grupos definidos. Usa --grupos, --grupos-file o SCIENTI_GRUPOS en .env")
        run_both_mode(grupos)


if __name__ == "__main__":
    main()