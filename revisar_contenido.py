"""
Revisa los archivos de contenido/ antes de hacer git push:
  • que todos los .json estén bien escritos (comas, comillas, llaves)
  • que los títulos y botones respeten los límites de WhatsApp
  • que no se repitan ids
  • lista los textos que aún dicen [EDITAR]
  • muestra los cupos actuales de admisiones

Uso:  python revisar_contenido.py
"""
import json
import os
import sys

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contenido")
ARCHIVOS = ["general", "admisiones", "cursos", "salidas", "informacion", "certificados", "almuerzo", "entrada_salida"]
SECCIONES_VALIDAS = {"admisiones", "cursos", "salidas", "informacion", "certificados", "almuerzo", "entrada_salida", "humano"}

errores, avisos = [], []


def largo(texto):
    return len((texto or "").encode("utf-16-le")) // 2


def limite(archivo, ruta, texto, maximo):
    if texto is not None and largo(texto) > maximo:
        errores.append(f"{archivo}.json → {ruta}: tiene {largo(texto)} caracteres (máximo {maximo}): «{texto}»")


def requerido(archivo, datos, *claves):
    for clave in claves:
        if clave not in datos:
            errores.append(f"{archivo}.json → falta el campo '{clave}'")


def ids_unicos(archivo, items, nombre):
    vistos = set()
    for item in items:
        id_ = str(item.get("id", ""))
        if not id_:
            errores.append(f"{archivo}.json → un elemento de '{nombre}' no tiene id")
        elif ":" in id_ or " " in id_:
            errores.append(f"{archivo}.json → el id '{id_}' no puede tener espacios ni ':'")
        elif id_ in vistos:
            errores.append(f"{archivo}.json → el id '{id_}' está repetido en '{nombre}'")
        vistos.add(id_)


def buscar_editar(archivo, valor, ruta=""):
    if isinstance(valor, dict):
        for clave, sub in valor.items():
            if not clave.startswith("_"):
                buscar_editar(archivo, sub, f"{ruta}.{clave}" if ruta else clave)
    elif isinstance(valor, list):
        for i, sub in enumerate(valor):
            etiqueta = sub.get("id") or sub.get("titulo") if isinstance(sub, dict) else i
            buscar_editar(archivo, sub, f"{ruta}[{etiqueta}]")
    elif isinstance(valor, str) and "[EDITAR" in valor:
        avisos.append(f"{archivo}.json → {ruta}")


