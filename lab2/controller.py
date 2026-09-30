import os
import database as db
from model import LanguageModel


class AppController:
    def __init__(self, model):
        self.model = model

    def process_uploaded_file(self, uploaded_file, save_dir):
        save_path = os.path.join(save_dir, uploaded_file.name)
        if os.path.exists(save_path):
            base, ext = os.path.splitext(uploaded_file.name)
            save_path = os.path.join(save_dir, f"{base}_upload{ext}")

        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # ОДИН вызов — получаем и классификацию, и данные для БД
        text = self.model.extract_text_from_pdf(save_path)
        result = self.model.analyze_text(text)

        # Сохраняем результаты классификации
        db.add_or_update_document(
            uploaded_file.name, save_path, source='frontend',
            results=result['classification'], status='processed'
        )

        # Сохраняем данные для БД
        db_data = result['db_data']
        for lang, data in db_data['freq_words'].items():
            db.save_freq_words(uploaded_file.name, lang, data)
        for lang, data in db_data['short_words'].items():
            db.save_short_words(uploaded_file.name, lang, data)
        db.save_ngrams(uploaded_file.name, db_data['ngrams'])

        return result['classification']

    def get_all_documents(self):
        return db.get_all_documents()

    def get_freq_words(self, filename, lang):
        return db.get_freq_words(filename, lang)

    def get_short_words(self, filename, lang):
        return db.get_short_words(filename, lang)

    def get_ngrams(self, filename):
        return db.get_ngrams(filename)

    def delete_document(self, filename, save_dir):
        db.delete_document(filename)
        filepath = os.path.join(save_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)