# Bot de WhatsApp — CREAR

Menú automático para WhatsApp (Cloud API de Meta) hecho en Flask.
Los papás consultan admisiones, cursos, salidas, avisos, certificados y almuerzo,
y registran llegadas tarde, salidas temprano, almuerzos y solicitudes de certificado.
Cada registro se guarda y llega como notificación al WhatsApp principal del colegio.

## Estructura

```
app.py                 Servidor: webhook de Meta y página /registros
flujos.py              Lógica de la conversación (menús, submenús y formularios)
whatsapp.py            Envío de mensajes a Meta (texto, listas, botones, PDF)
registros.py           Guarda los registros (Supabase o archivo) y notifica a administración
config.py              Lee las variables del .env
contenido.py           Lee los textos de la carpeta contenido/
contenido/             ← TODOS los textos del bot. Esto es lo que editas durante el año
static/admisiones.pdf  PDF que se envía en admisiones (reemplázalo por el real)
templates/             Página web de registros
simulador.py           Prueba el bot en la terminal, sin WhatsApp
revisar_contenido.py   Revisa los .json antes de subir cambios
supabase.sql           Tabla para guardar registros en Supabase
```

## Editar textos, cupos, costos y fechas

1. Abre el archivo de `contenido/` que necesitas (cada uno trae una nota `_ayuda`).
2. Cambia el texto entre comillas. No borres comas, llaves ni comillas.
3. Revisa y prueba:
   ```bash
   python revisar_contenido.py
   python simulador.py
   ```
4. Sube el cambio (Render lo publica solo en 1–2 minutos):
   ```bash
   git add .
   git commit -m "Actualizo cupos de noviembre"
   git push
   ```

| Quiero… | Archivo | Qué cambio |
|---|---|---|
| Actualizar cupos | `admisiones.json` | `"cupos": 3` (0 = sin cupos) |
| Avisar que este mes los cursos cuestan la mitad | `cursos.json` | `"aviso_mes": "🏖️ Por vacaciones…"` |
| Un curso sin clases este mes | `cursos.json` | `"activo": false` en ese curso |
| Publicar una salida pedagógica | `salidas.json` | `"activo": true` y los datos |
| Agregar un aviso | `informacion.json` | Copiar un bloque de `avisos` con otro `id` |
| Cerrar almuerzos en vacaciones | `almuerzo.json` | `"inscripciones_abiertas": false` |

Formato de WhatsApp: `*negrita*`, `_cursiva_`, `\n` = salto de línea.

## Correr en tu Mac

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # y llena los valores
python simulador.py --demo  # prueba sin WhatsApp
python app.py               # servidor real (en otra pestaña: ngrok)
```

```bash
ngrok http 5000 --url https://squatting-ludicrous-ninetieth.ngrok-free.dev
```

## Administración

- **Notificaciones:** llegan a los números de `ADMIN_NUMEROS`.
- **Ventana de 24 h de WhatsApp:** el bot solo puede escribirle texto libre a un número
  que le haya escrito en las últimas 24 h. Desde el número principal escribe **resumen**
  al bot cada mañana: recibes el resumen del día y quedas habilitado para las notificaciones.
  Para no depender de eso, crea una plantilla de tipo *Utilidad* en Meta con un parámetro
  (`{{1}}`) y pon su nombre en `NOTIF_TEMPLATE`.
- **Página de registros:** `BASE_URL/registros?clave=TU_ADMIN_KEY`.

## Desplegar en Render

1. New → Web Service → conectar este repo.
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app --workers 1 --threads 8 --timeout 60`
   (un solo worker: las conversaciones en curso viven en memoria)
4. Environment: las mismas variables del `.env`, con `BASE_URL=https://TU-APP.onrender.com`.
5. En Meta → Webhooks: `https://TU-APP.onrender.com/webhook`.

En Render los archivos locales se borran en cada reinicio: configura `SUPABASE_URL` y
`SUPABASE_KEY` (service_role) y crea la tabla con `supabase.sql`.
