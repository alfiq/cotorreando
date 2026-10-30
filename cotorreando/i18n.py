"""Tiny translation table. ``tr(key)`` returns the text for the current language."""

STRINGS = {
    "enable": ("Activar", "Enable"),
    "disable": ("Desactivar", "Disable"),
    "hide": ("Ocultar", "Hide"),
    "show": ("Mostrar", "Show"),
    "settings": ("Opciones…", "Settings…"),
    "train": ("Entrenar mi voz…", "Train my voice…"),
    "about": ("Acerca de…", "About…"),
    "quit": ("Salir", "Quit"),
    "loading": ("Cargando modelo…", "Loading model…"),
    "downloading": ("Descargando modelo… {pct}%", "Downloading model… {pct}%"),
    "ready": ("Listo", "Ready"),
    "disabled": ("Desactivado", "Disabled"),
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
    "blob_size": ("Tamaño del blob", "Blob size"),
    "small": ("Pequeño", "Small"),
    "medium": ("Mediano", "Medium"),
    "large": ("Grande", "Large"),
    "use_gpu": ("Usar GPU si está disponible", "Use GPU when available"),
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
    # Training
    "train_title": ("Entrenar mi voz", "Train my voice"),
    "dataset": ("Conjunto de frases", "Phrase set"),
    "record": ("Grabar", "Record"),
    "stop": ("Detener", "Stop"),
    "next": ("Siguiente", "Next"),
    "prev": ("Anterior", "Previous"),
    "start_training": ("Entrenar", "Train"),
    "progress": ("Frase {i} de {n} · grabadas {done}", "Phrase {i} of {n} · recorded {done}"),
    "deps_title": ("Dependencias adicionales", "Additional dependencies"),
    "deps_text": (
        "Entrenar requiere instalar un entorno aparte (~6 GB) con:\n\n"
        "• PyTorch con CUDA (BSD-3)\n• NVIDIA NeMo Toolkit [asr] (Apache-2.0)\n"
        "• uv para crear el entorno (MIT/Apache-2.0)\n\n"
        "Se instala en {path}. Se necesita GPU NVIDIA y conexión a internet.\n¿Continuar?",
        "Training needs a separate environment (~6 GB) with:\n\n"
        "• PyTorch with CUDA (BSD-3)\n• NVIDIA NeMo Toolkit [asr] (Apache-2.0)\n"
        "• uv to create the environment (MIT/Apache-2.0)\n\n"
        "It is installed in {path}. Needs an NVIDIA GPU and internet.\nContinue?"),
    "training": ("Entrenando… esto puede tardar varios minutos.", "Training… this may take a few minutes."),
    "trained": ("Listo. Adaptador «{name}» activado.", "Done. Adapter “{name}” enabled."),
    "train_failed": ("El entrenamiento falló. Revisa el registro.", "Training failed. See the log."),
    "need_more": ("Graba al menos 10 frases.", "Record at least 10 phrases."),
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
