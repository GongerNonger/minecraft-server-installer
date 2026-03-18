"""
Minecraft Server Installer  v1.3
Supports: Modpack (CurseForge), Vanilla, Paper (plugins), Fabric (mods)
Mod sources: Modrinth slugs, Modrinth URLs, CurseForge URLs, modlist.txt file
"""

import os
import re
import ssl
import sys
import json
import shutil
import zipfile
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# Disable SSL verification — certificates are not bundled in the exe and all
# download targets are known trusted hosts (GitHub, Adoptium, CurseForge, etc.)
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


# ── Config file (stores CurseForge API key, never hardcoded) ────────────────
CONFIG_PATH = Path.home() / ".mc_installer_config.json"

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}

def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


# ── Colour helpers ───────────────────────────────────────────────────────────
def c(text, colour):
    codes = {"green": "\033[92m", "yellow": "\033[93m",
             "red": "\033[91m", "cyan": "\033[96m", "bold": "\033[1m", "reset": "\033[0m"}
    return f"{codes.get(colour,'')}{text}{codes['reset']}"

def header(text):
    width = 60
    print("\n" + "=" * width)
    print(f"  {c(text, 'bold')}")
    print("=" * width)

def info(msg):  print(f"  {c('>', 'cyan')} {msg}")
def ok(msg):    print(f"  {c('✓', 'green')} {msg}")
def warn(msg):  print(f"  {c('!', 'yellow')} {msg}")
def err(msg):   print(f"  {c('✗', 'red')} {msg}")

def ask(prompt, default=None):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        val = input(f"  {c('?', 'cyan')} {prompt}{suffix}: ").strip()
        if val == "" and default is not None:
            return default
        if val:
            return val

def ask_int(prompt, default, lo, hi):
    while True:
        val = ask(prompt, default)
        try:
            n = int(val)
            if lo <= n <= hi:
                return n
        except ValueError:
            pass
        warn(f"Please enter a number between {lo} and {hi}.")

def ask_yn(prompt, default="y"):
    while True:
        val = ask(prompt + " (y/n)", default).lower()
        if val in ("y", "yes"):
            return True
        if val in ("n", "no"):
            return False


# ── Downloader ───────────────────────────────────────────────────────────────
def download(url, dest, label="", extra_headers=None):
    label = label or Path(dest).name
    info(f"Downloading {label} ...")
    try:
        headers = {"User-Agent": "mc-installer/1.2"}
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=_SSL_CTX) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length", 0))
            done = 0
            while chunk := r.read(65536):
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = int(done / total * 30)
                    bar = "█" * pct + "░" * (30 - pct)
                    print(f"\r    [{bar}] {done//1024}KB / {total//1024}KB ", end="", flush=True)
        print()
        ok(f"Downloaded {label}")
    except Exception as e:
        err(f"Failed to download {label}: {e}")
        sys.exit(1)


# ── Java ─────────────────────────────────────────────────────────────────────
def _find_java_in_common_paths():
    """Check common Windows Java install locations."""
    search_roots = [
        Path("C:/Program Files/Java"),
        Path("C:/Program Files/Eclipse Adoptium"),
        Path("C:/Program Files/Microsoft"),
        Path("C:/Program Files/Amazon Corretto"),
        Path("C:/Program Files/Zulu"),
    ]
    for root in search_roots:
        if root.exists():
            for java_exe in root.rglob("java.exe"):
                if "bin" in java_exe.parts:
                    return str(java_exe)
    return None

def _fetch_jre_download_url():
    """Get the latest Temurin 21 JRE zip URL from the Adoptium API."""
    try:
        api_url = (
            "https://api.adoptium.net/v3/assets/latest/21/hotspot"
            "?architecture=x64&image_type=jre&os=windows&vendor=eclipse"
        )
        data = _get_json(api_url)
        for asset in data:
            binary = asset.get("binary", {})
            pkg = binary.get("package", {})
            url = pkg.get("link", "")
            if url.endswith(".zip"):
                return url
    except Exception:
        pass
    # Hard fallback to a known-good release
    return (
        "https://github.com/adoptium/temurin21-binaries/releases/download/"
        "jdk-21.0.7%2B6/OpenJDK21U-jre_x64_windows_hotspot_21.0.7_6.zip"
    )

def ensure_java(install_dir: Path):
    # 1. Java already on PATH
    java = shutil.which("java")
    if java:
        ok(f"Java found: {java}")
        return "java"

    # 2. Already bundled from a previous install
    bundled = install_dir / "jre" / "bin" / "java.exe"
    if bundled.exists():
        ok("Bundled Java found.")
        return str(bundled)

    # 3. Check common Windows install locations
    found = _find_java_in_common_paths()
    if found:
        ok(f"Java found: {found}")
        return found

    # 4. Download and bundle Temurin JRE 21
    warn("Java not found — downloading Temurin JRE 21 (one-time, ~50 MB)...")
    jre_url = _fetch_jre_download_url()
    info(f"Source: {jre_url}")
    jre_zip = install_dir / "jre.zip"
    jre_dir = install_dir / "jre"
    download(jre_url, str(jre_zip), "Java 21 JRE")
    info("Extracting Java...")
    try:
        with zipfile.ZipFile(jre_zip, "r") as z:
            z.extractall(str(install_dir / "_jre_tmp"))
    except Exception as e:
        err(f"Failed to extract Java: {e}")
        sys.exit(1)
    extracted = list((install_dir / "_jre_tmp").iterdir())
    if extracted:
        if jre_dir.exists():
            shutil.rmtree(str(jre_dir))
        shutil.move(str(extracted[0]), str(jre_dir))
    shutil.rmtree(str(install_dir / "_jre_tmp"), ignore_errors=True)
    jre_zip.unlink(missing_ok=True)
    for p in jre_dir.rglob("java.exe"):
        ok("Java 21 installed.")
        return str(p)
    err("Could not locate java.exe after extraction.")
    sys.exit(1)


# ── Server jar helpers ────────────────────────────────────────────────────────
MINECRAFT_VERSIONS = ["1.21.4", "1.21.1", "1.20.6", "1.20.4", "1.20.1", "1.19.4"]

def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mc-installer/1.2"})
    return json.loads(urllib.request.urlopen(req, context=_SSL_CTX).read())

def fetch_paper_url(mc_version):
    try:
        data  = _get_json(f"https://api.papermc.io/v2/projects/paper/versions/{mc_version}")
        build = max(data["builds"])
        data2 = _get_json(f"https://api.papermc.io/v2/projects/paper/versions/{mc_version}/builds/{build}")
        fname = data2["downloads"]["application"]["name"]
        return f"https://api.papermc.io/v2/projects/paper/versions/{mc_version}/builds/{build}/downloads/{fname}"
    except Exception as e:
        err(f"Failed to get Paper URL: {e}"); sys.exit(1)

