# bilingual_app/db_manager.py
import sqlite3
import os
import datetime # Import the datetime module

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
        # SQLite stores DATETIME from CURRENT_TIMESTAMP as 'YYYY-MM-DD HH:MM:SS'
        # datetime.fromisoformat can parse this format if Python >= 3.7
        # If using Python < 3.7, use strptime:
        # return datetime.datetime.strptime(val_bytes.decode('utf-8'), '%Y-%m-%d %H:%M:%S')
        return datetime.datetime.fromisoformat(val_bytes.decode('utf-8'))
    except ValueError:
        # Handle cases where the timestamp string is malformed
        # You might want to log this error. For now, returning None.
        # import logging
        # logging.warning(f"Could not parse timestamp: {val_bytes.decode('utf-8')}")
        return None

# For writing Python datetime objects to SQLite (not strictly needed for current code, but good practice)
def adapt_datetime(dt_obj):
    """Adapts a Python datetime object to a string suitable for SQLite."""
    return dt_obj.isoformat(" ")

# Register the converters with SQLite
# PARSE_DECLTYPES will use the converter registered for "DATETIME" (matching the schema)
# PARSE_COLNAMES can also trigger conversion if column names suggest a type (e.g. "upload_timestamp" -> "TIMESTAMP")
sqlite3.register_converter("DATETIME", convert_timestamp)
sqlite3.register_converter("TIMESTAMP", convert_timestamp) # Covers cases where SQLite might identify it as TIMESTAMP
sqlite3.register_adapter(datetime.datetime, adapt_datetime)


def get_db_connection():
    """Establishes a connection to the SQLite database."""
    # Enable type detection and conversion
    conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row # Access columns by name
    return conn

def init_db(app=None):
    """Initializes the database schema."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            paragraph_index INTEGER NOT NULL,
            sentence_index_in_paragraph INTEGER NOT NULL,
            english_text TEXT NOT NULL,
            chinese_text TEXT NOT NULL,
            FOREIGN KEY (article_id) REFERENCES articles (id)
        )
    ''')
    conn.commit()
    conn.close()
    if app:
        app.logger.info("Database initialized.")

def add_article(filename):
    """Adds a new article (filename) and returns its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO articles (filename) VALUES (?)", (filename,))
        article_id = cursor.lastrowid
        conn.commit()
        return article_id
    except sqlite3.IntegrityError: # Filename already exists
        cursor.execute("SELECT id FROM articles WHERE filename = ?", (filename,))
        article_id = cursor.fetchone()['id']
        # Optionally, clear old sentences for this article if re-uploading
        cursor.execute("DELETE FROM sentences WHERE article_id = ?", (article_id,))
        conn.commit()
        return article_id # Return existing ID, content will be overwritten
    finally:
        conn.close()

def add_sentence(article_id, paragraph_index, sentence_index, english, chinese):
    """Adds a sentence pair to the database."""
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
    # The upload_timestamp should now be automatically converted to a datetime object
    cursor.execute("SELECT id, filename, upload_timestamp FROM articles ORDER BY upload_timestamp DESC")
    articles = cursor.fetchall()
    conn.close()
    return articles

def get_article_filename(article_id):
    """Retrieves the filename for a given article ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM articles WHERE id = ?", (article_id,))
    article = cursor.fetchone()
    conn.close()
    return article['filename'] if article else None

def get_sentences_for_article(article_id):
    """Retrieves all sentences for a given article, ordered correctly."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT paragraph_index, sentence_index_in_paragraph, english_text, chinese_text
        FROM sentences
        WHERE article_id = ?
        ORDER BY paragraph_index, sentence_index_in_paragraph
    ''', (article_id,))
    sentences = cursor.fetchall()
    conn.close()
    return sentences

def add_sentences_batch(article_id, sentences_data):
    """Adds multiple sentence pairs to the database in a single transaction."""
    if not sentences_data:
        return 0

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Prepare data for executemany
        # sentences_data should be a list of tuples:
        # [(paragraph_index, sentence_index, english, chinese), ...]
        data_to_insert = [
            (article_id, s_data[0], s_data[1], s_data[2], s_data[3])
            for s_data in sentences_data
        ]

        cursor.executemany('''
            INSERT INTO sentences (article_id, paragraph_index, sentence_index_in_paragraph, english_text, chinese_text)
            VALUES (?, ?, ?, ?, ?)
        ''', data_to_insert)
        conn.commit()
        return len(data_to_insert)
    except sqlite3.Error as e:
        conn.rollback() # Rollback in case of error
        # Re-raise the exception or handle it as appropriate
        # For example, log it and return 0 or an error indicator
        # For now, let's re-raise to see the error in Flask logs
        raise e
    finally:
        conn.close()

if __name__ == '__main__':
    # For testing purposes, run this script directly to initialize the DB
    print(f"Initializing database at: {DATABASE_PATH}")
    init_db() # This will use the connection with type detection configured
    print("Database schema created (if it didn't exist).")
    
    # Example of how the converter works:
    # conn = get_db_connection()
    # conn.execute("INSERT INTO articles (filename) VALUES ('test_manual_ts.txt')")
    # conn.commit()
    # articles_test = get_all_articles()
    # if articles_test:
    #     print(f"Test article timestamp type: {type(articles_test[0]['upload_timestamp'])}")
    #     print(f"Test article timestamp value: {articles_test[0]['upload_timestamp']}")
    # conn.close()