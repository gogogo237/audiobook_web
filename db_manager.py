import sqlite3
import os
import datetime
import logging # Standard logging

# --- Configuration (could be moved to a central config if preferred) ---
DATABASE_NAME = 'bilingual_data.db'
# Ensure the instance folder exists for the database
INSTANCE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
if not os.path.exists(INSTANCE_FOLDER):
    os.makedirs(INSTANCE_FOLDER)
DATABASE_PATH = os.path.join(INSTANCE_FOLDER, DATABASE_NAME)

AUDIO_PART_CHECKSUM_DELIMITER = ";" # Define delimiter for concatenated checksums

# --- Default Logger if app_logger is not provided ---
# This allows functions to be called outside Flask app context for scripts/testing
default_logger = logging.getLogger('db_manager_default')
if not default_logger.hasHandlers(): # Avoid adding multiple handlers if re-imported
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    default_logger.addHandler(handler)
    default_logger.setLevel(logging.INFO)


# --- SQLite type converters ---
def convert_datetime_from_db(val_bytes):
    """Converts ISO formatted string from DB to datetime object."""
    if not val_bytes:
        return None
    try:
        # Try to parse with or without microseconds, and with space or 'T' separator
        dt_str = val_bytes.decode('utf-8')
        if '.' in dt_str:
            return datetime.datetime.fromisoformat(dt_str.replace(" ", "T"))
        else: # If no microseconds, fromisoformat might fail, try strptime
            try:
                return datetime.datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return datetime.datetime.fromisoformat(dt_str.replace(" ", "T")) # Retry with T just in case
    except ValueError as e:
        # Fallback for very old formats or log error
        default_logger.warning(f"DB_CONVERTER: Could not convert bytes to datetime: {val_bytes}. Error: {e}")
        return None

def adapt_datetime_to_db(dt_obj):
    """Adapts datetime object to ISO string format for DB storage."""
    if dt_obj is None:
        return None
    return dt_obj.isoformat(" ") # Use space as T separator

sqlite3.register_converter("DATETIME", convert_datetime_from_db)
sqlite3.register_converter("TIMESTAMP", convert_datetime_from_db)
sqlite3.register_adapter(datetime.datetime, adapt_datetime_to_db)


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON") # Ensure foreign key constraints are enforced
    return conn

def _execute_sql_script(cursor, sql_script):
    try:
        cursor.executescript(sql_script)
    except sqlite3.Error as e:
        # This is a bit broad; ideally, we'd catch specific errors if script execution has known issues.
        # For schema changes, OperationalError is common.
        raise sqlite3.OperationalError(f"Error executing SQL script: {e}\nScript:\n{sql_script}")

