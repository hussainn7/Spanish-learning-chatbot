import asyncio
import subprocess
import re
import telebot
from telebot import types
import logging
from g4f.client import Client
import g4f
from configBOT import TOKEN, PRICE, information_about_company
from paymentBOT import check, create
import os
import sqlite3
from gtts import gTTS
import pytube
import speech_recognition as sr
import datetime
import schedule
import time
from googletrans import Translator

translator = Translator()
# https://www.youtube.com/watch?v=1aA1WGON49E&ab_channel=TEDxTalks

logging.basicConfig(level=logging.INFO)

os.environ["PATH"] += os.pathsep + r"C:\ffmpeg\bin"

g4f_client = Client()

INTRODUCTION_MESSAGE = ("Привет! Я твой учитель испанского языка. Спросите меня о чем угодно.")

FREE_PERIOD = 1 * 10  # 10 seconds for testing

ADMIN_USER_ID = 1262676599

bot = telebot.TeleBot(TOKEN)


def escape_markdown_v2(text):
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(r'([{}])'.format(re.escape(escape_chars)), r'\\\1', text)


def init_db():
    conn = sqlite3.connect('user_data.db')
    try:
        c = conn.cursor()
        c.execute(
            '''CREATE TABLE IF NOT EXISTS used_free_period (user_id INTEGER PRIMARY KEY)''')
        c.execute(
            '''CREATE TABLE IF NOT EXISTS premium_users (user_id INTEGER PRIMARY KEY, expiration_date TEXT)''')
        c.execute(
            '''CREATE TABLE IF NOT EXISTS payments (user_id INTEGER, payment_id TEXT, PRIMARY KEY (user_id, payment_id))''')
        conn.commit()
    finally:
        conn.close()


def has_used_free_period(user_id):
    conn = sqlite3.connect('user_data.db')
    try:
        c = conn.cursor()
        c.execute(
            'SELECT user_id FROM used_free_period WHERE user_id = ?', (user_id,))
        result = c.fetchone()
    finally:
        conn.close()
    return result is not None


def mark_free_period_used(user_id):
    conn = sqlite3.connect('user_data.db')
    try:
        c = conn.cursor()
        c.execute(
            'INSERT OR IGNORE INTO used_free_period (user_id) VALUES (?)', (user_id,))
        conn.commit()
    finally:
        conn.close()


def is_premium_user(user_id):
    conn = sqlite3.connect('user_data.db')
    try:
        c = conn.cursor()
        c.execute(
            'SELECT expiration_date FROM premium_users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        if result:
            expiration_date = datetime.datetime.strptime(
                result[0], '%Y-%m-%d %H:%M:%S')
            return expiration_date > datetime.datetime.now()
        else:
            return False
    finally:
        conn.close()


def mark_as_premium(user_id):
    expiration_date = datetime.datetime.now(
    ) + datetime.timedelta(days=30)  # Premium subscription for 30 days
    expiration_date_str = expiration_date.strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect('user_data.db')
    try:
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO premium_users (user_id, expiration_date) VALUES (?, ?)',
                  (user_id, expiration_date_str))
        conn.commit()
    finally:
        conn.close()


