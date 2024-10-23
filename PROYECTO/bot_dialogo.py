import asyncio
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from transformers import pipeline
from gtts import gTTS
import language_tool_python
import time
import logging
import nest_asyncio

# Evita conflictos con event loops en entornos interactivos
nest_asyncio.apply()

# Configuración del registro de errores
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Inicialización del modelo GPT-2
generator = pipeline('text-generation', model='gpt2')

# Diccionario para guardar el contexto del usuario
user_context = {}

# Inicialización de LanguageTool para corrección en inglés
tool = language_tool_python.LanguageTool('en-US')

# Preguntas iniciales y subsecuentes para cada tema
topic_questions = {
    "Sports": [
        "What is your favorite sport?",
        "Do you prefer to play sports or watch them?",
        "Who is your favorite athlete?"
    ],
    "Travel": [
        "What place would you like to visit and why?",
        "Do you prefer beach holidays or city breaks?",
        "Tell me about your last trip."
    ],
    "Technology": [
        "What recent technological advancement has impressed you the most?",
        "Do you prefer Android or iOS devices?",
        "How do you think AI will impact the future?"
    ]
}

# Función para generar respuestas basadas en el tema
def generate_response(user_input, topic):
    prompt = f"Conversation about {topic}: {user_input}"
    try:
        response = generator(
            prompt,
            max_new_tokens=100,
            num_return_sequences=1,
            temperature=0.7,
            top_k=50
        )
        return response[0]['generated_text']
    except Exception as e:
        logging.error(f"Error generating response: {e}")
        return "Sorry, an error occurred while generating the response."

# Función para convertir texto a voz
def text_to_speech(text, lang='en'):
    tts = gTTS(text=text, lang=lang)
    audio_path = f"response_{int(time.time())}.mp3"
    tts.save(audio_path)
    return audio_path

# Función para enviar audio en segundo plano
async def send_audio_in_background(bot, chat_id, audio_path):
    try:
        await bot.send_audio(chat_id=chat_id, audio=open(audio_path, 'rb'))
        logging.info(f"Audio sent successfully to {chat_id}")
    except Exception as e:
        logging.error(f"Error sending audio to {chat_id}: {e}")
    finally:
        os.remove(audio_path)

# Función para corregir gramática en inglés
def correct_english(text):
    matches = tool.check(text)
    if matches:
        corrected_text = language_tool_python.utils.correct(text, matches)
        if corrected_text.lower().strip() != text.lower().strip():
            return corrected_text
    return None

# Token del bot de Telegram
TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Función para mostrar el menú de temas
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu_text = (
        "Hello! I am your language practice bot.\n"
        "Select a topic to practice:\n"
        "1. Sports\n"
        "2. Travel\n"
        "3. Technology\n"
        "Please type the number of the topic you want to practice."
    )
    user_context[update.message.chat.id] = {"topic": None, "question_index": 0}
    await update.message.reply_text(menu_text)

# Función para manejar mensajes
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = update.message.chat.id

    if user_context[chat_id]["topic"] is None:
        if user_message in ['1', '2', '3']:
            topic = ['Sports', 'Travel', 'Technology'][int(user_message) - 1]
            user_context[chat_id]["topic"] = topic
            user_context[chat_id]["question_index"] = 0
            first_question = topic_questions[topic][0]
            await update.message.reply_text(f"You have selected: {topic}. Let's start!\n{first_question}")
        else:
            await update.message.reply_text("Please select a valid topic (1, 2, or 3).")
    else:
        corrected_message = correct_english(user_message)
        if corrected_message:
            await update.message.reply_text(f"Correction: {corrected_message}")
            user_message = corrected_message

        topic = user_context[chat_id]["topic"]
        response = generate_response(user_message, topic)
        await update.message.reply_text(response)

        audio_file = text_to_speech(response)
        asyncio.create_task(send_audio_in_background(context.bot, chat_id, audio_file))

        question_index = user_context[chat_id]["question_index"] + 1
        if question_index < len(topic_questions[topic]):
            user_context[chat_id]["question_index"] = question_index
            next_question = topic_questions[topic][question_index]
            await update.message.reply_text(next_question)
        else:
            await update.message.reply_text("Thanks for practicing! You can select another topic with /start.")

# Función principal para iniciar el bot en modo webhook
async def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Configuración del webhook
    PORT = int(os.environ.get('PORT', 8443))
    WEBHOOK_URL = f"https://{os.getenv('HEROKU_APP_NAME')}.herokuapp.com/{TOKEN}"

    # Inicializar y configurar webhook
    await application.initialize()
    await application.bot.set_webhook(WEBHOOK_URL)

    # Iniciar el webhook
    await application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL
    )
    await application.idle()

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            print("El event loop ya está corriendo. Usando asyncio.run() en su lugar.")
            asyncio.run(main())  # Ejecuta de manera segura si ya hay un loop corriendo.
        else:
            loop.run_until_complete(main())
    except RuntimeError as e:
        print(f"Error con el event loop: {e}. Creando uno nuevo.")
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        new_loop.run_until_complete(main())