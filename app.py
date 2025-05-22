import os
import tempfile
import shutil
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import db_manager
import text_parser
import audio_processor
import tts_utils # <-- NEW IMPORT

import logging
from logging.handlers import RotatingFileHandler

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_TEXT_EXTENSIONS = {'txt'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'mp4', 'wav', 'm4a'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'your_very_secret_key_here_please_change_me' # TODO: Change this!
app.config['AENEAS_PYTHON_PATH'] = r"C:\Program Files\Python39\python.exe" # TODO: Make this environment configurable
app.config['PROCESSED_SRT_FOLDER'] = os.path.join(app.instance_path, 'processed_srts')
app.config['TEMP_FILES_FOLDER'] = os.path.join(app.instance_path, 'temp_files')
app.config['CONVERTED_AUDIO_FOLDER'] = os.path.join(app.instance_path, 'converted_audio')
app.config['MP3_PARTS_FOLDER'] = os.path.join(app.instance_path, 'mp3_parts')
app.config['MAX_AUDIO_PART_SIZE_MB'] = 20

# --- NEW TTS Configuration ---
app.config['KOKORO_MANDARIN_VOICE'] = 'zf_xiaoxiao'  # TODO: REPLACE with your actual Mandarin voice
app.config['KOKORO_ENGLISH_VOICE'] = 'af_heart'    # TODO: REPLACE with your actual English voice
app.config['KOKORO_LANG_CODE_ZH'] = 'z'
app.config['KOKORO_LANG_CODE_EN'] = 'a' # Or 'b' depending on your chosen English voice
app.config['KOKORO_SAMPLE_RATE'] = 24000 # Kokoro's typical output, confirm if different
app.config['TTS_INTER_SENTENCE_SILENCE_MS'] = 500
# --- End NEW TTS Configuration ---


# --- Logging Configuration ---
if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path)

log_dir = os.path.join(app.instance_path, 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_file = os.path.join(log_dir, 'app.log')
file_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024 * 10, backupCount=5)
formatter = logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO) # Changed to INFO for production, DEBUG for dev
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO) # Changed to INFO
app.logger.info('Application startup: File logging configured.')


# --- Database Initialization ---
with app.app_context():
    db_manager.init_db(app)
    # --- NEW: Initialize TTS on app startup ---
    tts_init_success = tts_utils.initialize_kokoro(
        app.config['KOKORO_LANG_CODE_ZH'],
        app.config['KOKORO_LANG_CODE_EN'],
        logger=app.logger
    )
    if tts_init_success:
        app.logger.info("APP: Kokoro TTS engines initialized (or already were).")
        if not tts_utils.check_voices_configured(app.config['KOKORO_MANDARIN_VOICE'], app.config['KOKORO_ENGLISH_VOICE'], app.logger):
            app.logger.warning("APP: *** KOKORO VOICES MAY BE MISCONFIGURED IN app.py! TTS might fail. ***")
    else:
        app.logger.error("APP: *** KOKORO TTS FAILED TO INITIALIZE. TTS features will be unavailable. ***")
    # --- End NEW TTS Initialization ---

def allowed_text_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_TEXT_EXTENSIONS

def allowed_audio_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS

def _ensure_dirs_exist():
    # ... (no change to this function)
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    if not os.path.exists(app.config['PROCESSED_SRT_FOLDER']):
        os.makedirs(app.config['PROCESSED_SRT_FOLDER'])
    if not os.path.exists(app.config['TEMP_FILES_FOLDER']):
        os.makedirs(app.config['TEMP_FILES_FOLDER'])
    if not os.path.exists(app.config['CONVERTED_AUDIO_FOLDER']):
        os.makedirs(app.config['CONVERTED_AUDIO_FOLDER'])
    if not os.path.exists(app.config['MP3_PARTS_FOLDER']):
        os.makedirs(app.config['MP3_PARTS_FOLDER'])

_ensure_dirs_exist()