def fetch_fabric_loader(mc_version):
    try:
        loader    = _get_json(f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}")[0]["loader"]["version"]
        installer = _get_json("https://meta.fabricmc.net/v2/versions/installer")[0]["version"]
        return loader, installer
    except Exception as e:
        err(f"Failed to get Fabric loader info: {e}"); sys.exit(1)

def fetch_fabric_installer_url():
    try:
        return _get_json("https://meta.fabricmc.net/v2/versions/installer")[0]["url"]
    except Exception as e:
        err(f"Failed to get Fabric installer URL: {e}"); sys.exit(1)


# ── Mod source detection ──────────────────────────────────────────────────────
CF_URL_RE  = re.compile(r"curseforge\.com/minecraft/mc-mods/([A-Za-z0-9\-_]+)", re.I)
MR_URL_RE  = re.compile(r"modrinth\.com/mod/([A-Za-z0-9\-_]+)", re.I)

def parse_mod_entry(raw: str):
    raw = raw.strip()
    cf = CF_URL_RE.search(raw)
    if cf:
        return ("curseforge", cf.group(1))
    mr = MR_URL_RE.search(raw)
    if mr:
        return ("modrinth", mr.group(1))
    if raw:
        return ("modrinth_slug", raw)
    return None


# ── Modrinth downloader ───────────────────────────────────────────────────────
def fetch_mod_modrinth(slug, mc_version, loader, mods_dir: Path) -> bool:
    try:
        url  = (f"https://api.modrinth.com/v2/project/{slug}/version"
                f"?game_versions=[\"{mc_version}\"]&loaders=[\"{loader}\"]")
        data = _get_json(url)
        if not data:
            warn(f"No Modrinth version for '{slug}' on {mc_version}/{loader} — skipping.")
            return False
        file_info = data[0]["files"][0]
        download(file_info["url"], str(mods_dir / file_info["filename"]), file_info["filename"])
        return True
    except Exception as e:
        warn(f"Modrinth '{slug}': {e}")
        return False


# ── CurseForge downloader ─────────────────────────────────────────────────────
CF_LOADER_MAP = {"fabric": 4, "forge": 1, "quilt": 5, "neoforge": 6}
CF_GAME_ID    = 432  # Minecraft

def fetch_mod_curseforge(slug, mc_version, loader, mods_dir: Path, api_key: str) -> bool:
    headers = {"x-api-key": api_key, "User-Agent": "mc-installer/1.2"}
    try:
        search_url = (f"https://api.curseforge.com/v1/mods/search"
                      f"?gameId={CF_GAME_ID}&slug={slug}&pageSize=1")
        req  = urllib.request.Request(search_url, headers=headers)
        data = json.loads(urllib.request.urlopen(req, context=_SSL_CTX).read())
        mods = data.get("data", [])
        if not mods:
            warn(f"CurseForge: could not find mod '{slug}' — skipping.")
            return False
        mod_id = mods[0]["id"]
        mod_name = mods[0]["name"]

        loader_type = CF_LOADER_MAP.get(loader, 4)
        files_url = (f"https://api.curseforge.com/v1/mods/{mod_id}/files"
                     f"?gameVersion={mc_version}&modLoaderType={loader_type}&pageSize=5")
        req2  = urllib.request.Request(files_url, headers=headers)
        fdata = json.loads(urllib.request.urlopen(req2).read())
        files = fdata.get("data", [])

        if not files:
            files_url2 = (f"https://api.curseforge.com/v1/mods/{mod_id}/files"
                          f"?gameVersion={mc_version}&pageSize=5")
            req3  = urllib.request.Request(files_url2, headers=headers)
            fdata2 = json.loads(urllib.request.urlopen(req3).read())
            files = fdata2.get("data", [])

        if not files:
            warn(f"CurseForge: no file for '{mod_name}' on {mc_version}/{loader} — skipping.")
            return False

        best = sorted(files, key=lambda f: f["fileDate"], reverse=True)[0]
        dl_url  = best.get("downloadUrl")
        fname   = best["fileName"]

        if not dl_url:
            warn(f"CurseForge: '{mod_name}' has no direct download URL (restricted mod) — skipping.")
            return False

        download(dl_url, str(mods_dir / fname), fname, extra_headers={"x-api-key": api_key})
        return True

    except urllib.error.HTTPError as e:
        if e.code == 403:
            warn(f"CurseForge API key rejected. Check your key and try again.")
        else:
            warn(f"CurseForge '{slug}': HTTP {e.code}")
        return False
    except Exception as e:
        warn(f"CurseForge '{slug}': {e}")
        return False


# ── Unified mod downloader ────────────────────────────────────────────────────
def download_mod(source, slug, mc_version, loader, mods_dir, cf_api_key) -> bool:
    if source == "curseforge":
        if not cf_api_key:
            warn(f"Skipping CurseForge mod '{slug}' — no API key set.")
            return False
        return fetch_mod_curseforge(slug, mc_version, loader, mods_dir, cf_api_key)
    else:
        return fetch_mod_modrinth(slug, mc_version, loader, mods_dir)


# ── modlist.txt parser ────────────────────────────────────────────────────────
def load_modlist_file(path: str) -> list:
    entries = []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as e:
        err(f"Could not read modlist file: {e}")
        return []
    for raw_line in lines:
        line = raw_line.split("#")[0].strip()
        if not line:
            continue
        parsed = parse_mod_entry(line)
        if parsed:
            entries.append(parsed)
    return entries


# ── Preset mods ───────────────────────────────────────────────────────────────
PRESET_MODS = {
    "performance": [
        ("modrinth_slug", "sodium",       "Sodium — rendering engine, massive FPS boost"),
        ("modrinth_slug", "lithium",      "Lithium — game logic & server optimisation"),
        ("modrinth_slug", "ferrite-core", "FerriteCore — memory usage optimisation"),
    ],
    "qol": [
        ("modrinth_slug", "inventory-profiles-next", "Inventory Sort — auto-sort inventory"),
        ("modrinth_slug", "jade",                    "Jade — block info tooltip on crosshair"),
        ("modrinth_slug", "ftb-chunks",              "FTB Chunks — chunk claiming & minimap"),
    ],
    "content": [
        ("modrinth_slug", "create-fabric",           "Create — automation and machinery"),
        ("modrinth_slug", "farmers-delight-fabric",  "Farmer's Delight — farming & cooking"),
        ("modrinth_slug", "waystones",               "Waystones — fast travel waypoints"),
    ],
}


# ── playit.gg ────────────────────────────────────────────────────────────────
def fetch_playit_url() -> str:
    try:
        data   = _get_json("https://api.github.com/repos/playit-cloud/playit-agent/releases/latest")
        assets = data.get("assets", [])
        for keyword in ("windows-x86_64-signed.exe", "windows-x86_64.exe"):
            for asset in assets:
                if keyword in asset["name"]:
                    return asset["browser_download_url"]
    except Exception:
        pass
    return "https://github.com/playit-cloud/playit-agent/releases/download/v0.17.1/playit-windows-x86_64-signed.exe"

