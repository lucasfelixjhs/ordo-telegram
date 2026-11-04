"""ATENCIÓN: sobrescribe data/santoral.csv (se pierden las biografías y elecciones nuevas).
Construye data/santoral.csv a partir de las planillas originales y el inventario de Drive.

Se usa una sola vez (o cuando se quiera regenerar). Luego la tabla se edita a mano.
"""
import csv, re, sys, unicodedata, difflib
from pathlib import Path
import openpyxl

SRC = Path(sys.argv[1])          # carpeta con bios.xlsx y drive_inventory.txt
OUT = Path(sys.argv[2])          # carpeta data/ del proyecto


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


STOP = set("san santa santo santos santas de del la las los el y e beato beata bienaventurada virgen maria "
           "nuestra senora bvm a b c d e f g h i j k 1 2 3 4 jpg jpeg png webp avif copy".split())


def toks(s):
    return {t for t in norm(s).split() if t not in STOP and len(t) > 2}


# ---------------------------------------------------------------- planilla base
wb = openpyxl.load_workbook(SRC / "bios.xlsx")
ws = wb["Base de datos de celebraciones"]
comun_map = {r[0].strip(): r[1].strip() for r in wb["Mapeo títuloscomunes"].iter_rows(values_only=True) if r[0]}
bios_extra = [(r[0], r[1]) for r in wb["Biografías"].iter_rows(min_row=2, values_only=True) if r[0] and r[1]]

GRADOS = {"solemnidad": "Solemnidad", "fiesta": "Fiesta", "memoria obligatoria": "Memoria obligatoria",
          "memoria libre": "Memoria libre", "conmemoración": "Conmemoración"}

# celebraciones del Señor (precedencia 4 si solemnidad, 9 si fiesta)
SENOR = ["anunciación del señor", "presentación del señor", "transfiguración", "exaltación de la santa cruz",
         "letrán", "divino niño", "natividad del señor", "epifanía", "santísimo nombre de jesús"]
MARIA_KEYS = ["maría", "virgen", "nuestra señora", "santa maría la mayor"]

# celebraciones que maneja el motor (temporal) y se quitan de la tabla fija
QUITAR = {"12-30", "01-13"}

# filas que dependen de la región: (mm-dd, fragmento del nombre) -> regiones
REGION_OVERRIDE = {
    ("05-03", "felipe"): "!PGY",
    ("05-11", "felipe"): "PGY",
    ("07-09", "zhao"): "!ARG",
    ("07-10", "zhao"): "ARG",
    ("08-23", "rosa de lima"): "!ARG !PGY",
    ("08-30", "rosa de lima"): "ARG PGY",
    ("09-14", "exaltación"): "!PGY",
    ("05-03", "kurusu"): "PGY",
    ("10-12", "aparecida"): "BRS",
}
NOTAS = {
    "08-15": "Hoy, después de las Completas, es oportuno decir la antífona final de la Santísima Virgen "
             "<i>Salve, Reina de los cielos</i> (Ave Regina Cælorum).",
}

COMUN_OVERRIDE = {
    "07-26": "del Común de santos varones y del Común de santas mujeres",
    "10-16": "del Común de vírgenes",
    "08-16": "del Común de santos varones",
    "06-30": "del Común de mártires: para varios mártires",
    "08-31": "del Común de santos varones",
    "02-02": "del propio",
    "02-17": "del Común de santos varones y del Común de santos religiosos",
}
PREC_OVERRIDE = {"07-20": 8}   # Divino Niño: solemnidad propia de ADF
BIO_ALIAS = {"SANTA ÁGUEDA": "Santa Ágata"}
IMG_MANUAL = {  # imágenes de Drive sin fecha en el nombre
    "1FPL2sh-qupD8oGs35NIKrvSX71YKNk6g": "06-30", "1FReonKNmsDCFwAE3LsxfuKt2wfKOklM7": "06-30",
    "1FQgimh-2iPPxhjR5_s83oekVLq5roCuQ": "06-30", "1cDtLAp2xT50AQeoRdOx0QWpq9oy29s18": "09-14",
    "1h5tCoXQjS1Zrokife8Spkt7r2_vW3rvd": "09-03", "1h6BF-Z-oEaRGtbXOuCNXQmF0_iLb8x4B": "09-03",
}

