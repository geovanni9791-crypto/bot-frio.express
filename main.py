import os
import sqlite3
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

# 2. Base de datos con soporte para almacenar la última unidad consultada por usuario
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

# Memoria temporal para saber qué unidad está modificando cada usuario con fotos
ultima_unidad_usuario = {}

async def guardar_plantilla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto and "FRIO EXPRESS" in texto:
        no_eco = "Desconocido"
        for linea in texto.split('\n'):
            if "No. Eco" in linea or "Eco.:" in linea or "Eco" in linea:
                no_eco = linea.split(":")[-1].strip()
                break
        
        # Aseguramos que el lugar siempre sea Aguascalientes en el texto guardado
        if "Lugar:" in texto:
            lineas = texto.split('\n')
            nuevo_texto = []
            for l in lineas:
                if "Lugar:" in l:
                    nuevo_texto.append("Lugar: Aguascalientes")
                else:
                    nuevo_texto.append(l)
            texto = "\n".join(nuevo_texto)
        
        conn = sqlite3.connect('revisiones.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO revisiones (no_eco, plantilla) VALUES (?, ?)', (no_eco, texto))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ ¡Plantilla completa de la unidad {no_eco} guardada con éxito! (Lugar fijado en Aguascalientes)")

async def buscar_unidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Escribe el número económico. Ejemplo: /buscar T-2191")
        return

    no_eco_buscado = context.args[0].strip()

    conn = sqlite3.connect('revisiones.db')
    cursor = conn.cursor()
    cursor.execute('SELECT plantilla FROM revisiones WHERE no_eco LIKE ? ORDER BY id DESC LIMIT 1', (f"%{no_eco_buscado}%",))
    resultado = cursor.fetchone()
    conn.close()

    if resultado:
        plantilla_completa = resultado[0]
        # Guardamos en memoria qué unidad está consultando este usuario
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

    # Como mandó foto, le pedimos simular el odómetro o detectamos la intención
    # (Aquí simularemos la lectura del odómetro o puedes capturar el texto que acompañe a la foto)
    caption = update.message.caption or "Odómetro actualizado"
    
    datos = ultima_unidad_usuario[user_id]
    plantilla = datos["plantilla"]
    
    # Reemplazamos o agregamos el kilometraje en la plantilla
    if "Km" in plantilla or "Kilometraje" in plantilla:
        lineas = plantilla.split('\n')
        nueva_plantilla = []
        for l in lineas:
            if "Km" in l or "Kilometraje" in l:
                nueva_plantilla.append(f"Kilometraje / Odómetro: {caption}")
            else:
                nueva_plantilla.append(l)
        plantilla_actualizada = "\n".join(nueva_plantilla)
    else:
        plantilla_actualizada = plantilla + f"\nKilometraje: {caption}"

    await update.message.reply_text(f"🔄 *Plantilla modificada con el odómetro:*\n\n{plantilla_actualizada}")

def main():
    keep_alive()
    
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("buscar", buscar_unidad))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), guardar_plantilla))
    app.add_handler(MessageHandler(filters.PHOTO, modificar_con_foto))

    print("🤖 Bot de Frio Express en la nube activo...")
    app.run_polling()

if __name__ == '__main__':
    main()
