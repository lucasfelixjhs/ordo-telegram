"""Motor del calendario litúrgico (Ordo ADF).

Calcula, para cualquier año, qué se celebra cada día aplicando:
- Pascua y todas las fiestas móviles que dependen de ella;
- los tiempos litúrgicos, domingos y semanas del Salterio;
- la Tabla de precedencia de los días litúrgicos (NUALC 59);
- los traslados de solemnidades impedidas (NUALC 5, 56, 60) y las reglas propias del Ordo;
- la concurrencia de I Vísperas (NUALC 61).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
ANTIFONAS_O = {17: "O Sapientia", 18: "O Adonai", 19: "O Radix Iesse", 20: "O Clavis David",
               21: "O Oriens", 22: "O Rex gentium", 23: "O Emmanuel"}


def romano(n: int) -> str:
    vals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, s in [(30, "XXX"), (20, "XX")] + vals:
        while n >= v:
            out += s
            n -= v
    return out


def pascua(y: int) -> date:
    """Domingo de Pascua (algoritmo gregoriano anónimo)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(y, mes, dia)


def domingo_en_o_antes(d: date) -> date:
    return d - timedelta(days=(d.weekday() + 1) % 7)


def domingo_despues(d: date) -> date:
    return d + timedelta(days=7 - (d.weekday() + 1) % 7 or 7)


def adviento_1(y: int) -> date:
    return domingo_en_o_antes(date(y, 12, 3))


def ciclo_dominical(d: date) -> str:
    """Ciclo A, B o C del año litúrgico al que pertenece la fecha (comienza el I Domingo de Adviento)."""
    fin = d.year + 1 if d >= adviento_1(d.year) else d.year
    return {1: "A", 2: "B", 0: "C"}[fin % 3]


@dataclass
class Celebracion:
    nombre: str
    grado: str                 # Solemnidad, Fiesta, Memoria obligatoria, Memoria libre, Conmemoración, Domingo, Feria...
    precedencia: int           # 1..18 según la Tabla de los días litúrgicos (menor = más importante)
    titulo: str = ""
    color: str = ""
    comun: str = ""
    nota: str = ""
    imagenes: list[str] = field(default_factory=list)
    imagen_fija: str = ""
    biografia: str = ""
    clave: str = ""            # identificador estable (para imágenes de celebraciones móviles)
    temporal: bool = False     # pertenece al Propio del Tiempo
    trasladada_de: date | None = None

    @property
    def es_solemnidad(self) -> bool:
        return self.grado == "Solemnidad"


@dataclass
class DiaLiturgico:
    fecha: date
    tiempo: str                # Adviento, Navidad, Ordinario, Cuaresma, Triduo, Pascua
    semana: int | None
    salterio: int | None
    feria: Celebracion         # el día del Tiempo (domingo o feria)
    principal: Celebracion     # lo que se celebra efectivamente
    conmemoraciones: list[Celebracion] = field(default_factory=list)   # se pueden conmemorar
    libres: list[Celebracion] = field(default_factory=list)            # memorias libres posibles
    omitidas: list[Celebracion] = field(default_factory=list)
    primeras_visperas: bool = False   # sus I Vísperas se celebran la tarde anterior
    antifona_o: str = ""

    @property
    def es_domingo(self) -> bool:
        return self.fecha.weekday() == 6