def remind_about_subscription():
    conn = sqlite3.connect('user_data.db')
    try:
        c = conn.cursor()
        c.execute('SELECT user_id FROM premium_users WHERE expiration_date < ? AND expiration_date > ?',
                  (datetime.datetime.now() + datetime.timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'),
                  datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        users_to_remind = c.fetchall()
        for user_id in users_to_remind:
            bot.send_message(
                user_id, "You have 2 days left until the end of your subscription.")
    finally:
        conn.close()


# Schedule the reminder to run daily
schedule.every().day.at("09:00").do(remind_about_subscription)


def clear_used_free_periods():
    conn = sqlite3.connect('user_data.db')
    try:
        c = conn.cursor()
        c.execute('DELETE FROM used_free_period')
        conn.commit()
    finally:
        conn.close()


def clear_expired_premium_subscriptions():
    conn = sqlite3.connect('user_data.db')
    try:
        c = conn.cursor()
        c.execute('DELETE FROM premium_users WHERE expiration_date < ?',
                  (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))
        conn.commit()
    finally:
        conn.close()


def clear_premium_periods():
    conn = sqlite3.connect('user_data.db')
    try:
        c = conn.cursor()
        c.execute('DELETE FROM premium_users')
        conn.commit()
    finally:
        conn.close()


init_db()

user_start_times = {}


def daily_job():
    clear_expired_premium_subscriptions()
    print("Expired premium subscriptions cleared.")


schedule.every().day.at("00:00").do(daily_job)


async def generate_response(text):
    print("Generating response...")
    response = await g4f.ChatCompletion.create_async(
        model=g4f.models.default,
        messages=[{"role": "user", "content": text}],
        provider=g4f.Provider.PerplexityLabs
    )
    print("Response generated.")
    return response


# Function to convert voice message to text
def voice_to_text(voice_file):
    print("Converting voice to text...")
    recognizer = sr.Recognizer()
    with sr.AudioFile(voice_file) as source:
        audio_data = recognizer.record(source)
    try:
        text = recognizer.recognize_google(audio_data)
        print("Text converted from voice:", text)
        return text
    except sr.UnknownValueError:
        print("Google Speech Recognition could not understand audio")
        return None
    except sr.RequestError:
        print("Could not request results from Google Speech Recognition service")
        return None


# Function to convert the audio file to WAV format
def convert_to_wav(audio_file):
    print("Converting audio file to WAV format...")
    wav_file = 'converted_audio.wav'
    subprocess.run(['ffmpeg', '-y', '-i', audio_file, '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', wav_file])
    print("Audio file converted to WAV format.")
    return wav_file


# Function to convert text to speech and save as OGG format using gTTS
def text_to_speech(text):
    print("Converting text to speech...")
    tts = gTTS(text=text, lang='en')
    ogg_file = 'response.ogg'
    tts.save(ogg_file)
    print("Text converted to speech and saved as OGG format.")
    return ogg_file


@bot.message_handler(commands=['start', 'language'])
def start(message):
    user_id = message.from_user.id
    markup = types.ReplyKeyboardMarkup(row_width=1)

    # Adding language selection options
    markup.add(types.KeyboardButton("🇪🇸 Español"), types.KeyboardButton("🇷🇺 Русский"))

    bot.reply_to(message, "Hola! 🌟 Elige tu idioma preferido / Выберите ваш язык", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text in ["🇪🇸 Español", "🇷🇺 Русский"])
def select_language(message):
    language = message.text

    if language == "🇪🇸 Español":
        # Set user language to Spanish
        markup = types.ReplyKeyboardMarkup(row_width=1)
        markup.add(types.KeyboardButton("🚀 Inicio"),types.KeyboardButton("🅰 Transcripción"),
                   types.KeyboardButton('👥 Perfil'),
                   types.KeyboardButton("❓ ¿Qué es eso?"))
        welcome_message = "¡Hola! Soy tu profesor de español. ¡Pregúntame cualquier cosa!"
    elif language == "🇷🇺 Русский":
        # Set user language to Russian
        markup = types.ReplyKeyboardMarkup(row_width=1)
        markup.add(types.KeyboardButton("🚀 Начать"),
                   types.KeyboardButton('👥 Профиль'), types.KeyboardButton("📟Перевод"), types.KeyboardButton("🅰 Транскрибация"),
                   types.KeyboardButton("❓ Что это?"))
        welcome_message = "Привет! Я твой учитель испанского языка. Спросите меня о чем угодно."

    bot.send_message(message.chat.id, welcome_message, reply_markup=markup)


translation_enabled = False


# Define a dictionary to store the announcement messages
announcement_messages = {}

# Handler for the /announce command
@bot.message_handler(commands=['announce'])
def start_announcement(message):
    # Set the user's state to 'waiting_for_announcement'
    user_id = message.from_user.id
    announcement_messages[user_id] = ''
    bot.send_message(user_id, "Отправьте оповещение, чтобы всем разослать.")

# Handler for receiving the announcement message
@bot.message_handler(func=lambda message: message.from_user.id in announcement_messages and announcement_messages[message.from_user.id] == '' and notification_preferences.get(message.from_user.id, True))
def receive_announcement(message):
    user_id = message.from_user.id
    announcement_message = message.text
    # Save the announcement message
    announcement_messages[user_id] = announcement_message
    bot.send_message(user_id, "Сообщение для оповещения сохранено. Начинаю отправку...")

    # Proceed with the announcement process
    send_announcement_to_all(user_id)

def send_announcement_to_all(user_id):
    # Fetch all users
    conn = sqlite3.connect('user_data.db')
    try:
        c = conn.cursor()
        c.execute('SELECT user_id FROM used_free_period')
        users = c.fetchall()
    finally:
        conn.close()

    # Send the announcement to users who have notifications enabled
    for user in users:
        if notification_preferences.get(user[0], True):
            bot.send_message(user[0], 'Оповещение\n' + announcement_messages[user_id])

    # Inform the admin about the successful announcement
    bot.send_message(user_id, "Сообщение успешно отправлено всем пользователям.")



@bot.message_handler(func=lambda message: message.text == "🅰 Transcripción")
def toggle_transcription(message):
    global translation_enabled

    translation_enabled = not translation_enabled

    if translation_enabled:
        bot.reply_to(message, "La transcripción está activada. Los mensajes de voz se transcribirán.")
    else:
        bot.reply_to(message, "La transcripción está desactivada.")

@bot.message_handler(func=lambda message: message.text == "🅰 Транскрибация")
def toggle_transcription(message):
    global translation_enabled

    translation_enabled = not translation_enabled

    if translation_enabled:
        bot.reply_to(message, "Транскрибация включена. Голосовые сообщения будут транскрибироваться.")
    else:
        bot.reply_to(message, "Транскрибация выключена.")

# Handler for the "Translation" button
@bot.message_handler(func=lambda message: message.text == "📟Перевод")
def toggle_translation(message):
    global translation_enabled
    translation_enabled = not translation_enabled
    if translation_enabled:
        bot.send_message(message.chat.id, "Перевод включен. Все испанские сообщения будут переведены на русский.")
    else:
        bot.send_message(message.chat.id, "Перевод выключен.")


@bot.message_handler(func=lambda message: message.text == '🚀 Inicio')
def start_button(message):
    markup_start = types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True)
    markup_start.add(types.KeyboardButton('solo charlar'), types.KeyboardButton("palabra"),
                     types.KeyboardButton('practicar temas'), types.KeyboardButton("la transcripción"),
                     types.KeyboardButton("parafrasear"), types.KeyboardButton('artículo de actualidad'),
                     types.KeyboardButton("aprender español"), types.KeyboardButton('🔙 Volver al menú principal'))
    bot.reply_to(message, "Hola, soy tu profesor de español. Pregúntame lo que quieras.", reply_markup=markup_start)


@bot.message_handler(func=lambda message: message.text == '📝 Audio a texto')
def handle_transcribe_button(message):
    user_id = message.from_user.id
    if not is_premium_user(user_id):
        bot.reply_to(message, "Esta función sólo está disponible para usuarios Premium.")
    else:
        msg = bot.reply_to(message, "Proporcione la URL de YouTube para la transcripción:")
        bot.register_next_step_handler(msg, transcribe_youtube_video)


@bot.message_handler(func=lambda message: message.text == '❓ Что это?')
def who_are_we(message):
    markup_who = types.ReplyKeyboardMarkup(row_width=1)
    markup_who.add(types.KeyboardButton('👫 Познакомиться'), types.KeyboardButton("📚 Материалы"),
                   types.KeyboardButton("🎓 Обучение"), types.KeyboardButton('📒 Консультации'),
                   types.KeyboardButton("💡 Идеи к улучшению"), types.KeyboardButton("💃 Мероприятия на испанском"),
                   types.KeyboardButton('🔙 Назад в главное меню'))
    bot.reply_to(message, information_about_company, reply_markup=markup_who)


@bot.message_handler(func=lambda message: message.text == '🎓 Обучение')
def start_button(message):
    bot.reply_to(message, "Здесь можно записаться на обучение")


@bot.message_handler(func=lambda message: message.text == '📚 Материалы')
def start_button(message):
    bot.reply_to(message, "Здесь будет клссный материал")


@bot.message_handler(func=lambda message: message.text == '💃 Мероприятия на испанском')
def start_button(message):
    bot.reply_to(message, "Здесь будут классные мероприятия")


@bot.message_handler(func=lambda message: message.text == '📒 Консультации')
def start_button(message):
    bot.reply_to(message, "Проконтактируйте нас, если что вдруг")


@bot.message_handler(func=lambda message: message.text == '👫 Познакомиться')
def start_button(message):
    bot.reply_to(message, "Здесь будут очень интересные ссылки на некоторые материалы")


@bot.message_handler(func=lambda message: message.text == '💡 Идеи к улучшению')
def prompt_for_idea(message):
    # Create a keyboard with a "Cancel" button
    markup = types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True)
    markup.add(types.KeyboardButton('Отмена'))

    msg = bot.reply_to(message,
                       "Пожалуйста, напишите свою идею по улучшению нашего сервиса или нажмите «Отмена», чтобы вернуться назад:",
                       reply_markup=markup)
    bot.register_next_step_handler(msg, handle_idea_or_cancel)


