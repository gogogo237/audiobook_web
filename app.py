# bilingual_app/app.py
import os
import tempfile
import shutil 
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
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
app.config['CONVERTED_AUDIO_FOLDER'] = os.path.join(app.instance_path, 'converted_audio') # For persistent MP3s

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
            
            # Store persistent MP3 path in DB
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
                return bilingual_srt_generated_path_str
            else:
                app.logger.warning(f"APP: Failed to generate final bilingual SRT for article {article_id}.")
                flash("Failed to generate the final bilingual SRT file.", "warning")
                return None
    except Exception as e:
        app.logger.error(f"APP: Error during audio alignment for article {article_id}: {e}", exc_info=True)
        flash(f"An error occurred during audio processing: {str(e)}", "danger")
    return None


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No text file part.', 'danger')
            return redirect(request.url)
        
        text_file = request.files['file']
        if text_file.filename == '':
            flash('No text file selected.', 'danger')
            return redirect(request.url)
        
        article_id = None
        raw_bilingual_text_content = None

        if text_file and allowed_text_file(text_file.filename):
            text_filename_secure = secure_filename(text_file.filename)
            
            try:
                raw_bilingual_text_content = text_file.stream.read().decode('utf-8')
                text_file.stream.seek(0)
            except UnicodeDecodeError:
                app.logger.error(f"UnicodeDecodeError for text file {text_filename_secure}.", exc_info=True)
                flash('Text file not UTF-8 encoded.', 'danger')
                return redirect(request.url)
            except Exception as e:
                app.logger.error(f"Error reading text file stream for {text_filename_secure}: {e}", exc_info=True)
                flash(f'Error reading text file: {str(e)}', 'danger')
                return redirect(request.url)

            if not raw_bilingual_text_content.strip():
                flash(f'Text file "{text_filename_secure}" is empty.', 'warning')
                app.logger.warning(f"APP: Uploaded text file '{text_filename_secure}' is empty.")
                return redirect(request.url)

            try:
                article_id = db_manager.add_article(text_filename_secure)
                app.logger.info(f"APP: Added/updated article '{text_filename_secure}' with ID {article_id}.")
                
                processed_text_sentences_data = []
                for p_idx, s_idx, en, zh in text_parser.parse_bilingual_file_content(raw_bilingual_text_content):
                    processed_text_sentences_data.append((p_idx, s_idx, en, zh))
                
                sentences_added_count = 0
                if processed_text_sentences_data:
                    sentences_added_count = db_manager.add_sentences_batch(article_id, processed_text_sentences_data)
                
                if sentences_added_count > 0:
                    flash(f'Text file "{text_filename_secure}" processed. {sentences_added_count} sentence pairs added.', 'success')
                    app.logger.info(f"APP: Added {sentences_added_count} sentence pairs for article ID {article_id}.")
                else:
                    flash(f'Text file "{text_filename_secure}" processed, but no valid sentence pairs found.', 'warning')
                    app.logger.warning(f"APP: No valid sentence pairs found in '{text_filename_secure}' for article ID {article_id}.")
            
            except Exception as e:
                app.logger.error(f"APP: Error processing text file {text_filename_secure}: {e}", exc_info=True)
                flash(f'Error processing text file "{text_filename_secure}": {str(e)}', 'danger')
                return redirect(request.url)
        else:
            flash('Invalid text file type.', 'danger')
            app.logger.warning(f"APP: Invalid text file type uploaded: {text_file.filename if text_file else 'None'}")
            return redirect(request.url)

        if article_id and 'audio_file' in request.files:
            audio_file = request.files['audio_file']
            if audio_file and audio_file.filename != '':
                if allowed_audio_file(audio_file.filename):
                    if not raw_bilingual_text_content: 
                         app.logger.error(f"APP: Internal error: Text content (raw_bilingual_text_content) not available for audio processing for article ID {article_id}.")
                         flash("Internal error: Text content not available for audio processing.", "danger")
                    else:
                        article_filename_base = Path(text_filename_secure).stem
                        app.logger.info(f"APP: Processing audio alignment for article ID {article_id} using uploaded text content.")
                        _process_audio_alignment(
                            article_id, 
                            audio_file, 
                            raw_bilingual_text_content,
                            article_filename_base
                        )
                else:
                    flash(f'Invalid audio file type: "{audio_file.filename}". Supported: {ALLOWED_AUDIO_EXTENSIONS}', 'warning')
                    app.logger.warning(f"APP: Invalid audio file type uploaded: {audio_file.filename}")
        
        return redirect(url_for('index'))

    try:
        articles = db_manager.get_all_articles()
    except Exception as e:
        app.logger.error(f"APP: Error fetching articles for index page: {e}", exc_info=True)
        flash("Could not retrieve articles from database.", "danger")
        articles = []
        
    return render_template('index.html', articles=articles)


