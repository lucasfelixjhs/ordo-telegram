"""Redacción de los mensajes del canal a partir del día litúrgico."""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .calendario import MESES, Celebracion, DiaLiturgico, Ordo, romano

LIMITE_CAPTION = 1024
DIAS_SAL = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


@dataclass
class Mensaje:
    dia: date                 # día litúrgico al que corresponde
    envio: datetime           # cuándo se publica (hora local)
    texto: str                # HTML de Telegram
    imagen: str | None        # ID de archivo de Google Drive
    clave: str                # identificador único (para no publicar dos veces)
    visperas: bool


FEM = ("asunción", "natividad", "inmaculada", "presentación", "transfiguración", "exaltación", "dedicación",
       "conversión", "cátedra", "visitación", "anunciación", "pasión", "epifanía", "ascensión", "santísima",
       "sagrada", "conmemoración", "octava", "bienaventurada", "dedicación")
MASC = ("bautismo", "nacimiento", "santísimo", "sagrado", "inmaculado", "divino", "tránsito", "domingo", "día")
PLURAL = ("santos ángeles", "siete santos", "santos inocentes", "santos protomártires")


def articulo(nombre: str) -> str:
    low = nombre.lower()
    if low.startswith(PLURAL) or low.startswith("santos "):
        return "de los "
    if low.startswith("santas "):
        return "de las "
    w = low.split()[0]
    if w in FEM:
        return "de la "
    if w in MASC:
        return "del "
    return "de "


def e(s: str) -> str:
    return html.escape(s or "", quote=False)


def nombre_fmt(c: Celebracion) -> str:
    n = e(c.nombre)
    if c.grado in ("Solemnidad", "Domingo") or (c.temporal and c.precedencia <= 4):
        n = n.upper()
    t = f", <i>{e(c.titulo)}</i>" if c.titulo else ""
    return f"<b>{n}</b>{t}"


def fecha_txt(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]}"


def comun_txt(comun: str) -> str:
    c = comun.strip()
    if not c:
        return ""
    if c.startswith("del "):
        c = c[4:]
    return c


def horas_comun(comun: str) -> str:
    """'del propio y del Común de X' -> 'del <b>propio</b> y del <b>Común de X</b>'.

    Regla del canal: salvo las celebraciones del Señor (que dicen solo «del propio»), siempre se indica primero
    el propio y luego el común, porque muchas memorias tienen al menos la oración propia."""
    c = comun.strip() or "del propio"
    if c.startswith("del Común"):
        c = "del propio y " + c
    partes = [x[4:] if x.startswith("del ") else x for x in c.split(" y del ")]
    return "del " + " y del ".join(f"<b>{e(x)}</b>" for x in partes)


HORAS = "Los elementos para la oración de la Liturgia de las Horas se toman "


def lista_y(items: list[str], conj="o") -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" {conj} " + items[-1]


def _fecha_flexible(s: str) -> date | None:
    """Acepta 2026-12-08, 08/12/2026, 8/12/26."""
    s = (s or "").strip()
    try:
        if "-" in s:
            return date.fromisoformat(s[:10])
        d, m, y = [int(x) for x in s.split("/")[:3]]
        return date(y + 2000 if y < 100 else y, m, d)
    except (ValueError, TypeError):
        return None


