"""Genera elegir_imagenes.html: página para elegir la imagen de cada celebración.

Uso: python herramientas/crear_selector.py [inventario_drive.txt]
"""
import csv, json, re, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
inv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "herramientas" / "inventario_drive.txt"

nombres_archivo, por_mes = {}, {}
for line in inv_path.read_text(encoding="utf-8").splitlines():
    path, _, fid = line.rpartition(" | ")
    folder, _, fname = path.partition("/")
    nombres_archivo[fid.strip()] = fname
    por_mes.setdefault(folder, []).append(fid.strip())

items = []
for r in csv.DictReader(open(BASE / "data" / "santoral.csv", encoding="utf-8")):
    items.append(dict(tipo="santoral", clave=r["fecha"] + "|" + r["nombre"], fecha=r["fecha"], nombre=r["nombre"],
                      grado=r["grado"], region=r["regiones"], opciones=r["imagenes"].split(),
                      fija=r["imagen_fija"].strip(), mes=r["fecha"][:2]))
for r in csv.DictReader(open(BASE / "data" / "moviles.csv", encoding="utf-8")):
    items.append(dict(tipo="movil", clave=r["clave"], fecha="móvil", nombre=r["descripcion"], grado="", region="",
                      opciones=r["imagenes"].split(), fija=r["imagen_fija"].strip(), mes="00"))

datos = dict(items=items, archivos=nombres_archivo, por_mes=por_mes)
html = (BASE / "herramientas" / "selector_plantilla.html").read_text(encoding="utf-8")
out = BASE / "elegir_imagenes.html"
out.write_text(html.replace("/*DATOS*/null", json.dumps(datos, ensure_ascii=False)), encoding="utf-8")
print(out, len(items), "celebraciones")