@app.route('/article/<int:article_id>/align_audio', methods=['GET', 'POST'])
def align_audio_for_article(article_id):
    article_filename = db_manager.get_article_filename(article_id) 
    if not article_filename:
        flash('Article not found.', 'danger')
        app.logger.warning(f"APP: Attempt to align audio for non-existent article ID: {article_id}")
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        if 'audio_file' not in request.files:
            flash('No audio file part.', 'danger')
            return redirect(url_for('align_audio_for_article', article_id=article_id))
        audio_file = request.files['audio_file']
        if audio_file.filename == '':
            flash('No audio file selected.', 'danger')
            return redirect(url_for('align_audio_for_article', article_id=article_id))

        if audio_file and allowed_audio_file(audio_file.filename):
            app.logger.info(f"APP: Processing deferred audio alignment for article ID {article_id}. English sentences will be fetched from DB.")
            _process_audio_alignment(
                article_id,
                audio_file,
                None, 
                Path(article_filename).stem
            )
            return redirect(url_for('view_article', article_id=article_id))
        else:
            flash(f'Invalid audio file type: "{audio_file.filename}". Supported: {ALLOWED_AUDIO_EXTENSIONS}', 'warning')
            app.logger.warning(f"APP: Invalid audio file type for deferred alignment: {audio_file.filename}")
        return redirect(url_for('align_audio_for_article', article_id=article_id))

    return render_template('align_audio.html', article_id=article_id, article_filename=article_filename)


@app.route('/article/<int:article_id>')
def view_article(article_id):
    app.logger.debug(f"APP: Attempting to view article ID: {article_id}")
    article_filename = db_manager.get_article_filename(article_id)
    if not article_filename:
        flash('Article not found.', 'danger')
        app.logger.warning(f"APP: Article ID {article_id} not found for viewing.")
        return redirect(url_for('index'))

    try:
        sentences_from_db = db_manager.get_sentences_for_article(article_id)
        if app.logger.level <= logging.DEBUG and sentences_from_db: # Check app.logger not app_logger
            app.logger.debug(f"APP: Fetched {len(sentences_from_db)} sentences from DB for article {article_id}. First sentence data: {dict(sentences_from_db[0]) if sentences_from_db else 'N/A'}")
    except Exception as e:
        app.logger.error(f"APP: Error fetching sentences for article {article_id} ('{article_filename}'): {e}", exc_info=True)
        flash(f"Error retrieving content for article '{article_filename}'.", "danger")
        return redirect(url_for('index'))
    
    structured_article = []
    current_paragraph_index = -1
    current_paragraph_sentences = []
    has_timestamps = False 

    for sentence_row in sentences_from_db:
        if sentence_row['paragraph_index'] != current_paragraph_index:
            if current_paragraph_sentences:
                structured_article.append(current_paragraph_sentences)
            current_paragraph_sentences = []
            current_paragraph_index = sentence_row['paragraph_index']
        
        sentence_pair = {
            'english': sentence_row['english_text'],
            'chinese': sentence_row['chinese_text'],
            'start_time_ms': sentence_row['start_time_ms'],
            'end_time_ms': sentence_row['end_time_ms']
        }
        current_paragraph_sentences.append(sentence_pair)

        if sentence_row['start_time_ms'] is not None and sentence_row['end_time_ms'] is not None:
            has_timestamps = True
            
    if current_paragraph_sentences: 
        structured_article.append(current_paragraph_sentences)

    if not sentences_from_db and not structured_article:
        app.logger.info(f"APP: Article {article_id} ('{article_filename}') has no sentences in DB to display.")
    
    if not has_timestamps and sentences_from_db: 
        app.logger.warning(f"APP: Article {article_id} ('{article_filename}') has sentences, but `has_timestamps` is false. No valid start/end times found in sentence data.")
        if app.logger.level <= logging.DEBUG and sentences_from_db: # Check app.logger not app_logger
            app.logger.debug(f"APP: Sample of first sentence pair passed to template for article {article_id}: "
                             f"{structured_article[0][0] if structured_article and structured_article[0] else 'N/A'}")

    app.logger.debug(f"APP: Rendering article.html for ID {article_id}. `has_timestamps` is: {has_timestamps}")
    return render_template('article.html',
                           article_id=article_id,
                           article_filename=article_filename,
                           structured_article=structured_article,
                           has_timestamps=has_timestamps)


if __name__ == '__main__':
    app.logger.info(f"Starting Flask development server. Debug mode: {app.debug}")
    aeneas_path_env = os.environ.get("AENEAS_PYTHON_PATH")
    if aeneas_path_env:
       app.config['AENEAS_PYTHON_PATH'] = aeneas_path_env
    app.logger.info(f"AENEAS_PYTHON_PATH is set to: {app.config['AENEAS_PYTHON_PATH']}")
    
    app.run(debug=True, host='0.0.0.0', port=5000)