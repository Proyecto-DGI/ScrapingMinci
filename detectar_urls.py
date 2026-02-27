"""
detectar_urls.py
Abre el CvLAC en un navegador real, hace login automáticamente,
hace clic en cada sección del menú y captura las URLs reales.

Uso:
    python detectar_urls.py
"""

import os
import json
import time
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

LOGIN_URL = "https://scienti.minciencias.gov.co/cvlac/EnRecursoHumano/inicio.do"

# Secciones del menú lateral a capturar
MENU_ITEMS = [
    "Datos generales",
    "Proyectos",
    "Producción bibliográfica",
    "Productos de Investigación + Creación",
    "Producción técnica y tecnológica",
    "Actividades de formación",
    "Reconocimientos",
    "Participación en grupos de investigación",
]


def detectar_urls():
    nombre         = os.getenv("SCIENTI_NOMBRE", "")
    identificacion = os.getenv("SCIENTI_IDENTIFICACION", "")
    contrasena     = os.getenv("SCIENTI_CONTRASENA", "")

    if not all([nombre, identificacion, contrasena]):
        print("❌ Faltan credenciales en .env")
        return

    # Configurar Chrome para capturar URLs de red
    options = webdriver.ChromeOptions()
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    # Comentar la siguiente línea si quieres ver el navegador abrirse
    # options.add_argument("--headless")

    print("🚀 Iniciando Chrome...")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    wait = WebDriverWait(driver, 15)

    urls_encontradas = {}

    try:
        # 1. Ir al login
        print(f"🔐 Abriendo login: {LOGIN_URL}")
        driver.get(LOGIN_URL)
        time.sleep(2)

        # 2. Llenar formulario
        print("📝 Llenando credenciales...")
        try:
            driver.find_element(By.NAME, "txt_nmes_rh").send_keys(nombre)
            driver.find_element(By.NAME, "nro_documento_ident").send_keys(identificacion)
            driver.find_element(By.NAME, "txt_contrasena").send_keys(contrasena)
        except Exception as e:
            print(f"⚠️ Error llenando campos: {e}")
            print("Campos disponibles en el form:")
            for el in driver.find_elements(By.TAG_NAME, "input"):
                print(f"  name={el.get_attribute('name')} type={el.get_attribute('type')}")

        # 3. Submit
        try:
            btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit'], button[type='submit']")
            btn.click()
        except:
            driver.find_element(By.NAME, "txt_contrasena").submit()

        time.sleep(3)
        print(f"✅ URL después del login: {driver.current_url}")

        # 4. Capturar URL base del dashboard
        urls_encontradas["dashboard"] = driver.current_url

        # 5. Hacer clic en cada item del menú y capturar URL
        print("\n🔍 Capturando URLs del menú...")

        for item_texto in MENU_ITEMS:
            try:
                # Buscar el link por texto
                link = None
                for tag in ["a", "span", "li", "td"]:
                    elements = driver.find_elements(By.TAG_NAME, tag)
                    for el in elements:
                        if item_texto.lower() in el.text.lower():
                            link = el
                            break
                    if link:
                        break

                if link:
                    driver.execute_script("arguments[0].click();", link)
                    time.sleep(2)
                    url_actual = driver.current_url
                    urls_encontradas[item_texto] = url_actual
                    print(f"  ✅ {item_texto}")
                    print(f"     → {url_actual}")

                    # También capturar URLs de las peticiones XHR/fetch si las hay
                    logs = driver.get_log("performance")
                    for log in logs:
                        import json as j
                        msg = j.loads(log["message"])["message"]
                        if msg.get("method") == "Network.requestWillBeSent":
                            req_url = msg.get("params", {}).get("request", {}).get("url", "")
                            if "scienti" in req_url and req_url != url_actual:
                                key = f"{item_texto}_xhr"
                                if key not in urls_encontradas:
                                    urls_encontradas[key] = []
                                if req_url not in urls_encontradas[key]:
                                    urls_encontradas[key].append(req_url)
                else:
                    print(f"  ⚠️ No encontrado en menú: '{item_texto}'")
                    urls_encontradas[item_texto] = "NO_ENCONTRADO"

            except Exception as e:
                print(f"  ❌ Error en '{item_texto}': {e}")
                urls_encontradas[item_texto] = f"ERROR: {e}"

        # 6. Guardar resultados
        output_file = "urls_cvlac_reales.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(urls_encontradas, f, ensure_ascii=False, indent=2)

        print(f"\n{'='*60}")
        print(f"✅ URLs capturadas y guardadas en: {output_file}")
        print(f"{'='*60}")
        print("\nResumen:")
        for seccion, url in urls_encontradas.items():
            if not seccion.endswith("_xhr"):
                print(f"  {seccion:45} → {url}")

    finally:
        input("\n⏸️  Presiona Enter para cerrar el navegador...")
        driver.quit()


if __name__ == "__main__":
    detectar_urls()