rows = []
for r in ws.iter_rows(min_row=2, values_only=True):
    fecha = r[0]
    if not fecha or not r[3] or not str(r[3]).strip():
        continue
    md = fecha.strftime("%m-%d") if hasattr(fecha, "strftime") else str(fecha)[5:10]
    nombre = str(r[3]).strip()
    grado_raw = str(r[6] or "").strip().lower()
    if grado_raw.startswith("feria") or md in QUITAR:
        # 17-24 dic: solo conservamos las conmemoraciones
        m = re.search(r"Conmemoración de (.+)$", nombre)
        if md.startswith("12-") and m:
            sub = m.group(1)
            n, _, t = sub.partition(", ")
            rows.append(dict(fecha=md, nombre=n[0].upper() + n[1:], titulo=t, grado="Conmemoración", color="",
                             calendarios="CRG", regiones="", precedencia=17, comun="", nota="",
                             imagenes="", imagen_fija="", biografia=""))
        continue
    titulo = str(r[4] or "").strip()
    grado = GRADOS.get(grado_raw, grado_raw.capitalize())
    cal = [c.strip() for c in str(r[8] or "").split(",") if c.strip()]
    color = str(r[7] or "").strip()
    bio = str(r[9] or "").strip()
    img = ""
    if r[10]:
        m = re.search(r"(?:/d/|id=)([\w-]{20,})", str(r[10]))
        img = m.group(1) if m else ""
    low = nombre.lower()

    # Octava de Navidad 29 y 31: conmemoraciones dentro del día de la Octava
    if low.startswith("conmemoración de"):
        n = nombre[len("Conmemoración de "):]
        rows.append(dict(fecha=md, nombre=n[0].upper() + n[1:], titulo=titulo, grado="Conmemoración", color="",
                         calendarios=", ".join(cal), regiones="", precedencia=17, comun="", nota="",
                         imagenes=img, imagen_fija="", biografia=bio))
        continue

    solo_crg = set(cal) == {"CRG"}
    es_senor = any(k in low for k in SENOR)
    es_maria = any(k in low for k in MARIA_KEYS) and not low.startswith("san josé") \
        and "fundadores" not in low and "joaquín" not in low and "alacoque" not in low \
        and "magdalena" not in low and "maría antonia" not in low and "maría tránsito" not in low \
        and "goretti" not in low and "maría celia" not in low and "josemaría" not in low \
        and "ignacio de loyola" not in low and "maría de ligorio" not in low and "zaccar" not in low \
        and "maría vianney" not in low and "maría kolbe" not in low and "maría claret" not in low \
        and "luis maría" not in low and "maría felicia" not in low and "maría de jesús" not in low
    if low in ("natividad del señor", "epifanía del señor"):
        prec = 3
    elif grado == "Solemnidad":
        if es_senor:
            prec = 4
        elif es_maria and solo_crg:
            prec = 5
        elif solo_crg:
            prec = 6
        else:
            prec = 8
    elif grado == "Conmemoración":
        prec = 7  # Fieles difuntos
    elif grado == "Fiesta":
        if es_senor and solo_crg:
            prec = 9
        elif es_maria and solo_crg:
            prec = 11
        elif solo_crg:
            prec = 12
        else:
            prec = 13
    elif grado == "Memoria obligatoria":
        prec = 15 if solo_crg else 16
    else:
        prec = 17

    # regiones
    regiones = ""
    generales = {"CRG", "ADF"}
    if not (set(cal) & generales):
        regiones = " ".join(c for c in cal if c in ("ARG", "PGY", "BRS"))
    for (f, frag), reg in REGION_OVERRIDE.items():
        if f == md and frag in low:
            regiones = reg

    # común
    if es_maria:
        comun = "del propio y del Común de la Santísima Virgen María" if grado in ("Solemnidad", "Fiesta") \
            else "del Común de la Santísima Virgen María"
    elif es_senor or prec <= 7 or not titulo:
        comun = "del propio"
    else:
        c = comun_map.get(titulo, "")
        comun = ("del propio y " + c) if c and grado in ("Solemnidad", "Fiesta") else c
    comun = COMUN_OVERRIDE.get(md, comun)
    prec = PREC_OVERRIDE.get(md, prec)
    rows.append(dict(fecha=md, nombre=nombre, titulo=titulo, grado=grado, color=color,
                     calendarios=", ".join(cal), regiones=regiones, precedencia=prec, comun=comun,
                     nota=NOTAS.get(md, ""), imagenes=img, imagen_fija="", biografia=bio))