def main():
    contenido = {}
    for nombre in ARCHIVOS:
        ruta = os.path.join(CARPETA, nombre + ".json")
        try:
            with open(ruta, encoding="utf-8") as f:
                contenido[nombre] = json.load(f)
        except FileNotFoundError:
            errores.append(f"No existe contenido/{nombre}.json")
        except json.JSONDecodeError as e:
            errores.append(f"{nombre}.json está mal escrito en la línea {e.lineno}, columna {e.colno}: {e.msg}")

    if errores:
        return terminar()

    g = contenido["general"]
    requerido("general", g, "saludo", "menu", "botones", "textos", "grados", "etiquetas", "humano", "palabras_menu")
    limite("general", "saludo", g.get("saludo"), 1024)
    limite("general", "encabezado", g.get("encabezado"), 60)
    limite("general", "pie", g.get("pie"), 60)
    limite("general", "titulo_menu", g.get("titulo_menu"), 24)
    activos = [m for m in g.get("menu", []) if m.get("activo", True)]
    if len(activos) > 10:
        errores.append("general.json → el menú principal tiene más de 10 opciones activas")
    ids_unicos("general", g.get("menu", []), "menu")
    for m in g.get("menu", []):
        if m.get("id") not in SECCIONES_VALIDAS:
            errores.append(f"general.json → el id de menú '{m.get('id')}' no existe. Válidos: {', '.join(sorted(SECCIONES_VALIDAS))}")
        limite("general", f"menu[{m.get('id')}].titulo", m.get("titulo"), 24)
        limite("general", f"menu[{m.get('id')}].descripcion", m.get("descripcion"), 72)
    for clave, texto in g.get("botones", {}).items():
        limite("general", f"botones.{clave}", texto, 24 if clave in ("ver_mas", "volver_inicio") else 20)
    for grado in g.get("grados", []):
        limite("general", "grados", grado, 24)
    numero = g.get("humano", {}).get("numero", "")
    if not numero.isdigit():
        avisos.append("general.json → humano.numero todavía no es un número real (solo dígitos, ej: 573001234567)")

    a = contenido["admisiones"]
    requerido("admisiones", a, "bienvenida", "pregunta_grado", "boton_lista", "grados", "con_cupos", "sin_cupos")
    limite("admisiones", "boton_lista", a.get("boton_lista"), 20)
    limite("admisiones", "pregunta_grado", a.get("pregunta_grado"), 1024)
    limite("admisiones", "lista_espera.boton", a.get("lista_espera", {}).get("boton"), 20)
    ids_unicos("admisiones", a.get("grados", []), "grados")
    for grado in a.get("grados", []):
        limite("admisiones", f"grados[{grado.get('id')}].nombre", grado.get("nombre"), 24)
        if not isinstance(grado.get("cupos"), int) or grado["cupos"] < 0:
            errores.append(f"admisiones.json → cupos de '{grado.get('id')}' debe ser un número entero (0 o más), sin comillas")
    pdf = a.get("pdf", {}).get("archivo", "")
    if pdf and not pdf.startswith("http") and not os.path.exists(os.path.join(os.path.dirname(CARPETA), "static", pdf)):
        errores.append(f"admisiones.json → no existe el archivo static/{pdf}")

    for nombre, clave_lista, boton in (("cursos", "cursos", "boton_lista"), ("informacion", "avisos", "boton_lista"),
                                       ("certificados", "certificados", "boton_lista")):
        datos = contenido[nombre]
        requerido(nombre, datos, "introduccion", boton, clave_lista)
        limite(nombre, boton, datos.get(boton), 20)
        limite(nombre, "introduccion", datos.get("introduccion"), 1024)
        ids_unicos(nombre, datos.get(clave_lista, []), clave_lista)
        for item in datos.get(clave_lista, []):
            limite(nombre, f"{clave_lista}[{item.get('id')}].nombre/titulo", item.get("nombre") or item.get("titulo"), 24)
            limite(nombre, f"{clave_lista}[{item.get('id')}].descripcion_corta", item.get("descripcion_corta"), 72)
            limite(nombre, f"{clave_lista}[{item.get('id')}].resumen", item.get("resumen"), 72)

    limite("certificados", "formulario.boton_solicitar", contenido["certificados"].get("formulario", {}).get("boton_solicitar"), 20)
    limite("almuerzo", "formulario.boton_inscribir", contenido["almuerzo"].get("formulario", {}).get("boton_inscribir"), 20)
    for clave in ("llegada_tarde", "salida_temprana"):
        limite("entrada_salida", f"{clave}.boton", contenido["entrada_salida"].get(clave, {}).get("boton"), 20)

    # Cada formulario debe tener una pregunta para cada campo (el grado usa la pregunta general)
    try:
        sys.path.insert(0, os.path.dirname(CARPETA))
        from flujos import FORMULARIOS
        for tipo, (archivo, clave, campos) in FORMULARIOS.items():
            cfg = contenido[archivo].get(clave, {})
            requerido(f"{archivo}", cfg, "titulo", "confirmacion", "preguntas")
            for campo in campos:
                if campo != "grado" and campo not in cfg.get("preguntas", {}):
                    errores.append(f"{archivo}.json → {clave}.preguntas no tiene la pregunta '{campo}'")
    except ImportError:
        pass

    # Textos pendientes (se ignoran los elementos apagados)
    for nombre, datos in contenido.items():
        copia = json.loads(json.dumps(datos))
        for clave in ("salidas", "cursos", "avisos", "certificados", "menu"):
            if isinstance(copia.get(clave), list):
                copia[clave] = [x for x in copia[clave] if x.get("activo", True)]
        buscar_editar(nombre, copia)

    print("\n🎓 Cupos de admisiones:")
    for grado in a.get("grados", []):
        cupos = grado.get("cupos", 0)
        print(f"   {'✅' if cupos else '❌'} {grado.get('nombre', ''):<12} {cupos}")
    return terminar()


def terminar():
    if avisos:
        print(f"\n✏️  Textos pendientes por editar ({len(avisos)}):")
        for aviso in avisos:
            print("   •", aviso)
    if errores:
        print(f"\n❌ Errores que debes corregir ({len(errores)}):")
        for error in errores:
            print("   •", error)
        sys.exit(1)
    print("\n✅ El contenido está bien escrito. Puedes hacer git push.\n")


if __name__ == "__main__":
    main()
