import hashlib
import logging
import os
import sys
import threading
import time
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from src.config import INPUT
from src.db import repository as repo
from src.storage import s3
from src.documents import extract_text, SUPPORTED_EXTENSIONS
from src.errors import DocumentTextError
from src.search.pipeline import preprocess_with_positions
from src.language_detection.detector import detect_language

EXTENSIONS = SUPPORTED_EXTENSIONS
changed = threading.Event()

def reconcile():
    logging.info("Начало сверки каталога %s", INPUT)
    known = {row.file_path: row for row in repo.all_documents()}
    indexed = repo.indexed_states()
    present = set()
    paths = sorted(path for path in INPUT.rglob("*") if path.is_file() and path.suffix.lower() in EXTENSIONS)
    logging.info("Найдено поддерживаемых файлов %s", len(paths))
    processed = skipped = deferred = errors = removed = 0
    for position, path in enumerate(paths, start=1):
        name = os.path.normcase(str(path.resolve()))
        present.add(name)
        logging.info("Проверка файла %s/%s — %s", position, len(paths), path)
        try:
            before = path.stat()
            time.sleep(1)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                logging.info("Файл ещё записывается, обработка отложена — %s", path)
                deferred += 1
                changed.set()
                continue
            data = path.read_bytes()
            final = path.stat()
            if (after.st_size, after.st_mtime_ns) != (final.st_size, final.st_mtime_ns):
                logging.info("Файл изменился при чтении, обработка отложена — %s", path)
                deferred += 1
                changed.set()
                continue
            digest = hashlib.sha256(data).hexdigest()
            if (name in known and known[name].file_hash == digest
                    and indexed.get(known[name].id) == (digest, repo.PROCESSING_VERSION)):
                logging.info("Уже проиндексирован, изменений нет — %s", path)
                skipped += 1
                continue
            logging.info("Извлечение текста — %s", path)
            try:
                text = extract_text(data, path.name)
            except DocumentTextError as error:
                # Оригинал остаётся в каталоге; запрос к нему вернёт понятную ошибку.
                logging.warning("Текст недоступен — %s — %s", path, error)
                text = ""
            language = detect_language(text)
            logging.info("Определён язык %s — %s", language, path)
            logging.info("Подготовка поискового индекса — %s", path)
            lemmas, positions = ([], {})
            if language in {"ru", "en"}:
                lemmas, positions = preprocess_with_positions(text, language)
            key = "originals/" + hashlib.sha256(name.encode()).hexdigest() + path.suffix.lower()
            logging.info("Загрузка оригинала в S3 — %s", path)
            s3.put(key, data)
            logging.info("Сохранение метаданных и индекса в PostgreSQL — %s", path)
            repo.save_indexed_document(
                dict(title=path.stem, file_path=name, source_language=language, file_hash=digest, source_s3_key=key),
                lemmas, positions,
            )
            processed += 1
            logging.info("Обработан файл — %s — токенов %s, уникальных терминов %s", path, len(lemmas), len(positions))
        except Exception:
            errors += 1
            logging.exception("Ошибка обработки файла %s", path)
            changed.set()
    for name, row in known.items():
        if name not in present:
            logging.info("Удаление отсутствующего файла из каталога — %s", name)
            s3.delete(row.source_s3_key)
            repo.delete(row.id)
            removed += 1
    logging.info(
        "Сверка завершена — обработано %s, без изменений %s, отложено %s, ошибок %s, удалено %s",
        processed, skipped, deferred, errors, removed,
    )

class Handler(FileSystemEventHandler):
    def on_any_event(self, event):
        if event.event_type in {"created", "modified", "deleted", "moved"}:
            changed.set()

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout, force=True)
    logging.info("Запуск индексатора")
    logging.info("Папка наблюдения %s", INPUT)
    INPUT.mkdir(parents=True, exist_ok=True)
    logging.info("Подключение к PostgreSQL и подготовка таблиц")
    repo.initialize()
    logging.info("PostgreSQL готов. Подключение к S3 и подготовка bucket")
    s3.initialize()
    logging.info("S3 готов")
    observer = Observer()
    observer.schedule(Handler(), str(INPUT), recursive=True)
    observer.start()
    logging.info("Наблюдение за вложенными папками включено")
    changed.set()
    try:
        while True:
            if not changed.is_set():
                logging.info("Ожидание изменений файлов. Для остановки нажмите Ctrl+C")
            changed.wait()
            changed.clear()
            time.sleep(1)
            try:
                reconcile()
            except Exception:
                logging.exception("Ошибка синхронизации каталога")
                changed.set()
    except KeyboardInterrupt:
        logging.info("Остановка индексатора")
    finally:
        observer.stop()
        observer.join()

if __name__ == "__main__":
    main()
