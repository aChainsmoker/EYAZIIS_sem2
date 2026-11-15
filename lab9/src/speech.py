import queue
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
import numpy as np
import pyaudio
import torch
import whisper
from src.config import CONFIG, ROOT
from src.errors import RecognitionError

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
_model = None
_model_lock = threading.RLock()

def load_model():
    global _model
    with _model_lock:
        if _model is None:
            _model = whisper.load_model(CONFIG["whisper"]["model"], device=DEVICE)
        return _model


def _transcribe_samples(model, samples, language):
    with _model_lock:
        return model.transcribe(samples, language=language, task="transcribe", fp16=DEVICE == "cuda")


def transcribe_audio(audio_bytes: bytes, language: str) -> str:
    """Распознаёт полную запись, а не последние пять секунд микрофонного буфера."""
    if language not in {"ru", "en"}:
        raise RecognitionError("Выберите русский или английский язык речи: ru/en.")
    if not isinstance(audio_bytes, bytes) or not audio_bytes:
        raise RecognitionError("Запись пуста. Запишите сообщение заново.")
    settings = CONFIG["whisper"]
    bundled = ROOT / settings.get("ffmpeg_path", "ffmpeg/bin/ffmpeg.exe")
    executable = str(bundled) if bundled.is_file() else shutil.which("ffmpeg")
    if executable is None:
        raise RecognitionError("FFmpeg не найден. Укажите whisper.ffmpeg_path в config.toml.")
    try:
        decoded = subprocess.run(
            [executable, "-nostdin", "-threads", "0", "-i", "pipe:0", "-f", "s16le",
             "-ac", "1", "-acodec", "pcm_s16le", "-ar", "16000", "pipe:1"],
            input=audio_bytes, capture_output=True, check=True,
            timeout=float(settings.get("decode_timeout_seconds", 120)),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        samples = np.frombuffer(decoded.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        if not samples.size or np.sqrt(np.mean(samples ** 2)) < settings["min_audio_rms"]:
            raise RecognitionError("В записи нет достаточно громкой речи.")
        result = _transcribe_samples(load_model(), samples, language)
    except RecognitionError:
        raise
    except Exception as exc:
        raise RecognitionError("Не удалось распознать запись. Проверьте формат аудио и доступность модели Whisper.") from exc
    text = result["text"].strip()
    if not text:
        raise RecognitionError("Whisper не распознал сообщение. Повторите запись.")
    return text

class Recorder:
    def __init__(self, model, language):
        self.model = model
        self.language = language
        self.results = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def run(self):
        audio = None
        stream = None
        cfg = CONFIG["whisper"]
        rate = cfg["sample_rate"]
        duration = cfg["chunk_duration"]
        frames = int(rate * duration)
        buffer = deque(maxlen=int(cfg["buffer_size"] / duration))
        silence = 0
        last = 0
        try:
            audio = pyaudio.PyAudio()
            stream = audio.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True, frames_per_buffer=frames)
            while not self.stop_event.is_set():
                chunk = np.frombuffer(stream.read(frames, exception_on_overflow=False), dtype=np.int16).astype(np.float32) / 32768.0
                silence = silence + duration if np.max(np.abs(chunk)) < cfg["silence_threshold"] else 0
                buffer.append(chunk)
                if (silence >= cfg["silence_patience"] or len(buffer) == buffer.maxlen) and time.monotonic() - last > cfg["min_transcribe_interval"]:
                    samples = np.concatenate(buffer)
                    if silence:
                        samples = samples[:max(int(len(samples) - silence * rate), rate)]
                    if np.sqrt(np.mean(samples ** 2)) >= cfg["min_audio_rms"]:
                        result = _transcribe_samples(self.model, samples, self.language)
                        text = result["text"].strip()
                        if text:
                            self.results.put(("text", text))
                    buffer.clear()
                    silence = 0
                    last = time.monotonic()
        except Exception as exc:
            self.results.put(("error", str(exc)))
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            if audio is not None:
                audio.terminate()
