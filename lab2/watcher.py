import os
import time
import threading
import database as db
from model import LanguageModel


class FolderWatcher:
    def __init__(self, watch_folder, model):
        self.watch_folder = watch_folder
        self.model = model
        self._running = False
        self.known_files = set()
        self._load_known_files()

    def _load_known_files(self):
        docs = db.get_all_documents()
        self.known_files = {doc[0] for doc in docs}

    def start(self):
        if self._running:
            return
        self._running = True
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.thread.start()

    def _watch_loop(self):
        while self._running:
            if os.path.exists(self.watch_folder):
                current_files = set()
                for filename in os.listdir(self.watch_folder):
                    if filename.endswith(".pdf"):
                        current_files.add(filename)
                        filepath = os.path.join(self.watch_folder, filename)

                        existing_docs = db.get_all_documents()
                        if any(doc[0] == filename for doc in existing_docs):
                            continue

                        db.add_or_update_document(
                            filename, filepath, source='folder', status='processing'
                        )
                        try:
                            # ОДИН вызов — всё сразу
                            text = self.model.extract_text_from_pdf(filepath)
                            result = self.model.analyze_text(text)

                            db.add_or_update_document(
                                filename, filepath, source='folder',
                                results=result['classification'], status='processed'
                            )

                            db_data = result['db_data']
                            for lang, data in db_data['freq_words'].items():
                                db.save_freq_words(filename, lang, data)
                            for lang, data in db_data['short_words'].items():
                                db.save_short_words(filename, lang, data)
                            db.save_ngrams(filename, db_data['ngrams'])

                            self.known_files.add(filename)
                            print(f"Watcher: обработан {filename}")

                        except Exception as e:
                            print(f"Ошибка обработки {filename}: {e}")
                            db.add_or_update_document(
                                filename, filepath, source='folder', status='error'
                            )

                # Очистка БД при удалении файла
                removed_files = self.known_files - current_files
                for removed_file in removed_files:
                    print(f"Watcher: файл удалён — {removed_file}")
                    db.delete_document(removed_file)
                    self.known_files.discard(removed_file)

            time.sleep(3)

    def stop(self):
        self._running = False