def _process_audio_alignment(article_id,
                             audio_file_storage,
                             original_bilingual_text_content_string,
                             article_filename_base):
    # ... (This function remains largely the same - Aeneas path)
    # Minor logging adjustment for clarity if needed
    app.logger.info(f"APP: Starting AENEAS audio alignment process for article {article_id}")
    temp_dir_base = Path(app.config['TEMP_FILES_FOLDER'])
    processed_srt_dir_base = Path(app.config['PROCESSED_SRT_FOLDER'])
    
    try:
        with tempfile.TemporaryDirectory(dir=str(temp_dir_base), prefix=f"aeneas_job_{article_id}_") as job_temp_dir:
            job_temp_dir_path = Path(job_temp_dir)
            app.logger.info(f"APP: Created temporary job directory: {job_temp_dir_path} for article {article_id}")

            audio_filename_secure = secure_filename(audio_file_storage.filename)
            original_audio_temp_path = job_temp_dir_path / audio_filename_secure
            audio_file_storage.save(str(original_audio_temp_path))
            app.logger.info(f"APP: Saved uploaded audio to {original_audio_temp_path} for article {article_id}")

            app.logger.info(f"APP: Converting '{original_audio_temp_path}' to MP3 format for persistent storage (article {article_id}).")
            article_converted_audio_dir = Path(app.config['CONVERTED_AUDIO_FOLDER']) / str(article_id)
            article_converted_audio_dir.mkdir(parents=True, exist_ok=True)
            app.logger.info(f"APP: Persistent directory for converted audio for article {article_id}: {article_converted_audio_dir}")

            converted_mp3_path_str = audio_processor.convert_to_mp3(
                str(original_audio_temp_path),
                str(article_converted_audio_dir),
                logger=app.logger
            )
            app.logger.info(f"APP: Converted audio stored persistently at: {converted_mp3_path_str} for article {article_id}")
            
            db_manager.update_article_converted_mp3_path(article_id, converted_mp3_path_str, app_logger=app.logger)

            english_sentences_list_for_aeneas = []
            if original_bilingual_text_content_string:
                app.logger.info(f"APP: Extracting English sentences from provided raw bilingual text for article {article_id} (Aeneas)...")
                english_sentences_list_for_aeneas = audio_processor.extract_english_sentences_for_aeneas(
                    original_bilingual_text_content_string, logger=app.logger
                )
            else:
                app.logger.info(f"APP: Fetching English sentences from database for article {article_id} (deferred Aeneas alignment)...")
                english_sentences_list_for_aeneas = db_manager.get_english_sentences_for_article(article_id)
            
            if not english_sentences_list_for_aeneas:
                flash("No English sentences available (from text or DB) for Aeneas alignment.", "warning")
                app.logger.warning(f"APP: Aborting Aeneas audio alignment for article {article_id}: No English sentences.")
                return None
            else:
                app.logger.info(f"APP: Using {len(english_sentences_list_for_aeneas)} English sentences for Aeneas for article {article_id}.")

            plain_text_filename = f"{article_filename_base}_eng_for_aeneas.txt"
            plain_text_temp_path = job_temp_dir_path / plain_text_filename
            audio_processor.create_plain_text_file_from_list(
                english_sentences_list_for_aeneas,
                str(plain_text_temp_path),
                logger=app.logger
            )
            app.logger.info(f"APP: Created plain English text file at {plain_text_temp_path} for article {article_id}")

            aeneas_srt_filename = f"{article_filename_base}_aeneas_raw.srt"
            aeneas_srt_temp_path = job_temp_dir_path / aeneas_srt_filename
            app.logger.info(f"APP: Running Aeneas for article {article_id} (MP3: {converted_mp3_path_str}, Text: {plain_text_temp_path}). Output to: {aeneas_srt_temp_path}")
            audio_processor.run_aeneas_alignment(
                converted_mp3_path_str,
                str(plain_text_temp_path),
                str(aeneas_srt_temp_path),
                app.config['AENEAS_PYTHON_PATH'],
                logger=app.logger
            )
            app.logger.info(f"APP: Aeneas completed. Raw SRT should be at {aeneas_srt_temp_path} for article {article_id}")

            srt_timestamps = audio_processor.parse_aeneas_srt_file(str(aeneas_srt_temp_path), logger=app.logger)
            if not srt_timestamps:
                flash(f"Aeneas produced an SRT, but no timestamps parsed for {audio_filename_secure}.", "warning")
                app.logger.warning(f"APP: Aborting further processing for article {article_id}: No timestamps from Aeneas SRT. Path: {aeneas_srt_temp_path}")
                if not Path(aeneas_srt_temp_path).exists() or Path(aeneas_srt_temp_path).stat().st_size == 0:
                    app.logger.warning(f"APP: Aeneas SRT file {aeneas_srt_temp_path} is missing or empty for article {article_id}.")
                return None
            app.logger.info(f"APP: Successfully parsed {len(srt_timestamps)} timestamps from Aeneas SRT for article {article_id}. First 3: {srt_timestamps[:3]}")

            updated_count = db_manager.update_sentence_timestamps(article_id, srt_timestamps, app_logger=app.logger)
            app.logger.info(f"APP: DB update process reported {updated_count} sentence timestamps updated in DB for article {article_id}.")
            if updated_count == 0 and srt_timestamps:
                 flash(f"Timestamps parsed from Aeneas SRT ({len(srt_timestamps)} entries), but not applied to any DB sentences for {audio_filename_secure}. Check sentence count matching.", "warning")
            elif updated_count > 0:
                 flash(f"Aligned audio & updated {updated_count} sentence timestamps for {audio_filename_secure} using Aeneas.", "success")

            full_sentences_data_from_db = db_manager.get_sentences_for_article(article_id)
            bilingual_sentences_for_srt_gen = [
                {'english_text': s['english_text'], 'chinese_text': s['chinese_text']}
                for s in full_sentences_data_from_db
            ]
            final_bilingual_srt_filename = f"{article_filename_base}_bilingual_aeneas.srt" # Clarify source
            article_srt_dir = processed_srt_dir_base / str(article_id)
            article_srt_dir.mkdir(parents=True, exist_ok=True)
            final_bilingual_srt_path = article_srt_dir / final_bilingual_srt_filename
            
            bilingual_srt_generated_path_str = audio_processor.generate_bilingual_srt(
                article_id,
                bilingual_sentences_for_srt_gen,
                srt_timestamps,
                str(final_bilingual_srt_path),
                logger=app.logger
            )
            if bilingual_srt_generated_path_str:
                db_manager.update_article_srt_path(article_id, bilingual_srt_generated_path_str)
                app.logger.info(f"APP: Generated final bilingual SRT for article {article_id} at {bilingual_srt_generated_path_str} (Aeneas)")
            else:
                app.logger.warning(f"APP: Failed to generate final bilingual SRT for article {article_id} (Aeneas).")
                flash("Failed to generate the final bilingual SRT file (Aeneas).", "warning")
                return None

            # --- MP3 Splitting Logic (after Aeneas main processing) ---
            if converted_mp3_path_str:
                app.logger.info(f"APP: Proceeding to MP3 splitting for Aeneas-processed audio, article {article_id}")
                # Using the new splitting logic for consistency, though the old one could also be used here.
                # For this, we need sentence IDs and their timestamps (which we just got from Aeneas and put in DB).
                
                # Fetch sentence IDs in order
                sentence_db_ids_ordered = db_manager.get_sentence_ids_for_article_in_order(article_id, app_logger=app.logger)

                if len(sentence_db_ids_ordered) != len(srt_timestamps):
                    app.logger.error(f"APP: Mismatch for Aeneas splitting: DB sentence count ({len(sentence_db_ids_ordered)}) vs SRT timestamp count ({len(srt_timestamps)}) for article {article_id}. Skipping MP3 splitting.")
                else:
                    sentences_info_for_splitting = []
                    for i, db_id_dict in enumerate(sentence_db_ids_ordered):
                        sentences_info_for_splitting.append({
                            'id': db_id_dict['id'],
                            'original_start_ms': srt_timestamps[i][0],
                            'original_end_ms': srt_timestamps[i][1]
                        })
                    
                    article_mp3_parts_dir_path = Path(app.config['MP3_PARTS_FOLDER']) / str(article_id)
                    article_mp3_parts_dir_path.mkdir(parents=True, exist_ok=True)

                    split_details = audio_processor.split_mp3_by_size_estimation(
                        original_mp3_path=converted_mp3_path_str,
                        sentences_info=sentences_info_for_splitting,
                        max_part_size_bytes=app.config['MAX_AUDIO_PART_SIZE_MB'] * 1024 * 1024,
                        output_parts_dir=str(article_mp3_parts_dir_path),
                        article_filename_base=article_filename_base,
                        logger=app.logger
                    )

                    if split_details and split_details['num_parts'] > 0:
                        part_checksums_list = split_details.get('part_checksums', [])
                        db_manager.update_article_mp3_parts_info(
                            article_id,
                            str(article_mp3_parts_dir_path),
                            split_details['num_parts'],
                            part_checksums_list,
                            app_logger=app.logger
                        )
                        db_manager.batch_update_sentence_part_details(split_details['sentence_part_updates'], app_logger=app.logger)
                        app.logger.info(f"APP: Successfully split Aeneas MP3 for article {article_id} into {split_details['num_parts']} parts. Stored in {article_mp3_parts_dir_path}.")
                        flash(f"Audio processed (Aeneas). Original MP3 was large and split into {split_details['num_parts']} parts.", "info")
                    elif split_details and split_details['num_parts'] == 0 and Path(converted_mp3_path_str).stat().st_size > (app.config['MAX_AUDIO_PART_SIZE_MB'] * 1024 * 1024):
                        app.logger.warning(f"APP: Aeneas MP3 splitting failed or resulted in no parts for article {article_id}, despite being large.")
                        db_manager.clear_article_mp3_parts_info(article_id, app_logger=app.logger)
                        flash("Audio processed (Aeneas). Original MP3 was large, but splitting failed or produced no parts.", "warning")
                    else: # Not large enough to split or other case
                        app.logger.info(f"APP: Aeneas MP3 for article {article_id} not split (either too small or splitting not applicable). Clearing previous part info.")
                        db_manager.clear_article_mp3_parts_info(article_id, app_logger=app.logger)
            
            return bilingual_srt_generated_path_str
    except Exception as e:
        app.logger.error(f"APP: Error during AENEAS audio alignment for article {article_id}: {e}", exc_info=True)
        flash(f"An error occurred during Aeneas audio processing: {str(e)}", "danger")
    return None