def setup_playit(install_dir: Path) -> Path:
    playit_exe = install_dir / "playit.exe"
    if playit_exe.exists():
        ok("playit.exe already present, skipping download.")
        return playit_exe
    url = fetch_playit_url()
    download(url, str(playit_exe), "playit.exe")
    return playit_exe


# ── server.properties ────────────────────────────────────────────────────────
def build_server_properties(config: dict) -> str:
    lines = [
        "# Minecraft server properties",
        f"motd={config['motd']}",
        f"max-players={config['max_players']}",
        f"server-port={config['port']}",
        f"difficulty={config['difficulty']}",
        f"gamemode={config['gamemode']}",
        f"level-name={config['world_name']}",
        f"online-mode={str(config['online_mode']).lower()}",
        f"white-list={str(config['whitelist']).lower()}",
        "enable-rcon=false",
        "spawn-protection=16",
        "view-distance=10",
        "simulation-distance=8",
        "sync-chunk-writes=true",
        "enable-command-block=false",
    ]
    return "\n".join(lines) + "\n"


# ── Startup / backup scripts ─────────────────────────────────────────────────
def build_start_bat(java_path, jar_name, ram_gb, server_dir):
    return f"""@echo off
title Minecraft Server
cd /d "{server_dir}"
:start
echo Starting Minecraft Server...
"{java_path}" -Xmx{ram_gb}G -Xms{ram_gb}G -jar "{jar_name}" nogui
echo Server stopped. Restarting in 5 seconds... (Close this window to stop)
timeout /t 5
goto start
"""

def build_start_bat_forge(java_path, win_args_path: Path, ram_gb, server_dir: Path):
    try:
        rel = win_args_path.relative_to(server_dir)
    except ValueError:
        rel = win_args_path
    return f"""@echo off
title Minecraft Server
cd /d "{server_dir}"
:start
echo Starting Minecraft Server...
"{java_path}" -Xmx{ram_gb}G -Xms{ram_gb}G @{rel} nogui
echo Server stopped. Restarting in 5 seconds... (Close this window to stop)
timeout /t 5
goto start
"""

def build_backup_rolling_bat(server_dir, backup_dir, world_name):
    rolling_dir = str(Path(backup_dir) / "rolling")
    return f"""@echo off
set TIMESTAMP=%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%
set BACKUP_NAME=rolling_%TIMESTAMP%.zip
if not exist "{rolling_dir}" mkdir "{rolling_dir}"
echo Creating rolling backup: %BACKUP_NAME%
powershell -Command "Compress-Archive -Path '{server_dir}\\{world_name}' -DestinationPath '{rolling_dir}\\%BACKUP_NAME%' -Force"
echo Keeping last 4 rolling backups...
powershell -Command "Get-ChildItem '{rolling_dir}' -Filter 'rolling_*.zip' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 4 | Remove-Item -Force"
echo Rolling backup complete.
"""

def build_backup_daily_bat(server_dir, backup_dir, world_name):
    daily_dir = str(Path(backup_dir) / "daily")
    return f"""@echo off
set TIMESTAMP=%date:~-4%%date:~3,2%%date:~0,2%
set TIMESTAMP=%TIMESTAMP: =0%
set BACKUP_NAME=daily_%TIMESTAMP%.zip
if not exist "{daily_dir}" mkdir "{daily_dir}"
echo Creating daily backup: %BACKUP_NAME%
powershell -Command "Compress-Archive -Path '{server_dir}\\{world_name}' -DestinationPath '{daily_dir}\\%BACKUP_NAME%' -Force"
echo Keeping last 7 daily backups...
powershell -Command "Get-ChildItem '{daily_dir}' -Filter 'daily_*.zip' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 7 | Remove-Item -Force"
echo Daily backup complete.
"""

def build_start_bat_playit(java_path, jar_name, ram_gb, server_dir):
    return f"""@echo off
title Minecraft Server
cd /d "{server_dir}"

echo Starting playit.gg tunnel...
start "playit tunnel" /min "{server_dir}\\playit.exe"

echo Waiting for tunnel to initialise...
timeout /t 3 /nobreak > nul

:start
echo Starting Minecraft Server...
"{java_path}" -Xmx{ram_gb}G -Xms{ram_gb}G -jar "{jar_name}" nogui
echo Server stopped. Restarting in 5 seconds... (Close this window to stop)
timeout /t 5
goto start
"""

def build_start_bat_forge_playit(java_path, win_args_path: Path, ram_gb, server_dir: Path):
    try:
        rel = win_args_path.relative_to(server_dir)
    except ValueError:
        rel = win_args_path
    return f"""@echo off
title Minecraft Server
cd /d "{server_dir}"

echo Starting playit.gg tunnel...
start "playit tunnel" /min "{server_dir}\\playit.exe"

echo Waiting for tunnel to initialise...
timeout /t 3 /nobreak > nul

:start
echo Starting Minecraft Server...
"{java_path}" -Xmx{ram_gb}G -Xms{ram_gb}G @{rel} nogui
echo Server stopped. Restarting in 5 seconds... (Close this window to stop)
timeout /t 5
goto start
"""


def register_autostart(server_dir: Path, start_bat: Path):
    task_xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers><BootTrigger><Enabled>true</Enabled></BootTrigger></Triggers>
  <Principals><Principal><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Actions><Exec>
    <Command>"{start_bat}"</Command>
    <WorkingDirectory>{server_dir}</WorkingDirectory>
  </Exec></Actions>
</Task>"""
    xml_path = server_dir / "autostart_task.xml"
    xml_path.write_text(task_xml, encoding="utf-16")
    result = subprocess.run(
        ["schtasks", "/Create", "/TN", "MinecraftServer", "/XML", str(xml_path), "/F"],
        capture_output=True, text=True)
    xml_path.unlink(missing_ok=True)
    if result.returncode == 0:
        ok("Auto-start on boot registered (Task Scheduler).")
    else:
        warn(f"Could not register auto-start: {result.stderr.strip()}")

def register_rolling_backup_task(backup_bat: Path):
    result = subprocess.run(
        ["schtasks", "/Create", "/TN", "MinecraftBackupRolling", "/TR", str(backup_bat),
         "/SC", "MINUTE", "/MO", "30", "/F"],
        capture_output=True, text=True)
    if result.returncode == 0:
        ok("Rolling backup scheduled every 30 minutes (keeps last 4).")
    else:
        warn(f"Could not schedule rolling backup: {result.stderr.strip()}")

def register_daily_backup_task(backup_bat: Path):
    result = subprocess.run(
        ["schtasks", "/Create", "/TN", "MinecraftBackupDaily", "/TR", str(backup_bat),
         "/SC", "DAILY", "/ST", "03:00", "/F"],
        capture_output=True, text=True)
    if result.returncode == 0:
        ok("Daily backup scheduled at 3:00 AM (keeps last 7).")
    else:
        warn(f"Could not schedule daily backup: {result.stderr.strip()}")


# ── CurseForge API key setup ──────────────────────────────────────────────────
def get_cf_api_key(cfg: dict, needed: bool) -> str:
    key = cfg.get("curseforge_api_key", "")
    if key:
        return key
    if not needed:
        return ""
    print(f"""
  {c('CurseForge API Key Required', 'yellow')}
  You have CurseForge mods in your list. A free API key is needed.

  How to get one (2 minutes):
    1. Go to https://console.curseforge.com
    2. Sign up / log in
    3. Create a project → copy the API key

  The key is saved to {CONFIG_PATH} on this PC only.
