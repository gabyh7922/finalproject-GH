"""Descarga la versión vigente del Código del Trabajo desde LeyChile (BCN).

Fuente oficial: Biblioteca del Congreso Nacional de Chile, servicio de
intercambio de normas en XML. idNorma 207436 = DFL 1 de 2003 (texto refundido
del Código del Trabajo). El XML queda versionado en data/raw/ para que el
corpus sea reproducible aunque la ley cambie después.

Uso:
    uv run python scripts/download_data.py
"""

from pathlib import Path

import httpx

URL = "https://www.leychile.cl/Consulta/obtxml?opt=7&idNorma=207436"
OUT = Path("data/raw/codigo_trabajo.xml")


def main() -> None:
    response = httpx.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60, follow_redirects=True)
    response.raise_for_status()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(response.content)
    print(f"{len(response.content):,} bytes -> {OUT}")


if __name__ == "__main__":
    main()