@app.route('/')
def home_redirect():
    return redirect(url_for('list_books_page'))

@app.route('/books', methods=['GET', 'POST'])
def list_books_page():
    # ... (no change to this function)
    if request.method == 'POST':
        title = request.form.get('title')
        if not title or not title.strip():
            flash('Book title cannot be empty.', 'danger')
        else:
            try:
                db_manager.add_book(title.strip(), app_logger=app.logger)
                flash(f'Book "{title.strip()}" added successfully or already exists.', 'success')
            except Exception as e:
                app.logger.error(f"APP: Error adding book '{title}': {e}", exc_info=True)
                flash(f'Error adding book: {str(e)}', 'danger')
        return redirect(url_for('list_books_page'))

    try:
        books = db_manager.get_all_books()
    except Exception as e:
        app.logger.error(f"APP: Error fetching books: {e}", exc_info=True)
        flash("Could not retrieve books from database.", "danger")
        books = []
    return render_template('books.html', books=books)


@app.route('/book/<int:book_id>', methods=['GET', 'POST'])
def book_detail_page(book_id):
    # ... (GET part and initial POST checks for book, text_file are the same) ...
    book = db_manager.get_book_by_id(book_id)
    if not book:
        flash('Book not found.', 'danger')
        app.logger.warning(f"APP: Book ID {book_id} not found for viewing.")
        return redirect(url_for('list_books_page'))

    if request.method == 'POST':
        # ... (text file reading and initial DB entry for article and sentences) ...
        # This part is crucial and should be the same as your last working version
        # up to the point of `sentences_added_count`.

        if 'file' not in request.files:
            flash('No text file part.', 'danger')
            return redirect(url_for('book_detail_page', book_id=book_id))
        
        text_file = request.files['file']
        if text_file.filename == '':
            flash('No text file selected.', 'danger')
            return redirect(url_for('book_detail_page', book_id=book_id))
        
        article_id_processed = None
        raw_bilingual_text_content = None
        article_title_for_db = None
        article_safe_stem_for_files = None
        sentences_added_count = 0 # Initialize

        use_tts_checked = request.form.get('use_tts') == 'true'
        app.logger.info(f"APP: Upload for book {book_id}. TTS checkbox state: {use_tts_checked}")

        if text_file and allowed_text_file(text_file.filename):
            original_text_filename = text_file.filename
            article_title_for_db = Path(original_text_filename).stem
            article_safe_stem_for_files = secure_filename(article_title_for_db)
            
            try:
                raw_bilingual_text_content = text_file.stream.read().decode('utf-8')
                text_file.stream.seek(0) 
            # ... (error handling for text file read) ...
            except UnicodeDecodeError:
                app.logger.error(f"APP: UnicodeDecodeError for text file {original_text_filename} for book {book_id}.", exc_info=True)
                flash('Text file not UTF-8 encoded.', 'danger')
                return redirect(url_for('book_detail_page', book_id=book_id))
            except Exception as e:
                app.logger.error(f"APP: Error reading text file stream for {original_text_filename} (book {book_id}): {e}", exc_info=True)
                flash(f'Error reading text file: {str(e)}', 'danger')
                return redirect(url_for('book_detail_page', book_id=book_id))

            if not raw_bilingual_text_content.strip():
                flash(f'Text file "{original_text_filename}" is empty.', 'warning')
                app.logger.warning(f"APP: Uploaded text file '{original_text_filename}' for book {book_id} is empty.")
                return redirect(url_for('book_detail_page', book_id=book_id))

            try:
                article_id_processed = db_manager.add_article(book_id, article_title_for_db, app_logger=app.logger)
                app.logger.info(f"APP: Added/updated article '{article_title_for_db}' with ID {article_id_processed} for book ID {book_id}.")
                
                processed_text_sentences_data = []
                for p_idx, s_idx, en, zh in text_parser.parse_bilingual_file_content(raw_bilingual_text_content):
                    processed_text_sentences_data.append((p_idx, s_idx, en, zh))
                
                if processed_text_sentences_data:
                    sentences_added_count = db_manager.add_sentences_batch(article_id_processed, processed_text_sentences_data, app_logger=app.logger)
                
                if sentences_added_count > 0:
                    flash(f'Text file "{original_text_filename}" (processed as "{article_title_for_db}") for book "{book["title"]}" : {sentences_added_count} sentence pairs added.', 'success')
                    app.logger.info(f"APP: Added {sentences_added_count} sentence pairs for article ID {article_id_processed} ('{article_title_for_db}') in book {book_id}.")
                else:
                    flash(f'Text file "{original_text_filename}" (processed as "{article_title_for_db}") for book "{book["title"]}": no valid sentence pairs found.', 'warning')
                    app.logger.warning(f"APP: No valid sentence pairs found in '{original_text_filename}' (for article '{article_title_for_db}', ID {article_id_processed}, book {book_id}).")
            
            except Exception as e:
                app.logger.error(f"APP: Error processing text file {original_text_filename} (for article '{article_title_for_db}', book {book_id}): {e}", exc_info=True)
                flash(f'Error processing text file "{original_text_filename}" for book "{book["title"]}": {str(e)}', 'danger')
                return redirect(url_for('book_detail_page', book_id=book_id))
        else: 
            flash('Invalid text file type.', 'danger')
            app.logger.warning(f"APP: Invalid text file type uploaded for book {book_id}: {text_file.filename if text_file else 'None'}")
            return redirect(url_for('book_detail_page', book_id=book_id))

        # --- Audio Processing Decision ---
        if article_id_processed and sentences_added_count > 0:
            if use_tts_checked:
                app.logger.info(f"APP: TTS checkbox is checked. Processing audio using TTS for article ID {article_id_processed}.")
                # Pass the app instance (self) to audio_processor for config and logger
                tts_result = audio_processor.process_article_with_tts(
                    article_id_processed,
                    raw_bilingual_text_content,
                    article_safe_stem_for_files,
                    app # Passing the Flask app instance
                )
                if tts_result and tts_result.get("message"):
                    flash(tts_result["message"], tts_result.get("message_category", "info"))
                # No explicit redirect here, success/failure handled by flash from tts_result

            elif 'audio_file' in request.files: # TTS not checked, process uploaded audio file
                audio_file = request.files['audio_file']
                if audio_file and audio_file.filename != '':
                    if allowed_audio_file(audio_file.filename):
                        # ... (existing Aeneas call logic) ...
                        app.logger.info(f"APP: Processing Aeneas audio alignment for article ID {article_id_processed}...")
                        aeneas_srt_path = _process_audio_alignment(
                            article_id_processed,
                            audio_file,
                            raw_bilingual_text_content,
                            article_safe_stem_for_files
                        )
                        # _process_audio_alignment already flashes messages
                    else:
                        flash(f'Invalid audio file type: "{audio_file.filename}". Supported: {ALLOWED_AUDIO_EXTENSIONS}', 'warning')
                        app.logger.warning(f"APP: Invalid audio file type uploaded for book {book_id}: {audio_file.filename}")
                else: 
                    flash("No audio file uploaded and 'Use TTS' was not selected. Only text processed.", "info")
                    app.logger.info(f"APP: Article {article_id_processed} text processed. No audio file and TTS not selected.")
            else:
                flash("No audio file uploaded and 'Use TTS' was not selected. Only text processed.", "info")
                app.logger.info(f"APP: Article {article_id_processed} text processed. No audio file and TTS not selected.")
        elif article_id_processed and sentences_added_count == 0:
            app.logger.info(f"APP: No sentences were added for article {article_id_processed}. Skipping audio processing stage.")
            # Flash message for no sentences already handled.
        
        return redirect(url_for('book_detail_page', book_id=book_id))

    # ... (GET request part of book_detail_page remains the same) ...
    articles_for_book = []
    currently_reading_article_id = None
    try:
        articles_for_book = db_manager.get_articles_for_book(book_id, app_logger=app.logger)
        most_recent_location = db_manager.get_most_recent_reading_location_for_book(book_id, app_logger=app.logger)
        if most_recent_location:
            currently_reading_article_id = most_recent_location['article_id']
    except Exception as e:
        app.logger.error(f"APP: Error fetching articles or reading location for book ID {book_id}: {e}", exc_info=True)
        flash(f"Could not retrieve articles or reading status for book '{book['title']}'.", "danger")
        
    return render_template('book_detail.html',
                           book=book,
                           articles=articles_for_book,
                           currently_reading_article_id=currently_reading_article_id)

    # GET request (no change to this part of the function)
    articles_for_book = []
    currently_reading_article_id = None
    try:
        articles_for_book = db_manager.get_articles_for_book(book_id)
        most_recent_location = db_manager.get_most_recent_reading_location_for_book(book_id, app_logger=app.logger)
        if most_recent_location:
            currently_reading_article_id = most_recent_location['article_id']
            app.logger.info(f"APP: For book {book_id}, currently reading article ID is {currently_reading_article_id}")
    except Exception as e:
        app.logger.error(f"APP: Error fetching articles or reading location for book ID {book_id}: {e}", exc_info=True)
        flash(f"Could not retrieve articles or reading status for book '{book['title']}'.", "danger")
        
    return render_template('book_detail.html',
                           book=book,
                           articles=articles_for_book,
                           currently_reading_article_id=currently_reading_article_id)

