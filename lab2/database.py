import os
import mysql.connector
from mysql.connector import Error

# ================================================================
#  ПОЛУЧЕНИЕ КОНФИГУРАЦИИ ИЗ SECRETS ИЛИ ОКРУЖЕНИЯ
# ================================================================
try:
    import streamlit as st
    SECRETS = st.secrets
except Exception:
    SECRETS = {}

def get_db_config():
    return {
        'host': SECRETS.get('DB_HOST', os.environ.get('DB_HOST', 'localhost')),
        'user': SECRETS.get('DB_USER', os.environ.get('DB_USER', 'root')),
        'password': SECRETS.get('DB_PASSWORD', os.environ.get('DB_PASSWORD', '')),
        'database': SECRETS.get('DB_NAME', os.environ.get('DB_NAME', 'language_detection_db'))
    }

DB_CONFIG = get_db_config()

def get_connection(use_db=True):
    config = DB_CONFIG.copy()
    if not use_db:
        config.pop('database', None)
    return mysql.connector.connect(**config)

def init_db():
    try:
        conn = get_connection(use_db=False)
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.close()
        conn.close()

        conn = get_connection(use_db=True)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                filename VARCHAR(255) UNIQUE,
                filepath VARCHAR(500),
                source VARCHAR(50),
                res_frequent_words VARCHAR(50),
                res_short_words VARCHAR(50),
                res_nn VARCHAR(50),
                final_language VARCHAR(50),
                status VARCHAR(50) DEFAULT 'pending'
            )
        ''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS freq_words_spanish (
            id INT AUTO_INCREMENT PRIMARY KEY, document_filename VARCHAR(255),
            word VARCHAR(100), train_freq INT, doc_freq INT, INDEX (document_filename))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS freq_words_english (
            id INT AUTO_INCREMENT PRIMARY KEY, document_filename VARCHAR(255),
            word VARCHAR(100), train_freq INT, doc_freq INT, INDEX (document_filename))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS short_words_spanish (
            id INT AUTO_INCREMENT PRIMARY KEY, document_filename VARCHAR(255),
            word VARCHAR(100), train_prob DOUBLE, assigned_prob DOUBLE, doc_freq INT, INDEX (document_filename))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS short_words_english (
            id INT AUTO_INCREMENT PRIMARY KEY, document_filename VARCHAR(255),
            word VARCHAR(100), train_prob DOUBLE, assigned_prob DOUBLE, doc_freq INT, INDEX (document_filename))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS ngram_frequencies (
            id INT AUTO_INCREMENT PRIMARY KEY, document_filename VARCHAR(255),
            ngram VARCHAR(20), doc_freq INT, INDEX (document_filename))''')

        conn.commit()
        cursor.close()
        conn.close()
        print("База данных MySQL успешно инициализирована.")
    except Error as e:
        print(f"Ошибка инициализации БД MySQL: {e}")

def add_or_update_document(filename, filepath, source, results=None, status='pending'):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if results:
            sql = '''INSERT INTO documents (filename, filepath, source, res_frequent_words, res_short_words, res_nn, final_language, status)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                     ON DUPLICATE KEY UPDATE res_frequent_words=VALUES(res_frequent_words), res_short_words=VALUES(res_short_words), 
                     res_nn=VALUES(res_nn), final_language=VALUES(final_language), status=VALUES(status)'''
            cursor.execute(sql, (filename, filepath, source, results['frequent'], results['short'], results['nn'], results['final'], 'processed'))
        else:
            sql = 'INSERT IGNORE INTO documents (filename, filepath, source, status) VALUES (%s, %s, %s, %s)'
            cursor.execute(sql, (filename, filepath, source, status))
        conn.commit()
    except Error as e:
        print(f"Ошибка записи в БД: {e}")
    finally:
        cursor.close()
        conn.close()

def get_all_documents():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT filename, source, res_frequent_words, res_short_words, res_nn, final_language, status FROM documents")
        return cursor.fetchall()
    except Error as e:
        print(f"Ошибка чтения из БД: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def save_freq_words(filename, lang, freq_data):
    table = f"freq_words_{lang}"
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"DELETE FROM {table} WHERE document_filename = %s", (filename,))
        sql = f"INSERT INTO {table} (document_filename, word, train_freq, doc_freq) VALUES (%s, %s, %s, %s)"
        data = [(filename, item['word'], item['train_freq'], item['doc_freq']) for item in freq_data]
        cursor.executemany(sql, data)
        conn.commit()
    except Error as e:
        print(f"Ошибка сохранения частотных слов ({lang}): {e}")
    finally:
        cursor.close()
        conn.close()

def get_freq_words(filename, lang):
    table = f"freq_words_{lang}"
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT word, train_freq, doc_freq FROM {table} WHERE document_filename = %s", (filename,))
        return cursor.fetchall()
    except Error as e:
        print(f"Ошибка чтения частотных слов ({lang}): {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def save_short_words(filename, lang, short_data):
    table = f"short_words_{lang}"
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"DELETE FROM {table} WHERE document_filename = %s", (filename,))
        sql = f"INSERT INTO {table} (document_filename, word, train_prob, assigned_prob, doc_freq) VALUES (%s, %s, %s, %s, %s)"
        data = [(filename, item['word'], item['train_prob'], item['assigned_prob'], item['doc_freq']) for item in short_data]
        cursor.executemany(sql, data)
        conn.commit()
    except Error as e:
        print(f"Ошибка сохранения коротких слов ({lang}): {e}")
    finally:
        cursor.close()
        conn.close()

def get_short_words(filename, lang):
    table = f"short_words_{lang}"
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT word, train_prob, assigned_prob, doc_freq FROM {table} WHERE document_filename = %s", (filename,))
        return cursor.fetchall()
    except Error as e:
        print(f"Ошибка чтения коротких слов ({lang}): {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def save_ngrams(filename, ngram_data):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ngram_frequencies WHERE document_filename = %s", (filename,))
        sql = "INSERT INTO ngram_frequencies (document_filename, ngram, doc_freq) VALUES (%s, %s, %s)"
        data = [(filename, item['ngram'], item['doc_freq']) for item in ngram_data]
        cursor.executemany(sql, data)
        conn.commit()
    except Error as e:
        print(f"Ошибка сохранения N-грамм: {e}")
    finally:
        cursor.close()
        conn.close()

def get_ngrams(filename):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT ngram, doc_freq FROM ngram_frequencies WHERE document_filename = %s", (filename,))
        return cursor.fetchall()
    except Error as e:
        print(f"Ошибка чтения N-грамм: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def delete_document(filename):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM documents WHERE filename = %s", (filename,))
        cursor.execute("DELETE FROM freq_words_spanish WHERE document_filename = %s", (filename,))
        cursor.execute("DELETE FROM freq_words_english WHERE document_filename = %s", (filename,))
        cursor.execute("DELETE FROM short_words_spanish WHERE document_filename = %s", (filename,))
        cursor.execute("DELETE FROM short_words_english WHERE document_filename = %s", (filename,))
        cursor.execute("DELETE FROM ngram_frequencies WHERE document_filename = %s", (filename,))
        conn.commit()
    except Error as e:
        print(f"Ошибка удаления из БД: {e}")
    finally:
        cursor.close()
        conn.close()
def get_word_frequencies(filename):
    """
    Собирает частоты слов из таблиц freq_words_spanish и freq_words_english
    в единый формат: (language, word, train_freq, doc_freq).
    Используется в generate_printable_html для HTML-отчёта.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        rows = []
        for lang in ('spanish', 'english'):
            table = f"freq_words_{lang}"
            lang_display = lang.capitalize()  # Spanish / English
            cursor.execute(
                f"SELECT word, train_freq, doc_freq FROM {table} "
                f"WHERE document_filename = %s",
                (filename,)
            )
            for word, train_freq, doc_freq in cursor.fetchall():
                rows.append((lang_display, word, train_freq, doc_freq))
        return rows
    except Error as e:
        print(f"Ошибка чтения частот (сводно): {e}")
        return []
    finally:
        cursor.close()
        conn.close()