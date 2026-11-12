"""
Servidor del bot de WhatsApp de CREAR.

Rutas:
  GET  /           → "estoy vivo" (Render la usa para saber que el servidor responde)
  GET  /webhook    → Meta la llama una vez para verificar el webhook
  POST /webhook    → Meta la llama con cada mensaje que llega
  GET  /registros  → tabla con los registros del día (protegida con ADMIN_KEY)
  GET  /static/... → archivos públicos, como el PDF de admisiones
"""
import hashlib
import hmac
import threading
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

from flask import Flask, abort, render_template, request

import config
import flujos
import registros
from contenido import cargar

app = Flask(__name__)

# Los mensajes se procesan en segundo plano para responderle a Meta de inmediato
_hilos = ThreadPoolExecutor(max_workers=8)

# Meta a veces reenvía el mismo mensaje: recordamos los últimos ids procesados
_vistos = deque(maxlen=2000)
_vistos_set = set()
_candado = threading.Lock()

if not (config.WA_TOKEN and config.WA_PHONE_ID and config.VERIFY_TOKEN):
    print("⚠️  Faltan WA_TOKEN, WA_PHONE_ID o VERIFY_TOKEN en el .env / Environment.")


def _ya_procesado(mensaje_id):
    with _candado:
        if mensaje_id in _vistos_set:
            return True
        if len(_vistos) == _vistos.maxlen:
            _vistos_set.discard(_vistos[0])
        _vistos.append(mensaje_id)
        _vistos_set.add(mensaje_id)
        return False


def _firma_valida():
    """Si APP_SECRET está configurado, comprueba que la petición la firmó Meta."""
    if not config.APP_SECRET:
        return True
    firma = request.headers.get("X-Hub-Signature-256", "")
    esperada = "sha256=" + hmac.new(config.APP_SECRET.encode(), request.get_data(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(firma, esperada)


def _procesar_seguro(mensaje, nombre):
    try:
        flujos.procesar(mensaje, nombre)
    except Exception:
        print("❌ Error procesando un mensaje:")
        traceback.print_exc()


@app.get("/")
def salud():
    return "Bot CREAR funcionando ✅", 200


@app.get("/webhook")
def verificar_webhook():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == config.VERIFY_TOKEN:
        return request.args.get("hub.challenge", ""), 200
    return "Token de verificación incorrecto", 403


@app.post("/webhook")
def recibir_webhook():
    if not _firma_valida():
        abort(403)
    data = request.get_json(silent=True) or {}
    for entrada in data.get("entry", []):
        for cambio in entrada.get("changes", []):
            valor = cambio.get("value") or {}
            nombres = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in valor.get("contacts", [])}
            # "statuses" (enviado, entregado, leído) también llegan aquí; solo nos interesan "messages"
            for mensaje in valor.get("messages", []):
                if _ya_procesado(mensaje.get("id")):
                    continue
                print(f"📩 {mensaje.get('from')} · {mensaje.get('type')}")
                _hilos.submit(_procesar_seguro, mensaje, nombres.get(mensaje.get("from"), ""))
    return "ok", 200  # responder rápido; si no, Meta reintenta


@app.get("/registros")
def ver_registros():
    if not config.ADMIN_KEY or request.args.get("clave") != config.ADMIN_KEY:
        abort(403)
    hoy = datetime.now(config.ZONA).date()
    try:
        fecha = date.fromisoformat(request.args.get("fecha") or hoy.isoformat())
    except ValueError:
        fecha = hoy
    tipo = request.args.get("tipo") or ""
    lista = registros.listar(fecha=fecha, tipo=tipo or None)
    conteo = {}
    for r in registros.listar(fecha=fecha):
        conteo[r["tipo"]] = conteo.get(r["tipo"], 0) + 1
    return render_template(
        "registros.html",
        registros=lista,
        fecha=fecha,
        tipo=tipo,
        tipos=registros.NOMBRES_TIPO,
        conteo=conteo,
        clave=config.ADMIN_KEY,
        etiquetas=cargar("general")["etiquetas"],
    )


if __name__ == "__main__":
    import os
    app.run(port=int(os.getenv("PORT", "5000")), debug=False)
