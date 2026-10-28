import os
import sqlite3
import re
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# 1. Mini servidor web para mantener activo el servicio en PythonAnywhere
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "¡El bot inteligente de Frio Express está activo!"

def run_web():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# 2. Inicializar la base de datos local
def init_db():
    conn = sqlite3.connect('revisiones.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS revisiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            no_eco TEXT,
            plantilla TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Memoria temporal para rastrear qué unidad está consultando cada usuario para actualizarla con fotos
ultima_unidad_usuario = {}

async def guardar_plantilla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if not texto:
        return

    texto_upper = texto.upper()
    
    # Filtro inteligente amplio: detecta si el mensaje es un reporte de unidad buscando palabras clave o códigos
    es_reporte = any(k in texto_upper for k in ["ECO", "UNIDAD", "REVISIÓN", "REVISION", "T-", "KM", "KILOMETRAJE"])
    if not es_reporte:
        return  # Si es una charla normal del grupo, la ignora

    # Extraer el número económico de forma flexible (ej. T-2191, T2191, etc.)
    no_eco = "Desconocido"
    match_eco = re.search(r'T[-]?\d+', texto_upper)
    if match_eco:
        no_eco = match_eco.group(0).replace("T", "T-")
    else:
        for linea in texto.split('\n'):
            if "ECO" in linea.upper() or "UNIDAD" in linea.upper():
                partes = linea.split(":")
                if len(partes) > 1:
                    no_eco = partes[-1].strip()
                break

    # Procesamiento inteligente del formato para estandarizarlo y forzar Aguascalientes
    lineas = texto.split('\n')
    nuevo_formato = []
    lugar_encontrado = False

    for linea in lineas:
        linea_upper = linea.upper()
        # Forzar ubicación siempre en Aguascalientes
        if "LUGAR" in linea_upper or "UBICACION" in linea_upper:
            nuevo_formato.append("Lugar: Aguascalientes")
            lugar_encontrado = True
        else:
            nuevo_formato.append(linea)

    if not lugar_encontrado:
        nuevo_formato.insert(0, "Lugar: Aguascalientes")

    plantilla_final = "\n".join(nuevo_formato)

    # Guardar en SQLite
    conn = sqlite3.connect('revisiones.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO revisiones (no_eco, plantilla) VALUES (?, ?)', (no_eco, plantilla_final))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ ¡Plantilla de la unidad {no_eco} procesada y guardada con éxito! (Lugar fijado en Aguascalientes)")

async def buscar_unidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Escribe el número económico. Ejemplo: /buscar T-2191")
        return

    no_eco_buscado = context.args[0].strip().upper()

    conn = sqlite3.connect('revisiones.db')
    cursor = conn.cursor()
    cursor.execute('SELECT plantilla FROM revisiones WHERE UPPER(no_eco) LIKE ? ORDER BY id DESC LIMIT 1', (f"%{no_eco_buscado}%",))
    resultado = cursor.fetchone()
    conn.close()

    if resultado:
        plantilla_completa = resultado[0]
        # Guardar en memoria de usuario para la foto posterior
        ultima_unidad_usuario[update.effective_user.id] = {
            "no_eco": no_eco_buscado,
            "plantilla": plantilla_completa
        }
        await update.message.reply_text(f"🔍 *Formato completo encontrado:*\n\n{plantilla_completa}\n\n📸 *Siguiente paso:* Envía una foto del odómetro para actualizar automáticamente los kilómetros en esta plantilla.")
    else:
        await update.message.reply_text(f"❌ No se encontró ninguna revisión guardada para la unidad: {no_eco_buscado}")

async def modificar_con_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ultima_unidad_usuario:
        await update.message.reply_text("⚠️ Primero busca una unidad usando el comando `/buscar [número]` antes de mandar la foto del odómetro.")
        return

    # Extraer el texto que acompañe a la foto (si escribieron el kilometraje) o asignar un valor predeterminado
    caption = update.message.caption or "Actualizado por fotografía de odómetro"
    
    datos = ultima_unidad_usuario[user_id]
    plantilla = datos["plantilla"]

    # Reemplazar inteligentemente la línea de kilometraje u odómetro dentro de la plantilla
    lineas = plantilla.split('\n')
    nueva_plantilla = []
    km_actualizado = False

    for l in lineas:
        l_upper = l.upper()
        if "KM" in l_upper or "KILOMETRAJE" in l_upper or "ODOMETRO" in l_upper or "ODÓMETRO" in l_upper:
            nueva_plantilla.append(f"Kilometraje / Odómetro: {caption}")
            km_actualizado = True
        else:
            nueva_plantilla.append(l)

    if not km_actualizado:
        nueva_plantilla.append(f"Kilometraje: {caption}")

    plantilla_actualizada = "\n".join(nueva_plantilla)

    await update.message.reply_text(f"🔄 *Plantilla actualizada con el nuevo odómetro:*\n\n{plantilla_actualizada}")

def main():
    keep_alive()
    
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("buscar", buscar_unidad))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), guardar_plantilla))
    app.add_handler(MessageHandler(filters.PHOTO, modificar_con_foto))

    print("🤖 Bot inteligente de Frio Express activo en la nube...")
    app.run_polling()

if __name__ == '__main__':
    main()