# ... (rest of app.py: align_audio_for_article, view_article, save_reading_location, download_mp3_for_article, serve_mp3_part) ...
# The deferred align_audio_for_article route might also need a TTS checkbox if you want that option there too.
# For now, it will remain Aeneas-only.

@app.route('/article/<int:article_id>/align_audio', methods=['GET', 'POST'])
def align_audio_for_article(article_id):
    article = db_manager.get_article_by_id(article_id)
    if not article:
        flash('Article not found.', 'danger')
        app.logger.warning(f"APP: Attempt to align audio for non-existent article ID: {article_id}")
        return redirect(url_for('list_books_page'))
    
    book = db_manager.get_book_by_id(article['book_id']) if article['book_id'] else None
    
    article_title_from_db = article['filename'] # This is the user-facing title (stem of original txt)
    article_safe_stem_for_files = secure_filename(article_title_from_db)
    
    if request.method == 'POST':
        if 'audio_file' not in request.files:
            flash('No audio file part.', 'danger')
            return redirect(url_for('align_audio_for_article', article_id=article_id))
        audio_file = request.files['audio_file']
        if audio_file.filename == '':
            flash('No audio file selected.', 'danger')
            return redirect(url_for('align_audio_for_article', article_id=article_id))

        if audio_file and allowed_audio_file(audio_file.filename):
            app.logger.info(f"APP: Processing deferred AENEAS audio alignment for article ID {article_id} ('{article_title_from_db}'). English sentences will be fetched from DB.")
            # For deferred alignment, we pass None for original_bilingual_text_content_string
            # _process_audio_alignment will fetch sentences from DB.
            _process_audio_alignment(
                article_id,
                audio_file,
                None, # No raw text string needed, will pull from DB
                article_safe_stem_for_files
            )
            return redirect(url_for('view_article', article_id=article_id))
        else:
            flash(f'Invalid audio file type: "{audio_file.filename}". Supported: {ALLOWED_AUDIO_EXTENSIONS}', 'warning')
            app.logger.warning(f"APP: Invalid audio file type for deferred Aeneas alignment: {audio_file.filename}")
        return redirect(url_for('align_audio_for_article', article_id=article_id))

    # GET request
    return render_template('align_audio.html', article_id=article_id, article_filename=article_title_from_db, book=book)


