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

AUDIO_PART_CHECKSUM_DELIMITER = ";" # Define delimiter for concatenated checksums

# --- SQLite type converters ---
def convert_timestamp(val_bytes):
    if not val_bytes: 
        return None
    try:
        return datetime.datetime.fromisoformat(val_bytes.decode('utf-8'))
    except ValueError:
        return None

def adapt_datetime(dt_obj):
    return dt_obj.isoformat(" ")

sqlite3.register_converter("DATETIME", convert_timestamp)
sqlite3.register_converter("TIMESTAMP", convert_timestamp) 
sqlite3.register_adapter(datetime.datetime, adapt_datetime)


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row 
    return conn

def init_db(app=None):
    """Initializes the database schema for books, articles, sentences, and reading locations."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Create books table (if not exists)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE NOT NULL,
            creation_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    if app: app.logger.info("DB: Checked/created 'books' table.")

    # 2. Handle articles table
    cursor.execute("PRAGMA table_info(articles)")
    articles_columns = {col['name']: col for col in cursor.fetchall()}

    if not articles_columns: # 'articles' table does not exist
        if app: app.logger.info("DB: 'articles' table not found, creating new table with 'book_id' NOT NULL.")
        cursor.execute('''
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                filename TEXT UNIQUE NOT NULL,
                upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed_srt_path TEXT NULLABLE,
                converted_mp3_path TEXT NULLABLE,
                mp3_parts_folder_path TEXT NULLABLE,
                num_audio_parts INTEGER NULLABLE,
                audio_part_checksums TEXT NULLABLE, -- New column for checksums
                FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE RESTRICT 
            )
        ''') 
    else: # Table exists, check for columns
        if 'book_id' not in articles_columns: 
            if app: app.logger.info("DB: 'articles' table exists but 'book_id' column is missing. Adding 'book_id' as NULLABLE.")
            try:
                cursor.execute("ALTER TABLE articles ADD COLUMN book_id INTEGER NULLABLE REFERENCES books(id) ON DELETE RESTRICT")
                if app: app.logger.info("DB: Added 'book_id' (NULLABLE) column to 'articles' table. Existing articles will have NULL book_id.")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                     if app: app.logger.info("DB: Column 'book_id' already exists in 'articles' table (detected during ALTER attempt).")
                elif app: 
                    app.logger.error(f"DB: Failed to add 'book_id' to 'articles' table: {e}", exc_info=True)
        
        if 'converted_mp3_path' not in articles_columns:
            try:
                cursor.execute("ALTER TABLE articles ADD COLUMN converted_mp3_path TEXT NULLABLE")
                if app: app.logger.info("DB: Added 'converted_mp3_path' column to 'articles' table.")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    if app: app.logger.info("DB: Column 'converted_mp3_path' already exists in 'articles' table (detected during ALTER attempt).")
                elif app:
                    app.logger.error(f"DB: Failed to add 'converted_mp3_path' to 'articles' table: {e}", exc_info=True)

        if 'mp3_parts_folder_path' not in articles_columns:
            try:
                cursor.execute("ALTER TABLE articles ADD COLUMN mp3_parts_folder_path TEXT NULLABLE")
                if app: app.logger.info("DB: Added 'mp3_parts_folder_path' column to 'articles' table.")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower(): 
                    if app: app.logger.info("DB: Column 'mp3_parts_folder_path' already exists in 'articles'.")
                elif app: app.logger.error(f"DB: Failed to add 'mp3_parts_folder_path': {e}", exc_info=True)

        if 'num_audio_parts' not in articles_columns:
            try:
                cursor.execute("ALTER TABLE articles ADD COLUMN num_audio_parts INTEGER NULLABLE")
                if app: app.logger.info("DB: Added 'num_audio_parts' column to 'articles' table.")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    if app: app.logger.info("DB: Column 'num_audio_parts' already exists in 'articles'.")
                elif app: app.logger.error(f"DB: Failed to add 'num_audio_parts': {e}", exc_info=True)
        
        if 'audio_part_checksums' not in articles_columns: # Check for new checksums column
            try:
                cursor.execute("ALTER TABLE articles ADD COLUMN audio_part_checksums TEXT NULLABLE")
                if app: app.logger.info("DB: Added 'audio_part_checksums' column to 'articles' table.")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    if app: app.logger.info("DB: Column 'audio_part_checksums' already exists in 'articles' (detected during ALTER attempt).")
                elif app:
                    app.logger.error(f"DB: Failed to add 'audio_part_checksums' to 'articles' table: {e}", exc_info=True)

    # 3. Create sentences table (if not exists)
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
            FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE
        )
    ''')
    if app: app.logger.info("DB: Checked/created 'sentences' table.")

    # Check and add new columns to sentences if they don't exist (for existing DBs)
    cursor.execute("PRAGMA table_info(sentences)")
    sentences_columns = {col['name']: col for col in cursor.fetchall()}
    new_sentence_cols = {
        'audio_part_index': 'INTEGER NULLABLE',
        'start_time_in_part_ms': 'INTEGER NULLABLE',
        'end_time_in_part_ms': 'INTEGER NULLABLE'
    }
    for col_name, col_type in new_sentence_cols.items():
        if col_name not in sentences_columns:
            try:
                cursor.execute(f"ALTER TABLE sentences ADD COLUMN {col_name} {col_type}")
                if app: app.logger.info(f"DB: Added '{col_name}' column to 'sentences' table.")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    if app: app.logger.info(f"DB: Column '{col_name}' already exists in 'sentences'.")
                elif app:
                    app.logger.error(f"DB: Failed to add '{col_name}' to 'sentences': {e}", exc_info=True)


    # 4. Create/Update reading_locations table
    cursor.execute("PRAGMA table_info(reading_locations)")
    reading_locations_columns = {col['name']: col for col in cursor.fetchall()}

    if not reading_locations_columns: # Table doesn't exist, create with new schema
        if app: app.logger.info("DB: 'reading_locations' table not found. Creating new table with 'book_id'.")
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
        if app: app.logger.info("DB: Created 'reading_locations' table with 'book_id' and foreign key constraints.")
    elif 'book_id' not in reading_locations_columns:
        if app: app.logger.info("DB: 'reading_locations' table missing 'book_id'. Attempting to recreate table and migrate data.")
        
        temp_table_name = "reading_locations_old_migration"
        renamed_successfully = False
        try:
            # Drop if previous migration failed and left temp table
            cursor.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
            cursor.execute(f"ALTER TABLE reading_locations RENAME TO {temp_table_name}")
            if app: app.logger.info(f"DB: Renamed 'reading_locations' to '{temp_table_name}'.")
            renamed_successfully = True
        except sqlite3.Error as e:
            if app: app.logger.error(f"DB: Error preparing for 'reading_locations' migration (rename step): {e}. 'reading_locations' migration aborted.", exc_info=True)
        
        if renamed_successfully:
            try:
                # 2. Create new table with correct schema
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
                if app: app.logger.info("DB: Created new 'reading_locations' table with 'book_id' and FKs.")

                # 3. Copy data, fetching book_id from articles table
                migration_successful = False
                rows_migrated = 0
                cursor.execute(f'''
                    INSERT INTO reading_locations (article_id, book_id, paragraph_index, sentence_index_in_paragraph, last_updated)
                    SELECT
                        r_old.article_id,
                        a.book_id,
                        r_old.paragraph_index,
                        r_old.sentence_index_in_paragraph,
                        r_old.last_updated
                    FROM {temp_table_name} r_old
                    JOIN articles a ON r_old.article_id = a.id
                    WHERE a.book_id IS NOT NULL
                ''')
                rows_migrated = cursor.rowcount
                if app: app.logger.info(f"DB: Copied {rows_migrated} rows to new 'reading_locations' table.")
                migration_successful = True
            except sqlite3.Error as e:
                if app: app.logger.error(f"DB: SQLite error migrating data to 'reading_locations' from '{temp_table_name}': {e}. Data might be lost if old table is dropped.", exc_info=True)
            
            # 4. Drop old table
            if migration_successful:
                cursor.execute(f"DROP TABLE {temp_table_name}")
                if app: app.logger.info(f"DB: Dropped temporary table '{temp_table_name}'.")
            else:
                if app: app.logger.warning(f"DB: Migration of 'reading_locations' data failed or {rows_migrated} rows were copied. '{temp_table_name}' was NOT dropped automatically. Manual cleanup may be required.")
        else: # Renaming failed
             if app: app.logger.warning(f"DB: 'reading_locations' table could not be migrated as renaming step failed.")
    else: # Table exists and 'book_id' column is present
        if app: app.logger.info("DB: 'reading_locations' table exists and 'book_id' column is present.")


    conn.commit()
    conn.close()
    if app:
        app.logger.info("DB: Database schema initialization process complete.")

# --- Book Functions ---
def add_book(title, app_logger=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO books (title) VALUES (?)", (title,))
        book_id = cursor.lastrowid
        conn.commit()
        if app_logger: app_logger.info(f"DB: Added new book '{title}' with ID {book_id}.")
        return book_id
    except sqlite3.IntegrityError: 
        cursor.execute("SELECT id FROM books WHERE title = ?", (title,))
        book_id = cursor.fetchone()['id']
        if app_logger: app_logger.info(f"DB: Book '{title}' already exists with ID {book_id}. Returning existing ID.")
        return book_id
    finally:
        conn.close()

def get_book_by_id(book_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, creation_timestamp FROM books WHERE id = ?", (book_id,))
    book = cursor.fetchone()
    conn.close()
    return book

def get_all_books():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, creation_timestamp FROM books ORDER BY title ASC")
    books = cursor.fetchall()
    conn.close()
    return books

# --- Article Functions (modified) ---
def add_article(book_id, filename, app_logger=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, book_id FROM articles WHERE filename = ?", (filename,))
        existing_article = cursor.fetchone()

        if existing_article:
            article_id = existing_article['id']
            if app_logger: app_logger.info(f"DB: Article filename '{filename}' (ID: {article_id}) exists.")
            
            if existing_article['book_id'] != book_id:
                if app_logger: app_logger.warning(f"DB: Re-assigning article '{filename}' (ID: {article_id}) from book ID {existing_article['book_id']} to book ID {book_id}.")
                cursor.execute("UPDATE articles SET book_id = ?, upload_timestamp = CURRENT_TIMESTAMP WHERE id = ?", (book_id, article_id))
            else:
                cursor.execute("UPDATE articles SET upload_timestamp = CURRENT_TIMESTAMP WHERE id = ?", (article_id,))
            
            # Reset fields related to processing when re-uploading text
            cursor.execute("""
                UPDATE articles 
                SET processed_srt_path = NULL, converted_mp3_path = NULL, 
                    mp3_parts_folder_path = NULL, num_audio_parts = NULL,
                    audio_part_checksums = NULL -- Reset checksums
                WHERE id = ?
            """, (article_id,))
            cursor.execute("DELETE FROM sentences WHERE article_id = ?", (article_id,))
            cursor.execute("DELETE FROM reading_locations WHERE article_id = ?", (article_id,))
            conn.commit()
            if app_logger: app_logger.info(f"DB: Article '{filename}' (ID: {article_id}) fields reset for new upload/reprocessing.")
        else:
            cursor.execute("INSERT INTO articles (book_id, filename) VALUES (?, ?)", (book_id, filename))
            article_id = cursor.lastrowid
            conn.commit()
            if app_logger: app_logger.info(f"DB: Added new article '{filename}' to book ID {book_id} with article ID {article_id}.")
        return article_id
    except sqlite3.IntegrityError as e: 
        if app_logger: app_logger.error(f"DB: IntegrityError adding/updating article '{filename}' for book {book_id}: {e}", exc_info=True)
        cursor.execute("SELECT id FROM articles WHERE filename = ?", (filename,)) 
        res = cursor.fetchone()
        if res:
            if app_logger: app_logger.warning(f"DB: Article '{filename}' found (ID: {res['id']}) after IntegrityError. Check book association.")
            return res['id']
        raise
    finally:
        conn.close()

def get_articles_for_book(book_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, filename, upload_timestamp, processed_srt_path, converted_mp3_path, 
               mp3_parts_folder_path, num_audio_parts, book_id,
               audio_part_checksums -- Select new column
        FROM articles
        WHERE book_id = ?
        ORDER BY filename ASC
    """, (book_id,))
    articles = cursor.fetchall()
    conn.close()
    return articles

