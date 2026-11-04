"""Envío al canal de Telegram (Bot API)."""
from __future__ import annotations

import html
import io
import re
import time

import requests

API = "https://api.telegram.org/bot{token}/{metodo}"
LIMITE_CAPTION = 1024


def texto_visible(s: str) -> int:
    return len(html.unescape(re.sub(r"<[^>]+>", "", s)))


def descargar_imagen(drive_id: str) -> bytes | None:
    """Descarga una imagen pública de Google Drive y la convierte a JPEG apto para Telegram."""
    try:
        r = requests.get("https://drive.google.com/uc", params={"export": "download", "id": drive_id},
                         timeout=60)
        r.raise_for_status()
        if not r.headers.get("content-type", "").startswith("image/"):
            print(f"  ! {drive_id}: Drive no devolvió una imagen (¿archivo no público?)")
            return None
        from PIL import Image
        img = Image.open(io.BytesIO(r.content))
        img = img.convert("RGB")
        img.thumbnail((2560, 2560))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        return buf.getvalue()
    except Exception as ex:  # noqa: BLE001 - una imagen fallida no debe impedir el mensaje
        print(f"  ! no se pudo preparar la imagen {drive_id}: {ex}")
        return None


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    def _llamar(self, metodo: str, data: dict, files: dict | None = None) -> dict:
        for intento in range(5):
            r = requests.post(API.format(token=self.token, metodo=metodo), data=data, files=files, timeout=60)
            j = r.json()
            if j.get("ok"):
                return j["result"]
            espera = j.get("parameters", {}).get("retry_after")
            if r.status_code == 429 and espera:
                time.sleep(int(espera) + 1)
                continue
            if r.status_code >= 500:
                time.sleep(5 * (intento + 1))
                continue
            raise RuntimeError(f"Telegram {metodo}: {j.get('description')}")
        raise RuntimeError(f"Telegram {metodo}: demasiados reintentos")

    def enviar(self, texto: str, imagen_drive: str | None = None) -> None:
        foto = descargar_imagen(imagen_drive) if imagen_drive else None
        base = {"chat_id": self.chat_id, "parse_mode": "HTML"}
        if foto and texto_visible(texto) <= LIMITE_CAPTION:
            self._llamar("sendPhoto", {**base, "caption": texto}, {"photo": ("imagen.jpg", foto, "image/jpeg")})
            return
        if foto:
            self._llamar("sendPhoto", {"chat_id": self.chat_id}, {"photo": ("imagen.jpg", foto, "image/jpeg")})
        self._llamar("sendMessage", {**base, "text": texto, "link_preview_options": '{"is_disabled": true}'})