##############################################################################################################################################################

@bot.message_handler(func=lambda message: message.text == '❓ ¿Qué es eso?')
def who_are_we(message):
    markup_who = types.ReplyKeyboardMarkup(row_width=1)
    markup_who.add(types.KeyboardButton('👫 Conócete'), types.KeyboardButton("📚 Materiales"),
                   types.KeyboardButton("🎓 Formación"), types.KeyboardButton('📒 Asesoramiento'),
                   types.KeyboardButton("💡 Ideas para mejorar"), types.KeyboardButton("💃 Eventos en español"),
                   types.KeyboardButton('🔙 Volver al menú principal'))
    bot.reply_to(message, information_about_company, reply_markup=markup_who)


@bot.message_handler(func=lambda message: message.text == '🎓 Formación')
def start_button(message):
    bot.reply_to(message, "Puede inscribirse en la formación aquí")


@bot.message_handler(func=lambda message: message.text == '📒 Asesoramiento')
def start_button(message):
    bot.reply_to(message, "Llámenos si hay algún problema.")


@bot.message_handler(func=lambda message: message.text == '👫 Conócete')
def start_button(message):
    bot.reply_to(message, "Aquí habrá enlaces muy interesantes a parte del material")


@bot.message_handler(func=lambda message: message.text == '📚 Materiales')
def start_button(message):
    bot.reply_to(message, "Va a haber grandes cosas aquí.")