""")
    key = ask("Paste your CurseForge API key")
    cfg["curseforge_api_key"] = key
    save_config(cfg)
    ok("API key saved.")
    return key

def get_cf_api_key_required(cfg: dict) -> str:
    """Always prompts if no key is stored — modpacks always need one."""
    key = cfg.get("curseforge_api_key", "")
    if key:
        masked = "*" * (len(key) - 4) + key[-4:]
        print(f"\n  {c('CurseForge API key already saved:', 'cyan')} {masked}")
        if ask_yn("Keep this key?", "y"):
            return key
        # User wants to replace it
        key = ""

    print(f"""
  {c('CurseForge API Key Required', 'yellow')}
  Downloading modpacks requires a free CurseForge API key.

  How to get one (2 minutes):
    1. Go to https://console.curseforge.com
    2. Sign up / log in
    3. Go to "API Keys" and copy your key

  The key is saved to {CONFIG_PATH} on this PC only.
""")
    key = ask("Paste your CurseForge API key")
    cfg["curseforge_api_key"] = key
    save_config(cfg)
    ok("API key saved.")
    return key


# ── CurseForge modpack helpers ────────────────────────────────────────────────
CF_MODPACK_URL_RE = re.compile(r"curseforge\.com/minecraft/modpacks/([A-Za-z0-9\-_]+)", re.I)

def parse_modpack_slug(url: str) -> str:
    m = CF_MODPACK_URL_RE.search(url)
    if m:
        return m.group(1)
    # Accept bare slug too
    return url.strip().rstrip("/").split("/")[-1]

def _cf_req(url: str, api_key: str):
    headers = {"x-api-key": api_key, "User-Agent": "mc-installer/1.2"}
    req = urllib.request.Request(url, headers=headers)
    return json.loads(urllib.request.urlopen(req, context=_SSL_CTX).read())

def fetch_modpack_info(slug: str, api_key: str) -> dict:
    """Return the CurseForge mod object for this modpack slug, or None."""
    url = (f"https://api.curseforge.com/v1/mods/search"
           f"?gameId={CF_GAME_ID}&slug={slug}&classId=4471&pageSize=1")
    try:
        data = _cf_req(url, api_key)
        mods = data.get("data", [])
        return mods[0] if mods else None
    except urllib.error.HTTPError as e:
        if e.code == 403:
            err("CurseForge API key rejected.")
            cfg = load_config()
            cfg.pop("curseforge_api_key", None)
            save_config(cfg)
            warn("The saved key has been cleared. Restart the installer to enter a new one.")
            sys.exit(1)
        raise

def fetch_modpack_files(mod_id: int, api_key: str) -> list:
    url = (f"https://api.curseforge.com/v1/mods/{mod_id}/files"
           f"?pageSize=20&sortField=1&sortOrder=desc")
    data = _cf_req(url, api_key)
    return data.get("data", [])

def _is_server_file(f: dict) -> bool:
    name = (f.get("displayName", "") + f.get("fileName", "")).lower()
    return "server" in name

def find_server_pack(files: list):
    """Return the newest file whose name contains 'server', or None."""
    server_files = [f for f in files if _is_server_file(f)]
    if server_files:
        return sorted(server_files, key=lambda f: f.get("fileDate", ""), reverse=True)[0]
    return None

def find_client_pack(files: list):
    """Return the newest non-server file."""
    client_files = [f for f in files if not _is_server_file(f)]
    pool = client_files if client_files else files
    if pool:
        return sorted(pool, key=lambda f: f.get("fileDate", ""), reverse=True)[0]
    return None

META_FILE = ".mc_installer_meta.json"

def load_install_meta(install_dir: Path) -> dict:
    meta_path = install_dir / META_FILE
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text())
        except Exception:
            pass
    return {}

def save_install_meta(install_dir: Path, slug: str, mod_name: str, file_id: int, file_date: str):
    meta = {"slug": slug, "name": mod_name, "file_id": file_id, "file_date": file_date}
    (install_dir / META_FILE).write_text(json.dumps(meta, indent=2))

def check_existing_modpack(install_dir: Path, slug: str, files: list) -> bool:
    """
    Returns True if the modpack is already installed and up to date
    (caller should skip the download). Returns False if install should proceed.
    """
    meta = load_install_meta(install_dir)
    if not meta or meta.get("slug") != slug:
        return False

    installed_id = meta.get("file_id")
    server_file  = find_server_pack(files)
    latest       = server_file or find_client_pack(files)
    latest_id    = latest.get("id") if latest else None

    if installed_id and latest_id and installed_id == latest_id:
        ok(f"Modpack already installed and up to date ({meta.get('name')}).")
        return True

    if installed_id and latest_id and installed_id != latest_id:
        warn(f"A newer version of {meta.get('name')} is available.")
        return not ask_yn("Update to the latest version?", "y")

    # Meta exists but can't compare versions — ask
    warn("This directory already has a modpack installation.")
    return not ask_yn("Re-install / overwrite?", "n")

def run_forge_installer(java_path: str, install_dir: Path, installer_jar: Path) -> Path:
    """Run the Forge --installServer and return the path to win_args.txt."""
    info("Running Forge installer (this may take a minute)...")
    result = subprocess.run(
        [java_path, "-jar", str(installer_jar), "--installServer"],
        cwd=str(install_dir), capture_output=True, text=True)
    # Forge sometimes exits non-zero but still works — check for win_args.txt
    win_args_list = list(install_dir.rglob("win_args.txt"))
    if not win_args_list:
        err(f"Forge installer failed:\n{result.stderr[-600:]}")
        sys.exit(1)
    ok("Forge server installed.")
    return win_args_list[0]

def install_modpack_server(mod_info: dict, files: list, api_key: str,
                           install_dir: Path, java_path: str):
    """
    Download and set up the modpack server.
    Returns ("forge", win_args_path) or ("jar", jar_name).
    """
    slug       = mod_info.get("slug", "")
    mod_name   = mod_info.get("name", "")
    cf_headers = {"x-api-key": api_key}

    # ── Try the dedicated server pack first ───────────────────────────────────
    server_file = find_server_pack(files)
    used_server_pack = False

    if server_file and server_file.get("downloadUrl"):
        info(f"Found server pack: {server_file['displayName']}")
        zip_path = install_dir / "_server_pack.zip"
        download(server_file["downloadUrl"], str(zip_path),
                 "server pack", extra_headers=cf_headers)
        info("Extracting server pack...")
        with zipfile.ZipFile(str(zip_path), "r") as z:
            z.extractall(str(install_dir))
        zip_path.unlink(missing_ok=True)
        ok("Server pack extracted.")
        used_server_pack = True
    else:
        if server_file:
            warn("Server pack has no direct download URL — falling back to manifest.")
        else:
            info("No dedicated server pack found — using manifest to download mods.")

        # ── Manifest fallback: download client zip, extract mods ──────────────
        client_file = find_client_pack(files)
        if not client_file or not client_file.get("downloadUrl"):
            err("Could not find a downloadable modpack file.")
            sys.exit(1)

        zip_path = install_dir / "_client_pack.zip"
        download(client_file["downloadUrl"], str(zip_path),
                 "modpack", extra_headers=cf_headers)

        with zipfile.ZipFile(str(zip_path), "r") as z:
            if "manifest.json" not in z.namelist():
                err("No manifest.json in modpack zip.")
                sys.exit(1)
            manifest = json.loads(z.read("manifest.json"))
        zip_path.unlink(missing_ok=True)

        mods_dir = install_dir / "mods"
        mods_dir.mkdir(exist_ok=True)
        mod_files = manifest.get("files", [])
        info(f"Downloading {len(mod_files)} mods from manifest...")
        fail = 0
        for i, mf in enumerate(mod_files, 1):
            proj_id = mf["projectID"]
            file_id = mf["fileID"]
            print(f"\r    [{i}/{len(mod_files)}] mod {proj_id}...         ", end="", flush=True)
            try:
                fdata = _cf_req(
                    f"https://api.curseforge.com/v1/mods/{proj_id}/files/{file_id}",
                    api_key)
                finfo = fdata.get("data", {})
                dl_url = finfo.get("downloadUrl")
                fname  = finfo.get("fileName", f"mod_{proj_id}.jar")
                if dl_url:
                    req = urllib.request.Request(
                        dl_url,
                        headers={"User-Agent": "mc-installer/1.2", "x-api-key": api_key})
                    with urllib.request.urlopen(req, context=_SSL_CTX) as r, \
                            open(str(mods_dir / fname), "wb") as fh:
                        fh.write(r.read())
                else:
                    fail += 1
            except Exception:
                fail += 1
        print()
        ok(f"Mods: {len(mod_files) - fail} downloaded, {fail} skipped.")

    # ── If pack extracted into a single subdirectory, flatten it up ──────────
    top_items = [p for p in install_dir.iterdir()
                 if not p.name.startswith("_") and p.name not in ("jre", "backups")]
    if len(top_items) == 1 and top_items[0].is_dir():
        subdir = top_items[0]
        info(f"Server pack extracted into subfolder '{subdir.name}' — moving files up...")
        for item in subdir.iterdir():
            dest = install_dir / item.name
            if not dest.exists():
                shutil.move(str(item), str(dest))
        subdir.rmdir()
        ok("Files moved to server root.")

    # ── Run Forge installer if one is present ─────────────────────────────────
    installer_jars = list(install_dir.rglob("forge-*installer*.jar"))
    if not installer_jars:
        # Catch other naming conventions e.g. "installer.jar" in a forge folder
        installer_jars = [p for p in install_dir.rglob("*.jar")
                          if "installer" in p.name.lower() and "forge" in p.name.lower()]

    if installer_jars:
        installer_jar = sorted(installer_jars, key=lambda p: len(p.parts))[0]
        ok(f"Found Forge installer: {installer_jar.name}")
        win_args = run_forge_installer(java_path, install_dir, installer_jar)
        installer_jar.unlink(missing_ok=True)
        return ("forge", win_args)

    # ── Check if Forge is already installed (server pack pre-installed) ───────
    win_args_list = list(install_dir.rglob("win_args.txt"))
    if win_args_list:
        ok("Forge already set up in server pack.")
        return ("forge", win_args_list[0])

    # ── user_jvm_args.txt means Forge is already fully installed ─────────────
    if (install_dir / "user_jvm_args.txt").exists():
        win_args_list = list(install_dir.rglob("win_args.txt"))
        if win_args_list:
            ok("Forge server detected via user_jvm_args.txt.")
            return ("forge", win_args_list[0])

    # ── Scan every .bat at root for a Forge @win_args reference ──────────────
    for bat in install_dir.glob("*.bat"):
        try:
            content = bat.read_text(errors="ignore")
            match = re.search(r"@(libraries[/\\].+?win_args\.txt)", content)
            if match:
                win_args_path = install_dir / Path(match.group(1).replace("\\", "/"))
                if win_args_path.exists():
                    ok(f"Forge startup found in {bat.name}.")
                    return ("forge", win_args_path)
        except Exception:
            pass

    # ── Fallback: named server jars only ─────────────────────────────────────
    for candidate in ["server.jar", "minecraft_server.jar", "forge-server.jar"]:
        if (install_dir / candidate).exists():
            return ("jar", candidate)

    # Only pick root-level jars that plausibly look like launchers, not mods.
    # Mod jars tend to have "+mc" or "+1." in their name (Fabric version format)
    # or live in a mods/ subfolder.
    launcher_jars = [
        p for p in install_dir.glob("*.jar")
        if "installer" not in p.name.lower()
        and "+mc" not in p.name
        and re.search(r"\+1\.\d+", p.name) is None
        and any(kw in p.name.lower() for kw in ("server", "forge", "minecraft", "launch"))
    ]
    if launcher_jars:
        return ("jar", launcher_jars[0].name)

    # Show what IS in the folder to help diagnose
    err("Could not determine how to start this modpack server.")
    info("Files found in install directory:")
    for p in sorted(install_dir.rglob("*"))[:40]:
        print(f"    {p.relative_to(install_dir)}")
    sys.exit(1)


# ── Gonger Certified banner ───────────────────────────────────────────────────
def print_gonger_banner():
    y  = lambda t: "\033[93m" + t + "\033[0m"
    cy = lambda t: "\033[96m" + t + "\033[0m"
    sp = "           "  # 11 spaces — aligns box with wizard width
    print()
    print("  " + cy("    *      "))
    print("  " + cy("   /|\\    ") + sp + y("╔════════════════════╗"))
    print("  " + cy("  (o o)  ") + cy(" ~~~*~~~~>") + " " + y("║      \u2726   G   \u2726     \u2551"))
    print("  " + cy("   | |    ") + sp + y("║  GONGER CERTIFIED  ║"))
    print("  " + cy("  /\\_/\\  ") + sp + y("╚════════════════════╝"))
    print()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    os.system("cls" if os.name == "nt" else "clear")
    print(c("""
  ███╗   ███╗██╗███╗   ██╗███████╗ ██████╗██████╗  █████╗ ███████╗████████╗
  ████╗ ████║██║████╗  ██║██╔════╝██╔════╝██╔══██╗██╔══██╗██╔════╝╚══██╔══╝
  ██╔████╔██║██║██╔██╗ ██║█████╗  ██║     ██████╔╝███████║█████╗     ██║
  ██║╚██╔╝██║██║██║╚██╗██║██╔══╝  ██║     ██╔══██╗██╔══██║██╔══╝     ██║
  ██║ ╚═╝ ██║██║██║ ╚████║███████╗╚██████╗██║  ██║██║  ██║██║        ██║
  ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝        ╚═╝
  SERVER INSTALLER  v1.3
