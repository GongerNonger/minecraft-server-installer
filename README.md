# Minecraft Server Installer

A Windows-based wizard that sets up a fully configured Minecraft server in minutes. Supports modpacks, vanilla, plugins, and mods — no technical knowledge required.

![Version](https://img.shields.io/badge/version-1.3-green) ![Platform](https://img.shields.io/badge/platform-Windows-blue) ![Python](https://img.shields.io/badge/python-3.10%2B-blue)

---

## Features

- **Modpack servers** — paste any CurseForge modpack URL and it sets everything up automatically
- **Custom servers** — Vanilla, Paper (plugins), or Fabric (mods)
- **Auto Java install** — downloads Temurin JRE 21 if Java isn't found
- **Mod downloading** — supports Modrinth URLs/slugs and CurseForge URLs
- **playit.gg tunnel** — free tunneling so friends can join without port forwarding, and your home IP stays hidden
- **Rolling backups** — automatic backup every 30 minutes, keeps the last 4
- **Daily backups** — automatic backup at 3:00 AM, keeps the last 7
- **Auto-start on boot** — registers a Windows Task Scheduler entry so the server starts automatically
- **Gonger Certified** ✦

---

## Usage

### Option A — Download the .exe (easiest)

1. Download `MinecraftServerInstaller.exe` from [Releases](../../releases)
2. Double-click it
3. Follow the wizard

### Option B — Run from source

```bash
pip install pyinstaller
python mc_setup.py
```

---

## Modpack Setup

1. Choose **Modpack server** at the first prompt
2. Paste a CurseForge modpack URL, e.g.:
   ```
   https://www.curseforge.com/minecraft/modpacks/liminal-industries
   ```
3. The installer fetches the server pack, installs Forge/Fabric automatically, and writes the start scripts

> **CurseForge API key required for modpacks.**
> Get a free key at [console.curseforge.com](https://console.curseforge.com) → API Keys.
> The key is saved locally to `~\.mc_installer_config.json` and never shared.

### Friends setup
Friends don't need the server files — they just install the same modpack through the **CurseForge app** or **Prism Launcher** on their own PC.

---

## Backup Structure

```
ServerFolder/
  backups/
    rolling/   ← every 30 min, last 4 kept
    daily/     ← every day at 3 AM, last 7 kept
```

You can also run `backup_rolling.bat` or `backup_daily.bat` manually at any time.

---

## Networking

| Option | How it works |
|---|---|
| **playit.gg** | Free tunnel — no port forwarding, home IP hidden. Friends get an address like `abc.at.gg:12345` |
| **Port forwarding** | Open a port on your router and share your public IP with friends |

---

## Building the .exe

Requires Python 3.10+ and PyInstaller:

```bash
pip install pyinstaller
pyinstaller --onefile --console --name MinecraftServerInstaller mc_setup.py
```

Output is in `dist/MinecraftServerInstaller.exe`.

---

## Requirements

- Windows 10 / 11
- Internet connection
- Java 21 (auto-downloaded if missing)
