"""
session_manager.py
Maneja la autenticación y sesión persistente con ScienTI/CvLAC.
"""

import requests
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# URLs base - siempre HTTPS
BASE_URL       = "https://scienti.minciencias.gov.co"
LOGIN_URL      = f"{BASE_URL}/cvlac/EnRecursoHumano/inicio.do"
LOGIN_POST_URL = f"{BASE_URL}/cvlac/Login/s_login.do"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}


class HTTPSAdapter(requests.adapters.HTTPAdapter):
    """
    Adaptador que fuerza HTTPS en cualquier redirect.
    ScienTI a veces redirige de https → http causando 503.
    """
    def send(self, request, **kwargs):
        if request.url.startswith("http://"):
            request.url = request.url.replace("http://", "https://", 1)
            logger.debug(f"Redirect forzado a HTTPS: {request.url}")
        return super().send(request, **kwargs)


class ScienTISession:
    """
    Gestiona una sesión autenticada con la plataforma ScienTI/CvLAC.

    Uso:
        session = ScienTISession()
        if session.login(nombre="Elkin Albarracin", identificacion="91284614", contrasena="****"):
            html = session.get("https://scienti.minciencias.gov.co/cvlac/...")
    """

    def __init__(self, delay_between_requests: float = 1.5):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.authenticated = False
        self.delay = delay_between_requests

        # Montar adaptador HTTPS en ambos prefijos para cubrir cualquier redirect
        https_adapter = HTTPSAdapter()
        self.session.mount("https://", https_adapter)
        self.session.mount("http://", https_adapter)  # intercepta http y lo sube a https

    def login(
        self,
        nombre: str,
        identificacion: str,
        contrasena: str,
        nacionalidad: str = "C",
    ) -> bool:
        """
        Realiza el login en CvLAC y mantiene la sesión activa.
        """
        try:
            # 1. GET a la página de login para obtener cookies iniciales
            logger.info("Obteniendo página de login...")
            get_resp = self.session.get(LOGIN_URL, timeout=30, allow_redirects=True)
            get_resp.raise_for_status()
            time.sleep(0.5)

            # 2. POST con credenciales (nombres confirmados por debug_form_fields)
            payload = {
                "tpo_nacionalidad":    nacionalidad,
                "sgl_pais_nacim":      "COL",
                "txt_nmes_rh":         nombre,
                "nro_documento_ident": identificacion,
                "dta_nacimString":     "",
                "txt_contrasena":      contrasena,
            }

            logger.info(f"Intentando login para: {nombre} ({identificacion})")
            post_resp = self.session.post(
                LOGIN_POST_URL,
                data=payload,
                timeout=30,
                allow_redirects=True,
            )
            post_resp.raise_for_status()

            # 3. Verificar login exitoso
            if self._verify_login(post_resp.text):
                self.authenticated = True
                logger.info("✅ Login exitoso")
                return True
            else:
                logger.error("❌ Login fallido - credenciales incorrectas o estructura inesperada")
                # Descomentar para debug:
                # with open("debug_login_response.html", "w", encoding="utf-8") as f:
                #     f.write(post_resp.text)
                return False

        except requests.RequestException as e:
            logger.error(f"Error de red durante login: {e}")
            return False

    def _verify_login(self, html: str) -> bool:
        """Verifica si la respuesta HTML corresponde a una sesión autenticada."""
        success_indicators = [
            "Salir",
            "Datos generales",
            "Producción bibliográfica",
            "cerrarSesion",
            "inicio.do?accion=salir",
            "datosBasicos.do",
        ]
        return any(indicator in html for indicator in success_indicators)

    def get(self, url: str, params: dict = None, retries: int = 3) -> Optional[str]:
        """
        GET autenticado con rate limiting y reintentos.
        """
        if not self.authenticated:
            logger.warning("Sesión no autenticada. Ejecuta login() primero.")
            return None

        time.sleep(self.delay)

        for attempt in range(retries):
            try:
                resp = self.session.get(url, params=params, timeout=30, allow_redirects=True)
                resp.raise_for_status()
                return resp.text
            except requests.RequestException as e:
                wait = 2 ** attempt
                logger.warning(f"Intento {attempt+1}/{retries} falló: {e}. Esperando {wait}s...")
                time.sleep(wait)

        logger.error(f"Todos los reintentos fallaron para: {url}")
        return None

    def logout(self):
        """Cierra la sesión en ScienTI."""
        try:
            self.session.get(
                f"{BASE_URL}/cvlac/EnRecursoHumano/inicio.do?accion=salir",
                timeout=10,
                allow_redirects=True,
            )
            logger.info("Sesión cerrada correctamente")
        except Exception:
            pass
        finally:
            self.authenticated = False
            self.session.close()

    def debug_form_fields(self) -> None:
        """Imprime los campos reales del formulario de login."""
        from bs4 import BeautifulSoup
        resp = requests.get(LOGIN_URL, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")
        forms = soup.find_all("form")
        for i, form in enumerate(forms):
            print(f"\n--- Form {i} ---")
            print(f"Action: {form.get('action')}")
            print(f"Method: {form.get('method')}")
            for inp in form.find_all(["input", "select"]):
                name  = inp.get("name") or ""
                itype = inp.get("type") or "select"
                value = inp.get("value") or ""
                print(f"  {itype:10} | name={name:30} | value={value}")