""", "green"))
    print_gonger_banner()

    cfg = load_config()

    # ── Step 0: Modpack or custom? ────────────────────────────────────────────
    header("Step 1: What kind of server?")
    print(f"""
  {c('1) Modpack server', 'green')}  - Install a full modpack from CurseForge
                      (e.g. paste a link like curseforge.com/minecraft/modpacks/...)
                      All mods are downloaded automatically. Friends install the
                      same modpack through the CurseForge / Prism launcher.

  {c('2) Custom server', 'cyan')}   - Build your own: Vanilla, Paper (plugins),
                      or Fabric (pick your own mods).
""")
    while True:
        choice = ask("Enter 1 or 2", "1")
        if choice in ("1", "2"):
            break
        warn("Please enter 1 or 2.")

    is_modpack = choice == "1"

    # ── Variables set by either branch ───────────────────────────────────────
    server_type  = None   # "vanilla" / "paper" / "fabric" / "modpack"
    mc_version   = None
    jar_name     = None   # for vanilla/paper/fabric
    start_mode   = "jar"  # "jar" or "forge"
    win_args     = None   # Path — only for forge start mode
    selected_mods = []
    cf_api_key   = ""
    modpack_name = ""

    # ══════════════════════════════════════════════════════════════════════════
    # MODPACK BRANCH
    # ══════════════════════════════════════════════════════════════════════════
    if is_modpack:
        header("Step 2: Modpack Details")

        cf_api_key = get_cf_api_key_required(cfg)

        print(f"""
  Paste the CurseForge modpack URL, for example:
    {c('https://www.curseforge.com/minecraft/modpacks/liminal-industries', 'cyan')}
  Or just the slug:
    {c('liminal-industries', 'cyan')}