def get_article_by_id(article_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, book_id, filename, upload_timestamp, processed_srt_path, converted_mp3_path,
               mp3_parts_folder_path, num_audio_parts,
               audio_part_checksums -- Select new column
        FROM articles 
        WHERE id = ?
    """, (article_id,))
    article = cursor.fetchone()
    conn.close()
    return article

def get_article_filename(article_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM articles WHERE id = ?", (article_id,))
    article_row = cursor.fetchone()
    conn.close()
    return article_row['filename'] if article_row else None

def get_sentences_for_article(article_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, paragraph_index, sentence_index_in_paragraph, 
               english_text, chinese_text,
               start_time_ms, end_time_ms,
               audio_part_index, start_time_in_part_ms, end_time_in_part_ms
        FROM sentences
        WHERE article_id = ?
        ORDER BY paragraph_index, sentence_index_in_paragraph
    ''', (article_id,))
    sentences = cursor.fetchall()
    conn.close()
    return sentences

def get_sentence_ids_for_article_in_order(article_id, app_logger=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id
        FROM sentences
        WHERE article_id = ?
        ORDER BY paragraph_index, sentence_index_in_paragraph
    ''', (article_id,))
    ids = cursor.fetchall() # list of Row objects, e.g., [{'id': 1}, {'id': 2}]
    conn.close()
    return ids


def get_english_sentences_for_article(article_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT english_text
        FROM sentences
        WHERE article_id = ?
        ORDER BY paragraph_index, sentence_index_in_paragraph
    ''', (article_id,))
    return [row['english_text'] for row in cursor.fetchall()]


def add_sentences_batch(article_id, sentences_data):
    if not sentences_data:
        return 0
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        data_to_insert = [
            (article_id, s_data[0], s_data[1], s_data[2], s_data[3])
            for s_data in sentences_data
        ]
        cursor.executemany('''
            INSERT INTO sentences (article_id, paragraph_index, sentence_index_in_paragraph, 
                                   english_text, chinese_text)
            VALUES (?, ?, ?, ?, ?) 
            -- audio_part_index, start_time_in_part_ms, end_time_in_part_ms default to NULL
        ''', data_to_insert)
        conn.commit()
        return len(data_to_insert)
    except sqlite3.Error as e:
        conn.rollback() 
        raise e
    finally:
        conn.close()

def update_sentence_timestamps(article_id, timestamps_data, app_logger=None):
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
        
        min_len = min(len(sentence_ids_rows), len(timestamps_data))
        if min_len == 0:
            if app_logger:
                app_logger.warning(f"DB: No timestamps or sentences to update for article {article_id} (min_len is 0).")
            return 0

        updates = []
        for i in range(min_len):
            sentence_id = sentence_ids_rows[i]['id']
            start_ms, end_ms = timestamps_data[i]
            current_start_ms = int(start_ms) if start_ms is not None else None
            current_end_ms = int(end_ms) if end_ms is not None else None
            updates.append((current_start_ms, current_end_ms, sentence_id))
        
        if not updates:
            if app_logger: app_logger.warning(f"DB: No valid update data prepared for article {article_id}.")
            return 0

        cursor.executemany("""
            UPDATE sentences
            SET start_time_ms = ?, end_time_ms = ?
            WHERE id = ?
        """, updates)
        conn.commit()
        
        if app_logger:
             app_logger.info(f"DB: Committed {len(updates)} timestamp updates for article {article_id}.")
        return len(updates) 
    except sqlite3.Error as e:
        if app_logger:
            app_logger.error(f"DB: Database error updating timestamps for article {article_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        raise e 
    finally:
        if conn: conn.close()

def update_article_srt_path(article_id, srt_path):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE articles SET processed_srt_path = ? WHERE id = ?", (srt_path, article_id))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def update_article_converted_mp3_path(article_id, mp3_path, app_logger=None):
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

# --- MP3 Parts Info Update Functions ---
def update_article_mp3_parts_info(article_id, parts_folder_path, num_parts, part_checksums_list=None, app_logger=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    concatenated_checksums_str = None
    if part_checksums_list and num_parts > 0:
        if len(part_checksums_list) == num_parts:
            # Ensure all items are strings (empty string for failed checksums)
            safe_checksums = [cs if isinstance(cs, str) else "" for cs in part_checksums_list]
            concatenated_checksums_str = AUDIO_PART_CHECKSUM_DELIMITER.join(safe_checksums)
            if app_logger: 
                app_logger.info(f"DB: Concatenated checksums for article {article_id} ({len(safe_checksums)} parts): '{concatenated_checksums_str[:60]}...'")
        else:
            if app_logger: 
                app_logger.warning(f"DB: Checksum list length ({len(part_checksums_list)}) does not match num_parts ({num_parts}) for article {article_id}. Storing NULL for checksums.")
    elif num_parts == 0: # No parts, so no checksums.
         if app_logger: app_logger.info(f"DB: num_parts is 0 for article {article_id}, storing NULL for checksums.")
    else: # num_parts > 0 but no checksum list provided
        if app_logger: app_logger.warning(f"DB: No checksum list provided for article {article_id} with {num_parts} parts. Storing NULL for checksums.")

    try:
        cursor.execute("""
            UPDATE articles 
            SET mp3_parts_folder_path = ?, num_audio_parts = ?, audio_part_checksums = ?
            WHERE id = ?
        """, (parts_folder_path, num_parts if num_parts > 0 else None, concatenated_checksums_str, article_id)) # Store None if num_parts is 0
        conn.commit()
        if app_logger: 
            app_logger.info(f"DB: Updated MP3 parts info for article {article_id}: path='{parts_folder_path}', num_parts={num_parts}, checksums_stored={'YES' if concatenated_checksums_str else 'NO'}.")
    except sqlite3.Error as e:
        if app_logger: app_logger.error(f"DB: Error updating MP3 parts info for article {article_id}: {e}", exc_info=True)
        conn.rollback()
        raise
    finally:
        conn.close()

def clear_article_mp3_parts_info(article_id, app_logger=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Clear article level info
        cursor.execute("""
            UPDATE articles
            SET mp3_parts_folder_path = NULL, num_audio_parts = NULL, audio_part_checksums = NULL -- Clear checksums
            WHERE id = ?
        """, (article_id,))
        # Clear sentence level part info
        cursor.execute("""
            UPDATE sentences
            SET audio_part_index = NULL, start_time_in_part_ms = NULL, end_time_in_part_ms = NULL
            WHERE article_id = ?
        """, (article_id,))
        conn.commit()
        if app_logger: app_logger.info(f"DB: Cleared MP3 parts info (including checksums) for article {article_id}.")
    except sqlite3.Error as e:
        if app_logger: app_logger.error(f"DB: Error clearing MP3 parts info for article {article_id}: {e}", exc_info=True)
        conn.rollback()
        raise
    finally:
        conn.close()

def batch_update_sentence_part_details(sentence_updates, app_logger=None):
    # sentence_updates is a list of dicts:
    # [{'sentence_db_id': id, 'audio_part_index': pi, 'start_time_in_part_ms': spms, 'end_time_in_part_ms': epms}, ...]
    if not sentence_updates: return 0
    conn = get_db_connection()
    cursor = conn.cursor()
    updates_prepared = [(d['audio_part_index'], d['start_time_in_part_ms'], d['end_time_in_part_ms'], d['sentence_db_id']) for d in sentence_updates]
    try:
        cursor.executemany("UPDATE sentences SET audio_part_index=?, start_time_in_part_ms=?, end_time_in_part_ms=? WHERE id=?", updates_prepared)
        conn.commit()
        if app_logger: app_logger.info(f"DB: Batch updated sentence part details for {len(updates_prepared)} sentences.")
        return len(updates_prepared)
    except sqlite3.Error as e:
        if app_logger: app_logger.error(f"DB: Error batch updating sentence part details: {e}", exc_info=True)
        conn.rollback()
        raise
    finally:
        conn.close()


# --- Reading Location Functions ---
def set_reading_location(article_id, book_id, paragraph_index, sentence_index_in_paragraph, app_logger=None):
    """Sets or updates the reading location for a given article, including its book_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
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
        if app_logger:
            app_logger.info(f"DB: Set reading location for article {article_id} (book {book_id}) to P:{paragraph_index}, S:{sentence_index_in_paragraph}.")
    except sqlite3.Error as e:
        if app_logger:
            app_logger.error(f"DB: Error setting reading location for article {article_id} (book {book_id}): {e}", exc_info=True)
        conn.rollback()
        raise
    finally:
        conn.close()

def get_reading_location(article_id, app_logger=None):
    """Retrieves the reading location for a given article."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT article_id, book_id, paragraph_index, sentence_index_in_paragraph, last_updated
            FROM reading_locations
            WHERE article_id = ?
        """, (article_id,))
        location = cursor.fetchone()
        if app_logger and location:
            app_logger.debug(f"DB: Retrieved reading location for article {article_id}: P:{location['paragraph_index']}, S:{location['sentence_index_in_paragraph']} (Book: {location['book_id']}).")
        elif app_logger:
             app_logger.debug(f"DB: No reading location found for article {article_id}.")
        return location 
    except sqlite3.Error as e:
        if app_logger:
            app_logger.error(f"DB: Error getting reading location for article {article_id}: {e}", exc_info=True)
        raise
    finally:
        conn.close()

