import telebot
import asyncio
import logging
import speech_recognition as sr
from g4f.client import Client
import g4f
import subprocess
from gtts import gTTS
import os
import time
import sqlite3
from telebot import types

# Dynamically add ffmpeg binary directory to PATH
os.environ["PATH"] += os.pathsep + r"C:\ffmpeg\bin"

# Initialize the Telegram bot
TOKEN = '6597776046:AAFi8E55Rwfv1_Tt2D9QtCv04ylvx20_Os4'
bot = telebot.TeleBot(TOKEN)

# Initialize the g4f client
g4f_client = Client()

# Introduction message
INTRODUCTION_MESSAGE = "For now on you are Amm, an English teacher. Ask me anything."

# Free period in seconds (5 minutes)
FREE_PERIOD = 1 * 10  # 10 seconds for testing

# Payment message
PAYMENT_MESSAGE = "Your free period is over. Please make a payment to continue using the bot."

# Admin user ID
ADMIN_USER_ID = 1262676599

# Database setup
def init_db():
    conn = sqlite3.connect('user_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS used_free_period (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS premium_users (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

# Function to check if user has used the free period
def has_used_free_period(user_id):
    conn = sqlite3.connect('user_data.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM used_free_period WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

# Function to mark user as having used the free period
def mark_free_period_used(user_id):
    conn = sqlite3.connect('user_data.db')
    c = conn.cursor()
    c.execute('INSERT INTO used_free_period (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

# Function to check if user is a premium user
def is_premium_user(user_id):
    conn = sqlite3.connect('user_data.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM premium_users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

# Function to mark user as premium
def mark_as_premium(user_id):
    conn = sqlite3.connect('user_data.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO premium_users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()


# Function to clear all entries in the used_free_period table
def clear_used_free_periods():
    conn = sqlite3.connect('user_data.db')
    c = conn.cursor()
    c.execute('DELETE FROM used_free_period')
    conn.commit()
    conn.close()

# Initialize the database
init_db()

# Dictionary to track user interaction times
user_start_times = {}

# Function to generate response using g4f
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

# Start command handler
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    # if has_used_free_period(user_id) or is_premium_user(user_id):
    #     bot.reply_to(message, PAYMENT_MESSAGE)
    # else:
    user_start_times[user_id] = time.time()
    markup = types.ReplyKeyboardMarkup(row_width=1)
    markup.add(types.KeyboardButton('Transcribe'), types.KeyboardButton('Translation'), types.KeyboardButton('Profile'))
    bot.reply_to(message, INTRODUCTION_MESSAGE, reply_markup=markup)

# Transcribe button handler
@bot.message_handler(func=lambda message: message.text == 'Transcribe')
def handle_transcribe_button(message):
    user_id = message.from_user.id
    if not is_premium_user(user_id):
        bot.reply_to(message, "This feature is available only for premium users.")
    else:
        bot.reply_to(message, "Please provide the YouTube URL for transcription.")

# Translation button handler
@bot.message_handler(func=lambda message: message.text == 'Translation')
def handle_translation_button(message):
    bot.reply_to(message, "Please enter the text you want to translate.")

# Profile button handler
@bot.message_handler(func=lambda message: message.text == 'Profile')
def handle_profile_button(message):
    user_id = message.from_user.id
    if is_premium_user(user_id):
        bot.reply_to(message, "Your status: Premium")
    else:
        bot.reply_to(message, "Your status: Free")


# /paid7 command handler (simulate payment)
@bot.message_handler(commands=['paid7'])
def handle_paid7(message):
    user_id = message.from_user.id
    if user_id == ADMIN_USER_ID:
        mark_as_premium(user_id)
        bot.reply_to(message, 'Thank you for your payment! You can now continue using the bot.')
        # Remove user from free users table if present
        conn = sqlite3.connect('user_data.db')
        c = conn.cursor()
        c.execute('DELETE FROM used_free_period WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
    else:
        bot.reply_to(message, "You are not authorized to use this command.")



# Help command handler
@bot.message_handler(commands=['help'])
def send_help(message):
    print("Help command received.")
    bot.reply_to(message, "You can ask me anything, and I will try to help you.")

# /saf command handler (clear used free periods)
@bot.message_handler(commands=['saf'])
def handle_saf(message):
    user_id = message.from_user.id
    if user_id == ADMIN_USER_ID:
        clear_used_free_periods()
        bot.reply_to(message, "All used free periods have been cleared.")
    else:
        bot.reply_to(message, "You are not authorized to use this command.")

# Payment request function
def request_payment(chat_id):
    pass  # Placeholder for payment functionality

# Pre-checkout query handler
@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

# Successful payment handler
@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    user_id = message.from_user.id
    mark_as_premium(user_id)
    bot.send_message(message.chat.id, 'Thank you for your payment! You can now continue using the bot.')

# Check if the user is within the free period
def is_within_free_period(user_id):
    if user_id not in user_start_times:
        return False
    start_time = user_start_times[user_id]
    elapsed_time = time.time() - start_time
    if elapsed_time > FREE_PERIOD:
        mark_free_period_used(user_id)
        return False
    return True
# Handle voice messages
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    user_id = message.from_user.id
    if not is_within_free_period(user_id) and not is_premium_user(user_id):
        request_payment(message.chat.id)
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
        user_message_with_reminder = f"Remember, For now you are Amm, an English teacher, give me short answers not very long {text}"

        print("Generating response for voice message...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ai_response = loop.run_until_complete(generate_response(user_message_with_reminder))

        print("Converting text response to speech...")
        speech_file = text_to_speech(ai_response)

        print("Sending voice response...")
        bot.send_voice(message.chat.id, open(speech_file, 'rb'))

        logging.info("Voice response sent.")
    else:
        print("Could not understand the voice message.")
        bot.reply_to(message, "Sorry, I couldn't understand the voice message.")

# Message handler for text messages
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    if not is_within_free_period(user_id) and not is_premium_user(user_id):
        request_payment(message.chat.id)
        return

    if message.text:
        print("Text message received:", message.text)
        user_message = message.text
        user_message_with_reminder = f"Remember, For now you are Amm, an English teacher, give me short answers not very long {user_message}"

        print("Generating response for text message...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ai_response = loop.run_until_complete(generate_response(user_message_with_reminder))

        bot.reply_to(message, ai_response)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Start polling
print("Bot is starting...")
bot.polling()