""")
        while True:
            raw_url = ask("Modpack URL or slug")
            slug = parse_modpack_slug(raw_url)
            info(f"Looking up '{slug}' on CurseForge...")
            try:
                mod_info = fetch_modpack_info(slug, cf_api_key)
            except Exception as e:
                err(f"CurseForge lookup failed: {e}")
                if not ask_yn("Try a different URL?", "y"):
                    sys.exit(0)
                continue

            if not mod_info:
                warn(f"No modpack found for slug '{slug}'.")
                if not ask_yn("Try a different URL?", "y"):
                    sys.exit(0)
                continue
            break

        modpack_name = mod_info["name"]
        mod_id       = mod_info["id"]
        summary      = mod_info.get("summary", "")
        dl_count     = mod_info.get("downloadCount", 0)

        files = fetch_modpack_files(mod_id, cf_api_key)
        server_file = find_server_pack(files)
        client_file = find_client_pack(files)

        # Try to read MC version from the latest file's gameVersions
        detected_mc = ""
        ref_file = server_file or client_file
        if ref_file:
            for gv in ref_file.get("gameVersions", []):
                if re.match(r"^\d+\.\d+", gv):
                    detected_mc = gv
                    break

        print(f"""
  {c('Modpack found!', 'green')}

    Name        : {modpack_name}
    Summary     : {summary[:80]}{'...' if len(summary) > 80 else ''}
    Downloads   : {dl_count:,}
    MC Version  : {detected_mc or 'unknown (will be set by modpack)'}
    Server pack : {'Yes ✓' if server_file else 'No (will use manifest)'}
""")
        if not ask_yn("Use this modpack?", "y"):
            print("Installation cancelled.")
            sys.exit(0)

        server_type = "modpack"
        mc_version  = detected_mc or "1.20.1"

    # ══════════════════════════════════════════════════════════════════════════
    # CUSTOM BRANCH
    # ══════════════════════════════════════════════════════════════════════════
    else:
        header("Step 2: Server Type")
        print("""
  Choose your server type:
    1) Vanilla  - Official Mojang server, no mods or plugins
    2) Paper    - High performance, supports PLUGINS (vanilla client)
    3) Fabric   - Supports MODS (everyone needs matching mods)
""")
        while True:
            choice = ask("Enter 1, 2, or 3", "2")
            if choice in ("1", "2", "3"):
                server_type = {"1": "vanilla", "2": "paper", "3": "fabric"}[choice]
                break
            warn("Please enter 1, 2, or 3.")
        ok(f"Server type: {server_type.upper()}")

        header("Step 3: Minecraft Version")
        for i, v in enumerate(MINECRAFT_VERSIONS, 1):
            print(f"    {i}) {v}{' (recommended)' if i == 1 else ''}")
        print()
        mc_version = MINECRAFT_VERSIONS[ask_int("Choose a version number", 1, 1, len(MINECRAFT_VERSIONS)) - 1]
        ok(f"Minecraft version: {mc_version}")

    # ── Server settings (common) ──────────────────────────────────────────────
    header("Step 3: Server Settings" if is_modpack else "Step 4: Server Settings")
    world_name  = ask("World name", "world")
    motd        = ask("Server description (shown in server list)", modpack_name or "A Minecraft Server")
    max_players = ask_int("Max players", 10, 1, 100)
    port        = ask_int("Server port", 25565, 1024, 65535)
    ram_gb      = ask_int("RAM to allocate (GB)", 4, 1, 64)
    difficulty  = ask("Difficulty (peaceful/easy/normal/hard)", "normal")
    gamemode    = ask("Default gamemode (survival/creative/adventure)", "survival")
    online_mode = ask_yn("Enable online mode (requires legitimate MC accounts)", "y")
    whitelist   = ask_yn("Enable whitelist (only listed players can join)", "n")

    # ── Install location (common) ─────────────────────────────────────────────
    header("Step 4: Install Location" if is_modpack else "Step 5: Install Location")
    default_dir = str(Path.home() / ("ModpackServer" if is_modpack else "MinecraftServer"))
    install_dir = Path(ask("Where should the server be installed?", default_dir))
    backup_dir  = install_dir / "backups"
    install_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    ok(f"Install directory: {install_dir}")

    # ── Mods (custom Fabric only) ─────────────────────────────────────────────
    if server_type == "fabric":
        header("Step 6: Mods")

        print("""
  Choose a mod preset:
    1) Performance only   - Sodium, Lithium, FerriteCore
    2) QOL extras         - Performance + Inventory Sort, Jade, FTB Chunks
    3) Content mods       - Performance + Create, Farmer's Delight, Waystones
    4) All presets        - Everything above
    5) No preset          - Skip presets, use modlist/manual only
