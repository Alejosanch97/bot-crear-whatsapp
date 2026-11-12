"""
Lee los textos del bot desde la carpeta contenido/.
Se leen en cada mensaje, así que al editar un .json en tu Mac el cambio se ve
de inmediato (en Render, después del git push).
"""
import json
import os

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contenido")


def cargar(nombre):
    with open(os.path.join(CARPETA, nombre + ".json"), encoding="utf-8") as archivo:
        return json.load(archivo)
