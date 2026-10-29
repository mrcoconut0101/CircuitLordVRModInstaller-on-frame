#!/usr/bin/env python3
"""Big Walk VR installer for Steam Frame / SteamOS / Linux. No Wine needed.

Usage: python3 install-frame.py [install|uninstall] [--beta] [--game-dir PATH]
"""
import argparse, hashlib, io, json, os, re, shutil, sys, time, urllib.request, zipfile

MANIFEST_URL = "https://raw.githubusercontent.com/CircuitLord/CircuitLordVRModInstaller/main/manifest-v3.json"
GAME_FOLDER, GAME_EXE = "Big Walk", "Big Walk.exe"
RECORD = os.path.join("UserData", "BigWalkVRInstaller", "linux-install.json")
LAUNCH_OPTIONS = 'WINEDLLOVERRIDES="winhttp=n,b" %command%'
SKIP = {".package.json", "manifest.json", "icon.png", "readme.md"}
RUNTIME_PREFIX = "BepInEx/patchers/BigWalkVR.Runtime/"

def log(msg): print(f"==> {msg}", flush=True)
def die(msg): print(f"ERROR: {msg}", file=sys.stderr); sys.exit(1)

def fetch(url, sha=None):
    if not url.startswith("https://"): die(f"refusing non-HTTPS URL {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "CircuitLordVRModInstaller-linux"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r: data = r.read()
            break
        except Exception as e:
            if attempt == 3: die(f"download failed: {url}: {e}")
            time.sleep(2 ** (attempt + 1))
    if sha and hashlib.sha256(data).hexdigest().lower() != sha.lower(): die(f"checksum mismatch for {url}")
    return data

def steam_roots():
    home = os.path.expanduser("~")
    for p in [".steam/steam", ".local/share/Steam", ".var/app/com.valvesoftware.Steam/.local/share/Steam", ".steam/root"]:
        p = os.path.realpath(os.path.join(home, p))
        if os.path.isdir(os.path.join(p, "steamapps")): yield p

def find_game():
    seen = set()
    for root in steam_roots():
        libs = [root]
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf):
            libs += [m.replace("\\\\", "\\") for m in re.findall(r'"path"\s+"([^"]+)"', open(vdf, errors="ignore").read())]
        for lib in libs:
            d = os.path.realpath(os.path.join(lib, "steamapps", "common", GAME_FOLDER))
            if d not in seen and os.path.isfile(os.path.join(d, GAME_EXE)): return d
            seen.add(d)
    return None

def inside(base, rel):
    rel = rel.replace("\\", "/").lstrip("/")
    dest = os.path.realpath(os.path.join(base, rel))
    if not dest.startswith(os.path.realpath(base) + os.sep): die(f"unsafe path in package: {rel}")
    return dest

def extract(data, game, prefix="", preserve=()):
    written = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            if name.endswith("/") or not name.startswith(prefix): continue
            rel = name[len(prefix):]
            if not prefix and rel.lower() in SKIP: continue
            dest = inside(game, rel)
            written.append(rel)
            if rel in preserve and os.path.exists(dest): continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as out: shutil.copyfileobj(src, out)
            # the Windows installer deploys the runtime payload into the game root too
            if rel.startswith(RUNTIME_PREFIX):
                root_rel = rel[len(RUNTIME_PREFIX):]
                root_dest = inside(game, root_rel)
                os.makedirs(os.path.dirname(root_dest), exist_ok=True)
                shutil.copyfile(dest, root_dest); written.append(root_rel)
    return written

def uninstall(game):
    path = os.path.join(game, RECORD)
    files = json.load(open(path)).get("files", []) if os.path.exists(path) else []
    for rel in files:
        p = inside(game, rel)
        if os.path.isfile(p): os.remove(p)
    for f in ["winhttp.dll", "doorstop_config.ini", ".doorstop_version", "changelog.txt"]:
        p = os.path.join(game, f)
        if os.path.isfile(p): os.remove(p)
    shutil.rmtree(os.path.join(game, "BepInEx"), ignore_errors=True)
    if os.path.exists(path): os.remove(path)
    log("Big Walk VR removed. Remove the launch options in Steam to finish.")

