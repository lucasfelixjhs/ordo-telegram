"""Uso:
  python -m ordo publicar                 # lo ejecuta GitHub Actions: publica lo que toque ahora
  python -m ordo vista-previa 2027        # genera vista_previa_2027.html con todos los mensajes del año
  python -m ordo probar 2027-08-15        # envía el mensaje de ese día al chat de prueba
  python -m ordo dia 2027-08-15           # muestra en pantalla el día litúrgico y su mensaje
  python -m ordo adelanto                 # envía al canal de control lo que se publicará en las próximas 24 h
  python -m ordo sincronizar              # trae los datos de la planilla de Google
  python -m ordo proximos                 # regenera estado/proximos.tsv (lo muestra la planilla)
"""
from __future__ import annotations

import argparse
import html
import os
import sys
import time
import tomllib
from datetime import date, datetime, timedelta
from pathlib import Path

from .calendario import Ordo
from .mensajes import Redactor

BASE = Path(__file__).resolve().parent.parent
ESTADO = BASE / "estado" / "enviados.txt"
REGISTRO = BASE / "estado" / "registro.tsv"
PROXIMOS = BASE / "estado" / "proximos.tsv"
DIAS_C = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _plano(s: str) -> str:
    import re
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).replace("\t", " ").replace("\n\n", " ¶ ").replace("\n", " ")


def registrar(dia, clave, destino, resultado, detalle=""):
    REGISTRO.parent.mkdir(exist_ok=True)
    nuevo = not REGISTRO.exists()
    with open(REGISTRO, "a", encoding="utf-8") as f:
        if nuevo:
            f.write("momento\tdia\tmensaje\tdestino\tresultado\tdetalle\n")
        from zoneinfo import ZoneInfo
        ahora = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
        f.write(f"{ahora:%d/%m/%Y %H:%M:%S}\t{dia:%d/%m/%Y}\t{clave}\t{destino}\t{resultado}\t{_plano(detalle)[:300]}\n")


def sincronizar_planilla(cfg) -> None:
    sid = cfg.get("planilla", {}).get("id", "").strip()
    if not sid:
        return
    from .hoja import sincronizar
    for aviso in sincronizar(BASE, sid):
        print("AVISO:", aviso)
        registrar(date.today(), "-", "planilla", "aviso", aviso)


def cargar(sincronizar=False):
    cfg = tomllib.loads((BASE / "config.toml").read_text(encoding="utf-8"))
    if sincronizar:
        sincronizar_planilla(cfg)
    ordo = Ordo(BASE, cfg)
    return cfg, ordo, Redactor(ordo, cfg)


def enviados() -> set[str]:
    return set(ESTADO.read_text().split()) if ESTADO.exists() else set()


def marcar(clave: str) -> None:
    ESTADO.parent.mkdir(exist_ok=True)
    with open(ESTADO, "a") as f:
        f.write(clave + "\n")


def telegram(prueba=False):
    from .telegram import Telegram
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID_PRUEBA" if prueba else "TELEGRAM_CHAT_ID") or \
        (os.environ.get("TELEGRAM_CHAT_ID") if prueba else None)
    if not token or not chat:
        sys.exit("Faltan los secretos TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.")
    return Telegram(token, chat)


def cmd_publicar(args):
    cfg, ordo, red = cargar(sincronizar=True)
    escribir_proximos(red)
    ahora = datetime.now(red.tz)
    hoy = ahora.date()
    ya = enviados()
    tolerancia = timedelta(hours=args.tolerancia_horas)
    espera_max = timedelta(minutes=args.espera_minutos)
    pend = [m for m in red.mensajes(hoy - timedelta(days=1), hoy + timedelta(days=2))
            if m.clave not in ya and ahora - tolerancia <= m.envio <= ahora + espera_max]
    if not pend:
        print(f"{ahora:%Y-%m-%d %H:%M}: nada para publicar en esta ventana.")
        return
    tg = telegram()
    errores = False
    for m in sorted(pend, key=lambda m: m.envio):
        falta = (m.envio - datetime.now(red.tz)).total_seconds()
        if falta > 0:
            print(f"Esperando {int(falta)} s hasta las {m.envio:%H:%M} para publicar {m.clave}…")
            time.sleep(falta)
        try:
            tg.enviar(m.texto, m.imagen)
        except Exception as ex:  # noqa: BLE001
            registrar(m.dia, m.clave, "canal", "ERROR", str(ex))
            print(f"ERROR al publicar {m.clave}: {ex}")
            errores = True
            continue
        marcar(m.clave)
        registrar(m.dia, m.clave, "canal", "enviado" + (" (con imagen)" if m.imagen else ""), m.texto[:120])
        print(f"Publicado {m.clave} ({'I Vísperas' if m.visperas else 'del día'}).")
    if errores:
        sys.exit(1)


