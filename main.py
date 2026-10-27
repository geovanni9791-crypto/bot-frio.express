import os
import sqlite3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Configurar base de datos local temporal
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

async def guardar_plantilla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto and "FRIO EXPRESS" in texto:
        for linea in texto.split('\n'):
            if "No. Eco" in linea or "Eco.:" in linea:
                no_eco = linea.split(":")[-1].strip()
                
                conn = sqlite3.connect('revisiones.db')
                cursor = conn.cursor()
                cursor.execute('INSERT INTO revisiones (no_eco, plantilla) VALUES (?, ?)', (no_eco, texto))
                conn.commit()
                conn.close()
                
                await update.message.reply_text(f"✅ Plantilla de la unidad {no_eco} guardada correctamente.")
                break

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
        await update.message.reply_text(f"🔍 *Unidad encontrada:*\n\n{resultado[0]}")
    else:
        await update.message.reply_text(f"❌ No se encontró revisión para: {no_eco_buscado}")

def main():
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("buscar", buscar_unidad))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), guardar_plantilla))

    print("🤖 Bot de Frio Express en la nube activo...")
    app.run_polling()

if __name__ == '__main__':
    main()
