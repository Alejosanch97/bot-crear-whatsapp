"""
Configuración del bot.
Todo sale de variables de entorno: el archivo .env en tu Mac, o la pestaña
Environment en Render. Aquí no se escribe ningún secreto.
"""
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _numeros(nombre):
    """Convierte '57300..., +57 311...' en ['57300...', '57311...']."""
    crudo = os.getenv(nombre, "")
    return [n.replace("+", "").replace(" ", "").strip() for n in crudo.split(",") if n.strip()]


# Meta / WhatsApp
WA_TOKEN = os.getenv("WA_TOKEN", "")
WA_PHONE_ID = os.getenv("WA_PHONE_ID", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v25.0")
APP_SECRET = os.getenv("APP_SECRET", "")  # opcional: valida que los mensajes vengan de Meta

# Dirección pública del bot (ngrok o Render). Se usa para enviar el PDF de admisiones.
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")

# Administración: números que reciben las notificaciones y clave de la página /registros
ADMIN_NUMEROS = _numeros("ADMIN_NUMEROS")
ADMIN_KEY = os.getenv("ADMIN_KEY", "")

# Supabase (opcional). Si está vacío, los registros se guardan en data/registros.jsonl
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# Plantilla de Meta para notificar cuando la ventana de 24 h está cerrada (opcional)
NOTIF_TEMPLATE = os.getenv("NOTIF_TEMPLATE", "")
NOTIF_TEMPLATE_LANG = os.getenv("NOTIF_TEMPLATE_LANG", "es")

ZONA = ZoneInfo(os.getenv("ZONA_HORARIA", "America/Bogota"))
