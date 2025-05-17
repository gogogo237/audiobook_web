import os
import tempfile
import shutil 
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import db_manager  
import text_parser 
import audio_processor 

import logging
from logging.handlers import RotatingFileHandler

# Configuration
UPLOAD_FOLDER = 'uploads' 
ALLOWED_TEXT_EXTENSIONS = {'txt'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'mp4', 'wav', 'm4a'} 

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'your_very_secret_key_here_please_change_me'
app.config['AENEAS_PYTHON_PATH'] = r"C:\Program Files\Python39\python.exe" 
app.config['PROCESSED_SRT_FOLDER'] = os.path.join(app.instance_path, 'processed_srts')
app.config['TEMP_FILES_FOLDER'] = os.path.join(app.instance_path, 'temp_files')
app.config['CONVERTED_AUDIO_FOLDER'] = os.path.join(app.instance_path, 'converted_audio')
app.config['MP3_PARTS_FOLDER'] = os.path.join(app.instance_path, 'mp3_parts') # New folder for split MP3s
app.config['MAX_AUDIO_PART_SIZE_MB'] = 20 # Max size for MP3 parts (iOS target)

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
file_handler.setLevel(logging.DEBUG) 
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.DEBUG) 
app.logger.info('Application startup: File logging configured.')


# --- Database Initialization ---
with app.app_context():
    db_manager.init_db(app) 

def allowed_text_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_TEXT_EXTENSIONS

def allowed_audio_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS

def _ensure_dirs_exist():
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    if not os.path.exists(app.config['PROCESSED_SRT_FOLDER']):
        os.makedirs(app.config['PROCESSED_SRT_FOLDER'])
    if not os.path.exists(app.config['TEMP_FILES_FOLDER']):
        os.makedirs(app.config['TEMP_FILES_FOLDER'])
    if not os.path.exists(app.config['CONVERTED_AUDIO_FOLDER']):
        os.makedirs(app.config['CONVERTED_AUDIO_FOLDER'])
    if not os.path.exists(app.config['MP3_PARTS_FOLDER']): # Ensure MP3 parts folder exists
        os.makedirs(app.config['MP3_PARTS_FOLDER'])

_ensure_dirs_exist()

