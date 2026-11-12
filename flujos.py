"""
Lógica de la conversación.

Cómo leer este archivo
──────────────────────
• Cada opción del menú principal tiene su función: _admisiones, _cursos, _salidas…
• Los botones y listas llevan un id con prefijo, por ejemplo:
      "m:cursos"    → abrir la sección Cursos del menú principal
      "cur:danzas"  → ver el curso con id "danzas"
      "pag:adm:1"   → página 2 de la lista de grados de admisiones
  _opcion() mira el prefijo y llama a la función correcta (tablas al final).
• Los formularios (almuerzo, llegada tarde, certificado…) piden los datos uno por
  uno, muestran un resumen y, al confirmar, guardan el registro y avisan a los
  números de ADMIN_NUMEROS.
• Aquí no hay textos para los papás: todos están en la carpeta contenido/.
"""
import threading
import time
import unicodedata
from datetime import datetime
from urllib.parse import quote

import config
import registros
import whatsapp
from contenido import cargar

EXPIRACION_SESION = 30 * 60  # segundos sin actividad antes de olvidar un formulario a medias

# tipo de formulario: (archivo de contenido, clave dentro del archivo, campos en orden)
FORMULARIOS = {
    "llegada_tarde": ("entrada_salida", "llegada_tarde", ["estudiante", "grado", "hora", "motivo"]),
    "salida_temprana": ("entrada_salida", "salida_temprana", ["estudiante", "grado", "hora", "recoge", "motivo"]),
    "almuerzo": ("almuerzo", "formulario", ["estudiante", "grado", "dia"]),
    "certificado": ("certificados", "formulario", ["estudiante", "documento", "grado"]),
    "lista_espera": ("admisiones", "lista_espera", ["acudiente", "estudiante"]),
}


# ===========================================================================
# Sesiones: en qué paso va cada persona (se guardan en memoria)
# ===========================================================================
_sesiones = {}
_candados = {}
_candado_global = threading.Lock()


def _candado(tel):
    """Un candado por teléfono: si alguien manda dos mensajes seguidos se procesan en orden."""
    with _candado_global:
        if tel not in _candados:
            _candados[tel] = threading.Lock()
        return _candados[tel]


def _sesion(tel):
    ahora = time.time()
    sesion = _sesiones.get(tel)
    if not sesion or ahora - sesion["visto"] > EXPIRACION_SESION:
        sesion = {"form": None, "nombre": ""}
        _sesiones[tel] = sesion
    sesion["visto"] = ahora
    return sesion


# ===========================================================================
# Utilidades
# ===========================================================================
def normalizar(texto):
    """'¡Menú!' → 'menu' (minúsculas, sin tildes ni signos)."""
    texto = unicodedata.normalize("NFD", (texto or "").lower().strip())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.strip(" .,!¡?¿")


class _Seguro(dict):
    def __missing__(self, clave):
        return "{" + clave + "}"


def formatear(plantilla, **valores):
    """Reemplaza {estudiante}, {grado}… en los textos; si falta un valor lo deja igual."""
    try:
        return (plantilla or "").format_map(_Seguro(valores))
    except (ValueError, IndexError, AttributeError):
        return plantilla or ""


def _general():
    return cargar("general")


def _activos(items):
    return [x for x in items if x.get("activo", True)]


def _buscar(items, id_):
    return next((x for x in items if str(x.get("id")) == id_), None)


def _cupos_texto(n):
    return "1 cupo disponible" if n == 1 else f"{n} cupos disponibles"


def _boton_menu(g):
    return ("menu", g["botones"]["menu_principal"])


def _boton_humano(g):
    return ("m:humano", g["botones"]["humano"])


def _con_botones(tel, texto, opciones):
    """Texto con botones debajo. Si el texto es muy largo para un mensaje con botones, se envía aparte."""
    if whatsapp.largo(texto) <= 1024:
        whatsapp.botones(tel, texto, opciones)
    else:
        whatsapp.texto(tel, texto)
        whatsapp.botones(tel, _general()["textos"]["elige_opcion"], opciones)