@bot.message_handler(func=lambda message: message.text == '💃 Eventos en español')
def start_button(message):
    bot.reply_to(message, "Va a haber algunas actividades interesantes aquí")


@bot.message_handler(func=lambda message: message.text == '💡 Ideas para mejorar')
def prompt_for_idea(message):
    # Create a keyboard with a "Cancel" button
    markup = types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True)
    markup.add(types.KeyboardButton('Cancelar'))

    msg = bot.reply_to(message,
                       "Escriba su idea para mejorar nuestro servicio o haga clic en «Cancelar» para volver atrás:",
                       reply_markup=markup)
    bot.register_next_step_handler(msg, handle_idea_or_cancel)


def handle_idea_or_cancel(message):
    if message.text.lower() == 'Cancelar':
        bot.send_message(message.chat.id, "Su solicitud se ha cancelado correctamente.")
        start(message)
    else:
        forward_idea_to_admin(message)


########################################################################################################################################################

def forward_idea_to_admin(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    user_idea = message.text

    # Format the user info
    user_info = f"User ID: {user_id}\n"
    if username:
        user_info += f"Username: @{username}\n"
    if first_name or last_name:
        user_info += f"Name: {first_name} {last_name}\n"

    # Format the message to include user info and their idea
    admin_message = f"Была подана идея по улучшению сервиса:\n\n{user_idea}\n\nОт:\n{user_info}"

    # Send the idea to the admin
    bot.send_message(ADMIN_USER_ID, admin_message)

    markup = types.ReplyKeyboardMarkup(row_width=1)
    markup.add(types.KeyboardButton("🚀 Начать"),
               types.KeyboardButton('👥 Профиль'), types.KeyboardButton("📟Перевод"),
               types.KeyboardButton("🅰 Транскрибация"),
               types.KeyboardButton("❓ Что это?"))

    # Confirm receipt to the user
    bot.reply_to(message, "Спасибо за ваш отзыв! Ваша идея была отправлена в нашу команду.", reply_markup = markup)


@bot.message_handler(func=lambda message: message.text == '🚀 Начать')
def start_button(message):
    markup_start = types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True)
    markup_start.add(types.KeyboardButton('Поболтать'), types.KeyboardButton("Про слово"),
                     types.KeyboardButton('Практиковать темы'), types.KeyboardButton("Транскрипция"),
                     types.KeyboardButton("Перефразировать"), types.KeyboardButton('Про актуальную статью'),
                     types.KeyboardButton("Учить классически"), types.KeyboardButton('🔙 Назад в главное меню'))
    bot.reply_to(message, "Привет, я ваш учитель испанского. Спросите меня о чем угодно.", reply_markup=markup_start)