""")
        while True:
            mod_choice = ask("Choose 1-5", "1")
            if mod_choice in ("1", "2", "3", "4", "5"):
                break
            warn("Please enter 1-5.")

        if mod_choice == "1":
            selected_mods = [(s, slug, desc) for s, slug, desc in PRESET_MODS["performance"]]
        elif mod_choice == "2":
            selected_mods = [(s, slug, desc) for s, slug, desc in PRESET_MODS["performance"] + PRESET_MODS["qol"]]
        elif mod_choice == "3":
            selected_mods = [(s, slug, desc) for s, slug, desc in PRESET_MODS["performance"] + PRESET_MODS["content"]]
        elif mod_choice == "4":
            selected_mods = [(s, slug, desc) for p in PRESET_MODS.values() for s, slug, desc in p]

        if selected_mods:
            info("Preset mods selected:")
            for _, slug, desc in selected_mods:
                print(f"    • {desc}")

        print()
        modlist_path = ask("Path to a modlist.txt file (or press Enter to skip)", "")
        if modlist_path:
            file_entries = load_modlist_file(modlist_path)
            if file_entries:
                ok(f"Loaded {len(file_entries)} mods from modlist file.")
                for source, slug in file_entries:
                    selected_mods.append((source, slug, f"From modlist: {slug}"))
                    info(f"  [{source}] {slug}")
            else:
                warn("No valid mods found in that file.")

        print(f"""
  You can also paste mod links or slugs directly.
  Accepted formats:
    {c('https://www.curseforge.com/minecraft/mc-mods/create', 'cyan')}
    {c('https://modrinth.com/mod/sodium', 'cyan')}
    {c('sodium', 'cyan')}  (plain Modrinth slug)

  Enter one per line. Leave a blank line when done.
""")
        print(f"  {c('?', 'cyan')} Paste mods (blank line to finish):")
        while True:
            line = input("    ").strip()
            if not line:
                break
            parsed = parse_mod_entry(line)
            if parsed:
                source, slug = parsed
                selected_mods.append((source, slug, f"Manual: {slug}"))
                ok(f"Added [{source}] {slug}")
            else:
                warn(f"Could not parse: {line}")

        seen = set()
        deduped = []
        for entry in selected_mods:
            if entry[1] not in seen:
                seen.add(entry[1])
                deduped.append(entry)
        selected_mods = deduped

        needs_cf = any(s == "curseforge" for s, _, _ in selected_mods)
        cf_api_key = get_cf_api_key(cfg, needs_cf)

    # ── Options (common) ──────────────────────────────────────────────────────
    step_n = 5 if is_modpack else 7
    header(f"Step {step_n}: Options")
    do_autostart = ask_yn("Register server to start automatically when Windows boots", "y")
    do_backup    = ask_yn("Schedule automatic backups (rolling every 30 min + daily at 3 AM)", "y")

    # ── Networking (common) ───────────────────────────────────────────────────
    header(f"Step {step_n + 1}: Networking")
    print(f"""
  How do you want friends to connect?

    1) {c('Port Forwarding', 'cyan')}  - Open a port on your router yourself.
                        Your real home IP is visible to players.

    2) {c('playit.gg tunnel', 'green')} - Free tunnel service, no router changes needed.
                        Hides your home IP. Works even on networks
                        where port forwarding isn't possible (dorms, etc).
                        Requires a free playit.gg account on first run.
""")
    while True:
        net_choice = ask("Enter 1 or 2", "2")
        if net_choice in ("1", "2"):
            use_playit = net_choice == "2"
            break
        warn("Please enter 1 or 2.")

    if use_playit:
        ok("playit.gg selected — tunnel will be set up during installation.")
    else:
        ok("Port forwarding selected — see instructions at the end.")

    # ── Confirm ───────────────────────────────────────────────────────────────
    header("Ready to Install")
    if is_modpack:
        print(f"""
  Modpack     : {modpack_name}
  MC version  : {mc_version}
  Install dir : {install_dir}
  RAM         : {ram_gb}GB
  Max players : {max_players}  |  Port: {port}
  Gamemode    : {gamemode}  |  Difficulty: {difficulty}
  Online mode : {online_mode}  |  Whitelist: {whitelist}
  Auto-start  : {do_autostart}  |  Backups: {do_backup}
  Networking  : {'playit.gg tunnel (no port forwarding needed)' if use_playit else 'Port forwarding (manual)'}
""")
    else:
        print(f"""
  Server type : {server_type.upper()}
  MC version  : {mc_version}
  Install dir : {install_dir}
  RAM         : {ram_gb}GB
  Max players : {max_players}  |  Port: {port}
  Gamemode    : {gamemode}  |  Difficulty: {difficulty}
  Online mode : {online_mode}  |  Whitelist: {whitelist}
  Auto-start  : {do_autostart}  |  Backups: {do_backup}
  Networking  : {'playit.gg tunnel (no port forwarding needed)' if use_playit else 'Port forwarding (manual)'}
  Mods        : {len(selected_mods)} selected