def _cerrar(tel, texto):
    """Respuesta final de una sección: texto + botones Menú principal / Atención humana."""
    g = _general()
    _con_botones(tel, texto, [_boton_menu(g), _boton_humano(g)])


def _lista(tel, cuerpo, boton, filas, seccion, contexto, pagina=0, **extra):
    g = _general()
    whatsapp.lista(
        tel, cuerpo, boton, filas,
        titulo_seccion=seccion, contexto=contexto, pagina=pagina,
        textos_paginacion=(g["botones"]["ver_mas"], g["botones"]["volver_inicio"]),
        **extra,
    )


# ===========================================================================
# Punto de entrada: app.py llama a esta función por cada mensaje
# ===========================================================================
def procesar(mensaje, nombre_perfil=""):
    tel = mensaje.get("from")
    if not tel:
        return
    with _candado(tel):
        s = _sesion(tel)
        if nombre_perfil:
            s["nombre"] = nombre_perfil

        tipo = mensaje.get("type")
        if tipo == "interactive":
            interactivo = mensaje.get("interactive", {})
            respuesta = interactivo.get("list_reply") or interactivo.get("button_reply") or {}
            _opcion(tel, s, respuesta.get("id", ""))
        elif tipo == "text":
            _texto(tel, s, mensaje.get("text", {}).get("body", ""))
        elif s["form"]:
            # Audio, foto, sticker… en medio de un formulario
            whatsapp.texto(tel, _general()["textos"]["solo_texto"])
            _preguntar(tel, s)
        else:
            _menu_principal(tel, s)


def _texto(tel, s, cuerpo):
    g = _general()
    palabra = normalizar(cuerpo)

    if palabra in [normalizar(p) for p in g["palabras_menu"]]:
        if s["form"]:
            s["form"] = None
            whatsapp.texto(tel, g["textos"]["formulario_cancelado"])
        return _menu_principal(tel, s)

    if tel in config.ADMIN_NUMEROS and palabra in ("resumen", "registros", "hoy"):
        return _resumen_admin(tel)

    if s["form"]:
        return _recibir_campo(tel, s, cuerpo.strip())

    # Cualquier otro texto ("hola", "buenas"…) muestra el menú
    _menu_principal(tel, s)


def _opcion(tel, s, id_):
    if id_ == "menu" or id_.startswith("m:"):
        s["form"] = None  # salir del menú abandona cualquier formulario a medias
    if id_ == "menu":
        return _menu_principal(tel, s)
    if id_.startswith("m:"):
        seccion = SECCIONES.get(id_[2:])
        return seccion(tel, s) if seccion else _menu_principal(tel, s)
    if id_.startswith("pag:"):
        try:
            _, contexto, pagina = id_.split(":")
            return PAGINAS[contexto](tel, s, int(pagina))
        except (ValueError, KeyError):
            return _menu_principal(tel, s)

    prefijo, _, valor = id_.partition(":")
    manejador = OPCIONES.get(prefijo)
    if manejador:
        return manejador(tel, s, valor)
    _menu_principal(tel, s)


# ===========================================================================
# Menú principal
# ===========================================================================
def _menu_principal(tel, s=None, pagina=0):
    g = _general()
    filas = [(f"m:{op['id']}", op["titulo"], op.get("descripcion", "")) for op in _activos(g["menu"])]
    _lista(tel, g["saludo"], g["botones"]["ver_menu"], filas, g["titulo_menu"], "menu", pagina,
           encabezado=g.get("encabezado"), pie=g.get("pie"))


# ===========================================================================
# 1. Admisiones
# ===========================================================================
def _admisiones(tel, s):
    a = cargar("admisiones")
    whatsapp.texto(tel, a["bienvenida"])
    _lista_grados_admision(tel, s, 0)


def _lista_grados_admision(tel, s, pagina):
    a = cargar("admisiones")
    filas = []
    for grado in a["grados"]:
        cupos = int(grado.get("cupos") or 0)
        etiqueta = a["etiqueta_con_cupos"] if cupos > 0 else a["etiqueta_sin_cupos"]
        filas.append((f"adm:{grado['id']}", grado["nombre"], formatear(etiqueta, cupos_texto=_cupos_texto(cupos))))
    _lista(tel, a["pregunta_grado"], a["boton_lista"], filas, "Grados", "adm", pagina)