# New handler for the 'Transcribe' feature
@bot.message_handler(func=lambda message: message.text == '📝 Аудио в текст')
def handle_transcribe_button(message):
    user_id = message.from_user.id
    if not is_premium_user(user_id):
        bot.reply_to(message, "Эта функция доступна только для премиум-пользователей.")
    else:
        msg = bot.reply_to(message, "Пожалуйста, укажите URL-адрес YouTube для транскрипции:")
        bot.register_next_step_handler(msg, transcribe_youtube_video)


def transcribe_youtube_video(message):
    user_id = message.from_user.id
    youtube_url = message.text

    try:
        # Step 1: Download YouTube video
        bot.reply_to(message, "Загрузка видео...")
        yt = pytube.YouTube(youtube_url)
        video = yt.streams.filter(only_audio=True).first()
        video_file = video.download(filename="youtube_audio.mp4")

        # Step 2: Extract audio from video using ffmpeg
        bot.reply_to(message, "Извлечение звука из видео...")
        audio_file = "youtube_audio.wav"
        subprocess.run(
            ['ffmpeg', '-i', video_file, '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_file])

        # Step 3: Convert audio to text
        bot.reply_to(message, "Транскрибирование аудио...")
        recognizer = sr.Recognizer()
        with sr.AudioFile(audio_file) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)

        # Step 4: Send the transcription back to the user
        bot.reply_to(message, f"Транскрипция:\n\n{text}")

        # Cleanup: Remove downloaded and processed files
        os.remove(video_file)
        os.remove(audio_file)

    except Exception as e:
        bot.reply_to(message, f"An error occurred: {e}")


#####################################################################################################################################################
# Profile button handler
@bot.message_handler(func=lambda message: message.text == '👥 Perfil')
def handle_profile_button(message):
    user_id = message.from_user.id
    markup_profile = types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True)
    markup_profile.add(types.KeyboardButton('⛳Activar GPT-4o'), types.KeyboardButton('📝 Audio a texto'),types.KeyboardButton("🌎 Idioma"),
                       types.KeyboardButton('🔄 Reinicie'), types.KeyboardButton("💎Prima"),
                       types.KeyboardButton('🔙 Volver al menú principal'))
    if is_premium_user(user_id):
        bot.reply_to(message, "Su situación: Premium", reply_markup=markup_profile)
    else:
        bot.reply_to(message, "Su situación: Free", reply_markup=markup_profile)


@bot.message_handler(func=lambda message: message.text == '🔄 Reinicie')
def handle_transcribe_button(message):
    markup = types.ReplyKeyboardMarkup(row_width=1)
    markup.add(types.KeyboardButton("🚀 Inicio"), types.KeyboardButton("🅰 Transcripción"),
               types.KeyboardButton('👥 Perfil'),
               types.KeyboardButton("❓ ¿Qué es eso?"))
    time.sleep(3)
    bot.reply_to(message, 'El reinicio se ha realizado correctamente ♻️', reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == '💎Prima')
def handle_transcribe_button(message):
    user_id = message.from_user.id
    if is_premium_user(user_id):
        bot.reply_to(message, "Ya tiene una prima, ¡enhorabuena!")
    else:
        msg = bot.reply_to(message, "Premium te da un montón de características\n Audio/texto\n etc.")
        bot.reply_to(message, msg)


@bot.message_handler(func=lambda message: message.text == '⛳Activar GPT-4o')
def handle_transcribe_button(message):
    markup = types.ReplyKeyboardMarkup(row_width=1)
    markup.add(types.KeyboardButton("🚀 Inicio"), types.KeyboardButton("🅰 Transcripción"),
               types.KeyboardButton('👥 Perfil'),
               types.KeyboardButton("❓ ¿Qué es eso?"))
    user_id = message.from_user.id
    if not is_premium_user(user_id):
        bot.reply_to(message, "Esta función sólo está disponible para usuarios Premium.", reply_markup=markup)
    else:
        msg = bot.reply_to(message, "Activar GPT-4o\nMás rápido y fiable")