""")
    if not ask_yn("Proceed with installation?", "y"):
        print("Installation cancelled.")
        sys.exit(0)

    # ── Install ───────────────────────────────────────────────────────────────
    header("Installing...")

    java_path = ensure_java(install_dir)

    if is_modpack:
        # ── Check if already installed ────────────────────────────────────────
        if check_existing_modpack(install_dir, parse_modpack_slug(raw_url), files):
            # Already up to date — figure out start mode from what's on disk
            win_args_list = list(install_dir.rglob("win_args.txt"))
            if win_args_list:
                start_mode = "forge"
                win_args   = win_args_list[0]
            else:
                for candidate in ["server.jar", "minecraft_server.jar", "paper.jar"]:
                    if (install_dir / candidate).exists():
                        start_mode = "jar"
                        jar_name   = candidate
                        break
        else:
            # ── Modpack install ───────────────────────────────────────────────
            header(f"Downloading {modpack_name}")
            start_mode, result = install_modpack_server(
                mod_info, files, cf_api_key, install_dir, java_path)
            if start_mode == "forge":
                win_args = result
            else:
                jar_name = result
            # Save install metadata so we can skip re-download next time
            ref_file = find_server_pack(files) or find_client_pack(files)
            if ref_file:
                save_install_meta(install_dir, parse_modpack_slug(raw_url),
                                  modpack_name, ref_file.get("id", 0),
                                  ref_file.get("fileDate", ""))

    elif server_type == "vanilla":
        info("Fetching vanilla server URL...")
        try:
            manifest = _get_json("https://launchermeta.mojang.com/mc/game/version_manifest.json")
            ver_info = next(v for v in manifest["versions"] if v["id"] == mc_version)
            jar_url  = _get_json(ver_info["url"])["downloads"]["server"]["url"]
        except Exception as e:
            err(f"Could not fetch vanilla server URL: {e}"); sys.exit(1)
        jar_name = "server.jar"
        download(jar_url, str(install_dir / jar_name), "server.jar")

    elif server_type == "paper":
        jar_url  = fetch_paper_url(mc_version)
        jar_name = "paper.jar"
        download(jar_url, str(install_dir / jar_name), "paper.jar")

    elif server_type == "fabric":
        loader_ver, _ = fetch_fabric_loader(mc_version)
        installer_url = fetch_fabric_installer_url()
        installer_jar = install_dir / "fabric-installer.jar"
        download(installer_url, str(installer_jar), "Fabric installer")
        info("Running Fabric installer...")
        result = subprocess.run(
            [java_path, "-jar", str(installer_jar), "server",
             "-mcversion", mc_version, "-loader", loader_ver,
             "-downloadMinecraft", "-dir", str(install_dir)],
            capture_output=True, text=True)
        installer_jar.unlink(missing_ok=True)
        if result.returncode != 0:
            err(f"Fabric installer failed:\n{result.stderr}"); sys.exit(1)
        jar_name = "fabric-server-launch.jar"
        ok("Fabric server installed.")

    (install_dir / "eula.txt").write_text("eula=true\n")
    ok("EULA accepted.")

    cfg_props = dict(motd=motd, max_players=max_players, port=port, difficulty=difficulty,
                     gamemode=gamemode, world_name=world_name, online_mode=online_mode, whitelist=whitelist)
    (install_dir / "server.properties").write_text(build_server_properties(cfg_props))
    ok("server.properties written.")

    # ── Download mods (custom Fabric only) ───────────────────────────────────
    if selected_mods:
        mods_dir = install_dir / "mods"
        mods_dir.mkdir(exist_ok=True)
        header(f"Downloading {len(selected_mods)} Mods")
        success, fail = 0, 0
        for source, slug, _ in selected_mods:
            if download_mod(source, slug, mc_version, "fabric", mods_dir, cf_api_key):
                success += 1
            else:
                fail += 1
        ok(f"Mods: {success} downloaded, {fail} skipped.")
        if fail:
            warn("Skipped mods can be added manually to the mods/ folder.")

        client_zip = install_dir / "client_mods.zip"
        info("Creating client_mods.zip for your friends...")
        with zipfile.ZipFile(str(client_zip), "w") as z:
            for f in mods_dir.iterdir():
                z.write(str(f), f"mods/{f.name}")
        ok(f"Client mod pack: {client_zip}")
        info("Friends extract the mods/ folder into their .minecraft/mods/")

    # ── playit.gg ─────────────────────────────────────────────────────────────
    if use_playit:
        header("Setting Up playit.gg")
        setup_playit(install_dir)
        info("playit.exe downloaded to server folder.")
        info("On first launch it will print a claim URL — visit it to link your free account.")
        info("After claiming, your server address will show in the playit window (e.g. abc.at.gg:PORT)")

    # ── Write start scripts ───────────────────────────────────────────────────
    start_bat          = install_dir / "start_server.bat"
    backup_rolling_bat = install_dir / "backup_rolling.bat"
    backup_daily_bat   = install_dir / "backup_daily.bat"

    if start_mode == "forge":
        if use_playit:
            start_bat.write_text(build_start_bat_forge_playit(java_path, win_args, ram_gb, install_dir))
        else:
            start_bat.write_text(build_start_bat_forge(java_path, win_args, ram_gb, install_dir))
    else:
        if use_playit:
            start_bat.write_text(build_start_bat_playit(java_path, jar_name, ram_gb, install_dir))
        else:
            start_bat.write_text(build_start_bat(java_path, jar_name, ram_gb, install_dir))

    backup_rolling_bat.write_text(build_backup_rolling_bat(str(install_dir), str(backup_dir), world_name))
    backup_daily_bat.write_text(build_backup_daily_bat(str(install_dir), str(backup_dir), world_name))
    ok("start_server.bat written.")
    ok("backup_rolling.bat written (30-min rolling, keeps last 4).")
    ok("backup_daily.bat written (daily at 3 AM, keeps last 7).")

    if do_autostart:
        register_autostart(install_dir, start_bat)
    if do_backup:
        register_rolling_backup_task(backup_rolling_bat)
        register_daily_backup_task(backup_daily_bat)

    # ── Done ──────────────────────────────────────────────────────────────────
    header("Installation Complete!")

    modpack_note = ""
    if is_modpack:
        modpack_note = f"""
  {c('Modpack — Friends Setup:', 'green')}
    Friends need to install {c(modpack_name, 'cyan')} on their own PC.
    They can do this free through the CurseForge app or Prism Launcher.
    Search for "{modpack_name}" and click Install.
    They do NOT need the server files — just the client modpack.
"""

    print(f"""
  {c('Your Minecraft server is ready!', 'green')}

  Install location : {install_dir}
  Start server     : Double-click  start_server.bat
  Rolling backups  : Every 30 min → {backup_dir}\\rolling\\  (last 4 kept)
  Daily backups    : 3:00 AM      → {backup_dir}\\daily\\   (last 7 kept)
  Manual backup    : Double-click  backup_rolling.bat  or  backup_daily.bat
  Server port      : {port}
{modpack_note}
  {(
    c('playit.gg Tunnel:', 'green') + '''
    1. Double-click start_server.bat — playit opens in a separate window
    2. First run: copy the claim URL it shows and open it in a browser
    3. Log in / create a free playit.gg account and claim your agent
    4. Your public server address will appear in the playit window (e.g. abc.at.gg:12345)
    5. Share that address with friends — they type it directly into Minecraft
    6. Your home IP stays completely hidden'''
    if use_playit else
    c('Port Forwarding:', 'yellow') + f'''
    1. Open your router admin page (usually 192.168.1.1 or 192.168.0.1)
    2. Find "Port Forwarding" and forward TCP port {port} to this PC\'s local IP
    3. Share your public IP (search "what is my ip") with friends
    4. Friends connect using: YourPublicIP:{port}'''
  )}

  {c('Whitelist Commands (type in server console):', 'cyan')}
    whitelist add PlayerName
    op PlayerName
""")
    input("  Press Enter to exit...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInstallation cancelled.")
        sys.exit(0)
    except SystemExit as e:
        if e.code != 0:
            print()
            input("  Press Enter to exit...")
        sys.exit(e.code)
    except Exception as e:
        err(f"Unexpected error: {e}")
        print()
        input("  Press Enter to exit...")