class Ordo:
    def __init__(self, base: Path, config: dict):
        self.base = Path(base)
        self.cfg = config
        cal = config.get("calendario", {})
        self.regiones = set(cal.get("regiones", []))
        self.bautismo_modo = cal.get("bautismo", "13-enero")
        self.epifania_domingo = cal.get("epifania_en_domingo", False)
        self.ascension_domingo = cal.get("ascension_en_domingo", False)
        self.corpus_domingo = cal.get("corpus_en_domingo", False)
        self.dolores = int(cal.get("dolores_dias_antes_de_pascua", 9))
        self.santoral = self._leer_santoral()
        self.img_moviles = self._leer_moviles()
        self.domingos = self._leer_domingos()
        self._cache: dict[int, dict[date, DiaLiturgico]] = {}

    # ------------------------------------------------------------------ datos
    def _aplica_region(self, regiones: str) -> bool:
        toks = regiones.split()
        if not toks:
            return True
        neg = [t[1:] for t in toks if t.startswith("!")]
        pos = [t for t in toks if not t.startswith("!")]
        if any(n in self.regiones for n in neg):
            return False
        if pos:
            return any(p in self.regiones for p in pos)
        return True

    def _leer_santoral(self) -> dict[str, list[Celebracion]]:
        out: dict[str, list[Celebracion]] = {}
        with open(self.base / "data" / "santoral.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not self._aplica_region(r.get("regiones", "")):
                    continue
                c = Celebracion(
                    nombre=r["nombre"].strip(), titulo=r["titulo"].strip(), grado=r["grado"].strip(),
                    precedencia=int(r["precedencia"]), color=r["color"].strip(), comun=r["comun"].strip(),
                    nota=r["nota"].strip(), imagenes=r["imagenes"].split(), imagen_fija=r["imagen_fija"].strip(),
                    biografia=r["biografia"].strip(), clave=r["fecha"])
                out.setdefault(r["fecha"], []).append(c)
        return out

    def _leer_domingos(self) -> dict[tuple[str, str], dict]:
        p = self.base / "data" / "domingos.csv"
        if not p.exists():
            return {}
        with open(p, encoding="utf-8") as f:
            return {(r["clave"].strip().upper(), r["ciclo"].strip().upper()): r for r in csv.DictReader(f)}

    def _leer_moviles(self) -> dict[str, list[str]]:
        p = self.base / "data" / "moviles.csv"
        self.bio_moviles = {}
        if not p.exists():
            return {}
        with open(p, encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        self.bio_moviles = {r["clave"]: (r.get("biografia") or "").strip() for r in filas}
        return {r["clave"]: ([r["imagen_fija"].strip()] if (r.get("imagen_fija") or "").strip()
                             else r["imagenes"].split()) for r in filas}

    def _mov(self, clave, nombre, grado, prec, comun="del propio", color="Blanco", titulo=""):
        return Celebracion(nombre=nombre, grado=grado, precedencia=prec, comun=comun, color=color,
                           clave=clave, imagenes=self.img_moviles.get(clave, []), temporal=True, titulo=titulo,
                           biografia=self.bio_moviles.get(clave, ""))

    def _desde_tabla(self, md, nombre, prec):
        base = (self.santoral.get(md) or [None])[0]
        c = Celebracion(nombre, "Solemnidad", prec, temporal=True, comun="del propio", color="Blanco", clave=md)
        if base:
            c.imagenes, c.imagen_fija, c.biografia, c.nota = base.imagenes, base.imagen_fija, base.biografia, base.nota
        return c

    # ------------------------------------------------------------------ fechas clave
    def epifania(self, y: int) -> date:
        if self.epifania_domingo:
            return domingo_en_o_antes(date(y, 1, 8))      # domingo entre el 2 y el 8
        return date(y, 1, 6)

    def bautismo(self, y: int) -> date:
        if self.bautismo_modo == "domingo":
            ep = self.epifania(y)
            if ep.weekday() == 6 and ep.day >= 7:          # Epifanía el 7 u 8: lunes siguiente
                return ep + timedelta(days=1)
            return domingo_despues(ep)
        return date(y, 1, 13)

    def claves(self, y: int) -> dict[str, date]:
        p = pascua(y)
        asc = p + timedelta(days=42 if self.ascension_domingo else 39)
        corpus = p + timedelta(days=63 if self.corpus_domingo else 60)
        a1 = adviento_1(y)
        return dict(
            pascua=p, ceniza=p - timedelta(days=46), ramos=p - timedelta(days=7),
            jueves_santo=p - timedelta(days=3), pentecostes=p + timedelta(days=49), ascension=asc,
            trinidad=p + timedelta(days=56), corpus=corpus, sagrado_corazon=p + timedelta(days=68),
            inmaculado_corazon=p + timedelta(days=69), madre_iglesia=p + timedelta(days=50),
            sumo_sacerdote=p + timedelta(days=53), valle=p + timedelta(days=13),
            dolores=p - timedelta(days=self.dolores), adviento=a1, cristo_rey=a1 - timedelta(days=7),
            bautismo=self.bautismo(y), epifania=self.epifania(y),
        )

    def sagrada_familia(self, y: int) -> date:
        """Domingo dentro de la Octava de Navidad; si no hay, 30 de diciembre."""
        for d in range(26, 32):
            if date(y, 12, d).weekday() == 6:
                return date(y, 12, d)
        return date(y, 12, 30)

    # ------------------------------------------------------------------ Propio del Tiempo
    def temporal(self, d: date) -> tuple[str, int | None, int | None, Celebracion, list[Celebracion]]:
        """Devuelve (tiempo, semana, salterio, día del tiempo, celebraciones móviles de ese día)."""
        y = d.year
        k = self.claves(y)
        dia = DIAS[d.weekday()]
        dom = d.weekday() == 6
        moviles: list[Celebracion] = []
        p = k["pascua"]

        def sal(w):
            return (w - 1) % 4 + 1 if w else None

        # --- Navidad que viene del año anterior (1 de enero .. Bautismo)
        if d <= k["bautismo"] and d.month == 1:
            if d == k["bautismo"]:
                c = self._mov("bautismo", "Bautismo del Señor", "Fiesta", 9)
                return "Navidad", None, None, c, []
            if d == k["epifania"]:
                return "Navidad", None, None, self._desde_tabla("01-06", "Epifanía del Señor", 3), []
            if dom:
                nombre = ("II Domingo después de Navidad" if d < k["epifania"]
                          else "Domingo después de la Epifanía")
                return "Navidad", None, None, Celebracion(nombre, "Domingo", 10, temporal=True,
                                                           comun="del Propio del Tiempo"), []
            nombre = (f"{d.day} de enero, del Tiempo de Navidad" if d < k["epifania"]
                      else f"{dia.capitalize()} después de la Epifanía")
            return "Navidad", None, None, Celebracion(nombre, "Feria", 18, temporal=True, color="Blanco"), []

        # --- Navidad del año en curso (25-31 dic)
        if d.month == 12 and d.day >= 25:
            sf = self.sagrada_familia(y)
            if d == sf:
                moviles.append(self._mov("sagrada_familia", "Sagrada Familia de Jesús, María y José", "Fiesta", 9))
            if d.day == 25:
                return "Navidad", None, None, self._desde_tabla("12-25", "Natividad del Señor", 3), moviles
            n = d.day - 24
            c = Celebracion(f"Día {romano(n)} de la Octava de la Natividad", "Octava", 14, temporal=True,
                            comun="del Propio del Tiempo", color="Blanco")
            return "Navidad", None, None, c, moviles

        # --- Adviento
        if d >= k["adviento"]:
            w = (domingo_en_o_antes(d) - k["adviento"]).days // 7 + 1
            if dom:
                nombre = f"{romano(w)} Domingo de Adviento" + (" «Gaudete»" if w == 3 else "")
                c = Celebracion(nombre, "Domingo", 3, temporal=True, comun="del Propio del Tiempo",
                                color="Rosa o morado" if w == 3 else "Morado")
            elif d.day >= 17 and d.month == 12:
                c = Celebracion(f"Feria privilegiada de Adviento", "Feria privilegiada", 14, temporal=True,
                                comun="del Propio del Tiempo", color="Morado")
            else:
                c = Celebracion(f"{dia.capitalize()} de la {romano(w)} semana de Adviento", "Feria", 18,
                                temporal=True, color="Morado")
            return "Adviento", w, sal(w), c, []

        # --- Tiempo Ordinario I
        if d < k["ceniza"]:
            # semana = número de domingos transcurridos desde el Bautismo + 1
            w = 1 + sum(1 for i in range(1, (d - k["bautismo"]).days + 1)
                        if (k["bautismo"] + timedelta(days=i)).weekday() == 6)
            return self._ordinario(d, w, dom)

        # --- Cuaresma y Semana Santa
        if d < p:
            if d == k["ceniza"]:
                return "Cuaresma", None, 4, Celebracion("Miércoles de Ceniza", "Feria mayor", 3, temporal=True,
                                                         comun="del Propio del Tiempo", color="Morado"), []
            if d < k["ceniza"] + timedelta(days=4):
                return "Cuaresma", None, 4, Celebracion(f"{dia.capitalize()} después de Ceniza", "Feria de Cuaresma",
                                                         14, temporal=True, color="Morado"), []
            w = (domingo_en_o_antes(d) - (k["ceniza"] + timedelta(days=4))).days // 7 + 1
            if d == k["dolores"]:
                moviles.append(self._mov("dolores", "Nuestra Señora de los Dolores", "Conmemoración", 17,
                                         comun="del Común de la Santísima Virgen María", color="Morado"))
            if d >= k["ramos"]:
                if d == k["ramos"]:
                    c = Celebracion("Domingo de Ramos en la Pasión del Señor", "Domingo", 3, temporal=True,
                                    comun="del Propio del Tiempo", color="Rojo")
                elif d >= k["jueves_santo"]:
                    n = {0: "Jueves Santo", 1: "Viernes Santo de la Pasión del Señor", 2: "Sábado Santo"}[
                        (d - k["jueves_santo"]).days]
                    c = Celebracion(n, "Triduo pascual", 1, temporal=True, comun="del Propio del Tiempo",
                                    color={0: "Blanco", 1: "Rojo", 2: "Morado"}[(d - k["jueves_santo"]).days])
                    return "Triduo", 6, 2 if d.weekday() == 3 else None, c, []
                else:
                    c = Celebracion(f"{dia.capitalize()} Santo", "Feria mayor", 3, temporal=True,
                                    comun="del Propio del Tiempo", color="Morado")
                return "Cuaresma", 6, sal(6), c, moviles
            if dom:
                nombre = f"{romano(w)} Domingo de Cuaresma" + (" «Lætare»" if w == 4 else "")
                c = Celebracion(nombre, "Domingo", 3, temporal=True, comun="del Propio del Tiempo",
                                color="Rosa o morado" if w == 4 else "Morado")
            else:
                c = Celebracion(f"{dia.capitalize()} de la {romano(w)} semana de Cuaresma", "Feria de Cuaresma", 14,
                                temporal=True, color="Morado")
            return "Cuaresma", w, sal(w), c, moviles

        # --- Tiempo Pascual
        if d <= k["pentecostes"]:
            w = (domingo_en_o_antes(d) - p).days // 7 + 1
            if d == p:
                c = Celebracion("Domingo de Pascua de la Resurrección del Señor", "Solemnidad", 1, temporal=True,
                                comun="del propio", color="Blanco")
                return "Pascua", 1, None, c, []
            if d < p + timedelta(days=7):
                c = Celebracion(f"{dia.capitalize()} de la Octava de Pascua", "Octava", 3, temporal=True,
                                comun="del Propio del Tiempo", color="Blanco")
                return "Pascua", 1, None, c, []
            if d == k["ascension"]:
                return "Pascua", w, None, Celebracion("Ascensión del Señor", "Solemnidad", 2, temporal=True,
                                                       comun="del propio", color="Blanco"), []
            if d == k["pentecostes"]:
                return "Pascua", 8, None, Celebracion("Domingo de Pentecostés", "Solemnidad", 2, temporal=True,
                                                       comun="del propio", color="Rojo"), []
            if d == k["valle"]:
                moviles.append(Celebracion("Nuestra Señora del Valle", "Fiesta", 13, temporal=True, clave="valle",
                                           comun="del propio y del Común de la Santísima Virgen María",
                                           color="Azul o blanco",
                                           imagenes=self.img_moviles.get("valle", []),
                                           biografia=self.bio_moviles.get("valle", ""))
                               if "ARG" in self.regiones else None)
                moviles = [m for m in moviles if m]
            if dom:
                nombre = f"{romano(w)} Domingo de Pascua" + (" (de la Divina Misericordia)" if w == 2 else "")
                c = Celebracion(nombre, "Domingo", 3, temporal=True, comun="del Propio del Tiempo", color="Blanco")
            else:
                c = Celebracion(f"{dia.capitalize()} de la {romano(w)} semana de Pascua", "Feria", 18, temporal=True,
                                color="Blanco")
            return "Pascua", w, sal(w), c, moviles

        # --- Tiempo Ordinario II
        w = 34 - (k["cristo_rey"] - domingo_en_o_antes(d)).days // 7
        tiempo, w2, s, c, mov = self._ordinario(d, w, dom)
        if d == k["madre_iglesia"]:
            mov.append(self._mov("madre_iglesia", "Bienaventurada Virgen María, Madre de la Iglesia", "Fiesta", 13,
                                 comun="del propio y del Común de la Santísima Virgen María", color="Azul o blanco"))
        if d == k["sumo_sacerdote"]:
            mov.append(self._mov("sumo_sacerdote", "Nuestro Señor Jesucristo, Sumo y Eterno Sacerdote", "Solemnidad",
                                 8))
        if d == k["trinidad"]:
            mov.append(self._mov("trinidad", "Santísima Trinidad", "Solemnidad", 4))
        if d == k["corpus"]:
            mov.append(self._mov("corpus", "Santísimo Cuerpo y Sangre de Cristo", "Solemnidad", 4))
        if d == k["sagrado_corazon"]:
            mov.append(self._mov("sagrado_corazon", "Sagrado Corazón de Jesús", "Solemnidad", 4))
        if d == k["inmaculado_corazon"]:
            mov.append(self._mov("inmaculado_corazon", "Inmaculado Corazón de la bienaventurada Virgen María",
                                 "Fiesta", 13, comun="del propio y del Común de la Santísima Virgen María",
                                 color="Azul o blanco"))
        if d == k["cristo_rey"]:
            mov.append(self._mov("cristo_rey", "Nuestro Señor Jesucristo, Rey del Universo", "Solemnidad", 4))
        return tiempo, w2, s, c, mov

    def _ordinario(self, d, w, dom):
        if dom:
            c = Celebracion(f"{romano(w)} Domingo del Tiempo Ordinario", "Domingo", 10, temporal=True,
                            comun="del Propio del Tiempo", color="Verde")
        else:
            c = Celebracion(f"{DIAS[d.weekday()].capitalize()} de la {romano(w)} semana del Tiempo Ordinario",
                            "Feria", 18, temporal=True, color="Verde")
        return "Ordinario", w, (w - 1) % 4 + 1, c, []

    # ------------------------------------------------------------------ resolución del año
    def año(self, y: int) -> dict[date, DiaLiturgico]:
        if y in self._cache:
            return self._cache[y]
        # Se calcula con margen para resolver traslados y vísperas en los bordes del año.
        ini, fin = date(y - 1, 12, 1), date(y + 1, 1, 31)
        base: dict[date, tuple] = {}
        cands: dict[date, list[Celebracion]] = {}
        d = ini
        while d <= fin:
            tiempo, w, s, feria, mov = self.temporal(d)
            base[d] = (tiempo, w, s, feria)
            md = d.strftime("%m-%d")
            fijas = [] if md in ("01-06", "12-25") else [replace(c) for c in self.santoral.get(md, [])]
            cands[d] = [feria] + mov + fijas
            d += timedelta(days=1)

        # 1) traslado de solemnidades impedidas
        def mejor(lst):
            return min(lst, key=lambda c: c.precedencia)

        k = {yy: self.claves(yy) for yy in (y - 1, y, y + 1)}
        for d in sorted(cands):
            for c in list(cands[d]):
                if not c.es_solemnidad or (c.temporal and c.precedencia <= 3) or c.trasladada_de:
                    continue
                destino = self._destino_traslado(d, c, cands, k[d.year] if d.year in k else self.claves(d.year))
                if destino is None:
                    continue
                cands[d].remove(c)
                c.trasladada_de = d
                cands.setdefault(destino, []).append(c)

        # 2) Sagrada Familia impedida por solemnidad (p. ej., San Juan el 27 cae en domingo) -> 30 de diciembre
        for d in list(cands):
            for c in list(cands[d]):
                if c.clave == "sagrada_familia" and any(o.precedencia < 9 and o is not c for o in cands[d]):
                    cands[d].remove(c)
                    c.trasladada_de = d
                    cands[date(d.year, 12, 30)].append(c)

        # 3) día por día
        dias: dict[date, DiaLiturgico] = {}
        for d in sorted(cands):
            tiempo, w, s, feria = base[d]
            lst = sorted(cands[d], key=lambda c: (c.precedencia, 0 if c.temporal else 1))
            top = lst[0]
            dl = DiaLiturgico(d, tiempo, w, s, feria, top)
            if tiempo == "Adviento" and d.month == 12 and d.day in ANTIFONAS_O:
                dl.antifona_o = ANTIFONAS_O[d.day]
            memorias = [c for c in lst if c.precedencia >= 15 and not c.temporal or c.grado == "Conmemoración"]
            if top.precedencia >= 15:
                # día ferial: se celebra la memoria obligatoria; si no hay, las memorias libres son optativas
                obl = [c for c in memorias if c.grado == "Memoria obligatoria"]
                dl.principal = obl[0] if obl else feria
                dl.libres = [] if obl else [m for m in memorias if m.grado == "Memoria libre"]
                dl.conmemoraciones = [m for m in memorias if m.grado == "Conmemoración"]
                dl.omitidas = [m for m in memorias if m is not dl.principal and m not in dl.libres
                               and m not in dl.conmemoraciones]
            elif top.precedencia == 14:
                # Cuaresma, 17-24 dic., Octava de Navidad: las memorias solo se conmemoran
                dl.conmemoraciones = memorias
            else:
                dl.omitidas = [c for c in lst[1:] if c is not feria]
            dias[d] = dl

        # 4) I Vísperas: el día siguiente las tiene si es domingo/solemnidad/fiesta del Señor en domingo
        #    y precede en la tabla al día en curso (en igualdad prevalece el día en curso).
        for d in sorted(dias):
            dl = dias[d]
            p = dl.principal
            tiene = (p.es_solemnidad and p.grado != "Octava") or (dl.es_domingo and p.precedencia <= 10)
            if p.temporal and p.grado == "Octava":
                tiene = False
            prev = dias.get(d - timedelta(days=1))
            if tiene and prev:
                dl.primeras_visperas = p.precedencia < prev.principal.precedencia
            if p.clave == "12-25":
                dl.primeras_visperas = True     # las Vísperas del 24 son siempre I Vísperas de Navidad
        self._cache[y] = {d: v for d, v in dias.items() if d.year == y}
        self._todo = getattr(self, "_todo", {})
        self._todo.update(dias)
        return self._cache[y]

    def _destino_traslado(self, d: date, c: Celebracion, cands, k) -> date | None:
        """Día al que se traslada una solemnidad impedida (None si no está impedida)."""
        def prec_dia(x):
            return min(o.precedencia for o in cands.get(x, []) if o is not c) if cands.get(x) else 99

        if prec_dia(d) > c.precedencia:
            return None
        if prec_dia(d) == c.precedencia:
            if not any(o.es_solemnidad for o in cands[d] if o is not c):
                return None
            if c.temporal:            # empate entre solemnidades: se traslada la de fecha fija
                return None
        semana_santa = k["ramos"] <= d <= k["pascua"]
        octava_pascua = k["pascua"] <= d <= k["pascua"] + timedelta(days=7)
        nombre = c.nombre.lower()
        if "san josé, esposo" in nombre and semana_santa:
            return k["ramos"] - timedelta(days=1)          # sábado anterior al Domingo de Ramos
        if "anunciación" in nombre and (semana_santa or octava_pascua):
            return k["pascua"] + timedelta(days=8)         # lunes después del II Domingo de Pascua
        x = d + timedelta(days=1)
        for _ in range(30):
            sem = k["ramos"] <= x <= k["pascua"] + timedelta(days=7)
            if not sem and prec_dia(x) > 8:
                return x
            x += timedelta(days=1)
        return None

    def dia(self, d: date) -> DiaLiturgico:
        return self.año(d.year)[d]