# ... (view_article, save_reading_location, download_mp3_for_article, serve_mp3_part remain unchanged for now)

@app.route('/article/<int:article_id>')
def view_article(article_id):
    # ... (no change)
    app.logger.debug(f"APP: Attempting to view article ID: {article_id}")
    article_data = db_manager.get_article_by_id(article_id) 
    if not article_data:
        flash('Article not found.', 'danger')
        app.logger.warning(f"APP: Article ID {article_id} not found for viewing.")
        return redirect(url_for('list_books_page'))

    book = None
    if article_data['book_id']:
        book = db_manager.get_book_by_id(article_data['book_id'])
    if not book and article_data['book_id']: 
        app.logger.warning(f"APP: Book ID {article_data['book_id']} for article {article_id} not found. Article might be orphaned.")
        flash(f"Warning: The book associated with article '{article_data['filename']}' could not be found.", "warning")

    article_filename = article_data['filename']
    try:
        sentences_from_db = db_manager.get_sentences_for_article(article_id)
    except Exception as e:
        app.logger.error(f"APP: Error fetching sentences for article {article_id} ('{article_filename}'): {e}", exc_info=True)
        flash(f"Error retrieving content for article '{article_filename}'.", "danger")
        return redirect(url_for('list_books_page')) 
    
    structured_article_content = []
    current_paragraph_db_index = -1 
    current_paragraph_sentences = []
    has_timestamps = False 

    for sentence_row in sentences_from_db:
        if sentence_row['paragraph_index'] != current_paragraph_db_index:
            if current_paragraph_sentences:
                structured_article_content.append(current_paragraph_sentences)
            current_paragraph_sentences = []
            current_paragraph_db_index = sentence_row['paragraph_index']
        
        sentence_pair = {
            'english': sentence_row['english_text'],
            'chinese': sentence_row['chinese_text'],
            'start_time_ms': sentence_row['start_time_ms'],
            'end_time_ms': sentence_row['end_time_ms'],
            'paragraph_index': sentence_row['paragraph_index'], 
            'sentence_index_in_paragraph': sentence_row['sentence_index_in_paragraph'],
            'audio_part_index': sentence_row['audio_part_index'], 
            'start_time_in_part_ms': sentence_row['start_time_in_part_ms'], 
            'end_time_in_part_ms': sentence_row['end_time_in_part_ms'] 
        }
        current_paragraph_sentences.append(sentence_pair)
        
        if sentence_row['start_time_ms'] is not None and sentence_row['end_time_ms'] is not None:
            has_timestamps = True
            
    if current_paragraph_sentences: 
        structured_article_content.append(current_paragraph_sentences)
    
    reading_location_from_db = db_manager.get_reading_location(article_id, app_logger=app.logger)
    reading_location_for_template = dict(reading_location_from_db) if reading_location_from_db else None

    article_audio_part_checksums_str = None
    try:
        article_audio_part_checksums_str = article_data['audio_part_checksums']
    except KeyError: 
        app.logger.warning(f"APP: 'audio_part_checksums' key missing from article_data for article {article_id}. This might indicate a DB schema issue or an old record.")
        article_audio_part_checksums_str = None
    
    app.logger.debug(f"APP: Rendering article.html for ID {article_id}. `has_timestamps` is: {has_timestamps}. Reading location: {reading_location_for_template}")
    app.logger.debug(f"APP: Article data for template: num_audio_parts={article_data['num_audio_parts']}, mp3_parts_folder_path='{article_data['mp3_parts_folder_path']}', audio_part_checksums='{str(article_audio_part_checksums_str)[:30] if article_audio_part_checksums_str else 'None'}...'")
    
    return render_template('article.html',
                           article=article_data, 
                           book=book, 
                           structured_article=structured_article_content,
                           has_timestamps=has_timestamps,
                           reading_location=reading_location_for_template,
                           article_audio_part_checksums=article_audio_part_checksums_str)