def get_most_recent_reading_location_for_book(book_id, app_logger=None):
    """Retrieves the most recent reading location (article_id, p_idx, s_idx) for a given book."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT article_id, paragraph_index, sentence_index_in_paragraph, last_updated
            FROM reading_locations
            WHERE book_id = ?
            ORDER BY last_updated DESC
            LIMIT 1
        """, (book_id,))
        location = cursor.fetchone()
        if app_logger and location:
            app_logger.debug(f"DB: Most recent reading for book {book_id} is article {location['article_id']} "
                             f"at P:{location['paragraph_index']}, S:{location['sentence_index_in_paragraph']}.")
        elif app_logger and not location:
            app_logger.debug(f"DB: No reading location found for book {book_id}.")
        return location # Returns a Row object or None
    except sqlite3.Error as e:
        if app_logger:
            app_logger.error(f"DB: Error getting most recent reading location for book {book_id}: {e}", exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    print(f"Initializing database at: {DATABASE_PATH}")
    class DummyApp:
        def __init__(self):
            self.logger = logging.getLogger('db_manager_standalone')
            self.logger.setLevel(logging.DEBUG) # Changed to DEBUG for more verbose init
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.instance_path = INSTANCE_FOLDER
    
    init_db(app=DummyApp()) 
    print("Database schema created/checked.")