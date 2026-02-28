# ScienTI Scraper — Fase 3 

Extractor de datos de la plataforma ScienTI de MinCiencias.
Cubre GrupLAC (público) y CvLAC (autenticado).

## Instalación

```bash
pip install -r requirements.txt
```

## Estructura

```
scienti_scraper/
├── main.py                        # Orquestador CLI
├── requirements.txt
├── scrapers/
│   ├── gruplac_scraper.py         # Extracción pública de grupos
│   └── cvlac_scraper.py           # Extracción privada del investigador
├── mappers/
│   └── scienti_mapper.py          # Normalización al schema UPB
└── utils/
    └── session_manager.py         # Login y sesión persistente
```

## Uso

### 1. Diagnosticar campos del formulario de login
```bash
python main.py --mode debug-login
```
> Usar esto primero si el login falla — imprime los nombres exactos de los inputs del formulario.

### 2. Solo GrupLAC (sin login)
```bash
# Por código directo
python main.py --mode gruplac --grupos 00000000000890 00000000001234

# Desde archivo (uno por línea)
python main.py --mode gruplac --grupos-file grupos_upb.txt
```

### 3. Solo CvLAC (con login)
```bash
python main.py --mode cvlac --nombre "Juan Perez" --identificacion 12345678
# La contraseña se pide de forma segura (no queda en historial)
```

### 4. Ambos combinados
```bash
python main.py --mode both --grupos 00000000000890 --nombre "Juan Perez" --identificacion 12345678
```

## Output

Los JSONs se guardan en `output/` con timestamp:
- `gruplac_data_YYYYMMDD_HHMMSS.json`
- `cvlac_NombreInv_YYYYMMDD_HHMMSS.json`
- `scienti_completo_YYYYMMDD_HHMMSS.json`

## Si el login falla

1. Ejecutar `python main.py --mode debug-login`
2. Verificar los nombres de los campos del formulario en la consola
3. Actualizar el `payload` en `utils/session_manager.py` línea ~50

## Campo de enlace con DB interna

El campo **`radicado`** en proyectos es el campo de unión con Banner/PURE.
La función `_normalize_radicado()` en `scienti_mapper.py` estandariza el formato.
Ajustar esa función según las diferencias de formato encontradas en la Fase 2.