@app.route('/article/<int:article_id>/save_location', methods=['POST'])
def save_reading_location(article_id):
    # ... (no change)
    article = db_manager.get_article_by_id(article_id)
    if not article:
        app.logger.warning(f"APP: Attempt to save reading location for non-existent article ID: {article_id}")
        return jsonify({'status': 'error', 'message': 'Article not found'}), 404
    
    if not article['book_id']:
        app.logger.error(f"APP: Cannot save reading location for article {article_id} (title: '{article['filename']}') as it has no associated book_id.")
        return jsonify({'status': 'error', 'message': 'Article is not associated with a book.'}), 400
    
    book_id_for_location = article['book_id']
    data = request.get_json()
    if not data or 'paragraph_index' not in data or 'sentence_index_in_paragraph' not in data:
        app.logger.warning(f"APP: Invalid data for saving reading location for article {article_id}: {data}")
        return jsonify({'status': 'error', 'message': 'Missing paragraph or sentence index'}), 400
        
    p_idx = data.get('paragraph_index')
    s_idx = data.get('sentence_index_in_paragraph')

    try:
        p_idx = int(p_idx)
        s_idx = int(s_idx)
    except (ValueError, TypeError):
        app.logger.warning(f"APP: Invalid index types for saving reading location for article {article_id}: P:{p_idx}, S:{s_idx}")
        return jsonify({'status': 'error', 'message': 'Invalid index types'}), 400

    try:
        db_manager.set_reading_location(article_id, book_id_for_location, p_idx, s_idx, app_logger=app.logger)
        app.logger.info(f"APP: Successfully saved reading location for article {article_id} (book {book_id_for_location}) at P:{p_idx}, S:{s_idx}.")
        return jsonify({'status': 'success', 'message': 'Reading location saved.'})
    except Exception as e:
        app.logger.error(f"APP: Failed to save reading location for article {article_id} (book {book_id_for_location}): {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': f'Failed to save location: {str(e)}'}), 500

@app.route('/article/<int:article_id>/download_mp3')
def download_mp3_for_article(article_id):
    # ... (no change)
    article = db_manager.get_article_by_id(article_id)
    if not article:
        flash('Article not found.', 'danger')
        app.logger.warning(f"APP: Download MP3: Article ID {article_id} not found.")
        return redirect(url_for('list_books_page'))

    converted_mp3_path_str = article['converted_mp3_path']
    if not converted_mp3_path_str:
        flash('No converted MP3 file available for this article.', 'warning')
        app.logger.warning(f"APP: Download MP3: No converted_mp3_path for article ID {article_id}.")
        return redirect(url_for('view_article', article_id=article_id))

    mp3_file_path = Path(converted_mp3_path_str)
    if not mp3_file_path.is_file():
        flash('Converted MP3 file not found on server.', 'danger')
        app.logger.error(f"APP: Download MP3: File {mp3_file_path} not found for article ID {article_id}.")
        return redirect(url_for('view_article', article_id=article_id))

    directory = str(mp3_file_path.parent.resolve())
    filename = mp3_file_path.name
    original_text_filename_stem = Path(article['filename']).stem
    download_name = f"{original_text_filename_stem}.mp3"

    app.logger.info(f"APP: Serving MP3 file: {filename} from dir: {directory} for article ID {article_id} as {download_name}")
    return send_from_directory(directory, filename, as_attachment=True, download_name=download_name)


@app.route('/article/<int:article_id>/serve_mp3_part/<int:part_index>')
def serve_mp3_part(article_id, part_index):
    # ... (no change)
    article = db_manager.get_article_by_id(article_id)
    if not article or not article['mp3_parts_folder_path'] or article['num_audio_parts'] is None or part_index < 0 or part_index >= article['num_audio_parts']: 
        app.logger.warning(f"APP: Serve MP3 part: Invalid request for article {article_id}, part {part_index}.")
        return jsonify({'status': 'error', 'message': 'Audio part not found or invalid index.'}), 404

    parts_folder = Path(article['mp3_parts_folder_path'])
    article_filename_base = secure_filename(Path(article['filename']).stem)
    part_filename = f"{article_filename_base}_part_{part_index}.mp3"
    part_path = parts_folder / part_filename

    if not part_path.is_file():
        app.logger.error(f"APP: Serve MP3 part: File {part_path} not found for article {article_id}, part {part_index}.")
        return jsonify({'status': 'error', 'message': 'Audio part file not found on server.'}), 404

    app.logger.info(f"APP: Serving MP3 part: {part_filename} from dir: {parts_folder} for article ID {article_id}")
    
    should_download = request.args.get('download', 'false').lower() == 'true'
    
    download_name = f"{Path(article['filename']).stem}_part_{part_index + 1}.mp3" 

    return send_from_directory(str(parts_folder.resolve()), part_filename, 
                               as_attachment=should_download, download_name=download_name if should_download else None)


if __name__ == '__main__':
    app.logger.info(f"Starting Flask development server. Debug mode: {app.debug}")
    aeneas_path_env = os.environ.get("AENEAS_PYTHON_PATH")
    if aeneas_path_env:
       app.config['AENEAS_PYTHON_PATH'] = aeneas_path_env
    app.logger.info(f"AENEAS_PYTHON_PATH is set to: {app.config['AENEAS_PYTHON_PATH']}")
    
    # Check Kokoro voice config one last time before run
    if tts_utils.kokoro_available and \
       not tts_utils.check_voices_configured(app.config['KOKORO_MANDARIN_VOICE'], app.config['KOKORO_ENGLISH_VOICE'], app.logger):
        app.logger.warning("#####################################################################")
        app.logger.warning("## KOKORO VOICES ARE LIKELY MISCONFIGURED IN app.py!                 ##")
        app.logger.warning("## Please set KOKORO_MANDARIN_VOICE and KOKORO_ENGLISH_VOICE.        ##")
        app.logger.warning("## TTS functionality will likely fail until this is corrected.       ##")
        app.logger.warning("#####################################################################")

    app.run(debug=True, host='0.0.0.0', port=5002, ssl_context='adhoc')
    app.logger.info("Flask app is now running with ad-hoc SSL (HTTPS).")