def init_db(app=None):
    """Initializes the database schema for books, articles, sentences, and reading locations."""
    logger = app.logger if app and hasattr(app, 'logger') else default_logger
    conn = get_db_connection()
    cursor = conn.cursor()
    logger.info("DB: Starting database schema initialization/verification.")

    try:
        # 1. Create books table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT UNIQUE NOT NULL,
                creation_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.info("DB: Table 'books' checked/created.")

        # 2. Create or modify articles table
        cursor.execute("PRAGMA table_info(articles)")
        articles_columns = {col['name'] for col in cursor.fetchall()}
        
        if not articles_columns: # Table doesn't exist
            logger.info("DB: 'articles' table not found, creating new table.")
            cursor.execute('''
                CREATE TABLE articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    filename TEXT NOT NULL, 
                    upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processed_srt_path TEXT NULLABLE,
                    converted_mp3_path TEXT NULLABLE,
                    mp3_parts_folder_path TEXT NULLABLE,
                    num_audio_parts INTEGER NULLABLE,
                    audio_part_checksums TEXT NULLABLE,
                    FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE RESTRICT,
                    UNIQUE (book_id, filename) 
                )
            ''')
            logger.info("DB: 'articles' table created with all columns and UNIQUE constraint on (book_id, filename).")
        else: # Table exists, check for missing columns and add them
            logger.info("DB: 'articles' table exists. Verifying columns...")
            cols_to_add_articles = {
                'book_id': 'INTEGER REFERENCES books(id) ON DELETE RESTRICT', 
                'filename': 'TEXT', 
                'processed_srt_path': 'TEXT NULLABLE',
                'converted_mp3_path': 'TEXT NULLABLE',
                'mp3_parts_folder_path': 'TEXT NULLABLE',
                'num_audio_parts': 'INTEGER NULLABLE',
                'audio_part_checksums': 'TEXT NULLABLE'
            }
            for col_name, col_def in cols_to_add_articles.items():
                if col_name not in articles_columns:
                    try:
                        if col_name in ['book_id', 'filename'] and articles_columns: 
                             current_def = col_def + " NULLABLE" 
                             logger.warning(f"DB: Adding '{col_name}' as NULLABLE to existing 'articles' table. Manual data fill and NOT NULL constraint might be needed.")
                        else:
                             current_def = col_def + (" NOT NULL" if col_name in ['book_id', 'filename'] else "")
                        
                        cursor.execute(f"ALTER TABLE articles ADD COLUMN {col_name} {current_def.split('REFERENCES')[0].strip()}")
                        logger.info(f"DB: Added column '{col_name}' to 'articles' table with definition: '{current_def}'.")
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" in str(e).lower():
                            logger.info(f"DB: Column '{col_name}' already exists in 'articles'.")
                        else:
                            logger.error(f"DB: Failed to add column '{col_name}' to 'articles': {e}", exc_info=True)
            
            # Check for UNIQUE (book_id, filename) constraint
            # Method 1: Check table's DDL for "UNIQUE (book_id, filename)"
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='articles'")
            table_sql_row = cursor.fetchone()
            table_sql = table_sql_row['sql'] if table_sql_row else ""
            
            has_table_level_unique = "UNIQUE" in table_sql.upper() and \
                                     "BOOK_ID" in table_sql.upper() and \
                                     "FILENAME" in table_sql.upper() and \
                                     table_sql.upper().count("(", table_sql.upper().find("UNIQUE")) > \
                                     table_sql.upper().count(")", table_sql.upper().find("UNIQUE")) # crude check for (col, col)

            # Method 2: Check for a unique index explicitly created on these columns
            has_explicit_unique_index = False
            indexes_info = cursor.execute("PRAGMA index_list(articles)").fetchall()
            for index_row in indexes_info:
                if index_row['unique'] == 1: # If it's a unique index
                    # Get columns for this index
                    index_cols_info = cursor.execute(f"PRAGMA index_info('{index_row['name']}')").fetchall()
                    indexed_col_names = {col_info['name'] for col_info in index_cols_info}
                    if 'book_id' in indexed_col_names and 'filename' in indexed_col_names and len(indexed_col_names) == 2:
                        has_explicit_unique_index = True
                        logger.info(f"DB: Found explicit unique index '{index_row['name']}' on (book_id, filename).")
                        break
            
            if not has_table_level_unique and not has_explicit_unique_index:
                logger.warning("DB: UNIQUE constraint/index on (book_id, filename) for 'articles' table appears to be missing.")
                try:
                    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_book_filename ON articles(book_id, filename)")
                    logger.info("DB: Attempted to ensure UNIQUE INDEX idx_articles_book_filename ON articles(book_id, filename) exists.")
                except sqlite3.OperationalError as e:
                    logger.error(f"DB: Could not create UNIQUE INDEX on articles(book_id, filename). This might be due to existing duplicate data. Error: {e}")

        # ... (rest of the init_db function for 'sentences' and 'reading_locations' tables) ...
        # 3. Create sentences table
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
                audio_part_index INTEGER NULLABLE,
                start_time_in_part_ms INTEGER NULLABLE,
                end_time_in_part_ms INTEGER NULLABLE,
                FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE,
                UNIQUE (article_id, paragraph_index, sentence_index_in_paragraph) 
            )
        ''')
        logger.info("DB: Table 'sentences' checked/created.")
        
        cursor.execute("PRAGMA table_info(sentences)")
        sentences_columns = {col['name'] for col in cursor.fetchall()}
        cols_to_add_sentences = {
            'audio_part_index': 'INTEGER NULLABLE',
            'start_time_in_part_ms': 'INTEGER NULLABLE',
            'end_time_in_part_ms': 'INTEGER NULLABLE'
        }
        for col_name, col_type in cols_to_add_sentences.items():
            if col_name not in sentences_columns:
                try:
                    cursor.execute(f"ALTER TABLE sentences ADD COLUMN {col_name} {col_type}")
                    logger.info(f"DB: Added column '{col_name}' to 'sentences' table.")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        logger.info(f"DB: Column '{col_name}' already exists in 'sentences'.")
                    else:
                        logger.error(f"DB: Failed to add column '{col_name}' to 'sentences': {e}", exc_info=True)

        # 4. Create reading_locations table
        cursor.execute("PRAGMA table_info(reading_locations)")
        reading_loc_columns = {col['name'] for col in cursor.fetchall()}
        if not reading_loc_columns:
            logger.info("DB: 'reading_locations' table not found, creating new table.")
            cursor.execute('''
                CREATE TABLE reading_locations (
                    article_id INTEGER PRIMARY KEY, 
                    book_id INTEGER NOT NULL,
                    paragraph_index INTEGER NOT NULL,
                    sentence_index_in_paragraph INTEGER NOT NULL,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE,
                    FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
                )
            ''')
            logger.info("DB: 'reading_locations' table created.")
        else: 
            if 'book_id' not in reading_loc_columns:
                try:
                    cursor.execute("ALTER TABLE reading_locations ADD COLUMN book_id INTEGER REFERENCES books(id) ON DELETE CASCADE")
                    logger.info("DB: Added 'book_id' column to 'reading_locations'. It will be NULLABLE. Update existing rows if necessary.")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        logger.info("DB: Column 'book_id' already exists in 'reading_locations'.")
                    else:
                        logger.error(f"DB: Failed to add 'book_id' to 'reading_locations': {e}", exc_info=True)
        
        conn.commit()
        logger.info("DB: Database schema initialization/verification process complete.")
    except sqlite3.Error as e:
        logger.error(f"DB: Database error during schema initialization: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

# ... (rest of db_manager.py functions: add_book, get_book_by_id, etc. remain the same as previously provided)
# Ensure the previously provided full db_manager.py is used from here down, as only init_db was the issue.
# --- Book Functions ---
def add_book(title, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO books (title) VALUES (?)", (title.strip(),))
        book_id = cursor.lastrowid
        conn.commit()
        logger.info(f"DB: Added new book '{title.strip()}' with ID {book_id}.")
        return book_id
    except sqlite3.IntegrityError:
        cursor = conn.cursor() 
        cursor.execute("SELECT id FROM books WHERE title = ?", (title.strip(),))
        existing_book = cursor.fetchone()
        if existing_book:
            logger.info(f"DB: Book '{title.strip()}' already exists with ID {existing_book['id']}. Returning existing ID.")
            return existing_book['id']
        else: 
            logger.error(f"DB: IntegrityError for book '{title.strip()}' but could not find existing entry. This is unexpected.")
            raise
    except sqlite3.Error as e:
        logger.error(f"DB: Error adding book '{title.strip()}': {e}", exc_info=True)
        raise
    finally:
        if conn: conn.close()

def get_book_by_id(book_id, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, creation_timestamp FROM books WHERE id = ?", (book_id,))
        book = cursor.fetchone()
        return book 
    except sqlite3.Error as e:
        logger.error(f"DB: Error fetching book by ID {book_id}: {e}", exc_info=True)
        return None
    finally:
        if conn: conn.close()

def get_all_books(app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, creation_timestamp FROM books ORDER BY title ASC")
        books = cursor.fetchall()
        return books 
    except sqlite3.Error as e:
        logger.error(f"DB: Error fetching all books: {e}", exc_info=True)
        return []
    finally:
        if conn: conn.close()

# --- Article Functions ---
def add_article(book_id, filename_stem, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM articles WHERE book_id = ? AND filename = ?", (book_id, filename_stem))
        existing_article = cursor.fetchone()

        if existing_article:
            article_id = existing_article['id']
            logger.info(f"DB: Article '{filename_stem}' (ID: {article_id}) already exists in book {book_id}. Preparing for re-processing.")
            cursor.execute("""
                UPDATE articles
                SET upload_timestamp = CURRENT_TIMESTAMP,
                    processed_srt_path = NULL, converted_mp3_path = NULL,
                    mp3_parts_folder_path = NULL, num_audio_parts = NULL,
                    audio_part_checksums = NULL
                WHERE id = ?
            """, (article_id,))
            cursor.execute("DELETE FROM sentences WHERE article_id = ?", (article_id,))
            cursor.execute("DELETE FROM reading_locations WHERE article_id = ?", (article_id,))
            logger.info(f"DB: Cleared existing sentences and reset processing fields for article ID {article_id}.")
        else:
            cursor.execute("INSERT INTO articles (book_id, filename) VALUES (?, ?)", (book_id, filename_stem))
            article_id = cursor.lastrowid
            logger.info(f"DB: Added new article '{filename_stem}' to book ID {book_id} with article ID {article_id}.")
        
        conn.commit()
        return article_id
    except sqlite3.IntegrityError as e: 
        logger.error(f"DB: IntegrityError adding/updating article '{filename_stem}' for book {book_id}: {e}. This might indicate an issue with the UNIQUE constraint logic if it's not a new insert.", exc_info=True)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM articles WHERE book_id = ? AND filename = ?", (book_id, filename_stem))
        refetched_article = cursor.fetchone()
        if refetched_article:
            logger.warning(f"DB: Article '{filename_stem}' (ID: {refetched_article['id']}) found after IntegrityError. Proceeding with this ID.")
            return refetched_article['id'] 
        raise 
    except sqlite3.Error as e:
        logger.error(f"DB: Database error adding/updating article '{filename_stem}' for book {book_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()

def get_articles_for_book(book_id, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, filename, upload_timestamp, processed_srt_path, converted_mp3_path,
                   mp3_parts_folder_path, num_audio_parts, book_id, audio_part_checksums
            FROM articles
            WHERE book_id = ?
            ORDER BY filename ASC
        """, (book_id,))
        articles = cursor.fetchall()
        return articles
    except sqlite3.Error as e:
        logger.error(f"DB: Error fetching articles for book ID {book_id}: {e}", exc_info=True)
        return []
    finally:
        if conn: conn.close()

def get_article_by_id(article_id, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, book_id, filename, upload_timestamp, processed_srt_path, converted_mp3_path,
                   mp3_parts_folder_path, num_audio_parts, audio_part_checksums
            FROM articles
            WHERE id = ?
        """, (article_id,))
        article = cursor.fetchone()
        return article
    except sqlite3.Error as e:
        logger.error(f"DB: Error fetching article by ID {article_id}: {e}", exc_info=True)
        return None
    finally:
        if conn: conn.close()

# --- Sentence Functions ---
def add_sentences_batch(article_id, sentences_data, app_logger=None):
    logger = app_logger if app_logger else default_logger
    if not sentences_data:
        logger.info(f"DB: No sentence data provided for batch add to article {article_id}.")
        return 0
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        data_to_insert = [
            (article_id, s_data[0], s_data[1], s_data[2], s_data[3])
            for s_data in sentences_data
        ]
        cursor.executemany('''
            INSERT INTO sentences (article_id, paragraph_index, sentence_index_in_paragraph,
                                   english_text, chinese_text)
            VALUES (?, ?, ?, ?, ?)
        ''', data_to_insert)
        conn.commit()
        logger.info(f"DB: Batch added {len(data_to_insert)} sentences for article {article_id}.")
        return len(data_to_insert)
    except sqlite3.IntegrityError as e: 
        logger.error(f"DB: IntegrityError batch adding sentences for article {article_id}. Error: {e}", exc_info=True)
        if conn: conn.rollback()
        raise 
    except sqlite3.Error as e:
        logger.error(f"DB: Database error batch adding sentences for article {article_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()

def get_sentences_for_article(article_id, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, article_id, paragraph_index, sentence_index_in_paragraph,
                   english_text, chinese_text,
                   start_time_ms, end_time_ms,
                   audio_part_index, start_time_in_part_ms, end_time_in_part_ms
            FROM sentences
            WHERE article_id = ?
            ORDER BY paragraph_index, sentence_index_in_paragraph
        ''', (article_id,))
        sentences = cursor.fetchall()
        return sentences
    except sqlite3.Error as e:
        logger.error(f"DB: Error fetching sentences for article {article_id}: {e}", exc_info=True)
        return []
    finally:
        if conn: conn.close()