def _admision_grado(tel, s, grado_id):
    a = cargar("admisiones")
    g = _general()
    grado = _buscar(a["grados"], grado_id)
    if not grado:
        return _menu_principal(tel, s)

    cupos = int(grado.get("cupos") or 0)
    if cupos > 0:
        whatsapp.texto(tel, formatear(a["con_cupos"], grado=grado["nombre"], cupos_texto=_cupos_texto(cupos)))
        _enviar_pdf(tel, a.get("pdf"))
        return _cerrar(tel, a["cierre_con_cupos"])

    texto = formatear(a["sin_cupos"], grado=grado["nombre"])
    espera = a.get("lista_espera", {})
    if espera.get("activo", True):
        _con_botones(tel, texto, [(f"esp:{grado_id}", espera["boton"]), _boton_menu(g), _boton_humano(g)])
    else:
        _cerrar(tel, texto)


def _enviar_pdf(tel, pdf):
    if not pdf or not pdf.get("archivo"):
        return
    archivo = pdf["archivo"]
    if archivo.startswith("http"):
        enlace = archivo
    elif config.BASE_URL:
        enlace = f"{config.BASE_URL}/static/{quote(archivo)}"
    else:
        print("⚠️  Falta BASE_URL en el .env: no se pudo enviar el PDF de admisiones.")
        return
    whatsapp.documento(tel, enlace, pdf.get("nombre_archivo", archivo), pdf.get("mensaje", ""))


def _lista_espera(tel, s, grado_id):
    grado = _buscar(cargar("admisiones")["grados"], grado_id)
    if not grado:
        return _menu_principal(tel, s)
    _iniciar_formulario(tel, s, "lista_espera", {"grado": grado["nombre"]})


# ===========================================================================
# 2. Cursos
# ===========================================================================
def _cursos(tel, s):
    c = cargar("cursos")
    if (c.get("aviso_mes") or "").strip():
        whatsapp.texto(tel, c["aviso_mes"])
    _lista_cursos(tel, s, 0)


def _lista_cursos(tel, s, pagina):
    c = cargar("cursos")
    filas = [
        (f"cur:{x['id']}", x["nombre"], x.get("descripcion_corta", "") if x.get("activo", True) else c["etiqueta_inactivo"])
        for x in c["cursos"]
    ]
    if not filas:
        return _cerrar(tel, c["sin_cursos"])
    _lista(tel, c["introduccion"], c["boton_lista"], filas, "Cursos", "cur", pagina)


def _curso(tel, s, curso_id):
    c = cargar("cursos")
    curso = _buscar(c["cursos"], curso_id)
    if not curso:
        return _menu_principal(tel, s)
    if not curso.get("activo", True):
        mensaje = curso.get("mensaje_inactivo") or c["mensaje_inactivo"]
        return _cerrar(tel, formatear(mensaje, curso=curso["nombre"]))

    partes = [f"*{curso['nombre']}*"]
    if curso.get("descripcion"):
        partes.append(curso["descripcion"])
    detalles = [
        f"{etiqueta} {curso[clave]}"
        for clave, etiqueta in (
            ("dirigido_a", "👥 *Dirigido a:*"),
            ("horario", "🗓️ *Horario:*"),
            ("lugar", "📍 *Lugar:*"),
            ("costo", "💲 *Costo:*"),
        )
        if curso.get(clave)
    ]
    if detalles:
        partes.append("\n".join(detalles))
    if curso.get("nota"):
        partes.append(f"📝 {curso['nota']}")
    if c.get("pie_curso"):
        partes.append(c["pie_curso"])
    _cerrar(tel, "\n\n".join(partes))


