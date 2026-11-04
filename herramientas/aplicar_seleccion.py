"""Aplica seleccion_imagenes.csv (descargado del selector) a data/santoral.csv y data/moviles.csv.

Uso: python herramientas/aplicar_seleccion.py seleccion_imagenes.csv
"""
import csv, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sel = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")))
fijas = {(s["tipo"], s["clave"]): s["imagen_fija"].strip() for s in sel}

for archivo, tipo, clave in (("santoral.csv", "santoral", lambda r: r["fecha"] + "|" + r["nombre"]),
                             ("moviles.csv", "movil", lambda r: r["clave"])):
    p = BASE / "data" / archivo
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    n = 0
    for r in rows:
        v = fijas.get((tipo, clave(r)))
        if v:
            r["imagen_fija"] = v
            if v not in r["imagenes"].split():
                r["imagenes"] = (r["imagenes"] + " " + v).strip()
            n += 1
    w = csv.DictWriter(open(p, "w", newline="", encoding="utf-8"), fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)
    print(f"{archivo}: {n} imágenes fijadas")
