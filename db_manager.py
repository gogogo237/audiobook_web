# bilingual_app/db_manager.py
import sqlite3
import os
import datetime # Import the datetime module
import logging # Added for logging

DATABASE_NAME = 'bilingual_data.db'
# Ensure the instance folder exists for the database
INSTANCE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
if not os.path.exists(INSTANCE_FOLDER):
    os.makedirs(INSTANCE_FOLDER)
DATABASE_PATH = os.path.join(INSTANCE_FOLDER, DATABASE_NAME)

# --- SQLite type converters ---
# For reading DATETIME/TIMESTAMP from SQLite
def convert_timestamp(val_bytes):
    """Converts a byte string from SQLite (expected format YYYY-MM-DD HH:MM:SS) to a datetime object."""
    if not val_bytes: # Handles None and empty byte strings
        return None
    try:
        return datetime.datetime.fromisoformat(val_bytes.decode('utf-8'))
    except ValueError:
        return None

# For writing Python datetime objects to SQLite (not strictly needed for current code, but good practice)
def adapt_datetime(dt_obj):
    """Adapts a Python datetime object to a string suitable for SQLite."""
    return dt_obj.isoformat(" ")

sqlite3.register_converter("DATETIME", convert_timestamp)
sqlite3.register_converter("TIMESTAMP", convert_timestamp) 
sqlite3.register_adapter(datetime.datetime, adapt_datetime)


def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row 
    return conn

def init_db(app=None):
    """Initializes the database schema."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            processed_srt_path TEXT NULLABLE,
            converted_mp3_path TEXT NULLABLE 
        )
    ''')
    # Added converted_mp3_path column to articles table
    # If updating an existing schema, you might need an ALTER TABLE statement:
    # try:
    #     cursor.execute("ALTER TABLE articles ADD COLUMN converted_mp3_path TEXT NULLABLE")
    # except sqlite3.OperationalError as e:
    #     if "duplicate column name" in str(e):
    #         if app: app.logger.info("Column 'converted_mp3_path' already exists in 'articles' table.")
    #     else:
    #         raise
            
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            paragraph_index INTEGER NOT NULL,
            sentence_index_in_paragraph INTEGER NOT NULL,
            english_text TEXT NOT NULL,
            chinese_text TEXT NOT NULL,
            start_time_ms INTEGER NULLABLE,
            end_time_ms INTEGER NULLABLE,
            FOREIGN KEY (article_id) REFERENCES articles (id)
        )
    ''')
    conn.commit()
    conn.close()
    if app:
        app.logger.info("Database initialized (or schema checked).")

def add_article(filename):
    """Adds a new article (filename) and returns its ID. Clears old sentences and SRT path if exists."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO articles (filename) VALUES (?)", (filename,))
        article_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError: # Filename already exists
        cursor.execute("SELECT id FROM articles WHERE filename = ?", (filename,))
        article_id = cursor.fetchone()['id']
        # Clear old sentences, SRT path, and converted_mp3_path for this article if re-uploading
        cursor.execute("DELETE FROM sentences WHERE article_id = ?", (article_id,))
        cursor.execute("UPDATE articles SET processed_srt_path = NULL, converted_mp3_path = NULL WHERE id = ?", (article_id,))
        conn.commit()
    finally:
        conn.close()
    return article_id


def add_sentence(article_id, paragraph_index, sentence_index, english, chinese):
    """Adds a sentence pair to the database."""
    # This function is not batch-optimized, prefer add_sentences_batch
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sentences (article_id, paragraph_index, sentence_index_in_paragraph, english_text, chinese_text)
        VALUES (?, ?, ?, ?, ?)
    ''', (article_id, paragraph_index, sentence_index, english, chinese))
    conn.commit()
    conn.close()

def get_all_articles():
    """Retrieves all articles from the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Ensure all relevant columns are selected, including converted_mp3_path if needed on index
    cursor.execute("SELECT id, filename, upload_timestamp, processed_srt_path, converted_mp3_path FROM articles ORDER BY upload_timestamp DESC")
    articles = cursor.fetchall()
    conn.close()
    return articles

def get_article_filename(article_id):
    """Retrieves the filename for a given article ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM articles WHERE id = ?", (article_id,))
    article_row = cursor.fetchone()
    conn.close()
    return article_row['filename'] if article_row else None

def get_article_by_id(article_id):
    """Retrieves a single article by its ID, including all relevant paths."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, filename, upload_timestamp, processed_srt_path, converted_mp3_path 
        FROM articles 
        WHERE id = ?
    """, (article_id,))
    article = cursor.fetchone()
    conn.close()
    return article

def get_sentences_for_article(article_id):
    """Retrieves all sentences for a given article, ordered correctly, including timestamps."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT paragraph_index, sentence_index_in_paragraph, 
               english_text, chinese_text,
               start_time_ms, end_time_ms
        FROM sentences
        WHERE article_id = ?
        ORDER BY paragraph_index, sentence_index_in_paragraph
    ''', (article_id,))
    sentences = cursor.fetchall()
    conn.close()
    return sentences