@bot.message_handler(func=lambda message: message.text == '🔙 Volver al menú principal')
def back_menu(message):
    markup = types.ReplyKeyboardMarkup(row_width=1)
    markup.add(types.KeyboardButton("🚀 Inicio"), types.KeyboardButton('📝 Audio a texto'),
               types.KeyboardButton('👥 Perfil'),
               types.KeyboardButton("❓ ¿Qué es eso?"))
    bot.reply_to(message, "Hola, soy tu profesor de español. Pregúntame lo que quieras.", reply_markup=markup)


#######################################################################################################################################

notification_preferences = {}

# Profile button handler
@bot.message_handler(func=lambda message: message.text == '👥 Профиль')
def handle_profile_button(message):
    user_id = message.from_user.id
    markup_profile = types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True)
    markup_profile.add(types.KeyboardButton('⛳Включить GPT-4o'), types.KeyboardButton('📝 Аудио в текст'), types.KeyboardButton("🌎 Язык"), types.KeyboardButton('🔔 Оповещения'),
                       types.KeyboardButton('🔄 Перезапуск'), types.KeyboardButton("💎Premium"),
                       types.KeyboardButton('🔙 Назад в главное меню'))
    if is_premium_user(user_id):
        bot.reply_to(message, "Ваш статус: Premium", reply_markup=markup_profile)
    else:
        bot.reply_to(message, "Ваш статус: Free", reply_markup=markup_profile)


@bot.message_handler(func=lambda message: message.text == '🔔 Оповещения')
def handle_notification_button(message):
    user_id = message.from_user.id
    markup_notification = types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True)
    markup_notification.add(types.KeyboardButton('Включить'), types.KeyboardButton('Выключить'))

    bot.reply_to(message, "Выберите действие:", reply_markup=markup_notification)

# Handler for enabling or disabling notifications
@bot.message_handler(func=lambda message: message.text in ['Включить', 'Выключить'])
def handle_notification_preference(message):
    user_id = message.from_user.id
    markup = types.ReplyKeyboardMarkup(row_width=1)
    markup.add(types.KeyboardButton("🚀 Начать"),
               types.KeyboardButton('👥 Профиль'), types.KeyboardButton("📟Перевод"),
               types.KeyboardButton("🅰 Транскрибация"),
               types.KeyboardButton("❓ Что это?"))
    if message.text == 'Включить':
        notification_preferences[user_id] = True
        bot.reply_to(message, "Оповещения включены.", reply_markup = markup)
    else:
        notification_preferences[user_id] = False
        bot.reply_to(message, "Оповещения выключены.", reply_markup = markup)




@bot.message_handler(func=lambda message: message.text in ['🌎 Язык', '🌎 Idioma'])
def yazik_func(message):
    markup_language = types.ReplyKeyboardMarkup(row_width=1)
    markup_language.add(types.KeyboardButton("🇪🇸 Español"), types.KeyboardButton("🇷🇺 Русский"))
    bot.send_message(message.chat.id, "Elige tu idioma preferido / Выберите ваш язык",
                     reply_markup=markup_language)


@bot.message_handler(func=lambda message: message.text == '🔄 Перезапуск')
def handle_transcribe_button(message):
    markup = types.ReplyKeyboardMarkup(row_width=1)
    markup.add(types.KeyboardButton("🚀 Начать"), types.KeyboardButton('📝 Аудио в текст'),
               types.KeyboardButton('👥 Профиль'), types.KeyboardButton("📟Перевод"),
               types.KeyboardButton("❓ Что это?"))
    time.sleep(3)
    bot.reply_to(message, 'Перезапуск был успешен ♻️',reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == '🔙 Назад в главное меню')
def back_menu(message):
    markup = types.ReplyKeyboardMarkup(row_width=1)
    markup.add(types.KeyboardButton("🚀 Начать"), types.KeyboardButton('📝 Аудио в текст'),
               types.KeyboardButton('👥 Профиль'), types.KeyboardButton("📟Перевод"),
               types.KeyboardButton("❓ Что это?"))
    bot.reply_to(message, "Привет! Я твой учитель испанского языка. Спросите меня о чем угодно", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == '💎Premium')