def escribir_proximos(red, dias=30):
    from zoneinfo import ZoneInfo
    hoy = datetime.now(red.tz).date()
    ms = red.mensajes(hoy, hoy + timedelta(days=dias))
    ya = enviados()
    PROXIMOS.parent.mkdir(exist_ok=True)
    with open(PROXIMOS, "w", encoding="utf-8") as f:
        f.write("envío\tdía litúrgico\tcalendario\tmensaje\timagen\testado\ttexto completo\n")
        for m in ms:
            cal = m.clave.split("#", 1)[1] if "#" in m.clave else "todos"
            primera = _plano(m.texto.split("\n\n")[1] if m.texto.startswith("<b><u>") else m.texto.split("\n")[0])
            img = f"https://drive.google.com/file/d/{m.imagen}/view" if m.imagen else ""
            est = "enviado" if m.clave in ya else ("no enviado" if m.envio < datetime.now(red.tz) else "pendiente")
            f.write(f"{DIAS_C[m.envio.weekday()]} {m.envio:%d/%m %H:%M}\t{DIAS_C[m.dia.weekday()]} {m.dia:%d/%m/%Y}\t"
                    f"{cal}\t{primera}\t{img}\t{est}\t{_plano(m.texto)}\n")
    print(f"{PROXIMOS}: {len(ms)} mensajes en los próximos {dias} días")


def cmd_proximos(args):
    cfg, ordo, red = cargar(sincronizar=args.sincronizar)
    escribir_proximos(red)


def cmd_sincronizar(args):
    cfg = tomllib.loads((BASE / "config.toml").read_text(encoding="utf-8"))
    sincronizar_planilla(cfg)
    print("Planilla sincronizada.")


def cmd_adelanto(args):
    """Envía al canal de control (TELEGRAM_CHAT_ID_PRUEBA) lo que se publicará en las próximas 24 horas."""
    prueba = os.environ.get("TELEGRAM_CHAT_ID_PRUEBA")
    if not prueba or prueba == os.environ.get("TELEGRAM_CHAT_ID"):
        print("Sin canal de control distinto del canal principal: no se envía adelanto.")
        cfg, ordo, red = cargar(sincronizar=True)
        escribir_proximos(red)
        return
    cfg, ordo, red = cargar(sincronizar=True)
    escribir_proximos(red)
    ahora = datetime.now(red.tz)
    marca = f"adelanto-{ahora.date().isoformat()}"
    if marca in enviados():
        print("El adelanto de hoy ya se envió.")
        return
    ms = [m for m in red.mensajes(ahora.date(), ahora.date() + timedelta(days=2))
          if ahora < m.envio <= ahora + timedelta(hours=24)]
    tg = telegram(prueba=True)
    if not ms:
        tg.enviar("🔎 <b>Adelanto:</b> en las próximas 24 horas no hay publicaciones (feria sin celebración).")
    for m in ms:
        tg.enviar(f"🔎 <b>Adelanto</b> — se publicará el {DIAS_C[m.envio.weekday()]} {m.envio:%d/%m a las %H:%M}:"
                  f"\n\n{m.texto}", m.imagen)
        registrar(m.dia, m.clave, "control", "adelanto enviado")
    marcar(marca)


def cmd_probar(args):
    cfg, ordo, red = cargar(sincronizar=True)
    d = date.fromisoformat(args.fecha)
    ms = red.mensajes(d, d)
    if not ms:
        sys.exit(f"El {d} no tiene mensaje (feria sin celebración).")
    tg = telegram(prueba=True)
    for m in ms:
        tg.enviar(m.texto, m.imagen)
        registrar(m.dia, m.clave, "prueba", "enviado")
    print(f"Enviado(s) {len(ms)} mensaje(s) al chat de prueba.")


def cmd_dia(args):
    cfg, ordo, red = cargar()
    d = date.fromisoformat(args.fecha)
    dl = ordo.dia(d)
    print(f"{d}  {dl.tiempo}  semana {dl.semana}  salterio {dl.salterio}")
    print(f"Principal: {dl.principal.nombre} ({dl.principal.grado}, precedencia {dl.principal.precedencia})")
    for c in dl.omitidas:
        print(f"  omitida: {c.nombre} ({c.grado})")
    ms = red.mensajes(d, d)
    if ms:
        print(f"\nSe publica: {ms[0].envio:%d/%m %H:%M}  imagen: {ms[0].imagen}\n")
        print(ms[0].texto)
    else:
        print("\nNo se publica mensaje.")