class Redactor:
    def __init__(self, ordo: Ordo, config: dict):
        self.ordo = ordo
        self.cfg = config
        self.pub = config.get("publicacion", {})
        h = config.get("horarios", {})
        self.tz = ZoneInfo(h.get("zona_horaria", "America/Argentina/Buenos_Aires"))
        self.h_dia = time.fromisoformat(h.get("hora_diaria", "00:10"))
        self.h_vis = time.fromisoformat(h.get("hora_primeras_visperas", "18:00"))

    # ---------------------------------------------------------------- qué se publica
    def se_publica(self, dl: DiaLiturgico) -> bool:
        p = dl.principal
        if not p.temporal:
            return True
        if p.grado in ("Domingo", "Solemnidad", "Fiesta", "Triduo pascual"):
            return True
        if p.grado == "Feria mayor":
            return p.nombre == "Miércoles de Ceniza" or self.pub.get("semana_santa", True)
        if p.grado == "Octava":
            return dl.tiempo == "Navidad" or self.pub.get("octava_de_pascua", True)
        if p.grado == "Feria privilegiada":
            return self.pub.get("ferias_17_24_diciembre", True)
        if dl.conmemoraciones:
            return self.pub.get("ferias_de_cuaresma_con_conmemoracion", True)
        if dl.libres:
            return self.pub.get("memorias_libres", True)
        if self.pub.get("sabado_mariano") and dl.tiempo == "Ordinario" and dl.fecha.weekday() == 5:
            return True
        return bool(self.pub.get("ferias", False))

    # ---------------------------------------------------------------- imagen
    @staticmethod
    def clave_temporal(dl: DiaLiturgico) -> str:
        p = dl.principal
        if p.clave:
            return p.clave
        n = p.nombre
        fijas = {"Miércoles de Ceniza": "ceniza", "Jueves Santo": "jueves_santo", "Sábado Santo": "sabado_santo",
                 "Ascensión del Señor": "ascension", "Domingo de Pentecostés": "pentecostes"}
        if n in fijas:
            return fijas[n]
        if n.startswith("Viernes Santo"):
            return "viernes_santo"
        if n.startswith("Domingo de Ramos"):
            return "ramos"
        if n.startswith("Domingo de Pascua"):
            return "pascua"
        if p.grado == "Feria mayor":
            return "semana_santa"
        if p.grado == "Octava":
            return "octava_pascua" if dl.tiempo == "Pascua" else "octava_navidad"
        if p.grado == "Feria privilegiada":
            return "adviento_17_24"
        if p.grado == "Domingo":
            return {"Adviento": "domingo_adviento", "Cuaresma": "domingo_cuaresma", "Pascua": "domingo_pascua",
                    "Navidad": "domingo_navidad"}.get(dl.tiempo, "domingo_ordinario")
        return ""

    def imagen(self, dl: DiaLiturgico) -> str | None:
        p = dl.principal
        if p.temporal and not p.imagenes and not dl.libres and not dl.conmemoraciones:
            imgs = self.ordo.img_moviles.get(self.clave_temporal(dl), [])
            if imgs:
                return imgs[0] if len(imgs) == 1 or self.pub.get("modo_imagen") == "primera" \
                    else imgs[dl.fecha.year % len(imgs)]
        fuente = p
        if p.temporal and not p.imagenes:
            if dl.libres:
                fuente = dl.libres[0]
            elif dl.conmemoraciones:
                fuente = dl.conmemoraciones[0]
        if fuente.imagen_fija:
            return fuente.imagen_fija
        imgs = fuente.imagenes
        if not imgs and self.pub.get("imagen_mariana_generica", False) and "maría" in fuente.nombre.lower() \
                and "Virgen" in fuente.comun:
            imgs = self.ordo.img_moviles.get("mariana_generica", [])
        if not imgs:
            return None
        if self.pub.get("modo_imagen", "rotar") == "primera":
            return imgs[0]
        return imgs[dl.fecha.year % len(imgs)]

    # ---------------------------------------------------------------- texto
    def texto(self, dl: DiaLiturgico, visperas: bool) -> str:
        p = dl.principal
        hoy = "Celebramos" if visperas else "Hoy celebramos"
        lineas: list[str] = []
        bio_de: Celebracion | None = None

        if not p.temporal or p.grado in ("Solemnidad", "Fiesta"):
            grado = p.grado
            if p.temporal and p.precedencia <= 3 and p.grado == "Solemnidad" and "Domingo" in p.nombre:
                lineas.append(f"{hoy} el {nombre_fmt(p)}.")
            else:
                lineas.append(f"{hoy} la {grado} {articulo(p.nombre)}{nombre_fmt(p)}.")
            if p.trasladada_de:
                lineas[-1] += f" <i>(Trasladada del {fecha_txt(p.trasladada_de)}.)</i>"
            bio_de = p
        elif p.grado == "Domingo":
            lineas.append(f"{hoy} el {nombre_fmt(p)}.")
        elif p.grado in ("Triduo pascual", "Feria mayor", "Octava"):
            art = "el " if p.nombre.startswith("Día") else ""
            lineas.append(f"Hoy es {art}<b>{e(p.nombre)}</b>.")
        elif p.grado == "Feria privilegiada":
            lineas.append(f"Hoy, <b>{fecha_txt(dl.fecha)}</b>, feria privilegiada de Adviento.")
        else:
            dia_txt = e(p.nombre[0].lower() + p.nombre[1:])
            if dl.libres:
                ns = [f"{articulo(c.nombre)}{nombre_fmt(c)}" for c in dl.libres]
                lineas.append(f"Feria o Memoria libre {lista_y(ns, 'o')}.")
                bio_de = dl.libres[0]
            else:
                lineas.append(f"Feria: <b>{dia_txt}.</b>")

        # observaciones propias de ciertos días
        extra = []
        if p.nombre == "Miércoles de Ceniza":
            extra.append("Comienzo de las observancias cuaresmales. Día de ayuno y abstinencia.")
        if p.nombre == "Jueves Santo":
            extra.append("Con la Misa vespertina de la Cena del Señor comienza el Triduo pascual.")
        if p.nombre.startswith("Viernes Santo"):
            extra.append("Día de ayuno y abstinencia.")
        if dl.fecha.month == 12 and dl.fecha.day == 24 and dl.tiempo == "Adviento":
            extra.append("Con la Hora de Nona termina el Tiempo de Adviento.")
        if dl.antifona_o:
            extra.append(f"Antífona del Magníficat: <i>{dl.antifona_o}!</i>")
        if dl.fecha.weekday() == 4 and p.es_solemnidad and dl.tiempo != "Triduo":
            extra.append("Por ser solemnidad, hoy no obliga la abstinencia de los viernes.")

        # Liturgia de las Horas
        if dl.conmemoraciones:
            ns = [nombre_fmt(c) for c in dl.conmemoraciones]
            extra.append(f"Puede hacerse conmemoración de {lista_y(ns, 'y')}.")
            bio_de = bio_de or dl.conmemoraciones[0]
            horas = ("Todo se toma del Propio del Tiempo; si se hace la conmemoración, en el Oficio de lectura se "
                     "añade la lectura hagiográfica y en Laudes y Vísperas la antífona y oración del santo.")
        elif dl.libres:
            c = dl.libres[0].comun
            if c and not c.startswith("del propio"):
                c = "del propio y " + c
            horas = HORAS + horas_comun(c) + "."
        elif p.temporal and p.grado in ("Feria", "Feria de Cuaresma"):
            dia = DIAS_SAL[dl.fecha.weekday()]
            horas = HORAS + f"de la <b>Feria: {dia} de la {romano(dl.salterio)} semana del Salterio.</b>" \
                if dl.salterio else HORAS + "de la <b>Feria</b>."
            if dl.tiempo == "Ordinario":
                extra.append("Puede celebrarse también cualquiera de las <b>Misas votivas no privilegiadas</b> previstas "
                             "en el Calendario. Asimismo, puede hacerse la Memoria libre de cualquiera de los santos "
                             "inscritos para este día en el Martirologio Romano.")
            elif dl.tiempo in ("Adviento", "Navidad", "Pascua"):
                extra.append("Puede hacerse la Memoria libre de cualquiera de los santos inscritos para este día en "
                             "el Martirologio Romano.")
        elif p.temporal and p.grado not in ("Solemnidad", "Fiesta"):
            horas = HORAS + "del <b>Propio del Tiempo</b>"
            if dl.salterio and p.grado != "Octava":
                horas += f" y del Salterio, <b>semana {romano(dl.salterio)}</b>"
            horas += "."
        else:
            horas = HORAS + horas_comun(p.comun) + "."
        partes = ["\n".join(lineas)]
        despues = [x for x in extra if x.startswith("Puede celebrarse también") or x.startswith("Puede hacerse la Memoria")]
        extra = [x for x in extra if x not in despues]
        if extra:
            partes.append("\n".join(extra))
        partes.append(horas)
        partes += despues
        nota = (p.nota or "").strip()
        if visperas and nota:
            partes.append(nota)
        elif nota:
            partes.append(nota.replace("Hoy, después", "Esta noche, después"))
        bio = (bio_de.biografia if bio_de else "").strip()
        if bio:
            tag = "<blockquote expandable>" if len(bio) > 700 else "<blockquote>"
            partes.append(f"{tag}{e(bio)}</blockquote>")
        return "\n\n".join(partes)

    # ---------------------------------------------------------------- mensajes de un rango
    def _variantes(self):
        """Un Ordo por calendario: el general (CRG + ADF) y uno por cada región con indicación propia."""
        if not hasattr(self, "_vars"):
            import copy
            cal = self.cfg.get("calendario", {})
            regiones = cal.get("regiones", [])
            self._vars = []
            for reg in [None] + list(regiones):
                c = copy.deepcopy(self.cfg)
                c.setdefault("calendario", {})["regiones"] = [reg] if reg else []
                self._vars.append((reg, Ordo(self.ordo.base, c)))
            self._nombres = cal.get("nombres_regiones", {"ARG": "Argentina", "PGY": "Paraguay", "BRS": "Brasil"})
        return self._vars

    def _envio(self, d: date, vis: bool) -> datetime:
        return datetime.combine(d - timedelta(days=1) if vis else d, self.h_vis if vis else self.h_dia,
                                tzinfo=self.tz)

    def _etiqueta(self, regs: list) -> tuple[str, str]:
        nombres = [self._nombres.get(r, r) for r in regs if r]
        if None in regs:
            if not nombres:
                return "Otros países", "otros"
            return f"En {lista_y(nombres, 'y')} y otros países", "+".join(r for r in regs if r) + "+otros"
        return f"En {lista_y(nombres, 'y')}", "+".join(regs)

    def mensajes(self, desde: date, hasta: date) -> list[Mensaje]:
        out = []
        d = desde
        variantes = self._variantes()
        while d <= hasta:
            dias = [(reg, o.dia(d)) for reg, o in variantes]
            if any(self.se_publica(dl) for _, dl in dias):
                grupos: dict[tuple, list] = {}
                for reg, dl in dias:
                    vis = dl.primeras_visperas
                    k = (self.texto(dl, vis), self.imagen(dl), vis)
                    grupos.setdefault(k, []).append(reg)
                if len(grupos) == 1:
                    (txt, img, vis), = grupos
                    out.append(Mensaje(d, self._envio(d, vis), txt, img, d.isoformat(), vis))
                else:
                    orden = sorted(grupos.items(), key=lambda kv: (None in kv[1], [r for r, _ in variantes].index(kv[1][0])))
                    for i, ((txt, img, vis), regs) in enumerate(orden):
                        etiqueta, cod = self._etiqueta(regs)
                        cuando = self._envio(d, vis) + timedelta(seconds=i)
                        out.append(Mensaje(d, cuando, f"<b><u>{etiqueta}:</u></b>\n\n{txt}", img,
                                           f"{d.isoformat()}#{cod}", vis))
            d += timedelta(days=1)
        out = self._aplicar_cambios(out, desde, hasta)
        out.sort(key=lambda m: m.envio)
        return out

    # ---------------------------------------------------------------- cambios puntuales (pestaña de la planilla)
    def _cambios(self) -> list[dict]:
        import csv
        from .hoja import id_imagen
        p = self.ordo.base / "data" / "cambios.csv"
        if not p.exists():
            return []
        out = []
        for r in csv.DictReader(open(p, encoding="utf-8")):
            f = _fecha_flexible(r.get("fecha", ""))
            acc = (r.get("accion") or "").strip().lower().replace(" ", "_")
            if f and acc:
                r["_fecha"], r["_accion"] = f, acc
                img = (r.get("imagen") or "").strip()
                r["_imagen"] = None if img.lower() in ("ninguna", "sin imagen", "no") else (id_imagen(img) or "")
                out.append(r)
        return out

    def _aplicar_cambios(self, msgs: list[Mensaje], desde: date, hasta: date) -> list[Mensaje]:
        cambios = [c for c in self._cambios() if desde <= c["_fecha"] <= hasta]
        if not cambios:
            return msgs
        res = list(msgs)
        for i, c in enumerate(cambios):
            cal = (c.get("calendario") or "").strip().upper()
            cal = {"ARGENTINA": "ARG", "PARAGUAY": "PGY", "OTROS PAÍSES": "OTROS", "TODOS": ""}.get(cal, cal)

            def aplica(m):
                if m.dia != c["_fecha"]:
                    return False
                if not cal or "#" not in m.clave:
                    return True
                return cal in m.clave.split("#", 1)[1].upper().split("+")

            texto = (c.get("texto") or "").strip()
            acc = c["_accion"]
            if acc == "omitir":
                res = [m for m in res if not aplica(m)]
            elif acc in ("reemplazar_texto", "reemplazar"):
                for m in res:
                    if aplica(m) and texto:
                        cab = m.texto.split("\n\n", 1)[0] + "\n\n" if m.texto.startswith("<b><u>") else ""
                        m.texto = cab + texto
            elif acc in ("agregar_nota", "nota"):
                for m in res:
                    if aplica(m) and texto:
                        partes = m.texto.split("\n\n<blockquote")
                        m.texto = partes[0] + "\n\n" + texto + ("\n\n<blockquote" + partes[1] if len(partes) > 1 else "")
            elif acc in ("cambiar_imagen", "imagen"):
                for m in res:
                    if aplica(m) and c["_imagen"] is not False:
                        m.imagen = c["_imagen"] or None
            elif acc in ("mensaje_extra", "extra"):
                try:
                    h = time.fromisoformat((c.get("hora") or "").strip() or "00:10")
                except ValueError:
                    h = self.h_dia
                res.append(Mensaje(c["_fecha"], datetime.combine(c["_fecha"], h, tzinfo=self.tz), texto,
                                   c["_imagen"] or None, f"{c['_fecha'].isoformat()}#extra{i + 1}", False))
        return res
