"""
Simulador: prueba el bot en la terminal, SIN WhatsApp ni Meta.

    python simulador.py          → chateas tú como si fueras un papá
    python simulador.py --demo   → recorre todos los menús automáticamente

En el modo interactivo:
    • escribe el número de una opción (1, 2, 3…) para tocarla
    • escribe cualquier texto para enviarlo como mensaje
    • /admin resumen   → envía "resumen" desde el número de administración
    • /salir           → terminar
Los registros del simulador se guardan en data/simulador.jsonl (no se mezclan con los reales).
"""
import os
import sys

import config
import flujos
import registros
import whatsapp

PADRE = "573000000001"
NOMBRE_PADRE = "Acudiente de prueba"
ADMIN = config.ADMIN_NUMEROS[0] if config.ADMIN_NUMEROS else "57ADMIN"

config.ADMIN_NUMEROS = config.ADMIN_NUMEROS or [ADMIN]
config.SUPABASE_URL = ""  # el simulador nunca escribe en Supabase
config.BASE_URL = config.BASE_URL or "http://localhost:5000"
registros.ARCHIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "simulador.jsonl")

GRIS, VERDE, AZUL, AMARILLO, FIN = "\033[90m", "\033[92m", "\033[94m", "\033[93m", "\033[0m"
opciones = []  # (id, tipo) de los botones/lista del último mensaje al papá


def _sangria(texto):
    return "\n".join("   " + linea for linea in texto.splitlines())


def mostrar(payload):
    """Reemplaza el envío a Meta: imprime lo que el bot mandaría."""
    para = payload["to"]
    es_admin = para in config.ADMIN_NUMEROS
    color = AMARILLO if es_admin else VERDE
    print(f"\n{color}{'🔔 NOTIFICACIÓN → +' + para if es_admin else '🤖 BOT'}{FIN}")

    tipo = payload["type"]
    if tipo == "text":
        print(_sangria(payload["text"]["body"]))
    elif tipo == "document":
        d = payload["document"]
        print(_sangria(f"📎 {d['filename']}  ({d['link']})\n{d.get('caption', '')}"))
    elif tipo == "template":
        print(_sangria(f"📨 Plantilla {payload['template']['name']}"))
    elif tipo == "interactive":
        inter = payload["interactive"]
        if inter.get("header"):
            print(_sangria(f"[{inter['header']['text']}]"))
        print(_sangria(inter["body"]["text"]))
        if inter.get("footer"):
            print(_sangria(f"{GRIS}{inter['footer']['text']}{FIN}"))
        nuevas = []
        if inter["type"] == "list":
            print(_sangria(f"{AZUL}☰ {inter['action']['button']}{FIN}"))
            for fila in inter["action"]["sections"][0]["rows"]:
                nuevas.append((fila["id"], "list_reply"))
                desc = f" {GRIS}— {fila['description']}{FIN}" if fila.get("description") else ""
                print(f"     {AZUL}{len(nuevas)}.{FIN} {fila['title']}{desc}")
        else:
            for boton in inter["action"]["buttons"]:
                nuevas.append((boton["reply"]["id"], "button_reply"))
                print(f"     {AZUL}[{len(nuevas)}]{FIN} {boton['reply']['title']}")
        if not es_admin:
            opciones[:] = nuevas
    return {"ok": True, "codigo": None}


whatsapp.transporte = mostrar


def enviar(entrada, desde=PADRE):
    """Simula un mensaje del papá: número = tocar opción, '#id' = tocar por id, otro = texto."""
    contador = getattr(enviar, "n", 0) + 1
    enviar.n = contador
    if entrada.startswith("#"):
        id_ = entrada[1:]
        tipo = next((t for i, t in opciones if i == id_), "button_reply")
        mensaje = {"type": "interactive", "interactive": {tipo: {"id": id_}}}
    elif entrada.isdigit() and 1 <= int(entrada) <= len(opciones):
        id_, tipo = opciones[int(entrada) - 1]
        mensaje = {"type": "interactive", "interactive": {tipo: {"id": id_}}}
    else:
        mensaje = {"type": "text", "text": {"body": entrada}}
    mensaje.update({"from": desde, "id": f"sim{contador}"})
    flujos.procesar(mensaje, NOMBRE_PADRE if desde == PADRE else "Administración")


def demo():
    from contenido import cargar
    grados = cargar("admisiones")["grados"]
    con_cupo = next((g["id"] for g in grados if int(g.get("cupos") or 0) > 0), None)
    sin_cupo = next((g["id"] for g in grados if int(g.get("cupos") or 0) == 0), None)

    pasos = ["hola", "#m:admisiones"]
    if con_cupo:
        pasos += [f"#adm:{con_cupo}"]
    if sin_cupo:
        pasos += ["#m:admisiones", f"#adm:{sin_cupo}", f"#esp:{sin_cupo}", "María López", "Juanita López", "#conf:si"]
    pasos += [
        "#m:cursos", "#cur:danzas",
        "#m:salidas",
        "#m:informacion", "#inf:calendario",
        "#m:certificados", "#cer:estudio", "#cers:estudio", "Juan Pérez", "1012345678", "#pag:fg:1", "#fg:10", "#conf:si",
        "#m:almuerzo", "#alm:inscribir", "Ana Gómez", "#fg:4", "hoy", "#conf:si",
        "#m:entrada_salida", "#es:tarde", "Pedro Ruiz", "#fg:6", "8:30 a.m.", "cita médica", "#conf:si",
        "#m:entrada_salida", "#es:salida", "Laura Díaz", "#fg:8", "11:00 a.m.", "Su mamá, Carmen Díaz", "no", "#conf:no",
        "#m:humano",
        "/admin resumen",
    ]
    for paso in pasos:
        print(f"\n{AZUL}👤 PAPÁ:{FIN} {paso}" if not paso.startswith("/admin") else f"\n{AMARILLO}👤 ADMIN:{FIN} resumen")
        if paso.startswith("/admin "):
            enviar(paso[7:], desde=ADMIN)
        else:
            enviar(paso)
    print(f"\n{VERDE}✅ Demo terminada. Registros guardados en {registros.ARCHIVO}{FIN}")


def interactivo():
    print(f"{VERDE}Simulador del bot CREAR{FIN} — escribe 'hola' para empezar, un número para tocar una opción, /salir para terminar.")
    while True:
        try:
            entrada = input(f"\n{AZUL}👤 Tú:{FIN} ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not entrada:
            continue
        if entrada == "/salir":
            break
        if entrada.startswith("/admin "):
            enviar(entrada[7:], desde=ADMIN)
        else:
            enviar(entrada)


if __name__ == "__main__":
    demo() if "--demo" in sys.argv else interactivo()