# ---------------------------------------------------------------- biografías extra
for nom, txt in bios_extra:
    base = BIO_ALIAS.get(nom.split(",")[0], nom.split(",")[0])
    best, score = None, 0
    for row in rows:
        s = len(toks(base) & toks(row["nombre"]))
        full = difflib.SequenceMatcher(None, norm(base), norm(row["nombre"])).ratio()
        sc = s + full
        if s and sc > score:
            best, score = row, sc
    if best and score >= 1.6 and not best["biografia"]:
        best["biografia"] = re.sub(r"^\d+\s+", "", txt.strip())

# ---------------------------------------------------------------- imágenes de Drive
inv = []
for line in (SRC / "drive_inventory.txt").read_text().splitlines():
    path, _, fid = line.rpartition(" | ")
    folder, _, fname = path.partition("/")
    inv.append((folder, fname, fid.strip()))

sin_asignar = []
movibles = {}
for folder, fname, fid in inv:
    if fid in IMG_MANUAL:
        tgt = [r for r in rows if r["fecha"] == IMG_MANUAL[fid]][0]
        tgt["imagenes"] = (tgt["imagenes"] + " " + fid).strip()
        continue
    if folder == "00":
        movibles[fname] = fid
        continue
    m = re.match(r"^(\d{1,2})", fname)
    day = int(m.group(1)) if m else None
    cand = [r for r in rows if r["fecha"][:2] == folder]
    t = toks(re.sub(r"^\d+\.?\s*(&\s*\d+\.)?", "", fname))
    best, bscore = None, 0
    for r in cand:
        ov = len(t & toks(r["nombre"]))
        if not ov:
            continue
        d = abs(int(r["fecha"][3:]) - day) if day else 0
        sc = ov * 3 - min(d, 5) * 0.5
        if sc > bscore:
            best, bscore = r, sc
    if not best and day:
        same = [r for r in cand if int(r["fecha"][3:]) == day and r["grado"] != "Conmemoración"]
        if len(same) == 1:
            best = same[0]
    if best:
        ids = [x for x in best["imagenes"].split() if x]
        if fid not in ids:
            ids.append(fid)
        best["imagenes"] = " ".join(ids)
    else:
        sin_asignar.append(f"{folder}/{fname} | {fid}")

# las celebraciones duplicadas por región comparten imágenes y biografía
for a in rows:
    for b in rows:
        if a is not b and norm(a["nombre"]) == norm(b["nombre"]):
            for k in ("imagenes", "biografia"):
                if not a[k] and b[k]:
                    a[k] = b[k]
for a in rows:   # Felipe y Santiago (PGY) se escribe "San Felipe"
    if a["fecha"] == "05-11":
        src = [b for b in rows if b["fecha"] == "05-03" and "felipe" in b["nombre"].lower()][0]
        a["nombre"] = src["nombre"]; a["imagenes"] = src["imagenes"]; a["biografia"] = a["biografia"] or src["biografia"]

# ---------------------------------------------------------------- salida
OUT.mkdir(parents=True, exist_ok=True)
cols = ["fecha", "nombre", "titulo", "grado", "precedencia", "color", "calendarios", "regiones",
        "comun", "nota", "imagenes", "imagen_fija", "biografia"]
rows.sort(key=lambda r: (r["fecha"], r["precedencia"]))
with open(OUT / "santoral.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in cols})
with open(OUT / "moviles_generado.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["clave", "imagenes"])
    w.writerow(["sagrado_corazon", movibles.get("Sagrado Corazón.jpg", "")])
    w.writerow(["inmaculado_corazon", movibles.get("Inmaculado Corazón.jpg", "")])
    w.writerow(["sumo_sacerdote", movibles.get("Sumo y eterno sacerdote.jpeg", "")])
    w.writerow(["madre_iglesia", movibles.get("Fiestas marianas/Madre de la Iglesia.jpg", "")])
    w.writerow(["mariana_generica", " ".join(v for k, v in movibles.items()
                                              if k.startswith("Fiestas marianas/") and "Madre de la Iglesia" not in k)])
(OUT.parent / "revisar_imagenes_sin_asignar.txt").write_text("\n".join(sin_asignar) + "\n", encoding="utf-8")
print(len(rows), "celebraciones;", sum(1 for r in rows if r["imagenes"]), "con imagen;",
      sum(1 for r in rows if r["biografia"]), "con biografía;", len(sin_asignar), "imágenes sin asignar")