def get_english_sentences_for_article(article_id):
    """Retrieves only English sentences for a given article, ordered correctly."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT english_text
        FROM sentences
        WHERE article_id = ?
        ORDER BY paragraph_index, sentence_index_in_paragraph
    ''', (article_id,))
    # Returns a list of strings
    return [row['english_text'] for row in cursor.fetchall()]


def add_sentences_batch(article_id, sentences_data):
    """Adds multiple sentence pairs to the database in a single transaction."""
    if not sentences_data:
        return 0

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        data_to_insert = [
            (article_id, s_data[0], s_data[1], s_data[2], s_data[3])
            for s_data in sentences_data # (p_idx, s_idx, en, zh)
        ]

        cursor.executemany('''
            INSERT INTO sentences (article_id, paragraph_index, sentence_index_in_paragraph, english_text, chinese_text)
            VALUES (?, ?, ?, ?, ?)
        ''', data_to_insert)
        conn.commit()
        return len(data_to_insert)
    except sqlite3.Error as e:
        conn.rollback() 
        raise e
    finally:
        conn.close()

def update_sentence_timestamps(article_id, timestamps_data, app_logger=None):
    """
    Updates sentence timestamps for a given article.
    timestamps_data: A list of (start_ms, end_ms) tuples, in the order of sentences.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id FROM sentences
            WHERE article_id = ?
            ORDER BY paragraph_index, sentence_index_in_paragraph
        """, (article_id,))
        sentence_ids_rows = cursor.fetchall()

        if app_logger:
            app_logger.info(f"DB: Attempting to update timestamps for article {article_id}. "
                            f"DB sentences found: {len(sentence_ids_rows)}. "
                            f"Timestamps provided from SRT: {len(timestamps_data)}.")
            if sentence_ids_rows and app_logger.level <= logging.DEBUG: # Only log if DEBUG or lower
                 app_logger.debug(f"DB: First 3 sentence IDs from DB: {[row['id'] for row in sentence_ids_rows[:3]]}")
            if timestamps_data and app_logger.level <= logging.DEBUG:
                 app_logger.debug(f"DB: First 3 timestamps_data from SRT: {timestamps_data[:3]}")

        if len(sentence_ids_rows) != len(timestamps_data):
            if app_logger:
                app_logger.warning(
                    f"DB: Timestamp data count ({len(timestamps_data)}) does not match "
                    f"sentence count ({len(sentence_ids_rows)}) for article {article_id}. "
                    f"Will update based on the minimum of the two ({min(len(sentence_ids_rows), len(timestamps_data))})."
                )
            
        min_len = min(len(sentence_ids_rows), len(timestamps_data))
        if min_len == 0:
            if app_logger:
                app_logger.warning(f"DB: No timestamps or sentences to update for article {article_id} (min_len is 0). Nothing to do.")
            return 0 # Return early, ensure connection is closed in finally

        updates = []
        for i in range(min_len):
            sentence_id = sentence_ids_rows[i]['id']
            start_ms, end_ms = timestamps_data[i]
            
            current_start_ms = int(start_ms) if start_ms is not None else None
            current_end_ms = int(end_ms) if end_ms is not None else None

            if app_logger and (current_start_ms is None or current_end_ms is None):
                app_logger.warning(f"DB: For article {article_id}, sentence_id {sentence_id} (index {i}), "
                                   f"received potentially null timestamp: original start_ms='{start_ms}', end_ms='{end_ms}'. "
                                   f"Will be stored as {current_start_ms}, {current_end_ms}.")

            updates.append((current_start_ms, current_end_ms, sentence_id))
        
        if not updates:
            if app_logger: app_logger.warning(f"DB: No valid update data prepared for article {article_id} after processing {min_len} items.")
            return 0

        if app_logger:
            app_logger.info(f"DB: Preparing to execute {len(updates)} timestamp updates for article {article_id}.")
            if app_logger.level <= logging.DEBUG:
                 app_logger.debug(f"DB: Sample update data (first 3): {updates[:3]}")

        cursor.executemany("""
            UPDATE sentences
            SET start_time_ms = ?, end_time_ms = ?
            WHERE id = ?
        """, updates)
        conn.commit()
        
        committed_row_count = cursor.rowcount 
        
        if app_logger:
             app_logger.info(f"DB: Successfully committed {len(updates)} timestamp updates for article {article_id}. (cursor.rowcount: {committed_row_count})")
        return len(updates) 
    except sqlite3.Error as e:
        if app_logger:
            app_logger.error(f"DB: Database error updating timestamps for article {article_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        raise e 
    finally:
        if conn: conn.close()

def update_article_srt_path(article_id, srt_path):
    """Updates the processed_srt_path for an article."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE articles SET processed_srt_path = ? WHERE id = ?", (srt_path, article_id))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        # Optionally, log this error using app_logger if passed or a local logger
        raise e
    finally:
        conn.close()

def update_article_converted_mp3_path(article_id, mp3_path, app_logger=None):
    """Updates the converted_mp3_path for an article."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE articles SET converted_mp3_path = ? WHERE id = ?", (mp3_path, article_id))
        conn.commit()
        if app_logger:
            app_logger.info(f"DB: Updated converted_mp3_path for article {article_id} to '{mp3_path}'.")
    except sqlite3.Error as e:
        if app_logger:
            app_logger.error(f"DB: Failed to update converted_mp3_path for article {article_id}: {e}", exc_info=True)
        conn.rollback()
        raise e
    finally:
        conn.close()


if __name__ == '__main__':
    print(f"Initializing database at: {DATABASE_PATH}")
    # Create a dummy app context for init_db logging if needed
    class DummyApp:
        def __init__(self):
            self.logger = logging.getLogger('db_manager_standalone')
            self.logger.setLevel(logging.INFO)
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.instance_path = INSTANCE_FOLDER # For init_db if it needs app.instance_path
    
    init_db(app=DummyApp()) 
    print("Database schema created/checked.")