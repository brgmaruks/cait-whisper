"""Frozen-bundle entry point.

PyInstaller builds ONE executable from this file. cait-whisper is a two-process
app: the floating widget (client.py) and the History/Dictionary window
(history_window.py), which the widget launches as a separate process.

From source those are two separate scripts. In a frozen bundle there are no
.py scripts to run, so both live inside the single exe and we dispatch on a
command-line flag:

    cait-whisper.exe                  -> the main widget (client.main)
    cait-whisper.exe --history-window -> the History window (history_window.main)

Keeping the history process a SEPARATE invocation (rather than a thread) keeps
its isolation, and importing only history_window for that case avoids dragging
client.py's audio/ASR imports into the lighter window.
"""

import sys


def run():
    if "--history-window" in sys.argv:
        import history_window
        history_window.main()
    else:
        import client
        client.main()


if __name__ == "__main__":
    run()
