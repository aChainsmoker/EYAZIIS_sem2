import os
import re
import json
import pickle
from collections import Counter
from sklearn.neural_network import MLPClassifier
from sklearn.feature_extraction.text import CountVectorizer
import numpy as np


class LanguageTrainer:
    def __init__(self, train_dir="train_data"):
        self.train_dir = train_dir
        self.frequent_profiles = {}
        self.short_word_profiles = {}
        self.nn_model = None
        self.nn_vectorizer = None
        self.languages = []

    def read_corpus(self, folder_path):
        """Читает все .txt и .pdf файлы из папки"""
        full_text = ""
        files_count = 0

        if not os.path.isdir(folder_path):
            print(f"  Папка не найдена: {folder_path}")
            return full_text

        for fname in sorted(os.listdir(folder_path)):
            fpath = os.path.join(folder_path, fname)
            if not os.path.isfile(fpath):
                continue

            try:
                if fname.lower().endswith('.txt'):
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        text = f.read()
                        full_text += text + "\n"
                        files_count += 1
                        print(f"   TXT: {fname} ({len(text)} символов)")

                elif fname.lower().endswith('.pdf'):
                    import PyPDF2
                    with open(fpath, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        text = ""
                        for page in reader.pages:
                            page_text = page.extract_text()
                            if page_text:
                                text += page_text + "\n"

                        if text.strip():
                            full_text += text + "\n"
                            files_count += 1
                            print(f"  PDF: {fname} ({len(text)} символов)")
                        else:
                            print(f"  PDF без текста (скан?): {fname}")

            except Exception as e:
                print(f"  Ошибка чтения {fname}: {e}")

        print(f"  Всего файлов прочитано: {files_count}")
        print(f"  Общий размер текста: {len(full_text)} символов ({len(full_text)/1024:.1f} Кб)")
        return full_text

    def build_frequent_words_profile(self, text, top_n=300, min_word_len=2):
        """Строит профиль частотных слов (ТОП-N слов длиной >= min_word_len)"""
        # Регулярка для слов (включая испанские буквы с ударениями)
        words = re.findall(r'\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]{2,}\b', text.lower())
        word_counts = Counter(words)
        return dict(word_counts.most_common(top_n))

    def build_short_words_profile(self, text, max_length=5, min_freq=3, min_word_len=2):
        """Строит профиль коротких слов"""
        words = re.findall(r'\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]{2,}\b', text.lower())
        short_words = [w for w in words if len(w) <= max_length]

        counts = Counter(short_words)
        filtered = {w: c for w, c in counts.items() if c > min_freq}

        total = sum(filtered.values())
        if total > 0:
            return {w: c / total for w, c in filtered.items()}
        return {}

    def train_neural_network(self, all_texts, chunk_size=200, overlap=100):
        """Обучает нейросеть на фрагментах текста"""
        X_train = []
        y_train = []

        print("\nПодготовка данных для нейросети:")
        for lang, text in all_texts.items():
            clean = re.sub(r'\s+', ' ', text)
            chunks = []
            for i in range(0, len(clean) - chunk_size, overlap):
                chunk = clean[i:i + chunk_size]
                # Пропускаем фрагменты с малым количеством букв
                letters = re.findall(r'[a-zA-Záéíóúüñ]', chunk)
                if len(letters) > 50:
                    chunks.append(chunk)

            X_train.extend(chunks)
            y_train.extend([lang] * len(chunks))
            print(f"  {lang}: {len(chunks)} фрагментов")

        print(f"\nВсего обучающих примеров: {len(X_train)}")

        if len(X_train) < 20:
            print("Слишком мало данных для обучения нейросети!")
            return None, None

        print("Векторизация текста (character N-граммы)...")
        self.nn_vectorizer = CountVectorizer(
            analyzer='char',
            ngram_range=(2, 4),
            max_features=5000,
            min_df=2
        )

        X_vec = self.nn_vectorizer.fit_transform(X_train)
        print(f"Размерность векторов: {X_vec.shape[1]} признаков")

        print("Обучение нейросети (MLP)...")
        # ИСПРАВЛЕНО: validation_split validation_fraction
        self.nn_model = MLPClassifier(
            hidden_layer_sizes=(200, 100, 50),
            activation='relu',
            solver='adam',
            alpha=0.001,
            batch_size=32,
            learning_rate='adaptive',
            max_iter=500,
            random_state=42,
            verbose=False,
            early_stopping=True,
            validation_fraction=0.1  # было validation_split
        )

        self.nn_model.fit(X_vec, y_train)

        train_accuracy = self.nn_model.score(X_vec, y_train)
        print(f"Точность на обучающей выборке: {train_accuracy:.2%}")

        return self.nn_model, self.nn_vectorizer

    def train(self):
        """Основной метод обучения"""
        print("=" * 60)
        print("ОБУЧЕНИЕ МОДЕЛИ РАСПОЗНАВАНИЯ ЯЗЫКА")
        print("=" * 60)

        if not os.path.exists(self.train_dir):
            print(f"Папка {self.train_dir} не найдена!")
            print("Создайте структуру:")
            print(f"  {self.train_dir}/")
            print(f"    spanish/")
            print(f"    english/")
            return False

        all_texts = {}

        print("\n1. ЧТЕНИЕ ТРЕНИРОВОЧНЫХ ТЕКСТОВ")
        print("-" * 60)
        for lang_folder in sorted(os.listdir(self.train_dir)):
            lang_path = os.path.join(self.train_dir, lang_folder)
            if os.path.isdir(lang_path):
                print(f"\nЯзык: {lang_folder.upper()}")
                text = self.read_corpus(lang_path)
                if text.strip():
                    all_texts[lang_folder] = text
                    self.languages.append(lang_folder)
                else:
                    print(f"  Текст пустой! Проверьте файлы в {lang_path}")

        if not all_texts:
            print("Не найдено текстов для обучения!")
            return False

        print(f"\nЗагружено языков: {len(self.languages)} - {', '.join(self.languages)}")

        # Проверка баланса
        for lang, text in all_texts.items():
            size_kb = len(text) / 1024
            status = "" if 20 <= size_kb <= 120 else ""
            print(f"  {status} {lang}: {size_kb:.1f} Кб (норма 20-120 Кб)")

        # 2. Профили частотных слов
        print("\n2. ПОСТРОЕНИЕ ПРОФИЛЕЙ ЧАСТОТНЫХ СЛОВ")
        print("-" * 60)
        for lang, text in all_texts.items():
            print(f"\n{lang.upper()}:")
            profile = self.build_frequent_words_profile(text, top_n=300)
            self.frequent_profiles[lang] = profile
            print(f"  Создан профиль: {len(profile)} слов")
            print(f"  ТОП-5 частых слов:")
            for i, (word, freq) in enumerate(list(profile.items())[:5]):
                print(f"    {i+1}. {word} - {freq}")

        # 3. Профили коротких слов
        print("\n3. ПОСТРОЕНИЕ ПРОФИЛЕЙ КОРОТКИХ СЛОВ")
        print("-" * 60)
        for lang, text in all_texts.items():
            print(f"\n{lang.upper()}:")
            profile = self.build_short_words_profile(text, max_length=5, min_freq=3)
            self.short_word_profiles[lang] = profile
            print(f"  Создан профиль: {len(profile)} слов")
            print(f"  ТОП-5 коротких слов:")
            for i, (word, prob) in enumerate(sorted(profile.items(), key=lambda x: x[1], reverse=True)[:5]):
                print(f"    {i+1}. {word} - {prob:.6f}")

        # 4. Обучение нейросети
        print("\n4. ОБУЧЕНИЕ НЕЙРОСЕТИ")
        print("-" * 60)
        self.train_neural_network(all_texts, chunk_size=200, overlap=100)

        # 5. Сохранение
        print("\n5. СОХРАНЕНИЕ МОДЕЛИ")
        print("-" * 60)
        self.save_model()

        print("\n" + "=" * 60)
        print("ОБУЧЕНИЕ ЗАВЕРШЕНО УСПЕШНО!")
        print("=" * 60)

        return True

    def save_model(self):
        model_dir = "trained_model"
        os.makedirs(model_dir, exist_ok=True)

        freq_file = os.path.join(model_dir, "frequent_profiles.json")
        with open(freq_file, 'w', encoding='utf-8') as f:
            json.dump(self.frequent_profiles, f, ensure_ascii=False, indent=2)
        print(f"Профили частотных слов: {freq_file}")

        short_file = os.path.join(model_dir, "short_word_profiles.json")
        with open(short_file, 'w', encoding='utf-8') as f:
            json.dump(self.short_word_profiles, f, ensure_ascii=False, indent=2)
        print(f"Профили коротких слов: {short_file}")

        if self.nn_model is not None:
            nn_file = os.path.join(model_dir, "neural_network.pkl")
            with open(nn_file, 'wb') as f:
                pickle.dump(self.nn_model, f)
            print(f"Нейросеть: {nn_file}")

            vec_file = os.path.join(model_dir, "vectorizer.pkl")
            with open(vec_file, 'wb') as f:
                pickle.dump(self.nn_vectorizer, f)
            print(f"Векторизатор: {vec_file}")

        meta_file = os.path.join(model_dir, "metadata.json")
        metadata = {
            'languages': self.languages,
            'frequent_words_count': {lang: len(p) for lang, p in self.frequent_profiles.items()},
            'short_words_count': {lang: len(p) for lang, p in self.short_word_profiles.items()}
        }
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"Метаданные: {meta_file}")

        print(f"\nВсе файлы сохранены в: {model_dir}/")


if __name__ == "__main__":
    trainer = LanguageTrainer(train_dir="train_data")
    success = trainer.train()