import asyncio
import base64
import contextlib
import json
import random
import string

import websockets
import yaml
from nacl import exceptions, pwhash, secret

with open("config.yml", "r") as f:
    config = yaml.safe_load(f)


def make_box(room_key: str | None, room_salt: bytes | None):
    if not room_key or room_salt is None:
        return None

    key = pwhash.argon2id.kdf(
        secret.SecretBox.KEY_SIZE,
        room_key.encode("utf-8"),
        room_salt,
        opslimit=pwhash.argon2id.OPSLIMIT_MODERATE,
        memlimit=pwhash.argon2id.MEMLIMIT_MODERATE,
    )
    return secret.SecretBox(key)


async def client():
    # get username from config, if it returns false get username from input, if blank generate a random 4c
    username = config["client"].get("username") or input("username: ").strip()  or ''.join(random.choices(string.ascii_letters + string.digits, k=4))

    # get room key, encryption is mandatory so this cannot be blank
    room_key = config["client"].get("room_key")
    while not room_key:
        room_key = input("room key (required, all messages are encrypted): ").strip()

    # get server from config, if it returns false get server from input, if blank use localhost
    server = config["client"].get("server") or input("server: ").strip() or "ws://127.0.0.1:8765"

    # get room name from config, if it returns false get it from input, if blank it is "general"
    room_name = config["client"].get("channel") or input("room: ").strip() or "general"

    # sends {server} the needed data to join
    async with websockets.connect(server) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "join",
                    "username": username,
                    "room": room_name,
                }
            )
        )

        # if server doesnt respond (most likely a typo)
        try:
            join_response = json.loads(await websocket.recv())
        except json.JSONDecodeError:
            print("failed to join channel: invalid server response")
            return

        # if join type isnt "joined" then send error
        if join_response.get("type") != "joined":
            print(join_response.get("message", "failed to join channel"))
            return

        # gets serverside salt
        room_salt_b64 = join_response.get("salt")
        room_salt = base64.b64decode(room_salt_b64) if room_salt_b64 else None
        box = make_box(room_key, room_salt)

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

                    # if message returns but you cant decrypt it (due to a diffrent room key)
                if payload.get("type") == "encrypted":
                    if box is None:
                        print(
                            "\r[encrypted message received, but no room key is set]\n>: ",
                            end="",
                            flush=True,
                        )
                        continue

                    try:
                        ciphertext = base64.b64decode(payload["ciphertext"])
                        plaintext = box.decrypt(ciphertext).decode("utf-8")
                        sender = payload.get("username", "unknown")
                        print(f"\r{sender}: {plaintext}\n>: ", end="", flush=True)
                    except (
                        KeyError,
                        ValueError,
                        exceptions.CryptoError,
                        UnicodeDecodeError,
                    ):
                        print("\r[unable to decrypt message]\n>: ", end="", flush=True)
                    continue

                if message.startswith(f"{username}: "):
                    continue
                print(f"\r{message}\n>: ", end="", flush=True)

        receive_task = asyncio.create_task(receiver())

        if box is None:
            print("failed to set up encryption, aborting")
            return

        try:
            while True:
                message = await asyncio.to_thread(input, ">: ")
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