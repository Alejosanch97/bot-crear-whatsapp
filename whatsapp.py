"""
Envío de mensajes a WhatsApp (Cloud API de Meta).
Cada función arma el mensaje en el formato que pide Meta y respeta sus límites
de caracteres (si un texto se pasa, se recorta con "…" en vez de fallar).
"""
import requests

import config

POR_PAGINA = 9  # filas por página cuando una lista tiene más de 10 opciones


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------
def largo(texto):
    """Cuenta caracteres como los cuenta Meta (un emoji puede valer 2)."""
    return len((texto or "").encode("utf-16-le")) // 2


def cortar(texto, maximo):
    texto = texto or ""
    if largo(texto) <= maximo:
        return texto
    resultado = ""
    for caracter in texto:
        if largo(resultado + caracter) > maximo - 1:
            break
        resultado += caracter
    return resultado + "…"


def _partir(texto, maximo=4000):
    """WhatsApp acepta textos de hasta 4096 caracteres: los largos se parten por párrafos."""
    if largo(texto) <= maximo:
        return [texto]
    partes, actual = [], ""
    for parrafo in texto.split("\n\n"):
        candidato = parrafo if not actual else actual + "\n\n" + parrafo
        if largo(candidato) <= maximo:
            actual = candidato
        else:
            if actual:
                partes.append(actual)
            actual = cortar(parrafo, maximo)
    if actual:
        partes.append(actual)
    return partes


# ---------------------------------------------------------------------------
# Transporte: la única función que habla con Meta
# ---------------------------------------------------------------------------
def _enviar_a_meta(payload):
    url = f"https://graph.facebook.com/{config.GRAPH_VERSION}/{config.WA_PHONE_ID}/messages"
    try:
        r = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {config.WA_TOKEN}"},
            timeout=15,
        )
    except requests.RequestException as error:
        print("⚠️  No se pudo conectar con Meta:", error)
        return {"ok": False, "codigo": None}

    if r.status_code == 200:
        return {"ok": True, "codigo": None}

    codigo = None
    try:
        codigo = r.json()["error"]["code"]
    except Exception:
        pass
    print(f"⚠️  Meta respondió {r.status_code}: {r.text}")
    return {"ok": False, "codigo": codigo}


# El simulador reemplaza esta variable para imprimir en la terminal en vez de enviar.
transporte = _enviar_a_meta


def _enviar(para, contenido):
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": para}
    payload.update(contenido)
    return transporte(payload)


# ---------------------------------------------------------------------------
# Tipos de mensaje
# ---------------------------------------------------------------------------
def texto(para, cuerpo):
    resultado = {"ok": True, "codigo": None}
    for parte in _partir(cuerpo):
        resultado = _enviar(para, {"type": "text", "text": {"body": parte, "preview_url": True}})
    return resultado


def botones(para, cuerpo, opciones, encabezado=None, pie=None):
    """opciones: lista de (id, titulo). WhatsApp permite máximo 3 botones de 20 caracteres."""
    interactivo = {
        "type": "button",
        "body": {"text": cortar(cuerpo, 1024)},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": id_[:256], "title": cortar(titulo, 20)}}
                for id_, titulo in opciones[:3]
            ]
        },
    }
    if encabezado:
        interactivo["header"] = {"type": "text", "text": cortar(encabezado, 60)}
    if pie:
        interactivo["footer"] = {"text": cortar(pie, 60)}
    return _enviar(para, {"type": "interactive", "interactive": interactivo})


def lista(para, cuerpo, boton, filas, titulo_seccion="Opciones", contexto=None, pagina=0,
          encabezado=None, pie=None, textos_paginacion=("➡️ Ver más", "⬅️ Volver al inicio")):
    """
    filas: lista de (id, titulo, descripcion).
    WhatsApp permite máximo 10 filas. Si hay más y se da un 'contexto',
    se muestran de 9 en 9 con una fila extra "Ver más".
    """
    if len(filas) > 10 and contexto:
        inicio = pagina * POR_PAGINA
        if inicio >= len(filas):
            pagina, inicio = 0, 0
        visibles = list(filas[inicio:inicio + POR_PAGINA])
        if inicio + POR_PAGINA < len(filas):
            visibles.append((f"pag:{contexto}:{pagina + 1}", textos_paginacion[0], ""))
        else:
            visibles.append((f"pag:{contexto}:0", textos_paginacion[1], ""))
    else:
        visibles = list(filas[:10])

    rows = []
    for id_, titulo, descripcion in visibles:
        fila = {"id": id_[:200], "title": cortar(titulo, 24)}
        if descripcion:
            fila["description"] = cortar(descripcion, 72)
        rows.append(fila)

    interactivo = {
        "type": "list",
        "body": {"text": cortar(cuerpo, 1024)},
        "action": {
            "button": cortar(boton, 20),
            "sections": [{"title": cortar(titulo_seccion, 24), "rows": rows}],
        },
    }
    if encabezado:
        interactivo["header"] = {"type": "text", "text": cortar(encabezado, 60)}
    if pie:
        interactivo["footer"] = {"text": cortar(pie, 60)}
    return _enviar(para, {"type": "interactive", "interactive": interactivo})


def documento(para, enlace, nombre_archivo, leyenda=""):
    contenido = {"link": enlace, "filename": nombre_archivo}
    if leyenda:
        contenido["caption"] = cortar(leyenda, 1024)
    return _enviar(para, {"type": "document", "document": contenido})


def plantilla(para, nombre, idioma, parametros):
    """Plantilla aprobada por Meta (sirve para escribir fuera de la ventana de 24 h)."""
    componentes = []
    if parametros:
        componentes.append({
            "type": "body",
            "parameters": [{"type": "text", "text": cortar(p, 1000)} for p in parametros],
        })
    return _enviar(para, {
        "type": "template",
        "template": {"name": nombre, "language": {"code": idioma}, "components": componentes},
    })
