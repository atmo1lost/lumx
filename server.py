import asyncio
import shutil
import os
import subprocess
import re
import sys
import websockets

print("server starting")

clients = set()
PORT = 8765


def ensure_cloudflared():
    cloudflared_path = os.environ.get("CLOUDFLARED_PATH", "cloudflared")
    if shutil.which(cloudflared_path):
        return cloudflared_path

    if sys.platform.startswith("linux"):
        install_cmds = [
            ["sudo", "apt-get", "update"],
            ["sudo", "apt-get", "install", "-y", "cloudflared"],
        ]
    elif sys.platform == "darwin":
        install_cmds = [
            ["brew", "install", "cloudflared"],
        ]
    else:
        raise FileNotFoundError("cloudflared is not installed and no autoinstall path is known for this platform")

    for cmd in install_cmds:
        print(f"running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)

    if shutil.which(cloudflared_path):
        return cloudflared_path

    raise FileNotFoundError("cloudflared installation finished but the binary was not found on PATH")


async def start_cloudflared(port):
    cloudflared_path = ensure_cloudflared()
    cmd = [cloudflared_path, "tunnel", "--url", f"http://localhost:{port}"]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

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

async def echo(websocket):
    print("client connected")
    clients.add(websocket)
    try:
        async for message in websocket:
            if not message.strip():
                continue
            print(f"received: {message}")
            dead_clients = set()
            for client in clients.copy():
                if client is websocket:
                    continue
                try:
                    await client.send(message)
                except websockets.ConnectionClosed:
                    dead_clients.add(client)
            clients.difference_update(dead_clients)
    finally:
        clients.discard(websocket)

async def main():
    tunnel_process = None
    public_url = None

    use_cloudflared = os.environ.get("LUMX_USE_CLOUDFLARED", "1") == "1"
    if use_cloudflared:
        try:
            tunnel_process, public_url = await start_cloudflared(PORT)
            print(f"lumx-server link: {public_url}")
        except FileNotFoundError:
            print("cloudflared was not found on PATH, running locally only")
        except RuntimeError as exc:
            print(str(exc))

    async with websockets.serve(echo, "localhost", PORT):
        # if public_url:
        #     print(f"lumx-server running on {public_url}")
        # else:
        #     print(f"lumx-server running on ws://localhost:{PORT}")
        await asyncio.Future()

    if tunnel_process is not None:
        tunnel_process.terminate()

asyncio.run(main())