# ===========================================================================
# 3. Salidas pedagógicas
# ===========================================================================
def _salidas(tel, s):
    sa = cargar("salidas")
    activas = _activos(sa["salidas"])
    if not activas:
        return _cerrar(tel, sa["sin_salidas"])

    bloques = [sa["introduccion"]]
    for salida in activas:
        lineas = [f"🚌 *{salida['titulo']}*"]
        for clave, etiqueta in (
            ("fecha", "📅 *Fecha:*"),
            ("lugar", "📍 *Lugar:*"),
            ("grados", "👥 *Grados:*"),
            ("costo", "💲 *Costo:*"),
            ("incluye", "✅ *Incluye:*"),
            ("fecha_limite_pago", "⏳ *Pago hasta:*"),
        ):
            if salida.get(clave):
                lineas.append(f"{etiqueta} {salida[clave]}")
        if salida.get("nota"):
            lineas.append(f"📝 {salida['nota']}")
        bloques.append("\n".join(lineas))
    if sa.get("pie"):
        bloques.append(sa["pie"])
    _cerrar(tel, "\n\n".join(bloques))


# ===========================================================================
# 4. Avisos importantes
# ===========================================================================
def _informacion(tel, s):
    _lista_avisos(tel, s, 0)


def _lista_avisos(tel, s, pagina):
    i = cargar("informacion")
    avisos = _activos(i["avisos"])
    if not avisos:
        return _cerrar(tel, i["sin_avisos"])
    filas = [(f"inf:{x['id']}", x["titulo"], x.get("resumen", "")) for x in avisos]
    _lista(tel, i["introduccion"], i["boton_lista"], filas, "Avisos", "inf", pagina)


def _aviso(tel, s, aviso_id):
    aviso = _buscar(cargar("informacion")["avisos"], aviso_id)
    if not aviso:
        return _menu_principal(tel, s)
    _cerrar(tel, f"*{aviso['titulo']}*\n\n{aviso['mensaje']}")


# ===========================================================================
# 5. Certificados
# ===========================================================================
def _certificados(tel, s):
    _lista_certificados(tel, s, 0)


def _lista_certificados(tel, s, pagina):
    k = cargar("certificados")
    certificados = _activos(k["certificados"])
    if not certificados:
        return _cerrar(tel, k["sin_certificados"])
    filas = [
        (f"cer:{x['id']}", x["nombre"], f"💲 {x['precio']}" if x.get("precio") else x.get("descripcion", ""))
        for x in certificados
    ]
    _lista(tel, k["introduccion"], k["boton_lista"], filas, "Certificados", "cer", pagina)


def _certificado(tel, s, certificado_id):
    k = cargar("certificados")
    g = _general()
    cert = _buscar(k["certificados"], certificado_id)
    if not cert:
        return _menu_principal(tel, s)
    partes = [f"📄 *{cert['nombre']}*"]
    if cert.get("descripcion"):
        partes.append(cert["descripcion"])
    detalles = [
        f"{etiqueta} {cert[clave]}"
        for clave, etiqueta in (
            ("precio", "💲 *Valor:*"),
            ("tiempo_entrega", "⏱️ *Entrega:*"),
            ("requisitos", "📋 *Requisitos:*"),
        )
        if cert.get(clave)
    ]
    if detalles:
        partes.append("\n".join(detalles))
    if k.get("pie_detalle"):
        partes.append(k["pie_detalle"])
    _con_botones(tel, "\n\n".join(partes), [(f"cers:{certificado_id}", k["formulario"]["boton_solicitar"]), _boton_menu(g)])


def _solicitar_certificado(tel, s, certificado_id):
    cert = _buscar(cargar("certificados")["certificados"], certificado_id)
    if not cert:
        return _menu_principal(tel, s)
    _iniciar_formulario(tel, s, "certificado", {"tipo": cert["nombre"]})


# ===========================================================================
# 6. Almuerzo
# ===========================================================================
def _almuerzo(tel, s):
    al = cargar("almuerzo")
    g = _general()
    if not al.get("inscripciones_abiertas", True):
        return _cerrar(tel, al["mensaje_cerrado"])
    _con_botones(tel, al["informacion"], [("alm:inscribir", al["formulario"]["boton_inscribir"]), _boton_menu(g)])


def _opcion_almuerzo(tel, s, valor):
    if valor == "inscribir" and cargar("almuerzo").get("inscripciones_abiertas", True):
        return _iniciar_formulario(tel, s, "almuerzo")
    _menu_principal(tel, s)


