import asyncio
import base64
import json
import shutil
import os
import subprocess
import re
import sys
import secrets
import websockets
import yaml
import pyperclip

with open("config.yml", "r") as f:
    config = yaml.safe_load(f)

print("server starting")

# aigh aigh aighhhhhhh
rooms = {}
PORT = 8765

if config["dev"]["verbose"] == True:
    print("ensuring cloudflared is installed")
def ensure_cloudflared():
    if config["dev"]["verbose"] == True:
        print("checking paths")
    cloudflared_path = os.environ.get("CLOUDFLARED_PATH", "cloudflared")
    if shutil.which(cloudflared_path):
        return cloudflared_path

    if sys.platform.startswith("linux"):
        install_cmds = [
            ["sudo", "apt", "update"],
            ["sudo", "apt", "install", "-y", "cloudflared"],
        ]

    elif sys.platform == "darwin":
        install_cmds = [
            ["brew", "install", "cloudflared"],
        ]

    elif sys.platform.startswith == "win32" or "win" or "windows":
        install_cmds = [
            ["cloudflared.exe", "service", "install"],
        ]
    else:
        if config["dev"]["verbose"] == True:
            print("issue!! look below.")
        raise FileNotFoundError("cloudflared is not installed and no autoinstall path is known for this platform\nremember to check docs at https://github.com/atmo1lost/lumx/wiki")

    for cmd in install_cmds:
        print(f"running: {' '.join(cmd)}")
        try:
            if config["dev"]["verbose"] == True:
                print("running subprocess to install")
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            raise FileNotFoundError(f"cloudflared install command failed: {' '.join(cmd)}") from exc

    if shutil.which(cloudflared_path):
        return cloudflared_path

    raise FileNotFoundError("cloudflared installation finished but the binary was not found on PATH")


async def start_cloudflared(port):
    print("starting cloudflared")
    cloudflared_path = ensure_cloudflared()
    cmd = [cloudflared_path, "tunnel", "--url", f"http://localhost:{port}"]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if config["dev"]["verbose"] == True:
        print("recompiling cloudflared url")
    pattern = re.compile(r"https://[^\s]+\.trycloudflare\.com")
    for _ in range(60):
        line = process.stdout.readline() if process.stdout else ""
        if line:
            match = pattern.search(line)
            if match:
                public_url = match.group(0).replace("https://", "wss://")
                return process, public_url
        await asyncio.sleep(0.25)

    process.terminate()
    raise RuntimeError("cloudflared started, but no public tunnel URL was found")

def get_room(room_name):
    if config["dev"]["verbose"] == True:
        print("getting rooms")
    room = rooms.get(room_name)
    if room is None:
        if config["dev"]["verbose"] == True:
            print("creating salt.")
        room = {
            # crate the salt
            "salt": secrets.token_bytes(16),
            "clients": set(),
        }
        if config["dev"]["verbose"] == True:
            print("finished creating room salt.")
        rooms[room_name] = room
    return room


async def echo(websocket):
    print("client connected")
    room = None
    try:
        raw_join = await websocket.recv()
        join = json.loads(raw_join)
        if join.get("type") != "join":
            await websocket.send(json.dumps({"type": "error", "message": "first message must be join"}))
            return

        room_name = str(join.get("room", "")).strip()
        username = str(join.get("username", "")).strip()
        if not room_name or not username:
            await websocket.send(json.dumps({"type": "error", "message": "missing room or username"}))
            return

        room = get_room(room_name)
        room["clients"].add(websocket)
        await websocket.send(
            json.dumps(
                {
                    "type": "joined",
                    "room": room_name,
                    "salt": base64.b64encode(room["salt"]).decode("ascii"),
                }
            )
        )
        print(f"client joined room: {room_name}")

        async for message in websocket:
            if not message.strip():
                continue
            print(f"received: {message}")
            dead_clients = set()
            for client in room["clients"].copy():
                if client is websocket:
                    continue
                try:
                    await client.send(message)
                except websockets.ConnectionClosed:
                    dead_clients.add(client)
            room["clients"].difference_update(dead_clients)
    finally:
        if room is not None:
            room["clients"].discard(websocket)

async def main():
    tunnel_process = None
    public_url = None

    use_cloudflared = os.environ.get("LUMX_USE_CLOUDFLARED", "1") == "1"
    if use_cloudflared:
        try:
            tunnel_process, public_url = await start_cloudflared(PORT)
            if public_url:
                serve_text = f"lumx-server running on: {public_url}"
            else:
                serve_text = "lumx-server running on: ws://localhost:8765"
            print(serve_text)
            pyperclip.copy(public_url)
            print("url copied.")
        except FileNotFoundError:
            print("cloudflared was not found on PATH, running locally only")
        except RuntimeError as exc:
            print(str(exc))
        except subprocess.CalledProcessError:
            print("cloudflared install failed, running locally only")

    async with websockets.serve(echo, "localhost", PORT):
        
        await asyncio.Future()

    if tunnel_process is not None:
        tunnel_process.terminate()

asyncio.run(main())