def get_sentence_ids_for_article_in_order(article_id, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id FROM sentences
            WHERE article_id = ?
            ORDER BY paragraph_index, sentence_index_in_paragraph
        ''', (article_id,))
        ids = cursor.fetchall()
        return ids 
    except sqlite3.Error as e:
        logger.error(f"DB: Error fetching sentence IDs for article {article_id}: {e}", exc_info=True)
        return []
    finally:
        if conn: conn.close()

def get_english_sentences_for_article(article_id, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT english_text FROM sentences
            WHERE article_id = ?
            ORDER BY paragraph_index, sentence_index_in_paragraph
        ''', (article_id,))
        return [row['english_text'] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"DB: Error fetching English sentences for article {article_id}: {e}", exc_info=True)
        return []
    finally:
        if conn: conn.close()

def get_sentence_id_by_indices(article_id, paragraph_index, sentence_index_in_paragraph, app_logger=None):
    """
    Retrieves the ID of a sentence based on its article ID, paragraph index,
    and sentence index within the paragraph.

    Args:
        article_id (int): The ID of the article.
        paragraph_index (int): The index of the paragraph.
        sentence_index_in_paragraph (int): The index of the sentence within the paragraph.
        app_logger (logging.Logger, optional): Logger instance. Defaults to None.

    Returns:
        int or None: The ID of the sentence if found, otherwise None.
    """
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id
            FROM sentences
            WHERE article_id = ? AND paragraph_index = ? AND sentence_index_in_paragraph = ?
        """, (article_id, paragraph_index, sentence_index_in_paragraph))
        row = cursor.fetchone()
        if row:
            logger.debug(f"DB: Found sentence ID {row['id']} for article {article_id}, P:{paragraph_index}, S:{sentence_index_in_paragraph}.")
            return row['id']
        else:
            logger.debug(f"DB: No sentence found for article {article_id}, P:{paragraph_index}, S:{sentence_index_in_paragraph}.")
            return None
    except sqlite3.Error as e:
        logger.error(f"DB: Error fetching sentence ID by indices for article {article_id}, P:{paragraph_index}, S:{sentence_index_in_paragraph}: {e}", exc_info=True)
        return None
    finally:
        if conn: conn.close()

def update_sentence_timestamps(article_id, timestamps_data, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM sentences
            WHERE article_id = ?
            ORDER BY paragraph_index, sentence_index_in_paragraph
        """, (article_id,))
        sentence_ids_rows = cursor.fetchall()

        logger.info(f"DB: Attempting to update timestamps for article {article_id}. "
                    f"DB sentences found: {len(sentence_ids_rows)}. "
                    f"Timestamps provided: {len(timestamps_data)}.")

        min_len = min(len(sentence_ids_rows), len(timestamps_data))
        if min_len == 0:
            logger.warning(f"DB: No timestamps or sentences to update for article {article_id} (min_len is 0).")
            return 0

        updates = []
        for i in range(min_len):
            sentence_id = sentence_ids_rows[i]['id']
            start_ms, end_ms = timestamps_data[i]
            current_start_ms = int(start_ms) if start_ms is not None else None
            current_end_ms = int(end_ms) if end_ms is not None else None
            updates.append((current_start_ms, current_end_ms, sentence_id))

        if not updates:
            logger.warning(f"DB: No valid timestamp update data prepared for article {article_id}.")
            return 0

        cursor.executemany("""
            UPDATE sentences
            SET start_time_ms = ?, end_time_ms = ?
            WHERE id = ?
        """, updates)
        conn.commit()
        logger.info(f"DB: Committed {cursor.rowcount} timestamp updates for article {article_id}. Expected {len(updates)}.")
        return cursor.rowcount
    except sqlite3.Error as e:
        logger.error(f"DB: Database error updating timestamps for article {article_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()

def update_sentence_single_timestamp(sentence_id, timestamp_type, new_time_ms, app_logger=None):
    logger = app_logger if app_logger else default_logger

    if timestamp_type not in ['start', 'end']:
        if logger: logger.error(f"DB: Invalid timestamp_type '{timestamp_type}' for sentence {sentence_id}.")
        return False

    if not isinstance(new_time_ms, (int, float)) or new_time_ms < 0: # Allow float temporarily, will be rounded by caller or here
        if logger: logger.error(f"DB: Invalid new_time_ms '{new_time_ms}' for sentence {sentence_id}. Must be non-negative number.")
        return False

    new_time_ms = int(round(new_time_ms)) # Ensure it's an integer for DB

    column_to_update = "start_time_ms" if timestamp_type == 'start' else "end_time_ms"

    sql = f"UPDATE sentences SET {column_to_update} = ? WHERE id = ?"

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if logger: logger.info(f"DB: Executing SQL: {sql} with params ({new_time_ms}, {sentence_id})")
        cursor.execute(sql, (new_time_ms, sentence_id))
        conn.commit()

        if cursor.rowcount > 0:
            if logger: logger.info(f"DB: Successfully updated {timestamp_type} for sentence {sentence_id} to {new_time_ms}ms.")
            return True
        else:
            if logger: logger.warning(f"DB: No row found for sentence ID {sentence_id} or timestamp value unchanged for {timestamp_type}.")
            # It's possible the value was the same, so rowcount is 0.
            # Consider this a success if no error, or query current value to be sure.
            # For now, if rowcount is 0, assume it's not an error state unless an exception occurs.
            # To be stricter, one could query the value before and after, or check if sentence_id exists.
            # However, the Flask endpoint already returns success if db_manager returns true and rowcount could be 0
            # if the value is the same. Let's return True if no error and rowcount is 0.
            # A more robust check would be to fetch the sentence and see if the value actually changed, or if it was already set to new_time_ms
            # For now, if no error, we'll consider it "processed". The calling JS might need to handle the case where the value didn't change.
            # Re-evaluating: if rowcount is 0, it means no update happened. This could be due to sentence_id not found.
            # This should be treated as a failure to update as intended.
            return False

    except sqlite3.Error as e:
        if logger: logger.error(f"DB: SQLite error updating {timestamp_type} for sentence {sentence_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

# --- Path and MP3 Part Update Functions ---
def update_article_srt_path(article_id, srt_path, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE articles SET processed_srt_path = ? WHERE id = ?", (srt_path, article_id))
        conn.commit()
        logger.info(f"DB: Updated processed_srt_path for article {article_id} to '{srt_path}'.")
    except sqlite3.Error as e:
        logger.error(f"DB: Failed to update srt_path for article {article_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()

def update_article_converted_mp3_path(article_id, mp3_path, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE articles SET converted_mp3_path = ? WHERE id = ?", (mp3_path, article_id))
        conn.commit()
        logger.info(f"DB: Updated converted_mp3_path for article {article_id} to '{mp3_path}'.")
    except sqlite3.Error as e:
        logger.error(f"DB: Failed to update converted_mp3_path for article {article_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()

def update_article_mp3_parts_info(article_id, parts_folder_path, num_parts, part_checksums_list=None, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    
    concatenated_checksums_str = None
    if part_checksums_list and num_parts > 0:
        if len(part_checksums_list) == num_parts:
            safe_checksums = [cs if isinstance(cs, str) else "" for cs in part_checksums_list]
            concatenated_checksums_str = AUDIO_PART_CHECKSUM_DELIMITER.join(safe_checksums)
        else:
            logger.warning(f"DB: Checksum list length ({len(part_checksums_list)}) != num_parts ({num_parts}) for article {article_id}. Storing NULL for checksums.")
    elif num_parts == 0:
         logger.info(f"DB: num_parts is 0 for article {article_id}, storing NULL for checksums.")

    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE articles
            SET mp3_parts_folder_path = ?, num_audio_parts = ?, audio_part_checksums = ?
            WHERE id = ?
        """, (parts_folder_path if num_parts > 0 else None, 
              num_parts if num_parts > 0 else None, 
              concatenated_checksums_str, 
              article_id))
        conn.commit()
        logger.info(f"DB: Updated MP3 parts info for article {article_id}: path='{parts_folder_path}', num_parts={num_parts}, checksums_stored={'YES' if concatenated_checksums_str else 'NO'}.")
    except sqlite3.Error as e:
        logger.error(f"DB: Error updating MP3 parts info for article {article_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()

def clear_article_mp3_parts_info(article_id, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE articles
            SET mp3_parts_folder_path = NULL, num_audio_parts = NULL, audio_part_checksums = NULL
            WHERE id = ?
        """, (article_id,))
        cursor.execute("""
            UPDATE sentences
            SET audio_part_index = NULL, start_time_in_part_ms = NULL, end_time_in_part_ms = NULL
            WHERE article_id = ?
        """, (article_id,))
        conn.commit()
        logger.info(f"DB: Cleared MP3 parts info for article {article_id}.")
    except sqlite3.Error as e:
        logger.error(f"DB: Error clearing MP3 parts info for article {article_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()

def batch_update_sentence_part_details(sentence_updates, app_logger=None):
    logger = app_logger if app_logger else default_logger
    if not sentence_updates:
        logger.info("DB: No sentence part details to update.")
        return 0
    conn = get_db_connection()
    
    updates_prepared = [(d['audio_part_index'], d['start_time_in_part_ms'], d['end_time_in_part_ms'], d['sentence_db_id'])
                        for d in sentence_updates]
    try:
        cursor = conn.cursor()
        cursor.executemany("""
            UPDATE sentences 
            SET audio_part_index=?, start_time_in_part_ms=?, end_time_in_part_ms=? 
            WHERE id=?
            """, updates_prepared)
        conn.commit()
        logger.info(f"DB: Batch updated sentence part details for {cursor.rowcount} sentences. Expected {len(updates_prepared)}.")
        return cursor.rowcount
    except sqlite3.Error as e:
        logger.error(f"DB: Error batch updating sentence part details: {e}", exc_info=True)
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()

# --- Reading Location Functions ---
def set_reading_location(article_id, book_id, paragraph_index, sentence_index_in_paragraph, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if book_id is None:
            logger.error(f"DB: Attempted to set reading location for article {article_id} with NULL book_id. Aborting.")
            raise ValueError("book_id cannot be NULL for reading_locations.")

        cursor.execute("""
            INSERT INTO reading_locations (article_id, book_id, paragraph_index, sentence_index_in_paragraph, last_updated)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(article_id) DO UPDATE SET
                book_id = excluded.book_id,
                paragraph_index = excluded.paragraph_index,
                sentence_index_in_paragraph = excluded.sentence_index_in_paragraph,
                last_updated = CURRENT_TIMESTAMP
        """, (article_id, book_id, paragraph_index, sentence_index_in_paragraph))
        conn.commit()
        logger.info(f"DB: Set reading location for article {article_id} (book {book_id}) to P:{paragraph_index}, S:{sentence_index_in_paragraph}.")
    except sqlite3.Error as e:
        logger.error(f"DB: Error setting reading location for article {article_id} (book {book_id}): {e}", exc_info=True)
        if conn: conn.rollback()
        raise
    finally:
        if conn: conn.close()

def get_reading_location(article_id, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT article_id, book_id, paragraph_index, sentence_index_in_paragraph, last_updated
            FROM reading_locations
            WHERE article_id = ?
        """, (article_id,))
        location = cursor.fetchone()
        if location:
            logger.debug(f"DB: Retrieved reading location for article {article_id}: P:{location['paragraph_index']}, S:{location['sentence_index_in_paragraph']} (Book: {location['book_id']}).")
        else:
             logger.debug(f"DB: No reading location found for article {article_id}.")
        return location
    except sqlite3.Error as e:
        logger.error(f"DB: Error getting reading location for article {article_id}: {e}", exc_info=True)
        return None
    finally:
        if conn: conn.close()

def get_most_recent_reading_location_for_book(book_id, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT rl.article_id, rl.paragraph_index, rl.sentence_index_in_paragraph, rl.last_updated
            FROM reading_locations rl
            JOIN articles a ON rl.article_id = a.id
            WHERE a.book_id = ?
            ORDER BY rl.last_updated DESC
            LIMIT 1
        """, (book_id,))
        location = cursor.fetchone()
        if location:
            logger.debug(f"DB: Most recent reading for book {book_id} is article {location['article_id']} "
                             f"at P:{location['paragraph_index']}, S:{location['sentence_index_in_paragraph']}.")
        else:
            logger.debug(f"DB: No reading location found for book {book_id}.")
        return location
    except sqlite3.Error as e:
        logger.error(f"DB: Error getting most recent reading location for book {book_id}: {e}", exc_info=True)
        return None
    finally:
        if conn: conn.close()

def delete_article(article_id, app_logger=None):
    logger = app_logger if app_logger else default_logger
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        logger.info(f"DB: Attempting to delete article_id: {article_id} and its related data.")

        # 1. Delete associated sentences.
        cursor.execute("DELETE FROM sentences WHERE article_id = ?", (article_id,))
        logger.info(f"DB: Deleted sentences for article_id: {article_id}. Rows affected: {cursor.rowcount}")

        # 2. Delete associated reading locations.
        cursor.execute("DELETE FROM reading_locations WHERE article_id = ?", (article_id,))
        logger.info(f"DB: Deleted reading locations for article_id: {article_id}. Rows affected: {cursor.rowcount}")

        # 3. Delete the article itself.
        cursor.execute("DELETE FROM articles WHERE id = ?", (article_id,))
        article_deleted_count = cursor.rowcount
        logger.info(f"DB: Deleted article entry for article_id: {article_id}. Rows affected: {article_deleted_count}")

        if article_deleted_count == 0:
            logger.warning(f"DB: Article with article_id: {article_id} was not found for deletion in 'articles' table.")

        conn.commit()
        logger.info(f"DB: Successfully committed deletions for article_id: {article_id}.")
        return True

    except sqlite3.Error as e:
        logger.error(f"DB: Error during deletion of article_id {article_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
            logger.info(f"DB: Rolled back transaction for article_id: {article_id} due to error.")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    print(f"Standalone DB Manager: Initializing database at: {DATABASE_PATH}")
    class DummyApp:
        def __init__(self):
            self.logger = logging.getLogger('db_manager_standalone_init')
            self.logger.setLevel(logging.DEBUG)
            if not self.logger.hasHandlers():
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
            self.instance_path = INSTANCE_FOLDER
    
    init_db(app=DummyApp())
    print("Standalone DB Manager: Database schema created/checked.")