import os
import sqlite3
import re
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# 1. Mini servidor web para mantener activo el servicio
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "¡El bot de Frio Express está vivo y activo!"

def run_web():
    app_flask.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# 2. Base de datos
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

ultima_unidad_usuario = {}

async def guardar_plantilla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if not texto:
        return

    # Filtro inteligente: Buscamos si el mensaje parece un reporte buscando un número económico (ej. T-2191 o T-xxxx) o palabras clave
    texto_upper = texto.upper()
    tiene_formato = any(palabra in texto_upper for palabra in ["ECO", "UNIDAD", "REVISIÓN", "REVISION", "T-"])

    if tiene_formato:
        no_eco = "Desconocido"
        
        # Intentamos extraer el número económico de forma flexible usando expresiones regulares
        match_eco = re.search(r'T[-]?\d+', texto_upper)
        if match_eco:
            no_eco = match_eco.group(0)
        else:
            # Si no tiene T-, buscamos después de la palabra Eco
            for linea in texto.split('\n'):
                if "ECO" in linea.upper() or "UNIDAD" in linea.upper():
                    partes = linea.split(":")
                    if len(partes) > 1:
                        no_eco = partes[-1].strip()
                    break

        # Forzar que el lugar sea siempre Aguascalientes de manera automática
        lineas = texto.split('\n')
        nuevo_texto = []
        lugar_encontrado = False
        
        for l in lineas:
            if "LUGAR" in l.upper():
                nuevo_texto.append("Lugar: Aguascalientes")
                lugar_encontrado = True
            else:
                nuevo_texto.append(l)
        
        if not lugar_encontrado:
            nuevo_texto.insert(0, "Lugar: Aguascalientes")
            
        plantilla_final = "\n".join(nuevo_texto)
        
        # Guardar en la base de datos
        conn = sqlite3.connect('revisiones.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO revisiones (no_eco, plantilla) VALUES (?, ?)', (no_eco, plantilla_final))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ ¡Plantilla de la unidad {no_eco} guardada automáticamente (Lugar: Aguascalientes)!")

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
        ultima_unidad_usuario[update.effective_user.id] = {
            "no_eco": no_eco_buscado,
            "plantilla": plantilla_completa
        }
        await update.message.reply_text(f"🔍 *Plantilla encontrada:*\n\n{plantilla_completa}\n\n📸 *Tip:* Envía una foto del odómetro para actualizar automáticamente su kilometraje.")
    else:
        await update.message.reply_text(f"❌ No se encontró revisión para la unidad: {no_eco_buscado}")

async def modificar_con_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ultima_unidad_usuario:
        await update.message.reply_text("⚠️ Primero busca una unidad con /buscar [número] antes de enviar la foto del odómetro.")
        return

    caption = update.message.caption or "Actualizado por foto"
    datos = ultima_unidad_usuario[user_id]
    plantilla = datos["plantilla"]
    
    # Reemplazar el kilometraje en la plantilla de forma inteligente
    lineas = plantilla.split('\n')
    nueva_plantilla = []
    km_actualizado = False
    
    for l in lineas:
        if "KM" in l.upper() or "KILOMETRAJE" in l.upper() or "ODOMETRO" in l.upper():
            nueva_plantilla.append(f"Kilometraje / Odómetro: {caption}")
            km_actualizado = True
        else:
            nueva_plantilla.append(l)
            
    if not km_actualizado:
        nueva_plantilla.append(f"Kilometraje: {caption}")
        
    plantilla_actualizada = "\n".join(nueva_plantilla)

    await update.message.reply_text(f"🔄 *Plantilla modificada con el odómetro:*\n\n{plantilla_actualizada}")

def main():
    keep_alive()
    
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("buscar", buscar_unidad))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), guardar_plantilla))
    app.add_handler(MessageHandler(filters.PHOTO, modificar_con_foto))

    print("🤖 Bot de Frio Express inteligente activo...")
    app.run_polling()

if __name__ == '__main__':
    main()