def handle_transcribe_button(message):
    user_id = message.from_user.id

    # Create inline keyboard markup for payment options
    markup_buy = types.InlineKeyboardMarkup()
    yoomoney_button = types.InlineKeyboardButton(text="YooMoney", callback_data='pay_yoomoney')
    crypto_button = types.InlineKeyboardButton(text="Crypto", callback_data='pay_crypto')
    markup_buy.add(yoomoney_button, crypto_button)

    # Send a message prompting the user to choose a payment method
    bot.send_message(
        message.chat.id,  # Correct attribute is 'chat.id' instead of 'chat_id'
        "Вы пользуетесь нашим сервисом в течение 1 минуты. Чтобы продолжить пользоваться сервисом, вам необходимо произвести оплату. Пожалуйста, выберите способ оплаты:",
        reply_markup=markup_buy
    )

    # Create reply keyboard markup for main options
    markup = types.ReplyKeyboardMarkup(row_width=1)
    markup.add(
        types.KeyboardButton("🚀 Начать"),
        types.KeyboardButton('📝 Аудио в текст'),
        types.KeyboardButton('👥 Профиль'),
        types.KeyboardButton("📟Перевод"),
        types.KeyboardButton("❓ Что это?")
    )

    # Check if the user is a premium user and respond accordingly
    if is_premium_user(user_id):  # Ensure the function 'is_premium_user' is defined
        bot.reply_to(message, "Вы уже имеете премиум, поздравляем!", reply_markup=markup)
    else:
        bot.reply_to(message, "Премиум даёт много функций\nАудио/текст и многое др.\nКУПИТЬ СЕЙЧАС", reply_markup=markup_buy)



@bot.message_handler(func=lambda message: message.text == '⛳Включить GPT-4o')
def handle_transcribe_button(message):
    user_id = message.from_user.id
    user_id = message.from_user.id
    markup = types.ReplyKeyboardMarkup(row_width=1)
    markup.add(types.KeyboardButton("🚀 Начать"), types.KeyboardButton('📝 Аудио в текст'),
               types.KeyboardButton('👥 Профиль'), types.KeyboardButton("📟Перевод"),
               types.KeyboardButton("❓ Что это?"))
    if not is_premium_user(user_id):
        bot.reply_to(message, "Эта функция доступна только для премиум-пользователей.", reply_markup=markup)
    else:
        bot.reply_to(message, "Активировать GPT-4o\nБолее быстрый и надёжный")
        markup_profile = types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True)
        markup_profile.add(types.KeyboardButton('⛳Активировать'), reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == '⛳Активировать')
def start_button(message):
    bot.reply_to(message, "Поздравяляю GPT-4o был успешно активирован!")


@bot.message_handler(commands=['buy777'])
def buy_handler(chat_id):
    # Create inline keyboard with two options: YooMoney and Crypto
    markup = types.InlineKeyboardMarkup()
    yoomoney_button = types.InlineKeyboardButton(text="YooMoney", callback_data='pay_yoomoney')
    crypto_button = types.InlineKeyboardButton(text="Crypto", callback_data='pay_crypto')
    markup.add(yoomoney_button, crypto_button)

    bot.send_message(chat_id,
                     "Вы пользуетесь нашим сервисом в течение 1 минуты. Чтобы продолжить пользоваться сервисом, вам необходимо произвести оплату. Пожалуйста, выберите способ оплаты:",
                     reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data in ['pay_yoomoney', 'pay_crypto'])
def handle_payment_option(call):
    chat_id = call.message.chat.id
    if call.data == 'pay_yoomoney':
        payment_url, payment_id = create(PRICE, chat_id)

        # Create inline keyboard with Pay and Check Payment options
        markup = types.InlineKeyboardMarkup()
        pay_button = types.InlineKeyboardButton(text="Оплатить", url=payment_url)
        check_button = types.InlineKeyboardButton(text="Проверить", callback_data=f'check_{payment_id}')
        markup.add(pay_button, check_button)

        bot.send_message(chat_id, "Пожалуйста, завершите оплату с помощью YooMoney:", reply_markup=markup)
    elif call.data == 'pay_crypto':
        bot.send_message(chat_id, "Мы уже добавляем его.")


# /saf command handler (clear used free periods)
@bot.message_handler(commands=['saf'])
def handle_saf(message):
    user_id = message.from_user.id
    if user_id == ADMIN_USER_ID:
        clear_used_free_periods()
        clear_premium_periods()
        bot.reply_to(message, "All used free periods have been cleared.")
    else:
        bot.reply_to(message, "You are not authorized to use this command.")


