# Contributing to cait-whisper

Thanks for your interest in contributing. This project is maintained as a human-AI partnership, and we welcome help from the community.

## How to Contribute

### Reporting Bugs

Bug reports are incredibly valuable. Please use the [bug report template](https://github.com/brgmaruks/cait-whisper/issues/new?template=bug_report.md) and include:
- Your Windows version and Python version
- Which ASR engine you're using
- Steps to reproduce the issue
- Relevant lines from `cait-whisper.log`

### Suggesting Features

Open a [feature request](https://github.com/brgmaruks/cait-whisper/issues/new?template=feature_request.md). Describe the problem you're trying to solve, not just the solution you want. This helps us find the right approach.

### Submitting Code

1. **Open an issue first** to discuss the change before writing code. This prevents wasted effort on approaches that don't align with the project direction.
2. **Keep PRs focused** on a single change. One bug fix or one feature per PR.
3. **Test manually** on Windows before submitting. Run the app, do a few transcriptions, check the log for errors.
4. **Follow existing patterns.** The codebase has specific conventions for threading, Tkinter safety, and config management. Read the code around your change.

### What We'd Love Help With

- **macOS and Linux support** - this is the biggest gap. The core logic is platform-agnostic, but the hotkey system, ctypes calls, and batch scripts are Windows-specific.
- **Test coverage** - unit tests for pure functions (dictionary matching, spoken punctuation, hallucination detection)
- **New ASR engine integrations**
- **Accessibility improvements**

## Development Setup

```bat
git clone https://github.com/brgmaruks/cait-whisper.git
cd cait-whisper
setup.bat
```

Run `start.bat` to launch. Logs go to `cait-whisper.log`.

## Expectations

This is a small project. Response times on issues and PRs may be a few days. We read everything and appreciate your patience.
