"""
Registros que dejan los papás (llegadas tarde, salidas, almuerzos, certificados,
lista de espera) y notificaciones a los números de administración.

Dónde se guardan:
• Si SUPABASE_URL y SUPABASE_KEY están configurados → tabla "registros" en Supabase.
  Es lo recomendado en Render, y es la base de la futura plataforma de certificados.
• Si no → archivo data/registros.jsonl (sirve para probar en tu Mac; en Render
  gratis este archivo se borra cada vez que el servidor se reinicia).
"""
import json
import os
from datetime import datetime, time

import requests

import config
import whatsapp

ARCHIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "registros.jsonl")

NOMBRES_TIPO = {
    "llegada_tarde": "⏰ Llegadas tarde",
    "salida_temprana": "🏃 Salidas temprano",
    "almuerzo": "🍽️ Almuerzos",
    "certificado": "📄 Certificados",
    "lista_espera": "📝 Lista de espera",
}


def _usa_supabase():
    return bool(config.SUPABASE_URL and config.SUPABASE_KEY)


def _cabeceras_supabase():
    return {
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Guardar
# ---------------------------------------------------------------------------
def guardar(tipo, datos, telefono, nombre_perfil):
    registro = {
        "creado": datetime.now(config.ZONA).isoformat(timespec="seconds"),
        "tipo": tipo,
        "telefono": telefono,
        "nombre_perfil": nombre_perfil,
        "estudiante": datos.get("estudiante", ""),
        "grado": datos.get("grado", ""),
        "datos": datos,
        "estado": "pendiente",
    }
    if _usa_supabase():
        try:
            r = requests.post(
                f"{config.SUPABASE_URL}/rest/v1/registros",
                json=registro,
                headers={**_cabeceras_supabase(), "Prefer": "return=minimal"},
                timeout=10,
            )
            if r.status_code < 300:
                return registro
            print("⚠️  Supabase no guardó el registro:", r.status_code, r.text)
        except requests.RequestException as error:
            print("⚠️  No se pudo conectar con Supabase:", error)
        # Si Supabase falla, al menos queda en el archivo local

    os.makedirs(os.path.dirname(ARCHIVO), exist_ok=True)
    with open(ARCHIVO, "a", encoding="utf-8") as archivo:
        archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return registro


# ---------------------------------------------------------------------------
# Consultar
# ---------------------------------------------------------------------------
def listar(fecha=None, tipo=None, limite=300):
    """Registros más recientes primero. fecha: objeto date (opcional)."""
    if _usa_supabase():
        params = {"select": "*", "order": "creado.desc", "limit": str(limite)}
        if tipo:
            params["tipo"] = f"eq.{tipo}"
        if fecha:
            inicio = datetime.combine(fecha, time.min, tzinfo=config.ZONA)
            fin = datetime.combine(fecha, time.max, tzinfo=config.ZONA)
            params["and"] = f"(creado.gte.{inicio.isoformat()},creado.lte.{fin.isoformat()})"
        try:
            r = requests.get(f"{config.SUPABASE_URL}/rest/v1/registros", params=params,
                             headers=_cabeceras_supabase(), timeout=10)
            if r.status_code < 300:
                return r.json()
            print("⚠️  Supabase no devolvió registros:", r.status_code, r.text)
        except requests.RequestException as error:
            print("⚠️  No se pudo conectar con Supabase:", error)
        return []

    if not os.path.exists(ARCHIVO):
        return []
    resultado = []
    with open(ARCHIVO, encoding="utf-8") as archivo:
        for linea in archivo:
            try:
                registro = json.loads(linea)
            except ValueError:
                continue
            if fecha and registro.get("creado", "")[:10] != fecha.isoformat():
                continue
            if tipo and registro.get("tipo") != tipo:
                continue
            resultado.append(registro)
    resultado.reverse()
    return resultado[:limite]


# ---------------------------------------------------------------------------
# Notificar a administración
# ---------------------------------------------------------------------------
def notificar_admins(texto):
    """
    Envía el aviso a cada número de ADMIN_NUMEROS.
    WhatsApp solo deja escribir texto libre si esa persona le escribió al bot
    en las últimas 24 h (error 131047). Si eso pasa y hay una plantilla
    configurada en NOTIF_TEMPLATE, se envía la plantilla.
    """
    for numero in config.ADMIN_NUMEROS:
        resultado = whatsapp.texto(numero, texto)
        if resultado["ok"]:
            continue
        if resultado["codigo"] == 131047 and config.NOTIF_TEMPLATE:
            # Las plantillas no aceptan saltos de línea dentro de un parámetro
            plano = " | ".join(linea.strip() for linea in texto.splitlines() if linea.strip())
            whatsapp.plantilla(numero, config.NOTIF_TEMPLATE, config.NOTIF_TEMPLATE_LANG, [plano])
        elif resultado["codigo"] == 131047:
            print(f"ℹ️  {numero} no le ha escrito al bot en 24 h: escribe 'resumen' desde ese número "
                  "o configura NOTIF_TEMPLATE. El registro sí quedó guardado.")
