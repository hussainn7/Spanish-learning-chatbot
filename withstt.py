import telebot
import asyncio
import logging
import speech_recognition as sr
from g4f.client import Client
import g4f
import subprocess
from gtts import gTTS
import os

# Initialize the Telegram bot
TOKEN = '6597776046:AAFi8E55Rwfv1_Tt2D9QtCv04ylvx20_Os4'
bot = telebot.TeleBot(TOKEN)

# Initialize the g4f client
g4f_client = Client()

# Introduction message
INTRODUCTION_MESSAGE = "For now on you are Amm, an English teacher. Ask me anything."

# Function to generate response using g4f
async def generate_response(text):
    print("Generating response...")
    response = await g4f.ChatCompletion.create_async(
        model=g4f.models.default,
        messages=[{"role": "user", "content": text}],
        provider=g4f.Provider.PerplexityLabs
    )
    print("Response generated.")
    return response  # Directly return the response since it's a string

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
    # Use ffmpeg to convert the file, adding the -y flag to overwrite without prompting
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
    print("Start command received.")
    bot.reply_to(message, INTRODUCTION_MESSAGE)

# Help command handler
@bot.message_handler(commands=['help'])
def send_help(message):
    print("Help command received.")
    bot.reply_to(message, "You can ask me anything, and I will try to help you.")

# Handle voice messages
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    print("Voice message received.")
    file_info = bot.get_file(message.voice.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    print("Voice file downloaded.")

    # Save voice message file locally
    with open('voice_message.ogg', 'wb') as new_file:
        new_file.write(downloaded_file)
    print("Voice file saved locally as 'voice_message.ogg'.")

    # Convert voice message to text
    print("Converting voice message to text...")
    wav_file = convert_to_wav('voice_message.ogg')
    text = voice_to_text(wav_file)
    if text:
        print("Voice message converted to text:", text)
        # Prepend reminder to user's message
        user_message_with_reminder = f"Remember, For now you are Amm, an English teacher, give me short answers not very long {text}"

        # Run the async function using asyncio
        print("Generating response for voice message...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ai_response = loop.run_until_complete(generate_response(user_message_with_reminder))

        # Convert text response to speech
        print("Converting text response to speech...")
        speech_file = text_to_speech(ai_response)

        # Send voice message
        print("Sending voice response...")
        bot.send_voice(message.chat.id, open(speech_file, 'rb'))

        logging.info("Voice response sent.")
    else:
        print("Could not understand the voice message.")
        bot.reply_to(message, "Sorry, I couldn't understand the voice message.")

# Message handler for text messages
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if message.text:  # If the message is a text message
        print("Text message received:", message.text)
        user_message = message.text

        # Prepend reminder to user's message
        user_message_with_reminder = f"Remember, For now you are Amm, an English teacher, give me short answers not very long {user_message}"

        # Run the async function using asyncio
        print("Generating response for text message...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ai_response = loop.run_until_complete(generate_response(user_message_with_reminder))

        bot.reply_to(message, ai_response)  # Reply with text

# Configure logging
logging.basicConfig(level=logging.INFO)

# Start polling
print("Bot is starting...")
bot.polling()
