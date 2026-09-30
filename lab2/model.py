import os
import re
import json
import math
import pickle
from collections import Counter
import PyPDF2
import time
from sklearn.neural_network import MLPClassifier
from sklearn.feature_extraction.text import CountVectorizer


class LanguageModel:
    def __init__(self, model_dir="trained_model", train_dir=None):
        self.model_dir = model_dir
        self.train_dir = train_dir
        self.frequent_profiles = {}
        self.short_word_profiles = {}
        self.nn_model = None
        self.nn_vectorizer = None
        self.languages = []

        if not self._load_model():
            print("Обученная модель не найдена. Используются заглушки.")
            self._use_stub_profiles()

    # ============================================================
    #  ЗАГРУЗКА МОДЕЛИ
    # ============================================================
    def _load_model(self):
        if not os.path.isdir(self.model_dir):
            return False
        try:
            freq_file = os.path.join(self.model_dir, "frequent_profiles.json")
            if os.path.exists(freq_file):
                with open(freq_file, "r", encoding="utf-8") as f:
                    self.frequent_profiles = json.load(f)
                self.languages = list(self.frequent_profiles.keys())

            short_file = os.path.join(self.model_dir, "short_word_profiles.json")
            if os.path.exists(short_file):
                with open(short_file, "r", encoding="utf-8") as f:
                    self.short_word_profiles = json.load(f)

            nn_file = os.path.join(self.model_dir, "neural_network.pkl")
            vec_file = os.path.join(self.model_dir, "vectorizer.pkl")
            if os.path.exists(nn_file) and os.path.exists(vec_file):
                with open(nn_file, "rb") as f:
                    self.nn_model = pickle.load(f)
                with open(vec_file, "rb") as f:
                    self.nn_vectorizer = pickle.load(f)
            else:
                return False
            return True
        except Exception as e:
            print(f"Ошибка загрузки модели: {e}")
            return False

    def _use_stub_profiles(self):
        self.languages = ["spanish", "english"]
        self.frequent_profiles = {
            "spanish": {
                "de": 150, "la": 140, "que": 130, "el": 120, "en": 110,
                "y": 100, "a": 95, "los": 90, "del": 85, "se": 80,
                "las": 75, "por": 70, "un": 65, "para": 60, "con": 55,
                "no": 50, "una": 48, "su": 45, "al": 42, "lo": 40,
            },
            "english": {
                "the": 200, "be": 180, "to": 170, "of": 160, "and": 150,
                "a": 140, "in": 130, "that": 120, "have": 110, "it": 100,
                "for": 95, "not": 90, "on": 85, "with": 80, "he": 75,
                "as": 70, "you": 65, "do": 60, "at": 55, "this": 50,
            },
        }
        self.short_word_profiles = {
            "spanish": {
                "de": 0.080, "la": 0.070, "el": 0.050, "en": 0.040,
                "y": 0.035, "a": 0.030, "los": 0.025, "del": 0.020,
                "un": 0.018, "es": 0.015, "que": 0.014, "por": 0.012,
                "con": 0.011, "una": 0.010, "su": 0.009, "al": 0.008,
                "lo": 0.007, "mas": 0.006, "pero": 0.005, "sus": 0.004,
            },
            "english": {
                "the": 0.090, "and": 0.060, "for": 0.045, "are": 0.035,
                "but": 0.030, "not": 0.025, "you": 0.022, "all": 0.020,
                "can": 0.018, "had": 0.016, "her": 0.014, "was": 0.012,
                "one": 0.011, "our": 0.010, "out": 0.009, "day": 0.008,
                "get": 0.007, "has": 0.006, "him": 0.005, "his": 0.004,
            },
        }
        X_train = [
                      "de la que el en y a los del se las por un para con no una su al lo",
                      "el rápido zorro marrón salta sobre el perro perezoso en el bosque",
                      "la casa es grande y bonita con un jardín muy hermoso en españa",
                      "buenos días cómo estás hoy espero que tengas un buen día amigo",
                  ] * 50 + [
                      "the be to of and a in that have i it for not on with he as you do",
                      "the quick brown fox jumps over the lazy dog in the forest today",
                      "the house is big and beautiful with a very nice garden in england",
                      "good morning how are you today i hope you have a good day friend",
                  ] * 50
        y_train = ["spanish"] * 200 + ["english"] * 200
        self.nn_vectorizer = CountVectorizer(
            analyzer="char", ngram_range=(2, 4), max_features=1000
        )
        X_vec = self.nn_vectorizer.fit_transform(X_train)
        self.nn_model = MLPClassifier(
            hidden_layer_sizes=(100, 50),
            max_iter=500,
            random_state=42,
        )
        self.nn_model.fit(X_vec, y_train)

    # ============================================================
    #  ИЗВЛЕЧЕНИЕ ТЕКСТА
    # ============================================================
    def extract_text_from_pdf(self, pdf_path):
        text = ""
        try:
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            print(f"Ошибка чтения PDF {pdf_path}: {e}")
        return text

    # ============================================================
    #  ЕДИНЫЙ МЕТОД АНАЛИЗА ТЕКСТА (заменяет все detect_* и prepare_*)
    # ============================================================
    def analyze_text(self, text):
        t0 = time.perf_counter()

        if not text.strip():
            return {
                'classification': {
                    'frequent': 'Unknown', 'short': 'Unknown',
                    'nn': 'Unknown', 'final': 'Unknown'
                },
                'db_data': {
                    'freq_words': {'spanish': [], 'english': []},
                    'short_words': {'spanish': [], 'english': []},
                    'ngrams': []
                }
            }

        # === ОДИН РАЗ парсим текст ===
        words = re.findall(r"\b\w+\b", text.lower())
        doc_counts = Counter(words)
        short_words = [w for w in words if len(w) <= 5]
        short_counts = Counter(short_words)

        # === МЕТОД 1: ЧАСТОТНЫХ СЛОВ ===
        t1 = time.perf_counter()
        freq_scores = {}
        freq_db_data = {}
        for lang, profile in self.frequent_profiles.items():
            score = 0.0
            for word, count_in_doc in doc_counts.items():
                if word in profile:
                    score += profile[word] * count_in_doc
            freq_scores[lang] = score
            lang_key = lang.lower()
            freq_db_data[lang_key] = [
                {'word': w, 'train_freq': c, 'doc_freq': doc_counts.get(w, 0)}
                for w, c in profile.items()
            ]
        res_freq = max(freq_scores, key=freq_scores.get) if max(freq_scores.values()) > 0 else 'Unknown'
        t2 = time.perf_counter()
        print(f"Метод частотных слов: {t2 - t1:.4f} сек → {res_freq}")

        # === МЕТОД 2: КОРОТКИХ СЛОВ ===
        min_prob = 1e-10
        short_scores = {}
        short_db_data = {}
        for lang, profile in self.short_word_profiles.items():
            log_sum = 0.0
            for word in short_words:
                prob = profile.get(word, min_prob)
                log_sum += math.log(prob)
            short_scores[lang] = log_sum
            lang_key = lang.lower()
            short_db_data[lang_key] = []
            for word in sorted(set(short_words)):
                prob_train = profile.get(word, 0)
                prob_assigned = prob_train if prob_train > 0 else min_prob
                short_db_data[lang_key].append({
                    'word': word,
                    'train_prob': prob_train,
                    'assigned_prob': prob_assigned,
                    'doc_freq': short_counts.get(word, 0)
                })
        res_short = max(short_scores, key=short_scores.get) if short_scores else 'Unknown'
        t3 = time.perf_counter()
        print(f"Метод коротких слов: {t3 - t2:.4f} сек → {res_short}")

        # === МЕТОД 3: НЕЙРОСЕТЕВОЙ ===
        res_nn = 'Unknown'
        ngram_db_data = []
        if self.nn_model is not None and self.nn_vectorizer is not None:
            try:
                X_vec = self.nn_vectorizer.transform([text])
                res_nn = self.nn_model.predict(X_vec)[0]
                ngram_vectorizer = CountVectorizer(
                    analyzer='char', ngram_range=(2, 4), max_features=100
                )
                ngrams_matrix = ngram_vectorizer.fit_transform([text])
                ngram_features = ngram_vectorizer.get_feature_names_out()
                ngram_counts = ngrams_matrix.toarray()[0]
                ngram_db_data = sorted([
                    {'ngram': f, 'doc_freq': int(c)}
                    for f, c in zip(ngram_features, ngram_counts)
                ], key=lambda x: x['doc_freq'], reverse=True)
            except Exception as e:
                print(f" Ошибка нейросети: {e}")
        t4 = time.perf_counter()
        print(f" Нейросетевой метод: {t4 - t3:.4f} сек → {res_nn}")

        # === ГОЛОСОВАНИЕ ===
        votes = [res_freq, res_short, res_nn]
        final = max(set(votes), key=votes.count)

        t_end = time.perf_counter()
        print(f" Итого анализ текста: {t_end - t0:.4f} сек | Итоговый язык: {final}")

        return {
            'classification': {
                'frequent': res_freq,
                'short': res_short,
                'nn': res_nn,
                'final': final
            },
            'db_data': {
                'freq_words': freq_db_data,
                'short_words': short_db_data,
                'ngrams': ngram_db_data
            }
        }

    # ============================================================
    #  АНАЛИЗ ДОКУМЕНТА (обновлён — использует analyze_text)
    # ============================================================
    def analyze_document(self, pdf_path):
        """Анализирует PDF и возвращает только результаты классификации"""
        text = self.extract_text_from_pdf(pdf_path)
        result = self.analyze_text(text)
        return result['classification']

    # ============================================================
    #  МЕТОДЫ ДЛЯ CONTROLLER (получение данных для БД)
    # ============================================================
    def get_all_db_data(self, text):
        """Возвращает все данные для сохранения в БД (один вызов — все данные)"""
        result = self.analyze_text(text)
        return result['db_data']