# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build spec for cait-whisper.
#
# Produces a one-FOLDER bundle (dist/cait-whisper/) containing cait-whisper.exe
# plus everything it needs - no Python install, no pip, no PATH. build.bat zips
# that folder into cait-whisper-windows.zip for the Releases page.
#
# Build:  build.bat   (or: pyinstaller cait-whisper.spec --noconfirm)
#
# Notes for iterating (PyInstaller + ML libs always needs a round or two):
#   - If the app launches but a feature errors with ModuleNotFoundError, add
#     the module to `hiddenimports` below.
#   - If a library can't find a data file (onnx model, config.yaml, a DLL),
#     it usually means collect_all missed it - add the package to `COLLECT_PKGS`.
#   - To SEE crash output during a debug build, flip `console=False` to True
#     in the EXE() call, rebuild, and run from a terminal.

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []

# Heavy / native packages whose data files + DLLs must be bundled. Each is
# attempted independently so one wrong name (e.g. a library renamed upstream)
# doesn't abort the whole build - the build log prints what was skipped.
COLLECT_PKGS = [
    "onnxruntime",            # Moonshine + RapidOCR backend (native DLLs)
    "ctranslate2",            # faster-whisper backend (native DLLs)
    "faster_whisper",
    "moonshine_onnx",         # useful-moonshine-onnx import name (verify!)
    "tokenizers",
    "rapidocr_onnxruntime",   # bundles ONNX models + config.yaml as data
    "cv2",                    # opencv, pulled in by rapidocr
    "sounddevice",            # bundles the PortAudio DLL
    "soundfile",              # bundles libsndfile
    "pystray",
    "PIL",
    "comtypes",               # pywinauto's UI Automation layer (codegen-heavy)
    "pywinauto",
    "keyboard",
    "numpy",
    "ollama",
    "openai",
]

for _pkg in COLLECT_PKGS:
    try:
        d, b, h = collect_all(_pkg)
        datas += d
        binaries += b
        hiddenimports += h
        print(f"[spec] collected {_pkg}: {len(d)} datas, {len(b)} binaries")
    except Exception as e:
        print(f"[spec] SKIP collect_all({_pkg}): {e}")

# Our own read-only resources, extracted under sys._MEIPASS at runtime and
# resolved via cw_paths.resource_path(). config.example.json seeds config.json
# on first run; assets/ holds the brand icon.
datas += [
    ("config.example.json", "."),
    ("assets", "assets"),
]

# Our own modules. The import graph from cait_whisper.py should pick these up,
# but list them explicitly so a lazy/conditional import is never dropped.
hiddenimports += [
    "client", "history_window", "theme", "cw_paths", "splash",
    "config_io", "llm_provider", "context", "commands",
    "pystray._win32",        # pystray picks its backend at runtime
]

block_cipher = None

a = Analysis(
    ["cait_whisper.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Keep the bundle lean: Parakeet (NeMo/PyTorch) is intentionally NOT
    # shipped in the download - it stays available via the source install.
    excludes=["torch", "torchaudio", "nemo", "nemo_toolkit",
              "matplotlib", "IPython", "pytest", "notebook"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Cait Whisper",       # the one file users double-click, first run and every run
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX can trigger antivirus false positives; off.
    console=False,             # windowed app (set True to debug crashes)
    disable_windowed_traceback=False,
    icon="assets/cait.ico",
    # Request admin via an embedded manifest so the global Ctrl+Win hotkey
    # works. One UAC prompt on launch; the History-window subprocess inherits
    # elevation from its parent, so it does not prompt again.
    uac_admin=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="cait-whisper",
)