# ===========================================================================
# 7. Llegadas y salidas
# ===========================================================================
def _entrada_salida(tel, s):
    e = cargar("entrada_salida")
    g = _general()
    _con_botones(tel, e["informacion"], [
        ("es:tarde", e["llegada_tarde"]["boton"]),
        ("es:salida", e["salida_temprana"]["boton"]),
        _boton_menu(g),
    ])


def _opcion_entrada_salida(tel, s, valor):
    tipo = {"tarde": "llegada_tarde", "salida": "salida_temprana"}.get(valor)
    if tipo:
        return _iniciar_formulario(tel, s, tipo)
    _menu_principal(tel, s)


# ===========================================================================
# 8. Atención humana
# ===========================================================================
def _humano(tel, s):
    g = _general()
    h = g["humano"]
    enlace = f"https://wa.me/{h['numero']}"
    if h.get("mensaje_prellenado"):
        enlace += "?text=" + quote(h["mensaje_prellenado"])
    _con_botones(tel, formatear(h["mensaje"], enlace=enlace), [_boton_menu(g)])


# ===========================================================================
# Formularios
# ===========================================================================
def _config_formulario(tipo):
    archivo, clave, campos = FORMULARIOS[tipo]
    return cargar(archivo)[clave], campos


def _iniciar_formulario(tel, s, tipo, prellenado=None):
    cfg, campos = _config_formulario(tipo)
    datos = dict(prellenado or {})
    s["form"] = {
        "tipo": tipo,
        "datos": datos,
        "orden": list(datos.keys()) + [c for c in campos if c not in datos],
        "pendiente": None,
    }
    if cfg.get("introduccion"):
        whatsapp.texto(tel, formatear(cfg["introduccion"], **datos))
    _siguiente_campo(tel, s)


def _siguiente_campo(tel, s):
    formulario = s["form"]
    _, campos = _config_formulario(formulario["tipo"])
    for campo in campos:
        if campo not in formulario["datos"]:
            formulario["pendiente"] = campo
            return _preguntar(tel, s)
    formulario["pendiente"] = None
    _confirmar(tel, s)


def _preguntar(tel, s):
    formulario = s["form"]
    campo = formulario["pendiente"]
    if campo is None:
        return _confirmar(tel, s)
    if campo == "grado":
        return _lista_grados_formulario(tel, s, 0)
    cfg, _ = _config_formulario(formulario["tipo"])
    whatsapp.texto(tel, formatear(cfg["preguntas"][campo], **formulario["datos"]))


def _lista_grados_formulario(tel, s, pagina):
    formulario = s.get("form")
    if not formulario or formulario["pendiente"] != "grado":
        return _menu_principal(tel, s)
    g = _general()
    cfg, _ = _config_formulario(formulario["tipo"])
    pregunta = cfg.get("preguntas", {}).get("grado") or g["textos"]["pregunta_grado"]
    filas = [(f"fg:{i}", nombre, "") for i, nombre in enumerate(g["grados"])]
    _lista(tel, formatear(pregunta, **formulario["datos"]), g["botones"]["elegir_grado"], filas, "Grados", "fg", pagina)


def _recibir_campo(tel, s, valor):
    formulario = s["form"]
    campo = formulario["pendiente"]
    if campo is None:
        return _confirmar(tel, s)  # esperaba Confirmar/Cancelar
    if campo == "grado":
        whatsapp.texto(tel, _general()["textos"]["usa_la_lista"])
        return _preguntar(tel, s)
    if not valor:
        return _preguntar(tel, s)
    formulario["datos"][campo] = whatsapp.cortar(valor, 200)
    _siguiente_campo(tel, s)


def _elegir_grado(tel, s, indice):
    formulario = s.get("form")
    grados = _general()["grados"]
    if not formulario or formulario["pendiente"] != "grado" or not indice.isdigit() or int(indice) >= len(grados):
        return _menu_principal(tel, s)
    formulario["datos"]["grado"] = grados[int(indice)]
    _siguiente_campo(tel, s)


def _etiqueta(campo):
    return _general()["etiquetas"].get(campo, campo.capitalize())


