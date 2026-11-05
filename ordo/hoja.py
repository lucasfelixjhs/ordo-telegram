"""Sincronización con la planilla de Google Sheets «Ordo – Panel de control».

La planilla es la fuente de verdad para santoral, móviles y cambios puntuales.
Antes de cada envío se descargan sus pestañas y se guardan en data/*.csv (que quedan en el repositorio
como respaldo e historial). Si la planilla no responde, se usan los últimos datos guardados.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import requests

EXPORT = "https://docs.google.com/spreadsheets/d/{id}/export?format=csv&gid={gid}"
# Las pestañas se crearon con estos identificadores fijos (no cambian aunque se renombren).
GID = {"Santoral": 1001, "Móviles": 1002, "Cambios puntuales": 1003, "Domingos": 1006}

ID_DRIVE = re.compile(r"(?:/d/|id=)([\w-]{20,})")


def id_imagen(s: str) -> str:
    s = (s or "").strip()
    m = ID_DRIVE.search(s)
    if m:
        return m.group(1)
    return s if re.fullmatch(r"[\w-]{20,}", s) else ""


def ids_imagenes(s: str) -> str:
    return " ".join(x for x in (id_imagen(t) for t in re.split(r"[\s,;]+", s or "")) if x)


def _bajar(sheet_id: str, hoja: str) -> list[dict]:
    r = requests.get(EXPORT.format(id=sheet_id, gid=GID[hoja]), timeout=60)
    r.raise_for_status()
    if "text/csv" not in r.headers.get("content-type", ""):
        raise RuntimeError(f"la pestaña «{hoja}» no devolvió CSV (¿la planilla no está compartida con enlace?)")
    filas = list(csv.DictReader(io.StringIO(r.content.decode("utf-8"))))
    return [{(k or "").strip(): (v or "").strip() for k, v in f.items()} for f in filas]


def _escribir(path: Path, campos: list[str], filas: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)


def sincronizar(base: Path, sheet_id: str) -> list[str]:
    """Descarga las pestañas y actualiza data/. Devuelve una lista de avisos (vacía si todo salió bien)."""
    avisos = []
    data = Path(base) / "data"

    try:
        filas = _bajar(sheet_id, "Santoral")
        out = []
        for f in filas:
            if not f.get("nombre"):
                continue
            mes, dia = f.get("mes", ""), f.get("dia", "")
            if not (mes.split(".")[0].isdigit() and dia.split(".")[0].isdigit()):
                avisos.append(f"Santoral: fila «{f.get('nombre')}» sin mes/día válidos, se ignora")
                continue
            f["fecha"] = f"{int(float(mes)):02d}-{int(float(dia)):02d}"
            f["precedencia"] = str(int(float(f.get("precedencia") or 17)))
            f["imagen_fija"] = id_imagen(f.get("imagen_fija", ""))
            f["imagenes"] = ids_imagenes(f.get("imagenes", ""))
            out.append(f)
        if len(out) < 100:
            raise RuntimeError(f"la pestaña Santoral tiene solo {len(out)} filas válidas")
        _escribir(data / "santoral.csv", ["fecha", "nombre", "titulo", "grado", "precedencia", "color",
                                          "calendarios", "regiones", "comun", "nota", "imagenes", "imagen_fija",
                                          "biografia"], out)
    except Exception as ex:  # noqa: BLE001
        avisos.append(f"Santoral: no se pudo leer la planilla ({ex}); se usan los datos guardados")

    try:
        filas = [f for f in _bajar(sheet_id, "Móviles") if f.get("clave")]
        if len(filas) < 10:
            raise RuntimeError(f"la pestaña Móviles tiene solo {len(filas)} filas")
        for f in filas:
            f["imagen_fija"] = id_imagen(f.get("imagen_fija", ""))
            f["imagenes"] = ids_imagenes(f.get("imagenes", ""))
        _escribir(data / "moviles.csv", ["clave", "descripcion", "imagenes", "imagen_fija", "biografia"], filas)
    except Exception as ex:  # noqa: BLE001
        avisos.append(f"Móviles: no se pudo leer la planilla ({ex}); se usan los datos guardados")

    try:
        filas = [f for f in _bajar(sheet_id, "Domingos") if f.get("clave") and f.get("ciclo")]
        if len(filas) < 100:
            raise RuntimeError(f"la pestaña Domingos tiene solo {len(filas)} filas")
        _escribir(data / "domingos.csv", ["clave", "domingo", "ciclo", "imagen_fija", "imagenes", "nota"], filas)
    except Exception as ex:  # noqa: BLE001
        avisos.append(f"Domingos: no se pudo leer la planilla ({ex}); se usan los datos guardados")

    try:
        crudo = _bajar(sheet_id, "Cambios puntuales")
        if crudo and "accion" not in crudo[0]:
            raise RuntimeError("faltan los encabezados de la pestaña")
        filas = [f for f in crudo if f.get("fecha") and f.get("accion")]
        _escribir(data / "cambios.csv", ["fecha", "calendario", "accion", "texto", "imagen", "hora", "comentario"],
                  filas)
    except Exception as ex:  # noqa: BLE001
        avisos.append(f"Cambios puntuales: no se pudo leer la planilla ({ex}); se usan los datos guardados")
    return avisos
