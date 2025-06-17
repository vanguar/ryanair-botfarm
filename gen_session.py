from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = 21727703
api_hash = "40c7f691abb0735c549cdb580c45f624"

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\nYour StringSession:\n")
    print(client.session.save())
