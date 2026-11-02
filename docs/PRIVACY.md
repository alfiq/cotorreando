# Privacy

Cotorreando hears your microphone and types into your programs, so you deserve to know what it
does with that. In short: **your voice is processed on your PC**, there are no accounts, no
telemetry and no analytics, and what it learns about you is kept encrypted with your password.

*Español: [PRIVACIDAD.md](PRIVACIDAD.md)*

## What it listens to, and when

- The microphone is only open while Cotorreando is **on** (the bubble is not grey). Turning it
  off, with the hotkey or the menu, closes the microphone.
- What becomes text depends on the listening mode:
  - **Open microphone**: every sentence you say.
  - **Push to talk**: only what you say while holding the hotkey.
  - **Voice activation**: wakes on voice above the threshold and listens until a few seconds of silence.
  - **Keyword activation**: wakes when it hears the keyword ("oye cotorro").
- To detect speech, audio goes through a local detector (Silero VAD). None of it is recorded.
- With echo cancellation on, it also reads what your speakers play, only to subtract it from the microphone.

## What it types, and how

- It types by **simulating the keyboard** (Windows `SendInput`) into the window that has the
  cursor. It never types into its own windows.
- **It does not read your keys.** There is no keyboard hook: to know you are typing it only looks
  at the time of the last input. If you type, dictation pauses and resumes shortly after (1.2 s by default).

## What goes over the network, and when

All recognition happens on your computer. These are the only connections, all HTTPS and with none of your data:

| What | Where | When |
|---|---|---|
| Voice model (~670 MB) | Hugging Face (`istupakov/parakeet-tdt-0.6b-v3-onnx`) | The first time, or when you ask to download it again. Not downloaded with your own model. |
| Speech detector (Silero VAD, ~2 MB) | GitHub (`snakers4/silero-vad`, v5.1.2) | The first time. |
| The model's `tokenizer.json` | Hugging Face (`nvidia/parakeet-tdt-0.6b-v3`) | The first time your words are boosted, with the downloaded model. |
| Update check | `api.github.com` | At most once a day. A plain GET with the User-Agent `Cotorreando/<version>`; GitHub sees your IP, as with any visit. It never downloads or installs anything. Turn it off in Settings › Privacy › Check for updates. |
| Training environment (optional, several GB) | GitHub (`uv`), PyPI, `download.pytorch.org`, Hugging Face (NeMo `nvidia/parakeet-tdt-0.6b-v3` and `Qwen/Qwen3-0.6B`) | Only if you train your voice. Training runs on your PC: your audio is not uploaded. |

Links (what's new, licenses, this page) open in your browser only when you click them.

## What it saves, and where

Everything lives in `%LOCALAPPDATA%\Cotorreando`:

| File or folder | What it is | Encrypted? |
|---|---|---|
| `settings.json` | Your settings (including the keyword and excluded apps). | No |
| `cotorreando.log` | Technical log of the last session (wiped on start). Errors, listening mode, microphone name, how many words a correction changed. **It does not contain what you dictate.** | No |
| `models\` | Downloaded models and your trained voice models (`models\adapters`). | No: dictation needs them |
| `vault\records\` | Audio and text of your corrections. | Yes |
| `vault\journal\` | Words noticed while the vault was locked, waiting to be merged into your lists. | Yes |
| `vault\*.sealed` | Lists of hard words, corrections and your own words; training checkpoint. | Yes |
| `vault\trained.json` | Only the ids (dates) of what was already trained on. | No |
| `recordings\` | Calibration readings of your voice. | Yes |
| `tools\`, `train-env\` | The training environment, if you installed it. | No (none of your data) |

**How it is encrypted**: with [age](https://age-encryption.org). Data is sealed to a public key,
so dictation can store it without being able to read it back. The private key is on disk
encrypted with **your password** and, separately, with a **recovery code** shown only once.
Reading anything back takes the password. Without a password you can dictate, but nothing is learnt and none of your voice is kept.

**Retention**: records and journal entries older than "Delete data older than (days)"
(180 by default) are deleted when Cotorreando starts.

## Learning

It is optional: turn it off in the welcome window or in Settings › Privacy › Learn from my
corrections; it also needs a password to have been created. When it is on:

- It keeps the **words the model was unsure of** (just the word, no audio).
- It looks for **corrections**: after dictating, it reads the field it typed into every 2 s,
  **only while that field has the focus**, for up to 2 minutes. If you swapped a few words for
  others that sound alike, it keeps the corrected sentence with its audio. If you deleted or
  rewrote the text, nothing is kept.
- It never reads or learns from **password fields**, nor from the **excluded apps** you list in Settings.
- All other audio is forgotten as soon as the sentence ends.

## See, export and delete your data

In Settings › Privacy (it asks for the password):

- **View my data…**: play, edit or delete each correction, or all of them; remove words from your lists.
- **Export** writes a `.cotorreando` file encrypted with a password you choose (audio only if you tick it).
- **Import** brings it into another install.

## Uninstalling

The uninstaller removes the program and the start-with-Windows entry, and then **asks whether to
delete your data** (the folder `%LOCALAPPDATA%\Cotorreando`). The default answer is no, so you can
reinstall without losing it. If you said no and change your mind, delete that folder by hand
(paste the path into File Explorer).

## Questions

Open an issue at <https://github.com/alfiq/cotorreando/issues>. The code is open: everything on
this page can be checked in the repository.