def _process_audio_alignment(article_id, 
                             audio_file_storage, 
                             original_bilingual_text_content_string,
                             article_filename_base): 
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
                app.logger.info(f"APP: Extracting English sentences from provided raw bilingual text for article {article_id}...")
                english_sentences_list_for_aeneas = audio_processor.extract_english_sentences_for_aeneas(
                    original_bilingual_text_content_string, logger=app.logger
                )
            else:
                app.logger.info(f"APP: Fetching English sentences from database for article {article_id} (deferred alignment)...")
                english_sentences_list_for_aeneas = db_manager.get_english_sentences_for_article(article_id)
            
            if not english_sentences_list_for_aeneas:
                flash("No English sentences available (from text or DB) for alignment.", "warning")
                app.logger.warning(f"APP: Aborting audio alignment for article {article_id}: No English sentences.")
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
                 flash(f"Aligned audio & updated {updated_count} sentence timestamps for {audio_filename_secure}.", "success")

            full_sentences_data_from_db = db_manager.get_sentences_for_article(article_id)
            bilingual_sentences_for_srt_gen = [
                {'english_text': s['english_text'], 'chinese_text': s['chinese_text']} 
                for s in full_sentences_data_from_db
            ]
            final_bilingual_srt_filename = f"{article_filename_base}_bilingual.srt"
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
                app.logger.info(f"APP: Generated final bilingual SRT for article {article_id} at {bilingual_srt_generated_path_str}")
            else:
                app.logger.warning(f"APP: Failed to generate final bilingual SRT for article {article_id}.")
                flash("Failed to generate the final bilingual SRT file.", "warning")
                return None

            # --- MP3 Splitting Logic (after main processing) ---
            if converted_mp3_path_str:
                original_mp3_size_bytes = Path(converted_mp3_path_str).stat().st_size
                max_size_bytes = app.config['MAX_AUDIO_PART_SIZE_MB'] * 1024 * 1024

                if original_mp3_size_bytes > max_size_bytes:
                    app.logger.info(f"APP: Original MP3 {converted_mp3_path_str} size {original_mp3_size_bytes} > {max_size_bytes}. Attempting to split for article {article_id}.")
                    
                    article_mp3_parts_dir_path = Path(app.config['MP3_PARTS_FOLDER']) / str(article_id)
                    article_mp3_parts_dir_path.mkdir(parents=True, exist_ok=True)

                    sentence_db_ids_ordered = db_manager.get_sentence_ids_for_article_in_order(article_id, app_logger=app.logger)

                    if len(sentence_db_ids_ordered) != len(srt_timestamps):
                        app.logger.error(f"APP: Mismatch: DB sentence count ({len(sentence_db_ids_ordered)}) vs SRT timestamp count ({len(srt_timestamps)}) for article {article_id}. Skipping MP3 splitting.")
                    else:
                        sentences_info_for_splitting = []
                        for i, db_id_dict in enumerate(sentence_db_ids_ordered):
                            sentences_info_for_splitting.append({
                                'id': db_id_dict['id'], 
                                'original_start_ms': srt_timestamps[i][0],
                                'original_end_ms': srt_timestamps[i][1]
                            })
                        
                        split_details = audio_processor.split_mp3_by_sentence_duration(
                            original_mp3_path=converted_mp3_path_str,
                            sentences_info=sentences_info_for_splitting,
                            max_part_size_bytes=max_size_bytes,
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
                            app.logger.info(f"APP: Successfully split MP3 for article {article_id} into {split_details['num_parts']} parts. Stored in {article_mp3_parts_dir_path}. Checksums {'processed' if part_checksums_list else 'not available'}.")
                            flash(f"Audio processed. Original MP3 was large and split into {split_details['num_parts']} parts for compatibility.", "info")
                        else:
                            app.logger.warning(f"APP: MP3 splitting failed or resulted in no parts for article {article_id}. Clearing any previous part info.")
                            db_manager.clear_article_mp3_parts_info(article_id, app_logger=app.logger) 
                            flash("Audio processed. Original MP3 was large, but splitting failed or produced no parts.", "warning")
                else: 
                    app.logger.info(f"APP: Original MP3 {converted_mp3_path_str} size {original_mp3_size_bytes} <= {max_size_bytes}. No splitting needed. Clearing any previous part info for article {article_id}.")
                    db_manager.clear_article_mp3_parts_info(article_id, app_logger=app.logger) 
            
            return bilingual_srt_generated_path_str 
    except Exception as e:
        app.logger.error(f"APP: Error during audio alignment for article {article_id}: {e}", exc_info=True)
        flash(f"An error occurred during audio processing: {str(e)}", "danger")
    return None


@app.route('/')
def home_redirect():
    return redirect(url_for('list_books_page'))

@app.route('/books', methods=['GET', 'POST'])
def list_books_page():
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
    book = db_manager.get_book_by_id(book_id)
    if not book:
        flash('Book not found.', 'danger')
        app.logger.warning(f"APP: Book ID {book_id} not found for viewing.")
        return redirect(url_for('list_books_page'))

    if request.method == 'POST': 
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

        if text_file and allowed_text_file(text_file.filename):
            original_text_filename = text_file.filename
            article_title_for_db = Path(original_text_filename).stem
            article_safe_stem_for_files = secure_filename(article_title_for_db)
            
            try:
                raw_bilingual_text_content = text_file.stream.read().decode('utf-8')
                text_file.stream.seek(0)
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
                
                sentences_added_count = 0
                if processed_text_sentences_data:
                    sentences_added_count = db_manager.add_sentences_batch(article_id_processed, processed_text_sentences_data)
                
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

        if article_id_processed and 'audio_file' in request.files:
            audio_file = request.files['audio_file']
            if audio_file and audio_file.filename != '':
                if allowed_audio_file(audio_file.filename):
                    if not raw_bilingual_text_content: 
                         app.logger.error(f"APP: Internal error: Text content not available for audio processing for article ID {article_id_processed}, book {book_id}.")
                         flash("Internal error: Text content not available for audio processing.", "danger")
                    elif not article_safe_stem_for_files: 
                         app.logger.error(f"APP: Internal error: Article file stem not available for audio processing for article ID {article_id_processed}, book {book_id}.")
                         flash("Internal error: Article file stem not available for audio processing.", "danger")
                    else:
                        app.logger.info(f"APP: Processing audio alignment for article ID {article_id_processed} ('{article_title_for_db}') in book {book_id} using uploaded text content.")
                        _process_audio_alignment(
                            article_id_processed, 
                            audio_file, 
                            raw_bilingual_text_content,
                            article_safe_stem_for_files
                        )
                else:
                    flash(f'Invalid audio file type: "{audio_file.filename}". Supported: {ALLOWED_AUDIO_EXTENSIONS}', 'warning')
                    app.logger.warning(f"APP: Invalid audio file type uploaded for book {book_id}: {audio_file.filename}")
        
        return redirect(url_for('book_detail_page', book_id=book_id))

    # GET request
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


@app.route('/article/<int:article_id>/align_audio', methods=['GET', 'POST'])
def align_audio_for_article(article_id):
    article = db_manager.get_article_by_id(article_id) 
    if not article:
        flash('Article not found.', 'danger')
        app.logger.warning(f"APP: Attempt to align audio for non-existent article ID: {article_id}")
        return redirect(url_for('list_books_page'))
    
    book = db_manager.get_book_by_id(article['book_id']) if article['book_id'] else None
    
    article_title_from_db = article['filename']
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
            app.logger.info(f"APP: Processing deferred audio alignment for article ID {article_id} ('{article_title_from_db}'). English sentences will be fetched from DB.")
            _process_audio_alignment(
                article_id,
                audio_file,
                None, 
                article_safe_stem_for_files
            )
            return redirect(url_for('view_article', article_id=article_id))
        else:
            flash(f'Invalid audio file type: "{audio_file.filename}". Supported: {ALLOWED_AUDIO_EXTENSIONS}', 'warning')
            app.logger.warning(f"APP: Invalid audio file type for deferred alignment: {audio_file.filename}")
        return redirect(url_for('align_audio_for_article', article_id=article_id))

    return render_template('align_audio.html', article_id=article_id, article_filename=article_title_from_db, book=book)


@app.route('/article/<int:article_id>')
def view_article(article_id):
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
    except KeyError: # Should not happen if column is selected, but as a fallback
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
    
    # ORIGINAL LINE:
    # app.run(debug=True, host='0.0.0.0', port=5000) 

    # MODIFIED LINE FOR AD-HOC SSL:
    app.run(debug=True, host='0.0.0.0', port=5000, ssl_context='adhoc')
    app.logger.info("Flask app is now running with ad-hoc SSL (HTTPS).")