def install(game, beta):
    log("Loading the download list")
    m = json.loads(fetch(f"{MANIFEST_URL}?t={int(time.time())}"))
    if m.get("schemaVersion") != 3: die("unsupported manifest version, update this script")
    mod = next(x for x in m["mods"] if x["id"] == "BigWalkVR")
    pkg = mod
    if beta:
        pkg = next((c for c in mod.get("channels", []) if c["id"] == "beta"), None) or die("no beta channel right now")
    preserve = {p.replace("\\", "/") for p in mod.get("preserve", [])}

    if os.path.isfile(os.path.join(game, "version.dll")):
        die("version.dll found (old MelonLoader install). Run 'uninstall' or verify game files in Steam first.")
    old = os.path.join(game, RECORD)
    if os.path.exists(old):
        for rel in json.load(open(old)).get("files", []):
            if rel in preserve: continue
            p = inside(game, rel)
            if os.path.isfile(p): os.remove(p)

    log(f"Downloading BepInEx {m['bepinex']['version']}")
    files = extract(fetch(m["bepinex"]["url"], m["bepinex"]["sha256"]), game, prefix="BepInExPack/")
    log(f"Downloading Big Walk VR {pkg['version']}{' (beta)' if beta else ''}")
    files += extract(fetch(pkg["url"], pkg["sha256"]), game, preserve=preserve)
    for rel in mod.get("tokenize", []):
        p = inside(game, rel)
        if os.path.isfile(p):
            # the game sees its folder through Proton's Z: drive
            win = "Z:" + game.replace("/", "\\")
            t = open(p).read().replace("{{GAMEDIR_JSON}}", win.replace("\\", "\\\\")).replace("{{GAMEDIR}}", win)
            open(p, "w").write(t)
    os.makedirs(os.path.dirname(old), exist_ok=True)
    json.dump({"version": pkg["version"], "channel": "beta" if beta else "stable", "files": sorted(set(files))}, open(old, "w"), indent=1)

    log("Installed!")
    print(f"""
LAST STEP (one time): in Steam, open Big Walk > Properties > General > Launch Options and paste:

    {LAUNCH_OPTIONS}

Then launch Big Walk from your Frame's library. Re-run this script any time to update.
""")

def report(game):
    """Prints a short crash summary that is easy to read off the headset."""
    p = os.path.join(game, "BepInEx", "LogOutput.log")
    if not os.path.isfile(p): die("No BepInEx log yet. Launch Big Walk once first.")
    lines = open(p, errors="ignore").read().splitlines()
    keys = ("[Error", "[Fatal", "Exception", "Failed", "failed")
    errors = [l.strip()[:120] for l in lines if any(k in l for k in keys)]
    print("\n===== CRASH SUMMARY =====")
    print(f"log lines: {len(lines)}")
    for l in (errors[:6] or ["no errors logged"]): print("  " + l)
    print("last line:\n  " + (lines[-1].strip()[:120] if lines else "(empty)"))
    print("=========================\n")

def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("action", nargs="?", default="install", choices=["install", "uninstall", "report"])
    a.add_argument("--beta", action="store_true")
    a.add_argument("--game-dir")
    a = a.parse_args()
    game = a.game_dir or find_game()
    if not game or not os.path.isfile(os.path.join(game, GAME_EXE)):
        die("Big Walk not found. Install it in Steam first, or pass --game-dir '/path/to/Big Walk'")
    log(f"Found Big Walk at {game}")
    if a.action == "report": report(game)
    elif a.action == "uninstall": uninstall(game)
    else: install(game, a.beta)

if __name__ == "__main__": main()