# Callback query handler for checking payment
@bot.callback_query_handler(func=lambda call: call.data.startswith('check'))
def check_handler(callback_query):
    payment_id = callback_query.data.split('_')[1]
    result = check(payment_id)
    if result:
        chat_id = result.get('chat_id')
        mark_as_premium(chat_id)  # Mark the user as a premium user
        bot.send_message(callback_query.message.chat.id, "Oплата прошла успешно! Вам был дан Premium")
    else:
        bot.send_message(callback_query.message.chat.id, "Оплата ещё не прошла или ошибка")


# Function to check if user is within free period
def is_within_free_period(user_id):
    if user_id not in user_start_times:
        user_start_times[user_id] = time.time()
        return True
    start_time = user_start_times[user_id]
    elapsed_time = time.time() - start_time
    if elapsed_time > FREE_PERIOD:
        mark_free_period_used(user_id)
        return False
    return True


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id

    # Check if user is within free period or is a premium user
    if not is_within_free_period(user_id) and not is_premium_user(user_id):
        buy_handler(message.chat.id)  # Pass chat.id directly
        return

    if translation_enabled:
        # If translation mode is enabled
        if message.text:
            # Translate only the generated responses
            user_message = message.text
            user_message_with_reminder = f"Привет ты больше не языковой помощник, теперь учитель испанского языка \n{user_message} отвечай СТРОГО на испанском, говори очень коротко СТРОГО"

            print("Generating response for text message...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ai_response = loop.run_until_complete(generate_response(user_message_with_reminder))

            # Translate the generated response
            translation = translator.translate(ai_response, src='es', dest='ru')

            # Send original and translated messages
            bot.send_message(message.chat.id, f"{ai_response}")
            bot.send_message(message.chat.id, f"Перевод:\n\n{translation.text}")
    else:
        # If translation mode is off or message is empty, proceed with generating response
        if message.text:
            print("Text message received:", message.text)
            user_message = message.text
            user_message_with_reminder = f"Привет ты больше не языковой помощник, теперь учитель испанского языка \n{user_message} отвечай СТРОГО на испанском, говори очень коротко СТРОГО"

            print("Generating response for text message...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ai_response = loop.run_until_complete(generate_response(user_message_with_reminder))

            bot.reply_to(message, ai_response)


@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    user_id = message.from_user.id
    if not is_within_free_period(user_id) and not is_premium_user(user_id):
        buy_handler(message.chat.id)  # Pass chat.id directly
        return

    print("Voice message received.")
    file_info = bot.get_file(message.voice.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    print("Voice file downloaded.")

    with open('voice_message.ogg', 'wb') as new_file:
        new_file.write(downloaded_file)
    print("Voice file saved locally as 'voice_message.ogg'.")

    wav_file = convert_to_wav('voice_message.ogg')
    text = voice_to_text(wav_file)
    if text:
        print("Voice message converted to text:", text)
        user_message_with_reminder = f"Привет ты теперь учитель испанского языка \n{text} отвечай СТРОГО на испанском, большие ответы не нужны"

        print("Generating response for voice message...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ai_response = loop.run_until_complete(generate_response(user_message_with_reminder))

        print("Converting text response to speech...")
        speech_file = text_to_speech(ai_response)

        translation = translator.translate(ai_response, src='es', dest='ru')

        print("Sending voice response...")

        # Check if transcription is enabled
        if translation_enabled:
            # Send both voice and text messages
            bot.send_voice(message.chat.id, open(speech_file, 'rb'))
            escaped_ai_response = escape_markdown_v2(ai_response)
            spoiler_text = f"||{escaped_ai_response}||"
            bot.send_message(message.chat.id, spoiler_text, parse_mode='MarkdownV2')
            bot.send_message(message.chat.id, translation.text)
        else:
            # Send only the voice message
            bot.send_voice(message.chat.id, open(speech_file, 'rb'))

        logging.info("Voice response and text sent.")
    else:
        print("Could not understand the voice message.")
        bot.reply_to(message, "Sorry, I couldn't understand the voice message.")



logging.basicConfig(level=logging.INFO)

# Start polling
print("Bot is starting...")
bot.polling()

while True:
    schedule.run_pending()
    time.sleep(60)
