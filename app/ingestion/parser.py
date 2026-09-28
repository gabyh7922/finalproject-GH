"""Parser del Código del Trabajo (XML oficial de LeyChile / BCN).

Convierte el XML de intercambio de normas de la Biblioteca del Congreso
Nacional en una lista de artículos limpios, cada uno con su ruta jerárquica
(Libro > Título > Capítulo > Párrafo). El artículo es la unidad natural de
una ley: es lo que un abogado cita ("art. 67") y por eso es también la unidad
de chunking y de citación del sistema.

Limpieza necesaria: el texto de LeyChile viene maquetado a dos columnas. La
columna derecha contiene notas de modificación ("L. 19.250 / Art. 1º Nº 38")
que indican qué ley cambió esa línea. Son útiles para un jurista pero ruido
para los embeddings (un vector de "vacaciones" no debería parecerse a otro por
compartir "L. 19.759"), así que se eliminan del texto indexado.

Uso:
    uv run python -m app.ingestion.parser   # escribe data/processed/articulos.json
"""

from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

NS = "{http://www.leychile.cl/esquemas}"
RAW_PATH = Path("data/raw/codigo_trabajo.xml")
OUT_PATH = Path("data/processed/articulos.json")

SOURCE_URL = "https://www.bcn.cl/leychile/navegar?idNorma=207436"

# Separador entre la columna de texto y la columna de notas al margen.
_MARGIN_GAP = re.compile(r" {4,}")
# Una línea que empieza con tanta sangría solo puede ser nota al margen
# (el texto normal tiene 0 o 5 espacios de sangría).
_MARGIN_ONLY_INDENT = 10
# Referencia legal suelta dentro de un encabezado ("L. 19.250", "Ley 20940").
_INLINE_LAW_REF = re.compile(r"\b(?:L\.|Ley|LEY)\s*\d[\d.]*")
# Fragmentos típicos de una nota de modificación.
_MARGIN_NOTE = re.compile(
    r"^(L\.|LEY|Ley|ART|Art\.|D\.O|DFL|D\.F\.L|N[°º]|Nº|INC|Inc\.|letra)\b", re.IGNORECASE
)

_HIERARCHY_TYPES = ("Libro", "Título", "Capítulo", "Párrafo", "Parágrafo", "Otros")


@dataclass
class Article:
    number: str  # "67", "40 BIS A" — normalizado a mayúsculas
    text: str  # texto limpio, sin notas al margen
    path: list[str] = field(default_factory=list)  # ["LIBRO I ...", "Título I ...", ...]
    derogado: bool = False
    transitorio: bool = False
    fecha_version: str = ""
    id_parte: str = ""

    @property
    def article_id(self) -> str:
        """Id estable y legible: 'art-67', 'art-40-bis-a', 'art-t-1' (transitorios)."""
        # "Ñ" -> "nn" antes de quitar tildes: si no, "152 quáter Ñ" choca con "152 quáter N".
        ascii_number = unicodedata.normalize("NFKD", self.number.lower().replace("ñ", "nn"))
        ascii_number = ascii_number.encode("ascii", "ignore").decode()
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_number).strip("-")
        return f"art-t-{slug}" if self.transitorio else f"art-{slug}"


def clean_article_text(raw: str) -> str:
    """Quita la columna de notas al margen y normaliza espacios, conservando incisos."""
    paragraphs: list[str] = []
    current: list[str] = []
    for line in raw.splitlines():
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if indent >= _MARGIN_ONLY_INDENT:
            continue  # línea que solo contiene nota al margen
        text_part = _MARGIN_GAP.split(stripped, maxsplit=1)[0]
        current.append(text_part)
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(re.sub(r"\s+", " ", p).strip() for p in paragraphs if p.strip())


def clean_heading(raw: str) -> str:
    """Encabezados ('Capítulo IV   L. 19.759  DE LA JORNADA'): descarta segmentos de nota."""
    segments = [s.strip() for s in re.split(r"\s{3,}|\n", raw or "") if s.strip()]
    kept = [s for s in segments if not _MARGIN_NOTE.match(s)]
    return re.sub(r"\s+", " ", _INLINE_LAW_REF.sub(" ", " ".join(kept))).strip()


def _normalize_number(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip().upper()


def _walk(container: ET.Element, path: list[str], out: list[Article]) -> None:
    for node in container.findall(f"{NS}EstructuraFuncional"):
        kind = node.attrib.get("tipoParte", "")
        text_node = node.find(f"{NS}Texto")
        raw_text = text_node.text if text_node is not None and text_node.text else ""
        children = node.find(f"{NS}EstructurasFuncionales")

        if kind in ("Artículo", "Artículo Transitorio") and children is None:
            name_node = node.find(f"{NS}Metadatos/{NS}NombreParte")
            number = _normalize_number(name_node.text if name_node is not None else "")
            out.append(
                Article(
                    number=number,
                    text=clean_article_text(raw_text),
                    path=list(path),
                    derogado=node.attrib.get("derogado") != "no derogado",
                    # Solo el bloque final "ARTICULOS TRANSITORIOS" cuenta: buscar la palabra en
                    # cualquier parte de la ruta marcaba por error el Título VII ("...empresas de
                    # servicios transitorios", arts. 183-A a 183-AE).
                    transitorio=node.attrib.get("transitorio") == "transitorio"
                    or kind == "Artículo Transitorio"
                    or (bool(path) and path[0].upper().startswith("ARTICULOS TRANSITORIOS")),
                    fecha_version=node.attrib.get("fechaVersion", ""),
                    id_parte=node.attrib.get("idParte", ""),
                )
            )
            continue

        next_path = path
        if kind in _HIERARCHY_TYPES or kind == "Artículo Transitorio":
            heading = clean_heading(raw_text)
            if heading:
                next_path = [*path, heading]
        if children is not None:
            _walk(children, next_path, out)


def parse_codigo(xml_path: Path = RAW_PATH) -> tuple[dict, list[Article]]:
    """Devuelve (metadatos de la norma, artículos en orden de aparición)."""
    root = ET.parse(xml_path).getroot()
    meta = {
        "norma_id": root.attrib.get("normaId"),
        "fecha_version": root.attrib.get("fechaVersion"),
        "fuente": SOURCE_URL,
    }
    articles: list[Article] = []
    top = root.find(f"{NS}EstructurasFuncionales")
    if top is not None:
        _walk(top, [], articles)
    return meta, articles


def main() -> None:
    meta, articles = parse_codigo()
    vigentes = [a for a in articles if not a.derogado]
    payload = {
        **meta,
        "total_articulos": len(articles),
        "vigentes": len(vigentes),
        "articulos": [{"article_id": a.article_id, **asdict(a)} for a in articles],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"{len(articles)} artículos ({len(vigentes)} vigentes) · versión {meta['fecha_version']}"
        f" -> {OUT_PATH}"
    )


if __name__ == "__main__":
    main()
