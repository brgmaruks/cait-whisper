# Troubleshooting

Most issues land in one of the buckets below. Before anything else, turn on **Dev Logs** (right-click menu -> "Dev Logs: ON") and reproduce the problem. The verbose log will tell you exactly what went wrong.

Open the log via right-click -> "View Log File" or from `cait-whisper.log` in the app folder.

## Hotkeys don't do anything

- **Did you run `start.bat` as administrator?** Windows requires elevation for global hotkey registration. The UAC prompt should appear on every launch.
- **Is another app hooking the same hotkey?** `Ctrl + Win + B` is used by Intel graphics and Lenovo Vantage, which is why cait-whisper avoids it. If a hotkey doesn't fire, try it with no other app in focus first.
- **Check the log** for "keyboard hook installed" at startup. If it's missing, Python's `keyboard` package isn't getting the required privileges.

## Model takes forever to load

- First launch downloads the model weights from Hugging Face (~400 MB for Moonshine base, ~1.5 GB for Whisper large-v3-turbo). This is a one-time cost.
- Subsequent launches load from the local cache in ~1-3 seconds.
- If downloads fail, check your internet connection. The log will show HuggingFace errors.
- **Slow on subsequent launches?** The Whisper engine uses int8 quantized weights. Loading involves memory-mapping the file, which is disk-speed dependent.

## Widget disappeared

- Right-click on the system tray icon -> "Show Widget" if available.
- Right-click anywhere the widget used to be and choose "Reset Position".
- Worst case: delete `config.json` (or edit the `appearance.position` entry) and restart.

## Transcription is garbage or repeated text

- The hallucination guard usually catches this. If it slips through, try switching to a different model.
- Check the log for `Hallucination detected` lines. If you're getting them frequently, your microphone might be picking up too much background noise, making the VAD unreliable.

## Auto-dictionary isn't learning

1. Turn on Dev Logs and try a correction.
2. Look for `[AutoDict]` lines in the log.

Common failure modes:

- **"watch NOT armed: auto-learn disabled"**: right-click -> "Auto-Learn: ON".
- **No `[AutoDict] watching...` after paste**: `_start_correction_watch` isn't being called. File a bug with log.
- **"Ctrl+A grabbed too much context"**: the field you're in returns the whole document when you press Ctrl+A. Copy your correction to the clipboard manually (Ctrl+C) and then press Enter. The app prefers clipboard-supplied corrections.
- **"no correction detected"**: you pressed Enter but the text hadn't changed. Make sure you edited the pasted text before pressing Enter.
- **Similarity check fails**: the correction pair doesn't sound similar enough (e.g. you're trying to replace "the" with "elephant"). Use the manual "add entry" option in the Dictionary tab instead.
- **Pending count below threshold**: you need two identical corrections before a dictionary entry is promoted. Make the same correction again to commit it.

## Voice commands don't fire

- **PURE mode is on**. Press `Shift + Alt + M` to switch to COMMAND mode. The dot should turn into a blue ring.
- **Classifier below confidence threshold**: the LLM fallback returned < 0.7 confidence. Happens when the utterance is ambiguous. Try a canonical phrase from the [features](features.md) list.
- **Ollama isn't running**: selection-based and screen-context commands silently fall back to dictation if Ollama is offline. Check with `ollama list` in a terminal.

## Selection-based commands do nothing

- **No text is actually selected**: the UI Automation query returned empty. Some apps don't expose selection (Electron apps, terminals, password fields).
- **Workaround**: copy the text first (Ctrl+C) and paste-rewrite via LLM manually, or use a different editor for now.

## "Screen Context: ON" doesn't seem to do anything

- It only activates in COMMAND mode. Switch with `Shift + Alt + M`.
- The first OCR call takes 2+ seconds while RapidOCR loads its ONNX model. Subsequent calls are fast.
- Dev Logs will show `[ScreenContext] captured NNN chars in X.XXs`. If this line is missing, RapidOCR didn't load. Make sure `rapidocr-onnxruntime` is installed: `venv\Scripts\pip install rapidocr-onnxruntime`.

## App won't quit cleanly

- Right-click -> "Quit" or Ctrl+C in the terminal (if run via python, not pythonw).
- If the process stays, open Task Manager and kill `python.exe` / `pythonw.exe` in the cait-whisper folder.

## Running without UAC prompts

If you'd rather not accept UAC every launch, create a scheduled task that runs `start.bat` at login with highest privileges:

```powershell
# Run this in PowerShell as Administrator
$action = New-ScheduledTaskAction -Execute "C:\path\to\cait-whisper\start.bat"
$trigger = New-ScheduledTaskTrigger -AtLogon
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -RunLevel Highest
Register-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -TaskName "cait-whisper"
```

After that, the scheduled task launches at login, skipping UAC. Disable it with `Disable-ScheduledTask -TaskName "cait-whisper"`.

## Still stuck

Open a [GitHub issue](https://github.com/brgmaruks/cait-whisper/issues/new) with:

1. Your Windows version (Win+R -> `winver`)
2. Python version (`python --version`)
3. Which ASR engine you're using
4. Steps to reproduce
5. The last 100 lines or so from `cait-whisper.log` (with Dev Logs enabled if possible)
