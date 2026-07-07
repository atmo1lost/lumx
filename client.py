import asyncio
import base64
import contextlib
import json
import websockets
from nacl import pwhash, secret, exceptions

ROOM_SALT = b"lumx-chat-key!!1"  # exactly 16 bytes

def make_box(room_key: str | None):
    if not room_key:
        return None

    key = pwhash.argon2id.kdf(
        secret.SecretBox.KEY_SIZE,
        room_key.encode("utf-8"),
        ROOM_SALT,
        opslimit=pwhash.argon2id.OPSLIMIT_MODERATE,
        memlimit=pwhash.argon2id.MEMLIMIT_MODERATE,
    )
    return secret.SecretBox(key)


async def client():
    username = input("username: ").strip()
    if username == "":
        print("invalid username, try again.")
        username = input("username: ").strip()
    room_key = input("room key (leave blank for plaintext): ").strip()

    print("(leave none for localhost)")
    server = input("websocket: ").strip()
    if server == "":
        server = "ws://localhost:8765"

    box = make_box(room_key)

    async with websockets.connect(server) as websocket:
        print(f"connected as {username}")

        async def receiver():
            async for message in websocket:
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    if message.startswith(f"{username}: "):
                        continue
                    print(f"\r{message}\n>: ", end="", flush=True)
                    continue

                if payload.get("type") == "encrypted":
                    if box is None:
                        print("\r[encrypted message received, but no room key is set]\n>: ", end="", flush=True)
                        continue

                    try:
                        ciphertext = base64.b64decode(payload["ciphertext"])
                        plaintext = box.decrypt(ciphertext).decode("utf-8")
                        sender = payload.get("username", "unknown")
                        print(f"\r{sender}: {plaintext}\n>: ", end="", flush=True)
                    except (KeyError, ValueError, exceptions.CryptoError, UnicodeDecodeError):
                        print("\r[unable to decrypt message]\n>: ", end="", flush=True)
                    continue

                if message.startswith(f"{username}: "):
                    continue
                print(f"\r{message}\n>: ", end="", flush=True)

        receive_task = asyncio.create_task(receiver())

        try:
            while True:
                message = await asyncio.to_thread(input, ">: ")

                if box is None:
                    await websocket.send(f"{username}: {message}")
                    continue

                ciphertext = box.encrypt(message.encode("utf-8"))
                await websocket.send(
                    json.dumps(
                        {
                            "type": "encrypted",
                            "username": username,
                            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
                        }
                    )
                )
        except (EOFError, KeyboardInterrupt):
            pass
        finally:
            receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await receive_task
            print()


asyncio.run(client())
