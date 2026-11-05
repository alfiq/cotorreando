"""Tiny translation table. ``tr(key)`` returns the text for the current language."""

STRINGS = {
    "enable": ("Activar", "Enable"),
    "disable": ("Desactivar", "Disable"),
    "hide": ("Ocultar", "Hide"),
    "show": ("Mostrar", "Show"),
    "settings": ("Opciones…", "Settings…"),
    "train": ("Calibrar mi voz…", "Calibrate my voice…"),
    "about": ("Acerca de…", "About…"),
    "quit": ("Salir", "Quit"),
    "loading": ("Cargando modelo…", "Loading model…"),
    "downloading": ("Descargando modelo… {pct}%", "Downloading model… {pct}%"),
    "ready": ("Listo", "Ready"),
    "load_failed": ("No se pudo cargar el modelo: {error}", "Could not load the model: {error}"),
    "mic_silent": ("El micrófono no envía audio. Revisa Configuración > Privacidad > Micrófono.",
                   "The microphone sends no audio. Check Settings > Privacy > Microphone."),
    "disabled": ("Desactivado", "Disabled"),
    # Model download and the user's own model
    "dl_title": ("Descargando el modelo de voz", "Downloading the speech model"),
    "dl_intro": ("La primera vez Cotorreando descarga el modelo de reconocimiento (unos 670 MB). "
                 "Después funciona sin conexión.",
                 "The first time, Cotorreando downloads the recognition model (about 670 MB). "
                 "After that it works offline."),
    "dl_starting": ("Conectando…", "Connecting…"),
    "dl_progress": ("{done} de {total} · {pct}%", "{done} of {total} · {pct}%"),
    "dl_progress_unknown": ("{done} descargados", "{done} downloaded"),
    "dl_speed": (" · {speed}/s · quedan {left}", " · {speed}/s · {left} left"),
    "dl_verifying": ("Comprobando los archivos…", "Checking the files…"),
    "dl_offline": ("No hay conexión a internet y el modelo aún no está descargado. "
                   "Conéctate y vuelve a intentarlo, o usa un modelo que ya tengas.\n\n{detail}",
                   "There is no internet connection and the model is not downloaded yet. "
                   "Connect and try again, or use a model you already have.\n\n{detail}"),
    "dl_interrupted": ("La descarga del modelo se interrumpió. Lo ya descargado se conserva y "
                       "se reanuda al reintentar; nada a medias se usará como modelo.\n\n{detail}",
                       "The model download was interrupted. What was downloaded is kept and "
                       "resumes when you retry; nothing half-done is ever used as the model.\n\n{detail}"),
    "dl_no_space": ("No hay espacio suficiente para el modelo: hacen falta {needed} libres y hay {free}. "
                    "Libera espacio en el disco y vuelve a intentarlo.",
                    "Not enough disk space for the model: {needed} free are needed and there are {free}. "
                    "Free up some space and try again."),
    "dl_cancelled": ("Descarga cancelada. Sin el modelo Cotorreando no puede dictar.",
                     "Download cancelled. Without the model Cotorreando cannot take dictation."),
    "model_corrupt": ("El modelo descargado no se puede cargar; puede estar dañado.\n\n{error}",
                      "The downloaded model cannot be loaded; it may be damaged.\n\n{error}"),
    "model_custom_failed": ("Tu modelo ({path}) no se puede cargar.\n\n{error}",
                            "Your model ({path}) cannot be loaded.\n\n{error}"),
    "model_problem": ("Problema con el modelo", "Model problem"),
    "retry": ("Reintentar", "Retry"),
    "redownload": ("Volver a descargar", "Download again"),
    "use_own_model": ("Usar mi modelo…", "Use my own model…"),
    "use_stock_model": ("Usar el modelo estándar", "Use the standard model"),
    "own_model": ("Modelo de reconocimiento", "Recognition model"),
    "own_model_stock": ("Parakeet TDT 0.6B v3 (estándar)", "Parakeet TDT 0.6B v3 (standard)"),
    "own_model_choose": ("Elegir carpeta…", "Choose folder…"),
    "own_model_pick": ("Carpeta con tu modelo", "Folder with your model"),
    "own_model_help": (
        "Sirve un modelo NVIDIA NeMo FastConformer-TDT (p. ej. Parakeet TDT 0.6B v2/v3) exportado a ONNX "
        "con la estructura de onnx-asr: nemo128.onnx (preprocesador de 128 bandas mel), "
        "encoder-model.onnx y decoder_joint-model.onnx (o sus variantes .int8.onnx) y vocab.txt "
        "(«token índice» por línea, el último índice es el blank). Audio de 16 kHz. "
        "No sirven modelos RNN-T, CTC, Whisper ni .nemo sin exportar. "
        "Opcional: tokenizer.json para potenciar tus palabras.",
        "Works with an NVIDIA NeMo FastConformer-TDT model (e.g. Parakeet TDT 0.6B v2/v3) exported to "
        "ONNX in the onnx-asr layout: nemo128.onnx (128-mel preprocessor), encoder-model.onnx and "
        "decoder_joint-model.onnx (or their .int8.onnx variants) and vocab.txt (\"token index\" per "
        "line, the last index is the blank). 16 kHz audio. RNN-T, CTC, Whisper or unexported .nemo "
        "models do not work. Optional: tokenizer.json to boost your words."),
    "model_invalid": ("Esa carpeta no contiene un modelo compatible: {reason}",
                      "That folder does not hold a compatible model: {reason}"),
    "model_no_folder": ("la carpeta {path} no existe.", "the folder {path} does not exist."),
    "model_missing": ("faltan {files}.", "missing {files}."),
    "model_bad_vocab": ("vocab.txt no tiene el formato «token índice» (línea {line}).",
                        "vocab.txt is not in the \"token index\" format (line {line})."),
    "model_bad_onnx": ("{file} no se puede abrir con ONNX Runtime: {detail}",
                       "{file} cannot be opened with ONNX Runtime: {detail}"),
    "model_bad_names": ("{file} no tiene las entradas y salidas esperadas (esperadas: {expected}; "
                        "tiene: {found}).",
                        "{file} does not have the expected inputs and outputs (expected: {expected}; "
                        "found: {found})."),
    "model_not_tdt": ("el decodificador no predice duraciones (salida de {width} para {vocab} tokens): "
                      "no es un modelo TDT.",
                      "the decoder predicts no durations (output of {width} for {vocab} tokens): "
                      "it is not a TDT model."),
    # Settings
    "general": ("General", "General"),
    "audio": ("Audio", "Audio"),
    "typing": ("Escritura", "Typing"),
    "model": ("Modelo", "Model"),
    "language": ("Idioma de la interfaz", "Interface language"),
    "mode": ("Modo de escucha", "Listening mode"),
    "mode_open": ("Micrófono abierto", "Open microphone"),
    "mode_ptt": ("Pulsar para hablar", "Push-to-talk"),
    "mode_activation": ("Activación", "Activation"),
    "activation": ("Activar con", "Activate with"),
    "act_voice": ("Voz", "Voice"),
    "act_keyword": ("Palabra clave", "Keyword"),
    "keyword": ("Palabra clave", "Keyword"),
    "hotkey": ("Atajo", "Hotkey"),
    "hotkey_press": ("Pulsa la combinación…", "Press the combination…"),
    "hotkey_invalid": ("Combinación no válida: usa Ctrl, Alt o Win con otra tecla, o una tecla F",
                       "Invalid combination: use Ctrl, Alt or Win with another key, or an F key"),
    "hotkey_reset": ("Restaurar", "Reset"),
    "hotkey_hint": ("Haz clic y pulsa las teclas; Esc cancela. Windows se reserva algunas combinaciones, "
                    "como Win+L.",
                    "Click and press the keys; Esc cancels. Windows keeps some combinations for itself, "
                    "like Win+L."),
    "blob_size": ("Tamaño del blob", "Blob size"),
    "small": ("Pequeño", "Small"),
    "medium": ("Mediano", "Medium"),
    "large": ("Grande", "Large"),
    "use_gpu": ("Usar GPU si está disponible", "Use GPU when available"),
    "unload_after": ("Liberar el modelo tras (minutos sin dictar)", "Free the model after (idle minutes)"),
    "unload_never": ("Nunca", "Never"),
    "unload_help": ("Libera memoria cuando no dictas; se vuelve a cargar al hablar. En modo palabra clave "
                    "sigue cargado mientras se detecta voz.",
                    "Frees memory while you are not dictating; it loads again when you speak. In keyword mode "
                    "it stays loaded while speech is detected."),
    "autostart": ("Iniciar con Windows", "Start with Windows"),
    "microphone": ("Micrófono", "Microphone"),
    "default": ("Predeterminado", "Default"),
    "noise": ("Eliminar ruido", "Noise suppression"),
    "echo": ("Cancelar eco", "Echo cancellation"),
    "agc": ("Control automático de ganancia", "Automatic gain control"),
    "auto_threshold": ("Umbral automático", "Automatic threshold"),
    "threshold": ("Umbral de energía (dBFS)", "Energy threshold (dBFS)"),
    "vad_threshold": ("Sensibilidad de voz (VAD)", "Voice sensitivity (VAD)"),
    "silence": ("Silencio para cortar (ms)", "Silence before cut (ms)"),
    "session": ("Seguir escuchando tras activar (s)", "Keep listening after activation (s)"),
    "calibrate": ("Recalibrar ruido", "Recalibrate noise"),
    "level": ("Nivel actual: {lvl:.0f} dBFS · umbral {thr:.0f}", "Level: {lvl:.0f} dBFS · threshold {thr:.0f}"),
    "holdoff": ("Pausa al teclear (ms)", "Pause while typing (ms)"),
    "streaming": ("Escribir mientras hablo", "Type while I speak"),
    "trailing": ("Espacio al final de cada frase", "Trailing space after each phrase"),
    "adapter": ("Adaptación de voz (LoRA)", "Voice adaptation (LoRA)"),
    "stock": ("Ninguna (modelo original)", "None (stock model)"),
    "restart": ("Algunos cambios se aplican al reiniciar.", "Some changes apply after a restart."),
    # Calibration
    "train_title": ("Calibrar mi voz", "Calibrate my voice"),
    "cal_welcome": ("Vamos a conocernos", "Let's get to know each other"),
    "cal_intro": ("Lee en voz alta unos textos breves, unos 3 minutos. Con ellos me adapto a tu voz, tu "
                  "micrófono y el ruido de este lugar. Tu voz se queda en tu PC.",
                  "Read a few short texts aloud, about 3 minutes. They let me adapt to your voice, your "
                  "microphone and the noise around you. Your voice stays on your PC."),
    "cal_language": ("Idioma en el que dictas", "Language you dictate in"),
    "cal_both": ("Ambos (unos 6 minutos)", "Both (about 6 minutes)"),
    "cal_cost": ("La primera vez se descargan de internet unos 6 GB: herramientas y paquetes de Python (GitHub, PyPI, "
                 "PyTorch) y modelos de Hugging Face. Tu audio no se sube. El ajuste tarda unos minutos.",
                 "The first time downloads about 6 GB from the internet: tools and Python packages (GitHub, PyPI, "
                 "PyTorch) and models from Hugging Face. Your audio is not uploaded. Tuning takes a few minutes."),
    "cal_cost_cpu": ("La primera vez se descargan de internet unos 3 GB: herramientas y paquetes de Python (GitHub, PyPI, "
                     "PyTorch) y modelos de Hugging Face. Tu audio no se sube. Sin GPU NVIDIA, el ajuste puede tardar bastante.",
                     "The first time downloads about 3 GB from the internet: tools and Python packages (GitHub, PyPI, "
                     "PyTorch) and models from Hugging Face. Your audio is not uploaded. Without an NVIDIA GPU, tuning can take a while."),
    "cal_skip_note": ("Si lo omites, puedes hacerlo cuando quieras en Opciones → Modelo.",
                      "If you skip it, you can do it anytime in Settings → Model."),
    "cal_skip": ("Omitir por ahora", "Skip for now"),
    "cal_start": ("Empezar", "Start"),
    "cal_read_hint": ("Lee con naturalidad, como hablas siempre.", "Read naturally, the way you always talk."),
    "cal_again": ("Repetir", "Start over"),
    "cal_done": ("Terminado", "Done"),
    "cal_cheer0": ("Buen inicio", "Good start"),
    "cal_cheer1": ("Vamos avanzando", "Making progress"),
    "cal_cheer2": ("Te escucho cada vez mejor", "I can hear you better and better"),
    "cal_cheer3": ("Cada vez más cerca", "Getting closer"),
    "cal_cheer4": ("Ya casi", "Almost there"),
    "cal_thanks": ("¡Gracias por tu ayuda!", "Thanks for your help!"),
    "cal_stage_install": ("Preparando lo necesario. Puedes seguir dictando mientras tanto.",
                          "Getting things ready. You can keep dictating in the meantime."),
    "cal_stage_train": ("Aprendiendo de tu voz. Puedes seguir dictando mientras tanto.",
                        "Learning from your voice. You can keep dictating in the meantime."),
    "cal_stage_export": ("Dando los últimos retoques…", "Adding the finishing touches…"),
    "cal_background": ("Seguir en segundo plano", "Continue in the background"),
    "cal_finish": ("Cerrar", "Close"),
    "cal_retry": ("Reintentar", "Try again"),
    "cal_ready": ("Listo", "All set"),
    "cal_result": ("En un texto de prueba, mis errores pasaron de {before:.1f} % a {after:.1f} %.",
                   "On a test text, my errors went from {before:.1f}% to {after:.1f}%."),
    "cal_no_gain": ("Esta vez no mejoré, así que me quedo con el modelo original.",
                    "It didn't improve this time, so I'm keeping the original model."),
    "cal_failed_title": ("No pude terminar", "I couldn't finish"),
    "cal_failed": ("Tus lecturas están guardadas. Detalles en {path}", "Your readings are saved. Details in {path}"),
    "cal_skipped_tip": ("Puedes calibrar tu voz cuando quieras en Opciones → Modelo.",
                        "You can calibrate your voice anytime in Settings → Model."),
    "cal_applied": ("Tu calibración ya está activa.", "Your calibration is now active."),
    "calibrate_voice": ("Calibrar mi voz…", "Calibrate my voice…"),
    "calibrate_help": ("Adapta el dictado a tu voz, micrófono y entorno. Repítelo si cambias de lugar o de micrófono.",
                       "Adapts dictation to your voice, microphone and surroundings. Repeat it if you change either."),
    "save": ("Guardar", "Save"),
    "cancel": ("Cancelar", "Cancel"),
    "appearance": ("Apariencia", "Appearance"),
    "listening": ("Escucha", "Listening"),
    "system": ("Sistema", "System"),
    "capture": ("Captura", "Capture"),
    "detection": ("Detección de voz", "Voice detection"),
    # Privacy
    "boost": ("Inclinarse hacia tus palabras", "Lean towards your words"),
    "boost_auto": ("Automático (si mejora con tu voz)", "Automatic (if it helps with your voice)"),
    "boost_on": ("Siempre", "Always"),
    "boost_off": ("Nunca", "Never"),
    "boost_note": ("Cuando el modelo duda entre palabras parecidas, prefiere las que corregiste o agregaste. "
                   "En automático se activa solo si el entrenamiento mide que acierta más con tu voz.",
                   "When the model hesitates between similar words it prefers the ones you corrected or added. "
                   "Automatic turns it on only if training measures that it gets your voice right more often."),
    "privacy": ("Privacidad", "Privacy"),
    "learning": ("Aprender de mis correcciones", "Learn from my corrections"),
    "check_updates": ("Buscar actualizaciones", "Check for updates"),
    "check_updates_note": ("Una vez al día pregunta a GitHub si hay una versión nueva. Es una petición web "
                           "normal, sin datos tuyos, y nunca descarga ni instala nada sola.",
                           "Once a day it asks GitHub whether there is a new version. It is a plain web "
                           "request, with none of your data, and it never downloads or installs anything."),
    "update_available": ("Hay una versión nueva de Cotorreando: {version} (tienes {current}).",
                         "A new version of Cotorreando is out: {version} (you have {current})."),
    "update_open": ("Ver novedades", "See what's new"),
    "update_skip": ("Omitir esta versión", "Skip this version"),
    "excluded": ("Apps excluidas (ej. keepass.exe, banco.exe)", "Excluded apps (e.g. keepass.exe, bank.exe)"),
    "retention": ("Borrar datos con más de (días)", "Delete data older than (days)"),
    "privacy_note": ("Tu voz, tu texto y tus palabras se cifran con age y solo se abren con tu contraseña. "
                     "Nunca se guarda lo que dictas en campos de contraseña. Tu modelo de voz entrenado no se "
                     "cifra, porque hace falta para dictar.",
                     "Your voice, text and words are encrypted with age and only open with your password. Nothing "
                     "dictated in password fields is ever kept. Your trained voice model is not encrypted, because "
                     "dictation needs it."),
    "password_set": ("Crear contraseña…", "Create password…"),
    "password_change": ("Cambiar contraseña…", "Change password…"),
    "password_setup": ("Crea una contraseña para proteger lo que Cotorreando aprende de ti. Puedes guardarla en "
                       "tu administrador de contraseñas. Sin ella puedes dictar, pero no se aprende nada.",
                       "Create a password to protect what Cotorreando learns from you. You can keep it in your "
                       "password manager. Without it you can dictate, but nothing is learnt."),
    "password_create": ("Crear", "Create"),
    "password_new_hint": ("Contraseña (mínimo 8 caracteres)", "Password (at least 8 characters)"),
    "password_again": ("Repítela", "Repeat it"),
    "password_old": ("Contraseña de la versión anterior", "Password of the previous version"),
    "password_generate": ("Generar una segura", "Generate a strong one"),
    "password_mismatch": ("Las contraseñas no coinciden.", "The passwords do not match."),
    "password_short": ("Debe tener al menos 8 caracteres.", "It must have at least 8 characters."),
    "password_weak": ("Es demasiado fácil de adivinar.", "It is too easy to guess."),
    "password_forgot": ("La olvidé", "I forgot it"),
    "password_wait": ("Demasiados intentos. Espera {seconds} segundos.", "Too many tries. Wait {seconds} seconds."),
    "recovery_show": ("Este es tu código de recuperación. Guárdalo en un lugar seguro: solo se muestra ahora y "
                      "es la única forma de entrar si olvidas tu contraseña.",
                      "This is your recovery code. Keep it somewhere safe: it is only shown now and it is the "
                      "only way in if you forget your password."),
    "recovery_saved": ("Ya lo guardé", "I saved it"),
    "recovery_prompt": ("Escribe tu código de recuperación y una contraseña nueva.",
                        "Enter your recovery code and a new password."),
    "recovery_wrong": ("Código de recuperación incorrecto.", "Wrong recovery code."),
    "notice_unlock": ("Escribe tu contraseña para activar tus correcciones.",
                      "Enter your password to turn on your corrections."),
    "notice_setup": ("Crea una contraseña para que Cotorreando pueda aprender de ti.",
                     "Create a password so Cotorreando can learn from you."),
    "notice_action": ("Escribirla", "Enter it"),
    "notice_setup_action": ("Crearla", "Create it"),
    "unlock_menu": ("Activar mis correcciones…", "Turn on my corrections…"),
    "later": ("Después", "Later"),
    "password_prompt": ("Contraseña de Cotorreando", "Cotorreando password"),
    "password_new": ("Nueva contraseña. Si la olvidas, tus datos guardados no se pueden recuperar.",
                     "New password. If you forget it, your saved data cannot be recovered."),
    "password_current": ("Escribe tu contraseña:", "Enter your password:"),
    "password_wrong": ("Contraseña incorrecta.", "Wrong password."),
    "data_view": ("Ver mis datos…", "View my data…"),
    "export": ("Exportar…", "Export…"),
    "export_password": ("Contraseña del archivo. Puede ser la misma que la de Cotorreando; la necesitarás para "
                        "importarlo.", "Password for the file. It can be the same as your Cotorreando password; "
                        "you will need it to import it."),
    "export_ok": ("Elegir dónde guardar…", "Choose where to save…"),
    "export_dictations": ("Incluir dictados con su audio", "Include dictations with their audio"),
    "export_dictations_note": ("El archivo será mucho más grande y guardará tu voz.",
                               "The file will be much larger and will hold your voice."),
    "export_done": ("Listo. Tus ajustes y palabras se exportaron.", "Done. Your settings and words were exported."),
    "export_failed": ("No se pudo exportar.", "Could not export."),
    "import": ("Importar…", "Import…"),
    "import_password": ("Contraseña del archivo que vas a importar:", "Password of the file to import:"),
    "import_ok": ("Importar", "Import"),
    "import_add": ("Agregar a mis palabras", "Add to my words"),
    "import_replace": ("Reemplazar mis palabras", "Replace my words"),
    "import_mode_note": ("Agregar suma los conteos de tus correcciones; reemplazar deja solo las del archivo. "
                         "Los dictados siempre se agregan, sin repetirse, y nunca se borran.",
                         "Add sums the counts of your corrections; replace keeps only the file's. "
                         "Dictations are always added, never twice, and never deleted."),
    "import_settings": ("Aplicar también los ajustes", "Also apply the settings"),
    "import_not_ours": ("Este archivo no es una exportación de Cotorreando o es de una versión más nueva.",
                        "This file is not a Cotorreando export, or it comes from a newer version."),
    "import_done": ("Se importaron {words} palabras, {corrections} correcciones y {records} dictados.",
                    "Imported {words} words, {corrections} corrections and {records} dictations."),
    "import_failed": ("No se pudo importar.", "Could not import."),
    "data_title": ("Datos guardados", "Saved data"),
    "data_delete": ("Borrar", "Delete"),
    "data_edit": ("Editar", "Edit"),
    "data_play": ("▶  Escuchar", "▶  Listen"),
    "data_stop": ("■  Detener", "■  Stop"),
    "data_old": ("Dictado original: {text}", "Original dictation: {text}"),
    "data_tab_dictations": ("Dictados", "Dictations"),
    "data_tab_words": ("Palabras", "Words"),
    "words_custom": ("TUS PALABRAS", "YOUR WORDS"),
    "words_custom_note": ("Nombres, términos o frases que dices seguido. El modelo se inclina hacia ellas cuando "
                          "duda, pero nunca las escribe si no las dijiste.",
                          "Names, terms or phrases you say often. The model leans towards them when it hesitates, "
                          "but never writes them if you did not say them."),
    "words_custom_hint": ("Ej. Tlaquepaque, Kubernetes, Itzel", "E.g. Tlaquepaque, Kubernetes, Itzel"),
    "words_add": ("Agregar", "Add"),
    "words_custom_bad": ("No se puede agregar: ya está, o lleva números.", "Cannot add it: it is already there, or has digits."),
    "words_boost": ("TUS CORRECCIONES", "YOUR CORRECTIONS"),
    "words_boost_note": ("Cuando el modelo duda, se inclina por la palabra corregida; más, cuantas más veces "
                         "la corriges. Nunca la cambia sin escucharte. Borra una y deja de inclinarse.",
                         "When the model hesitates it leans towards the corrected word, more the more often you "
                         "correct it. It never changes a word without hearing you. Delete one and it stops."),
    "words_boost_detail": ("{n} veces · peso {alpha:.1f}", "{n} times · weight {alpha:.1f}"),
    "words_hard": ("PALABRAS DIFÍCILES", "HARD WORDS"),
    "words_hard_note": ("Palabras en las que el modelo dudó. Se usan para practicar y entrenar.",
                        "Words the model was unsure of. Used for practice and training."),
    "words_hard_times": ("dudó {n} · leída {read}", "unsure {n} · read {read}"),
    "words_none": ("Nada por ahora.", "Nothing yet."),
    "data_empty": ("Todavía no hay nada guardado.", "Nothing has been saved yet."),
    "data_delete_all": ("Borrar todo", "Delete everything"),
    "data_confirm": ("¿Borrar todas tus correcciones y lecturas guardadas? No se puede deshacer.",
                     "Delete all your saved corrections and readings? This cannot be undone."),
    "kind_correction": ("Corrección", "Correction"),
    "kind_panel": ("Lectura", "Reading"),
    # Shutdown training
    "shut_title": ("¿Aprovechar para entrenar?", "Train before leaving?"),
    "shut_text": ("Tengo cosas nuevas que aprender. Puedo entrenar ahora y después apagar o reiniciar la PC.",
                  "I have new things to learn. I can train now and then shut down or restart the PC."),
    "shut_train_off": ("Entrenar y apagar", "Train and shut down"),
    "shut_train_restart": ("Entrenar y reiniciar", "Train and restart"),
    "shut_off": ("Apagar sin entrenar", "Shut down without training"),
    "shut_restart": ("Reiniciar sin entrenar", "Restart without training"),
    "shut_stay": ("No apagar", "Stay on"),
    "screen_prepare": ("Preparando lo necesario…", "Getting things ready…"),
    "screen_panels": ("Escribiendo textos con tus palabras difíciles…", "Writing texts with your difficult words…"),
    "screen_read": ("Lee en voz alta", "Read aloud"),
    "screen_train": ("Aprendiendo de tu voz…", "Learning from your voice…"),
    "screen_export": ("Dando los últimos retoques…", "Adding the finishing touches…"),
    "screen_saving": ("Guardando el avance…", "Saving progress…"),
    "screen_done": ("Listo", "All set"),
    "screen_hint": ("La tacha guarda el avance y continúa con el apagado.",
                    "The cross saves progress and carries on shutting down."),
    "screen_skip": ("Saltar lecturas", "Skip readings"),
    "train_notice": ("Tu voz ya está calibrada. Seguiré aprendiendo y solo volveré a entrenar cuando apagues "
                     "o reinicies la PC. Siempre te preguntaré antes.",
                     "Your voice is calibrated. I keep learning, and I only train again when you shut down "
                     "or restart the PC. I always ask first."),
    # Welcome (first run)
    "welcome_title": ("Bienvenido a Cotorreando", "Welcome to Cotorreando"),
    "welcome_text": (
        "<p><b>Tu voz se procesa en esta PC.</b> Sin cuentas, sin telemetría, sin nube. Solo se conecta "
        "para descargar el modelo de voz la primera vez (~670 MB: Parakeet TDT 0.6B v3 de NVIDIA, licencia "
        "CC BY 4.0) y dos archivos pequeños que necesita.</p>"
        "<p>Cotorreando escucha el micrófono mientras está activado y escribe simulando el teclado. "
        "Si tecleas, se pausa.</p>"
        "<p>Si lo permites y creas una contraseña, guarda audio y texto de tus correcciones para aprender "
        "de tu voz, en <b>%LOCALAPPDATA%\\Cotorreando</b>, cifrado con tu contraseña. "
        "Puedes verlo, borrarlo o desactivarlo en Opciones.</p>"
        "<p>Una vez al día pregunta a GitHub si hay una versión nueva: una petición web normal, sin "
        "datos tuyos. Nunca descarga ni instala nada por su cuenta; se apaga en Opciones › Privacidad.</p>"
        "<p>Las licencias están en Acerca de.</p>",
        "<p><b>Your voice is processed on this PC.</b> No accounts, no telemetry, no cloud. It only "
        "connects to download the voice model the first time (~670 MB: Parakeet TDT 0.6B v3 by NVIDIA, "
        "CC BY 4.0 license) and two small files it needs.</p>"
        "<p>Cotorreando listens to the microphone while it is on and types by simulating the keyboard. "
        "If you type, it pauses.</p>"
        "<p>If you allow it and create a password, it saves audio and text of your corrections to learn "
        "your voice, in <b>%LOCALAPPDATA%\\Cotorreando</b>, encrypted with your password. "
        "You can view, delete or turn it off in Settings.</p>"
        "<p>Once a day it asks GitHub whether there is a new version: a plain web request, with none "
        "of your data. It never downloads or installs anything by itself; turn it off in Settings › Privacy.</p>"
        "<p>The licenses are in About.</p>"),
    "privacy_link": ("Cómo cuida Cotorreando tu privacidad", "How Cotorreando handles your privacy"),
    "privacy_url": ("https://github.com/alfiq/cotorreando/blob/main/docs/PRIVACIDAD.md",
                    "https://github.com/alfiq/cotorreando/blob/main/docs/PRIVACY.md"),
    "welcome_learning": ("Guardar datos para aprender de mi voz", "Save data to learn from my voice"),
    "welcome_accept": ("Aceptar y continuar", "Accept and continue"),
    "welcome_exit": ("Salir", "Exit"),
    # About
    "about_title": ("Acerca de Cotorreando", "About Cotorreando"),
    "tagline": ("Dictado por voz para todo Windows.", "Voice dictation for all of Windows."),
    "author": ("Autor", "Author"),
    "credits": ("Créditos y licencias", "Credits and licenses"),
}

_lang = 0


def set_language(code: str) -> None:
    global _lang
    _lang = 1 if code == "en" else 0


def tr(key: str, **kw) -> str:
    text = STRINGS.get(key, (key, key))[_lang]
    return text.format(**kw) if kw else text