def cmd_vista_previa(args):
    cfg, ordo, red = cargar()
    y = int(args.año)
    ms = red.mensajes(date(y, 1, 1), date(y, 12, 31))
    out = Path(args.salida or BASE / f"vista_previa_{y}.html")
    filas = []
    for m in ms:
        dl = ordo.dia(m.dia)
        img = (f'<a href="https://drive.google.com/file/d/{m.imagen}/view" target="_blank">'
               f'<img loading="lazy" src="https://drive.google.com/thumbnail?id={m.imagen}&sz=w240" alt="imagen"></a>'
               if m.imagen else "—")
        txt = m.texto.replace("\n", "<br>")
        filas.append(f"<tr data-mes='{m.dia.month}'><td>{m.dia:%d/%m}<br><small>{dl.tiempo}</small></td>"
                     f"<td>{m.envio:%d/%m %H:%M}{' ★' if m.visperas else ''}</td><td>{img}</td>"
                     f"<td class='msg'>{txt}</td></tr>")
    out.write_text(PLANTILLA.replace("{{AÑO}}", str(y)).replace("{{FILAS}}", "\n".join(filas))
                   .replace("{{TOTAL}}", str(len(ms))), encoding="utf-8")
    print(f"{out} ({len(ms)} mensajes)")


PLANTILLA = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vista previa {{AÑO}}</title>
<style>:root{--bg:#fff;--fg:#1d1d1f;--muted:#666;--line:#e3e3e3;--quote:#c0392b}
@media (prefers-color-scheme:dark){:root{--bg:#17181a;--fg:#ececec;--muted:#9a9a9a;--line:#2c2d30;--quote:#e57368}}
body{font:14px/1.45 system-ui,sans-serif;margin:16px;background:var(--bg);color:var(--fg)}
table{border-collapse:collapse;width:100%}th{text-align:left;color:var(--muted);font-weight:500}
td{border-bottom:1px solid var(--line);padding:10px 8px;vertical-align:top}.msg{max-width:640px}
td img{width:120px;border-radius:6px}small{color:var(--muted)}
blockquote{border-left:3px solid var(--quote);margin:6px 0;padding-left:8px;color:var(--muted)}
select{font:inherit;padding:4px;margin:0 0 12px}</style>
<h1>Mensajes {{AÑO}} ({{TOTAL}})</h1><p>★ = se publica la tarde anterior a las I Vísperas.</p>
<label>Mes: <select onchange="for(const r of document.querySelectorAll('tr[data-mes]'))r.hidden=this.value&&r.dataset.mes!==this.value">
<option value="">Todos</option><option value="1">Enero</option><option value="2">Febrero</option><option value="3">Marzo</option>
<option value="4">Abril</option><option value="5">Mayo</option><option value="6">Junio</option><option value="7">Julio</option>
<option value="8">Agosto</option><option value="9">Septiembre</option><option value="10">Octubre</option>
<option value="11">Noviembre</option><option value="12">Diciembre</option></select></label>
<table><tr><th>Día</th><th>Envío</th><th>Imagen</th><th>Mensaje</th></tr>{{FILAS}}</table>"""


def main():
    ap = argparse.ArgumentParser(prog="ordo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publicar")
    p.add_argument("--tolerancia-horas", type=float, default=3)
    p.add_argument("--espera-minutos", type=float, default=40)
    p.set_defaults(f=cmd_publicar)
    p = sub.add_parser("probar")
    p.add_argument("fecha")
    p.set_defaults(f=cmd_probar)
    p = sub.add_parser("dia")
    p.add_argument("fecha")
    p.set_defaults(f=cmd_dia)
    p = sub.add_parser("adelanto")
    p.set_defaults(f=cmd_adelanto)
    p = sub.add_parser("sincronizar")
    p.set_defaults(f=cmd_sincronizar)
    p = sub.add_parser("proximos")
    p.add_argument("--sincronizar", action="store_true")
    p.set_defaults(f=cmd_proximos)
    p = sub.add_parser("vista-previa")
    p.add_argument("año")
    p.add_argument("--salida")
    p.set_defaults(f=cmd_vista_previa)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
