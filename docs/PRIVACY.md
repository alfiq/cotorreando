# Privacy

Privacy is a right, not a privilege. Cotorreando hears your microphone and types into your
programs, so you deserve to know what it does with that.

In short: **your voice is processed on your PC**. There are no accounts, no telemetry and no
analytics. What it learns about you is kept encrypted, and it only opens with your password or
your recovery code.

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
- **It does not record what you type.** There is no keyboard hook. What it does do:
  - It checks whether your hotkey's keys are held down, to know when you use it.
  - It looks at the time of your last key press or mouse movement, to know whether you are typing.
  - It watches mouse clicks, to know whether you moved the cursor and avoid typing somewhere else.
  - While you record a new hotkey in Settings, it reads which keys are held down.

  None of that is saved.
- **If you type while dictating, it drops the sentence you were saying** so it never types over
  you. It picks up again with the next sentence, 1.2 s after your last key (by default).

## What goes over the network, and when

All recognition happens on your computer. These are the connections it makes. All are HTTPS and
none carries your data; the download libraries send their version, like any program does:

| What | Where | When |
|---|---|---|
| Voice model (~670 MB) | Hugging Face (`istupakov/parakeet-tdt-0.6b-v3-onnx`) | The first time, or when you ask to download it again. Not downloaded with your own model. |
| Speech detector (Silero VAD, ~2 MB) | GitHub (`snakers4/silero-vad`, v5.1.2) | The first time. |
| The model's `tokenizer.json` | Hugging Face (`nvidia/parakeet-tdt-0.6b-v3`) | The first time your words are boosted, with the downloaded model. |
| Update check | `api.github.com` | At most once a day. A plain GET with the User-Agent `Cotorreando/<version>`; GitHub sees your IP, as with any visit. It never downloads or installs anything. Turn it off in Settings › Privacy › Check for updates. |
| Training environment (optional, several GB) | GitHub (`uv` and, if you lack it, Python 3.12), PyPI, `download.pytorch.org`, Hugging Face (NeMo `nvidia/parakeet-tdt-0.6b-v3` and `Qwen/Qwen3-0.6B`) | Only if you train your voice, and each training run checks Hugging Face again. Qwen is only used with an NVIDIA GPU, to write practice sentences with your hard words on your PC. Training runs on your PC: your audio is not uploaded. |

Links (what's new, licenses, this page) open in your browser only when you click them.

## What it saves, and where

Your data lives in `%LOCALAPPDATA%\Cotorreando`:

| File or folder | What it is | Encrypted? |
|---|---|---|
| `settings.json` | Your settings (including the keyword and excluded apps). | No |
| `cotorreando.log` | Technical log of the last session (wiped on start). Errors, listening mode, microphone name, how many words a correction changed. It does not contain what you dictate. If you train, it also holds the training tools' messages: check it before sharing it. | No |
| `models\` | Downloaded models and your trained voice models (`models\adapters`). | No: dictation needs them |
| `vault\records\` | Audio and text of your corrections. | Yes |
| `vault\journal\` | Words noticed while the vault was locked, waiting to be merged into your lists. | Yes |
| `vault\*.sealed` | Lists of hard words, corrections and your own words; training checkpoint. | Yes |
| `vault\trained.json` | Only the ids (dates) of what was already trained on. | No |
| `recordings\` | Calibration readings of your voice. | Yes |
| `tools\`, `train-env\` | The training environment, if you installed it. | No (none of your data) |

If you installed the training environment, the tools also leave a cache outside that folder: in
`%USERPROFILE%\.cache\huggingface` and in `uv`'s cache. Several GB, none of it yours.

**Without a password nothing of your voice or of what you dictate is kept.** You can still
dictate, but it does not learn. All that is kept are your settings, the technical log and the
models.

**The password and the recovery code.** The first time, once the model has loaded, it offers to
create a password. It is optional. When you create it you get a **recovery code**, shown only
that once. Print it and keep it somewhere safe. Not in a text file on the same computer, please.
If you forget your password, that code is the only way to get back your recordings, your
corrections and what it learnt about your voice. Take care of it.

To change the password, right-click the parrot, choose **Settings…**, and on the **Privacy** tab
press **Change password…**. If you forgot it, press **I forgot it** when asked for the password and
use the code.

**How it is encrypted**: with [age](https://age-encryption.org). Data is sealed to a public key,
so dictation can store it without being able to read it back. The private key is on disk,
encrypted with your password and, separately, with the recovery code.

We do our best so nobody else can read it. The rest is up to you: don't leave your computer
unlocked when you are away.

**Retention**: records and journal entries older than "Delete data older than (days)" (180 by
default) are deleted when Cotorreando starts. Calibration readings stay until you delete them.

## Learning

Cotorreando learns from its mistakes when you correct what it typed. It is optional: turn it off
in the welcome window or in Settings › Privacy › Learn from my corrections; it also needs a
password to have been created. When it is on:

- **When you start dictating it reads the text already in the field** (up to 20,000 characters),
  to get capitals and spaces right and prefer words you already used there. That stays in memory
  and is not saved.
- It keeps the **words the model was unsure of** (just the word, no audio).
- It looks for **corrections**: after dictating, it reads the field it typed into every 2 s,
  **only while that field has the focus**, for up to 2 minutes. If you swapped a few words for
  others that sound alike, it keeps the corrected sentence with its audio. If you rewrote almost
  all of it, that is not a correction. If you corrected a few words and then sent or deleted the
  text, the last corrected version it saw is kept.
- It never reads or learns from **fields Windows reports as password fields**, nor from the
  **excluded apps** you list in Settings.
- All other audio is forgotten as soon as the sentence ends.

## See, export and delete your data

In Settings › Privacy (it asks for the password):

- **View my data…**: play, edit or delete each correction, or all of them; remove words from your lists.
- **Export** writes a `.cotorreando` file encrypted with a password you choose (audio only if you tick it).
- **Import** brings it into another install.

## Uninstalling

The uninstaller removes the program and the start-with-Windows entry, and then **asks whether to
delete your data** (the folder `%LOCALAPPDATA%\Cotorreando`). The default button is No, so you can
reinstall without losing it, and a silent uninstall deletes nothing. If you said no and change
your mind, delete that folder by hand (paste the path into File Explorer).

The training cache (`%USERPROFILE%\.cache\huggingface` and `uv`'s) is not removed by the
uninstaller. Delete it by hand if you want the space back.

## Questions

Open an issue at <https://github.com/alfiq/cotorreando/issues>. The code is open, so you don't
have to take our word for it: everything on this page can be checked in the repository.