def _confirmar(tel, s):
    formulario = s["form"]
    g = _general()
    cfg, _ = _config_formulario(formulario["tipo"])
    lineas = [formatear(g["textos"]["confirmar_titulo"], titulo=cfg["titulo"]), ""]
    for campo in formulario["orden"]:
        lineas.append(f"• *{_etiqueta(campo)}:* {formulario['datos'].get(campo, '')}")
    lineas += ["", g["textos"]["confirmar_pregunta"]]
    _con_botones(tel, "\n".join(lineas), [("conf:si", g["botones"]["confirmar"]), ("conf:no", g["botones"]["cancelar"])])


def _respuesta_confirmacion(tel, s, valor):
    formulario = s.get("form")
    if not formulario or formulario["pendiente"] is not None:
        return _menu_principal(tel, s)
    if valor == "no":
        s["form"] = None
        return _cerrar(tel, _general()["textos"]["formulario_cancelado"])
    if valor == "si":
        return _finalizar(tel, s)
    _menu_principal(tel, s)


def _finalizar(tel, s):
    formulario = s["form"]
    s["form"] = None
    cfg, _ = _config_formulario(formulario["tipo"])
    datos = formulario["datos"]

    registros.guardar(formulario["tipo"], datos, tel, s.get("nombre", ""))

    ahora = datetime.now(config.ZONA)
    aviso = [cfg.get("titulo_notificacion") or f"🔔 {cfg['titulo']}", ""]
    aviso += [f"• *{_etiqueta(campo)}:* {datos.get(campo, '')}" for campo in formulario["orden"]]
    aviso += ["", f"📱 Acudiente: {s.get('nombre') or 'Sin nombre'} (+{tel})", f"🕒 {ahora:%d/%m/%Y %I:%M %p}"]
    registros.notificar_admins("\n".join(aviso))

    _cerrar(tel, formatear(cfg["confirmacion"], **datos))


# ===========================================================================
# Administración: un número de ADMIN_NUMEROS escribe "resumen"
# ===========================================================================
def _resumen_admin(tel):
    hoy = datetime.now(config.ZONA).date()
    lista_registros = registros.listar(fecha=hoy)
    lineas = [f"📋 *Resumen de hoy* ({hoy:%d/%m/%Y})"]
    if not lista_registros:
        lineas.append("\nTodavía no hay registros.")
    else:
        por_tipo = {}
        for registro in reversed(lista_registros):  # en orden de llegada
            por_tipo.setdefault(registro["tipo"], []).append(registro)
        for tipo, items in por_tipo.items():
            lineas += ["", f"*{registros.NOMBRES_TIPO.get(tipo, tipo)}* ({len(items)})"]
            for registro in items:
                datos = registro.get("datos") or {}
                extra = datos.get("hora") or datos.get("dia") or datos.get("tipo") or ""
                partes = [registro.get("estudiante"), registro.get("grado"), extra]
                lineas.append("• " + " – ".join(p for p in partes if p))
    if config.BASE_URL and config.ADMIN_KEY:
        lineas += ["", f"🔗 Ver todo: {config.BASE_URL}/registros?clave={quote(config.ADMIN_KEY)}"]
    whatsapp.texto(tel, "\n".join(lineas))


# ===========================================================================
# Tablas de ruteo (los ids de general.json → menu deben existir en SECCIONES)
# ===========================================================================
SECCIONES = {
    "admisiones": _admisiones,
    "cursos": _cursos,
    "salidas": _salidas,
    "informacion": _informacion,
    "certificados": _certificados,
    "almuerzo": _almuerzo,
    "entrada_salida": _entrada_salida,
    "humano": _humano,
}

OPCIONES = {
    "adm": _admision_grado,
    "esp": _lista_espera,
    "cur": _curso,
    "inf": _aviso,
    "cer": _certificado,
    "cers": _solicitar_certificado,
    "alm": _opcion_almuerzo,
    "es": _opcion_entrada_salida,
    "fg": _elegir_grado,
    "conf": _respuesta_confirmacion,
}

PAGINAS = {
    "menu": _menu_principal,
    "adm": _lista_grados_admision,
    "cur": _lista_cursos,
    "inf": _lista_avisos,
    "cer": _lista_certificados,
    "fg": _lista_grados_formulario,
}
