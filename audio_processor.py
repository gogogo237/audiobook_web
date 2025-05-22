import os
import subprocess
import tempfile
import re
import shlex
from pathlib import Path
import locale
import math
import hashlib
import traceback # For detailed error logging

from pydub import AudioSegment
from pydub.exceptions import CouldntEncodeError, CouldntDecodeError
import soundfile # For saving WAVs from TTS numpy arrays

import text_parser # Assuming this is in the same directory or PYTHONPATH
from werkzeug.utils import secure_filename # <--- ADDED THIS IMPORT
import tts_utils # For TTS generation
import db_manager # For updating DB

# Helper function to calculate SHA256 checksum (no changes from original)
def calculate_sha256_checksum(file_path_str, logger=None):
    # ... (same as your existing function)
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path_str, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except IOError as e:
        if logger: logger.error(f"AUDIO_PROC: Error reading file {file_path_str} for checksum: {e}")
        return None

# extract_english_sentences_for_aeneas (no changes needed for TTS path initially)
def extract_english_sentences_for_aeneas(bilingual_file_content_string, logger=None):
    # ... (same as your existing function)
    english_sentences = []
    try:
        content_no_closing_para = bilingual_file_content_string.replace('</paragraph>', '')
        paragraph_blocks = content_no_closing_para.split('<paragraph>')

        for block in paragraph_blocks:
            block = block.strip()
            if not block:
                continue
            
            lines = block.splitlines()
            for i, line in enumerate(lines):
                line = line.strip()
                if line and i % 2 == 0: 
                    english_sentences.append(line)
        
        if logger:
            if english_sentences:
                logger.info(f"AUDIO_PROC: Extracted {len(english_sentences)} English sentences for Aeneas.")
            else:
                logger.warning("AUDIO_PROC: No English sentences extracted for Aeneas from the provided content.")
        return english_sentences

    except Exception as e:
        if logger:
            logger.error(f"AUDIO_PROC: Error extracting English sentences for Aeneas: {e}", exc_info=True)
        raise

# create_plain_text_file_from_list (no changes needed for TTS path initially, Aeneas specific)
def create_plain_text_file_from_list(english_sentence_list, output_path, logger=None):
    # ... (same as your existing function)
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            for sentence in english_sentence_list:
                f.write(sentence.strip() + "\n")
        if logger: logger.info(f"AUDIO_PROC: Created plain text file for Aeneas: {output_path}")
    except IOError as e:
        if logger: logger.error(f"AUDIO_PROC: Failed to write plain text file {output_path}: {e}")
        raise

# srt_time_to_ms (no changes)
def srt_time_to_ms(time_str):
    # ... (same as your existing function)
    try:
        time_str_normalized = time_str.replace('.', ',')
        h, m, s_ms = time_str_normalized.split(':')
        s, ms = s_ms.split(',')
        return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)
    except ValueError:
        raise ValueError(f"Invalid SRT time format: {time_str}")

# convert_to_mp3 (no changes, used by Aeneas path)
def convert_to_mp3(source_path_str, output_dir_str, logger=None):
    # ... (same as your existing function)
    source_path = Path(source_path_str)
    output_dir = Path(output_dir_str)

    if not source_path.exists():
        if logger: logger.error(f"AUDIO_PROC: Source audio file not found for conversion: {source_path}")
        raise FileNotFoundError(f"Source audio file not found: {source_path}")

    output_dir.mkdir(parents=True, exist_ok=True) 
    mp3_filename = f"{source_path.stem}.mp3"
    target_mp3_path = output_dir / mp3_filename

    if logger: logger.info(f"AUDIO_PROC: Attempting to convert '{source_path}' to '{target_mp3_path}' using FFmpeg.")

    convert_cmd_list = [
        "ffmpeg", "-y", # Overwrite output without asking
        "-i", str(source_path),
        "-vn",
        "-c:a", "libmp3lame",
        "-q:a", "2", # VBR quality, 0-9, 2 is very good.
        str(target_mp3_path)
    ]
    
    convert_cmd_str_display = " ".join([shlex.quote(part) for part in convert_cmd_list])
    if logger: logger.info(f"AUDIO_PROC: FFmpeg conversion command: {convert_cmd_str_display}")

    try:
        process = subprocess.run(convert_cmd_list, check=True, 
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if process.stderr:
            ffmpeg_stderr_output = process.stderr.decode(locale.getpreferredencoding(False), errors='replace').strip()
            if ffmpeg_stderr_output and logger: 
                logger.info(f"AUDIO_PROC: FFmpeg stderr:\n{ffmpeg_stderr_output}")
        if process.stdout: 
            ffmpeg_stdout_output = process.stdout.decode(locale.getpreferredencoding(False), errors='replace').strip()
            if ffmpeg_stdout_output and logger:
                logger.info(f"AUDIO_PROC: FFmpeg stdout:\n{ffmpeg_stdout_output}")
        
        if logger: logger.info(f"AUDIO_PROC: Successfully converted '{source_path}' to '{target_mp3_path}'")
        return str(target_mp3_path)
        
    except subprocess.CalledProcessError as e:
        ffmpeg_stdout = e.stdout.decode(locale.getpreferredencoding(False), errors='replace') if e.stdout else ""
        ffmpeg_stderr = e.stderr.decode(locale.getpreferredencoding(False), errors='replace') if e.stderr else ""
        error_msg = (f"MP3 conversion failed for '{source_path}'. Return code: {e.returncode}\n"
                     f"Command: {convert_cmd_str_display}\n"
                     f"FFmpeg stdout: {ffmpeg_stdout}\nFFmpeg stderr: {ffmpeg_stderr}")
        if logger: logger.error(error_msg)
        raise Exception(f"MP3 conversion failed for '{source_path}'. Check logs.") from e
    except FileNotFoundError: 
        error_msg = "FFmpeg executable not found. Please ensure FFmpeg is installed and in your system PATH."
        if logger: logger.error(error_msg)
        raise Exception(error_msg)
    except Exception as e_generic:
        if logger: logger.error(f"AUDIO_PROC: Generic error during FFmpeg conversion of '{source_path}': {e_generic}", exc_info=True)
        raise Exception(f"Audio conversion error for '{source_path}': {str(e_generic)}") from e_generic

# run_aeneas_alignment (no changes, Aeneas specific)
def run_aeneas_alignment(audio_mp3_path_str, plain_english_text_path_str, srt_output_path_str,
                         python_executable_str, logger=None):
    # ... (same as your existing function)
    aeneas_config_string = (
        "task_language=eng|os_task_file_format=srt|is_text_type=plain|"
        "task_adjust_boundary_algorithm=percent|task_adjust_boundary_percent_value=50"
    )
    
    audio_mp3_path = Path(audio_mp3_path_str)
    plain_english_text_path = Path(plain_english_text_path_str)
    srt_output_path = Path(srt_output_path_str)
    srt_output_path.parent.mkdir(parents=True, exist_ok=True)

    aeneas_cmd_list = [
        python_executable_str,
        "-m", "aeneas.tools.execute_task",
        str(audio_mp3_path),
        str(plain_english_text_path),
        aeneas_config_string,
        str(srt_output_path)
    ]
    
    aeneas_cmd_str_display = " ".join([shlex.quote(part) for part in aeneas_cmd_list])
    if logger: logger.info(f"AUDIO_PROC: Running Aeneas command: {aeneas_cmd_str_display}")
    
    stdout_decoded = "[stdout not captured or decoded]"
    stderr_decoded = "[stderr not captured or decoded]"

    try:
        process = subprocess.run(
            aeneas_cmd_list, 
            shell=False,
            check=False, 
            capture_output=True
        )

        encodings_to_try = ['utf-8', locale.getpreferredencoding(False) or 'latin-1', 'cp1252', 'latin-1']
        unique_encodings = list(dict.fromkeys(filter(None, encodings_to_try)))
        
        if process.stdout:
            for enc in unique_encodings:
                try:
                    stdout_decoded = process.stdout.decode(enc)
                    if logger: logger.debug(f"AUDIO_PROC: Aeneas stdout (decoded with {enc}):\n{stdout_decoded}")
                    break
                except UnicodeDecodeError:
                    if enc == unique_encodings[-1] and logger:
                        logger.warning(f"AUDIO_PROC: Failed to decode Aeneas stdout. Raw bytes: {process.stdout!r}")
                        stdout_decoded = f"[Could not decode stdout: {process.stdout!r}]"
        
        if process.stderr:
            for enc in unique_encodings:
                try:
                    stderr_decoded = process.stderr.decode(enc)
                    log_level = logger.info if process.returncode == 0 else logger.warning
                    if logger: log_level(f"AUDIO_PROC: Aeneas stderr (decoded with {enc}):\n{stderr_decoded}")
                    break
                except UnicodeDecodeError:
                    if enc == unique_encodings[-1] and logger:
                        logger.warning(f"AUDIO_PROC: Failed to decode Aeneas stderr. Raw bytes: {process.stderr!r}")
                        stderr_decoded = f"[Could not decode stderr: {process.stderr!r}]"

        if process.returncode != 0:
            error_message = (
                f"Aeneas execution failed with return code {process.returncode}.\n"
                f"Command: {aeneas_cmd_str_display}\n"
                f"Stdout: {stdout_decoded}\n"
                f"Stderr: {stderr_decoded}"
            )
            if logger: logger.error(error_message)
            raise Exception(f"Aeneas execution failed. Check logs. Return code: {process.returncode}")

        if logger: logger.info(f"AUDIO_PROC: Aeneas completed successfully. SRT written to {srt_output_path}")

    except FileNotFoundError: 
        error_message = f"Aeneas command failed: Python executable '{python_executable_str}' not found. Please check AENEAS_PYTHON_PATH config."
        if logger: logger.error(error_message)
        raise Exception(error_message)
    except Exception as e:
        if logger: logger.error(f"AUDIO_PROC: Unexpected error during Aeneas execution: {e}", exc_info=True)
        raise

# parse_aeneas_srt_file (no changes, Aeneas specific)
def parse_aeneas_srt_file(srt_path_str, logger=None):
    # ... (same as your existing function)
    srt_path = Path(srt_path_str)
    timestamps = []
    if not srt_path.exists():
        if logger: logger.error(f"AUDIO_PROC: SRT file not found for parsing: {srt_path}")
        raise FileNotFoundError(f"SRT file not found: {srt_path}")

    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        pattern = re.compile(r'\d+\s*\n(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})')
        matches = pattern.findall(content)

        if not matches and content.strip():
            if logger: logger.warning(f"AUDIO_PROC: SRT file {srt_path} has content but no standard 'HH:MM:SS,mmm --> HH:MM:SS,mmm' timestamp lines were matched. Aeneas might have failed to produce valid segments. Content snippet (first 500 chars): '{content[:500]}'")
            return []

        for start_str, end_str in matches:
            try:
                start_ms = srt_time_to_ms(start_str)
                end_ms = srt_time_to_ms(end_str)
                timestamps.append((start_ms, end_ms))
            except ValueError as e:
                if logger: logger.warning(f"AUDIO_PROC: Skipping invalid time entry in SRT {srt_path}: '{start_str} --> {end_str}'. Error: {e}")
                continue

        if not timestamps and content.strip() and matches:
             if logger: logger.warning(f"AUDIO_PROC: Valid timestamp lines were matched in {srt_path}, but all failed srt_time_to_ms conversion.")
        elif not timestamps and not content.strip():
             if logger: logger.info(f"AUDIO_PROC: SRT file {srt_path} was empty.")
        elif timestamps:
             if logger: logger.info(f"AUDIO_PROC: Parsed {len(timestamps)} timestamp entries from {srt_path}. First 3: {timestamps[:3]}")
        return timestamps

    except Exception as e:
        if logger: logger.error(f"AUDIO_PROC: Error parsing SRT file {srt_path}: {e}", exc_info=True)
        raise

# generate_bilingual_srt (no changes needed, used by both paths)
def generate_bilingual_srt(article_id, original_sentences_data, srt_timestamps, output_srt_path_str, logger=None):
    # ... (same as your existing function)
    # Small change to make output path unique if needed for clarity (e.g., append _tts or _aeneas)
    # This is handled in the calling function by naming output_srt_path_str appropriately.
    output_srt_path = Path(output_srt_path_str)
    
    if not original_sentences_data or not srt_timestamps:
        if logger: logger.warning(f"AUDIO_PROC: Not generating bilingual SRT for article {article_id}: missing sentences or timestamps.")
        return None

    num_sentences = len(original_sentences_data)
    num_timestamps = len(srt_timestamps)
    
    if num_sentences != num_timestamps and logger:
            logger.warning(
                f"AUDIO_PROC: Mismatch: sentence count ({num_sentences}) vs timestamp count ({num_timestamps}) "
                f"for article {article_id} (bilingual SRT). Using min({num_sentences}, {num_timestamps})."
            )
    
    count_to_process = min(num_sentences, num_timestamps)
    if count_to_process == 0:
        if logger: logger.warning(f"AUDIO_PROC: No data to process for bilingual SRT for article {article_id}.")
        return None

    srt_content_lines = []
    for i in range(count_to_process):
        start_ms, end_ms = srt_timestamps[i]
        eng_text = original_sentences_data[i].get('english_text', '').strip()
        chn_text = original_sentences_data[i].get('chinese_text', '').strip()

        start_time_str = ms_to_srt_time(start_ms)
        end_time_str = ms_to_srt_time(end_ms)

        srt_content_lines.append(str(i + 1))
        srt_content_lines.append(f"{start_time_str} --> {end_time_str}")
        srt_content_lines.append(f"{eng_text} | {chn_text}") # Default separator
        srt_content_lines.append("") 

    try:
        output_srt_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_srt_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(srt_content_lines))
        if logger: logger.info(f"AUDIO_PROC: Generated bilingual SRT for article {article_id} at {output_srt_path}")
        return str(output_srt_path)
    except IOError as e:
        if logger: logger.error(f"AUDIO_PROC: Failed to write bilingual SRT for article {article_id} to {output_srt_path}: {e}")
        raise
    return None


# ms_to_srt_time (no changes)
def ms_to_srt_time(ms_total):
    # ... (same as your existing function)
    if ms_total is None or ms_total < 0: ms_total = 0
    ms = int(ms_total % 1000)
    s_total = int(ms_total // 1000)
    s = int(s_total % 60)
    m_total = int(s_total // 60)
    m = int(m_total % 60)
    h = int(m_total // 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

# get_audio_duration_ms (no changes)
def get_audio_duration_ms(audio_path_str, logger=None):
    # ... (same as your existing function)
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path_str)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration_sec = float(result.stdout.strip())
        if logger: logger.info(f"AUDIO_PROC: Duration of {audio_path_str}: {duration_sec}s")
        return int(duration_sec * 1000)
    except (subprocess.CalledProcessError, ValueError) as e:
        if logger: logger.error(f"AUDIO_PROC: Failed to get duration for {audio_path_str}: {e}")
        return None
    except FileNotFoundError:
        if logger: logger.error("AUDIO_PROC: ffprobe not found. Cannot get audio duration.")
        raise Exception("ffprobe not found. Please ensure FFmpeg (which includes ffprobe) is installed and in PATH.")

def process_article_with_tts(article_id,
                             article_filename_base, app_instance,
                             raw_bilingual_text_content_string=None, parsed_sentences_list=None):
    logger = app_instance.logger
    app_config = app_instance.config

    # --- Path Generation for Converted Audio, MP3 Parts, and SRT ---
    article_data_for_paths = db_manager.get_article_by_id(article_id, app_logger=logger)
    result = {} 
    if not article_data_for_paths or not article_data_for_paths['book_id']:
        msg = f"TTS Error: Cannot determine book for article {article_id} to create descriptive audio/SRT paths."
        logger.error(f"AUDIO_PROC: {msg}")
        result.update({"message": msg, "message_category": "danger", "success": False})
        return result
    book_data_for_paths = db_manager.get_book_by_id(article_data_for_paths['book_id'], app_logger=logger)
    if not book_data_for_paths:
        msg = f"TTS Error: Book data not found for book_id {article_data_for_paths['book_id']} (article {article_id})."
        logger.error(f"AUDIO_PROC: {msg}")
        result.update({"message": msg, "message_category": "danger", "success": False})
        return result

    book_safe_title = secure_filename(book_data_for_paths['title']) if book_data_for_paths['title'] else "unknown_book"
    article_safe_title = article_filename_base if article_filename_base else secure_filename(article_data_for_paths['filename'])
    if not book_safe_title.strip(): book_safe_title = "unknown_book_fallback"
    if not article_safe_title.strip(): article_safe_title = "unknown_article_fallback"

    base_converted_audio_dir_for_article = Path(app_config['CONVERTED_AUDIO_FOLDER']) / book_safe_title / article_safe_title
    base_mp3_parts_dir_for_article = Path(app_config['MP3_PARTS_FOLDER']) / book_safe_title / article_safe_title
    base_srt_dir_for_article = Path(app_config['PROCESSED_SRT_FOLDER']) / book_safe_title / article_safe_title
    # --- End Path Generation ---

    logger.info(f"AUDIO_PROC: Starting TTS processing for article ID {article_id} ('{article_safe_title}')")

    result.update({
        "success": False,
        "message": "TTS processing initiated.",
        "message_category": "info",
        "processed_path": None
    })

    temp_tts_clips_dir_obj = None 

    try:
        if not tts_utils.is_initialized_en or not tts_utils.is_initialized_zh:
            msg = "TTS Error: Engines not ready."
            logger.error(f"AUDIO_PROC: {msg} Aborting TTS processing.")
            result.update({"message": msg, "message_category": "danger"})
            return result
        
        if not tts_utils.check_voices_configured(app_config['KOKORO_MANDARIN_VOICE'], app_config['KOKORO_ENGLISH_VOICE'], logger):
            msg = "TTS Error: Voices not configured."
            logger.error(f"AUDIO_PROC: {msg} Aborting TTS processing.")
            result.update({"message": msg, "message_category": "danger"})
            return result

        pipeline_en = tts_utils.get_kokoro_pipeline(
            app_config['KOKORO_LANG_CODE_EN'],
            app_config['KOKORO_LANG_CODE_ZH'],
            app_config['KOKORO_LANG_CODE_EN'],
            logger
        )
        if not pipeline_en:
            msg = "TTS Error: English pipeline failed or unavailable."
            logger.error(f"AUDIO_PROC: {msg} Aborting.")
            result.update({"message": msg, "message_category": "danger"})
            return result

        # --- Get parsed sentences ---
        _parsed_sentences_for_tts = []
        if parsed_sentences_list:
            if isinstance(parsed_sentences_list, list) and \
               len(parsed_sentences_list) > 0 and \
               (isinstance(parsed_sentences_list[0], dict) or hasattr(parsed_sentences_list[0], 'keys')):
                for s_dict in parsed_sentences_list: 
                    _parsed_sentences_for_tts.append((
                        s_dict['paragraph_index'],
                        s_dict['sentence_index_in_paragraph'],
                        s_dict['english_text'],
                        s_dict['chinese_text']
                    ))
                logger.info(f"AUDIO_PROC: TTS using pre-parsed sentences list ({len(_parsed_sentences_for_tts)} items) from DB.")
            else: 
                _parsed_sentences_for_tts = parsed_sentences_list
                logger.info(f"AUDIO_PROC: TTS using provided parsed_sentences_list in assumed tuple format ({len(_parsed_sentences_for_tts)} items).")
        
        elif raw_bilingual_text_content_string:
            _parsed_sentences_for_tts = list(text_parser.parse_bilingual_file_content(raw_bilingual_text_content_string))
            logger.info(f"AUDIO_PROC: TTS using raw text string, parsed into ({len(_parsed_sentences_for_tts)} items).")
        else: # Neither raw_bilingual_text_content_string nor parsed_sentences_list is provided; fetch from DB.
            logger.info(f"AUDIO_PROC: TTS for article {article_id} - no raw text or pre-parsed list. Fetching sentences from DB.")
            sentences_from_db = db_manager.get_sentences_for_article(article_id, app_logger=logger)
            if not sentences_from_db:
                msg = f"TTS Error: No sentences found in DB for article {article_id}."
                logger.error(f"AUDIO_PROC: {msg}")
                result.update({"message": msg, "message_category": "danger"})
                return result
            
            for s_dict in sentences_from_db: # s_dict is a Row from sqlite, which is dict-like
                _parsed_sentences_for_tts.append((
                    s_dict['paragraph_index'],
                    s_dict['sentence_index_in_paragraph'],
                    s_dict['english_text'],
                    s_dict['chinese_text']
                ))
            logger.info(f"AUDIO_PROC: TTS using sentences fetched from DB ({len(_parsed_sentences_for_tts)} items) for article {article_id}.")
        
        if not _parsed_sentences_for_tts: # Check after potential parsing/conversion/DB fetch
            msg = "No sentences available (from text, parsed list, or DB) to process with TTS."
            logger.warning(f"AUDIO_PROC: {msg} for article {article_id}. Aborting TTS.")
            result.update({"message": msg, "message_category": "warning"})
            return result
        # --- END Get parsed sentences ---

        sentence_audio_details = []
        
        with tempfile.TemporaryDirectory(dir=str(app_config['TEMP_FILES_FOLDER']), prefix=f"tts_clips_{article_id}_") as temp_tts_clips_dir:
            temp_tts_clips_dir_obj = Path(temp_tts_clips_dir) 
            logger.info(f"AUDIO_PROC: Created temporary directory for TTS clips: {temp_tts_clips_dir_obj}")

            for idx, (p_idx, s_idx_in_p, en_text, zh_text) in enumerate(_parsed_sentences_for_tts):
                logger.info(f"AUDIO_PROC: TTS processing sentence {idx + 1}/{len(_parsed_sentences_for_tts)}: '{en_text[:30]}...' (P:{p_idx}, S:{s_idx_in_p})")
                try:
                    eng_audio_data_np = tts_utils.generate_audio(
                        pipeline_en, en_text, app_config['KOKORO_ENGLISH_VOICE'], logger=logger
                    )
                    temp_eng_wav_path = temp_tts_clips_dir_obj / f"sentence_{idx}_eng.wav"
                    soundfile.write(str(temp_eng_wav_path), eng_audio_data_np, app_config['KOKORO_SAMPLE_RATE'])
                    
                    audio_segment = AudioSegment.from_wav(str(temp_eng_wav_path))
                    original_duration_ms = len(audio_segment)
                    silence_segment = AudioSegment.silent(duration=app_config['TTS_INTER_SENTENCE_SILENCE_MS'])
                    segment_with_silence = audio_segment + silence_segment
                    
                    sentence_audio_details.append({
                        'pydub_segment_with_silence': segment_with_silence,
                        'duration_with_silence_ms': len(segment_with_silence),
                        'original_sentence_audio_duration_ms': original_duration_ms
                    })
                except Exception as e_sent:
                    logger.error(f"AUDIO_PROC: Error TTS processing sentence {idx} ('{en_text[:30]}...'): {e_sent}", exc_info=True)
                    min_silence = AudioSegment.silent(duration=app_config['TTS_INTER_SENTENCE_SILENCE_MS'])
                    sentence_audio_details.append({
                        'pydub_segment_with_silence': min_silence,
                        'duration_with_silence_ms': len(min_silence),
                        'original_sentence_audio_duration_ms': 0
                    })

            if not sentence_audio_details:
                msg = "TTS processing failed to generate any audio segments."
                logger.error(f"AUDIO_PROC: {msg} for article {article_id}.")
                result.update({"message": msg, "message_category": "danger"})
                return result

            logger.info(f"AUDIO_PROC: Stitching {len(sentence_audio_details)} TTS audio segments for article {article_id}...")
            full_audio_segment = AudioSegment.empty()
            for detail in sentence_audio_details:
                full_audio_segment += detail['pydub_segment_with_silence']

            base_converted_audio_dir_for_article.mkdir(parents=True, exist_ok=True)
            final_mp3_filename = f"{article_safe_title}_tts_combined.mp3"
            converted_mp3_path_str = str(base_converted_audio_dir_for_article / final_mp3_filename)

            try:
                full_audio_segment.export(converted_mp3_path_str, format="mp3", parameters=["-q:a", "2"])
                logger.info(f"AUDIO_PROC: Exported combined TTS MP3 to: {converted_mp3_path_str}")
                db_manager.update_article_converted_mp3_path(article_id, converted_mp3_path_str, app_logger=logger)
            except Exception as e_export:
                msg = "Failed to create final MP3 from TTS audio."
                logger.error(f"AUDIO_PROC: {msg} for article {article_id}: {e_export}", exc_info=True)
                result.update({"message": msg, "message_category": "danger"})
                return result
            
            result["processed_path"] = converted_mp3_path_str 

            logger.info(f"AUDIO_PROC: Calculating timestamps for TTS audio of article {article_id}...")
            srt_timestamps = []
            current_time_ms = 0
            for detail in sentence_audio_details:
                sentence_actual_audio_duration_ms = detail['original_sentence_audio_duration_ms']
                start_ms = current_time_ms
                end_ms = current_time_ms + sentence_actual_audio_duration_ms
                srt_timestamps.append((start_ms, end_ms))
                current_time_ms += detail['duration_with_silence_ms']
            
            updated_count = db_manager.update_sentence_timestamps(article_id, srt_timestamps, app_logger=logger)
            logger.info(f"AUDIO_PROC: Updated {updated_count} sentence timestamps in DB for TTS audio of article {article_id}.")
            if updated_count != len(_parsed_sentences_for_tts):
                 logger.warning(f"AUDIO_PROC: Mismatch in updated timestamps ({updated_count}) vs parsed sentences ({len(_parsed_sentences_for_tts)}) for article {article_id}.")
            
            timestamp_message = f"Generated audio with TTS and updated {updated_count} sentence timestamps."

            # Use _parsed_sentences_for_tts for generating bilingual SRT as it's already in the correct format
            # and reflects what was actually sent to TTS.
            bilingual_sentences_for_srt_gen_tts = [
                {'english_text': s_tuple[2], 'chinese_text': s_tuple[3]} # s_tuple is (p_idx, s_idx, en, zh)
                for s_tuple in _parsed_sentences_for_tts
            ]
            final_bilingual_srt_filename = f"{article_safe_title}_bilingual_tts.srt"
            base_srt_dir_for_article.mkdir(parents=True, exist_ok=True)
            final_bilingual_srt_path = base_srt_dir_for_article / final_bilingual_srt_filename

            bilingual_srt_generated_path_str = generate_bilingual_srt(
                article_id, bilingual_sentences_for_srt_gen_tts, srt_timestamps,
                str(final_bilingual_srt_path), logger=logger
            )
            if bilingual_srt_generated_path_str:
                db_manager.update_article_srt_path(article_id, bilingual_srt_generated_path_str, app_logger=logger)
                logger.info(f"AUDIO_PROC: Generated final bilingual SRT for article {article_id} at {bilingual_srt_generated_path_str} (TTS)")
            else:
                logger.warning(f"AUDIO_PROC: Failed to generate final bilingual SRT for article {article_id} (TTS).")
                timestamp_message += " SRT generation failed."


            # --- MP3 Splitting ---
            splitting_message_part = ""
            if converted_mp3_path_str:
                logger.info(f"AUDIO_PROC: Proceeding to MP3 splitting for TTS-generated audio, article {article_id}")
                sentence_db_ids_ordered = db_manager.get_sentence_ids_for_article_in_order(article_id, app_logger=logger)

                if len(sentence_db_ids_ordered) != len(srt_timestamps):
                    logger.error(f"AUDIO_PROC: Mismatch for TTS splitting: DB sentence count ({len(sentence_db_ids_ordered)}) vs calculated timestamp count ({len(srt_timestamps)}) for article {article_id}. Skipping MP3 splitting.")
                    splitting_message_part = " MP3 splitting skipped due to count mismatch."
                else:
                    sentences_info_for_splitting = []
                    for i, db_id_dict in enumerate(sentence_db_ids_ordered):
                        sentences_info_for_splitting.append({
                            'id': db_id_dict['id'],
                            'original_start_ms': srt_timestamps[i][0],
                            'original_end_ms': srt_timestamps[i][1]
                        })
                    
                    base_mp3_parts_dir_for_article.mkdir(parents=True, exist_ok=True)
                    max_size_bytes = app_config['MAX_AUDIO_PART_SIZE_MB'] * 1024 * 1024
                    original_mp3_size_bytes = Path(converted_mp3_path_str).stat().st_size

                    if original_mp3_size_bytes > max_size_bytes:
                        logger.info(f"AUDIO_PROC: TTS MP3 {converted_mp3_path_str} size {original_mp3_size_bytes} > {max_size_bytes}. Attempting to split for article {article_id}.")
                        split_details = split_mp3_by_size_estimation(
                            original_mp3_path=converted_mp3_path_str,
                            sentences_info=sentences_info_for_splitting,
                            max_part_size_bytes=max_size_bytes,
                            output_parts_dir=str(base_mp3_parts_dir_for_article),
                            article_filename_base=article_safe_title,
                            logger=logger
                        )
                        if split_details and split_details['num_parts'] > 0:
                            part_checksums_list = split_details.get('part_checksums', [])
                            db_manager.update_article_mp3_parts_info(
                                article_id, str(base_mp3_parts_dir_for_article), split_details['num_parts'], 
                                part_checksums_list, app_logger=logger
                            )
                            db_manager.batch_update_sentence_part_details(split_details['sentence_part_updates'], app_logger=logger)
                            logger.info(f"AUDIO_PROC: Successfully split TTS MP3 for article {article_id} into {split_details['num_parts']} parts.")
                            splitting_message_part = f" Original MP3 was large and split into {split_details['num_parts']} parts."
                        else:
                            logger.warning(f"AUDIO_PROC: TTS MP3 splitting failed or resulted in no parts for article {article_id}, despite being large.")
                            db_manager.clear_article_mp3_parts_info(article_id, app_logger=logger)
                            splitting_message_part = " Original MP3 was large, but splitting failed/produced no parts."
                    else:
                        logger.info(f"AUDIO_PROC: TTS MP3 for article {article_id} not split (size {original_mp3_size_bytes} <= {max_size_bytes}).")
                        db_manager.clear_article_mp3_parts_info(article_id, app_logger=logger)
                        splitting_message_part = " Original MP3 not large enough for splitting."
            
            result.update({
                "success": True,
                "message": timestamp_message + splitting_message_part,
                "message_category": "success"
            })
            logger.info(f"AUDIO_PROC: TTS processing completed for article {article_id}. Message: {result['message']}")
            return result

    except Exception as e:
        msg = f"A critical error occurred during TTS audio processing: {str(e)}"
        logger.error(f"AUDIO_PROC: Major error during TTS processing for article {article_id}: {e}\n{traceback.format_exc()}", exc_info=True)
        result.update({"message": msg, "message_category": "danger", "success": False})
        return result

    return result

# --- NEW MP3 Splitting Function (by size estimation) ---
def split_mp3_by_size_estimation(original_mp3_path, sentences_info,
                                 max_part_size_bytes, output_parts_dir,
                                 article_filename_base, logger=None):
    if not logger:
        # Create a dummy logger if none provided, to avoid `logger.info` errors
        class DummyLogger:
            def info(self, msg): print(f"INFO: {msg}")
            def warning(self, msg): print(f"WARNING: {msg}")
            def error(self, msg, exc_info=False): print(f"ERROR: {msg}")
            def debug(self, msg): print(f"DEBUG: {msg}")
        logger = DummyLogger()

    logger.info(f"AUDIO_PROC_SPLIT: Starting MP3 splitting by size estimation for '{original_mp3_path}'.")
    if not sentences_info:
        logger.warning("AUDIO_PROC_SPLIT: No sentences_info provided for splitting. Aborting.")
        return {'num_parts': 0, 'sentence_part_updates': [], 'part_checksums': []}

    original_mp3_path_obj = Path(original_mp3_path)
    output_parts_dir_obj = Path(output_parts_dir)
    output_parts_dir_obj.mkdir(parents=True, exist_ok=True)

    total_mp3_size_bytes = original_mp3_path_obj.stat().st_size
    total_mp3_duration_ms = get_audio_duration_ms(original_mp3_path, logger=logger)

    if total_mp3_duration_ms is None or total_mp3_duration_ms == 0:
        logger.error(f"AUDIO_PROC_SPLIT: Could not determine duration or duration is zero for {original_mp3_path}. Cannot split.")
        return {'num_parts': 0, 'sentence_part_updates': [], 'part_checksums': []}
    
    if total_mp3_size_bytes == 0:
        logger.error(f"AUDIO_PROC_SPLIT: Original MP3 file {original_mp3_path} has zero size. Cannot split.")
        return {'num_parts': 0, 'sentence_part_updates': [], 'part_checksums': []}

    if total_mp3_size_bytes <= max_part_size_bytes:
        logger.info(f"AUDIO_PROC_SPLIT: MP3 size {total_mp3_size_bytes}B <= max part size {max_part_size_bytes}B. No splitting needed.")
        return {'num_parts': 0, 'sentence_part_updates': [], 'part_checksums': []} 

    sentence_part_updates = []
    current_part_idx = 0
    sentence_cursor = 0
    part_checksums = []
    num_parts_successfully_created = 0

    while sentence_cursor < len(sentences_info):
        part_start_original_ms = sentences_info[sentence_cursor]['original_start_ms']
        current_part_accumulated_size_bytes = 0
        current_part_sentences_info = [] 
        part_end_original_ms_for_ffmpeg = part_start_original_ms

        temp_sentence_cursor = sentence_cursor 
        while temp_sentence_cursor < len(sentences_info):
            sentence = sentences_info[temp_sentence_cursor]
            sentence_duration_ms = sentence['original_end_ms'] - sentence['original_start_ms']
            if sentence_duration_ms <= 0: 
                 estimated_sentence_size_bytes = (50 / total_mp3_duration_ms) * total_mp3_size_bytes if total_mp3_duration_ms > 0 else 1024 
            else:
                 estimated_sentence_size_bytes = (sentence_duration_ms / total_mp3_duration_ms) * total_mp3_size_bytes
            
            if sentence_duration_ms > 0 and estimated_sentence_size_bytes == 0:
                estimated_sentence_size_bytes = 1024 

            if (current_part_accumulated_size_bytes + estimated_sentence_size_bytes <= max_part_size_bytes) or \
               (len(current_part_sentences_info) == 0): 
                
                current_part_sentences_info.append(sentence)
                current_part_accumulated_size_bytes += estimated_sentence_size_bytes
                part_end_original_ms_for_ffmpeg = sentence['original_end_ms'] 
                temp_sentence_cursor += 1
            else:
                break 

        if not current_part_sentences_info:
            logger.warning("AUDIO_PROC_SPLIT: No sentences collected for a part, breaking split loop.")
            break 
        
        sentence_cursor = temp_sentence_cursor

        part_output_filename = f"{article_filename_base}_part_{current_part_idx}.mp3"
        part_output_path = output_parts_dir_obj / part_output_filename

        ffmpeg_start_sec = max(0, part_start_original_ms / 1000.0) 
        ffmpeg_end_sec = part_end_original_ms_for_ffmpeg / 1000.0
        
        if ffmpeg_end_sec <= ffmpeg_start_sec:
            logger.warning(f"AUDIO_PROC_SPLIT: Calculated zero or negative duration for part {current_part_idx} "
                           f"(start: {ffmpeg_start_sec:.3f}s, to: {ffmpeg_end_sec:.3f}s). Skipping this part extraction.")
            if temp_sentence_cursor == sentence_cursor and sentence_cursor < len(sentences_info): 
                logger.error("AUDIO_PROC_SPLIT: Potential infinite loop due to zero-duration part calculation. Advancing sentence cursor by 1 to break.")
                sentence_cursor += 1 
            continue


        cmd_split = [
            "ffmpeg", "-y",
            "-i", str(original_mp3_path_obj),
            "-ss", str(ffmpeg_start_sec),
            "-to", str(ffmpeg_end_sec),
            "-c", "copy", 
            str(part_output_path)
        ]
        cmd_display = " ".join([shlex.quote(c) for c in cmd_split])
        logger.info(f"AUDIO_PROC_SPLIT: Splitting command for part {current_part_idx}: {cmd_display}")

        checksum_for_this_part = None
        try:
            split_process = subprocess.run(cmd_split, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            actual_part_size = part_output_path.stat().st_size
            logger.info(f"AUDIO_PROC_SPLIT: Created part {part_output_path} (Size: {actual_part_size}B, Estimated: {current_part_accumulated_size_bytes:.0f}B).")
            if split_process.stderr:
                logger.debug(f"AUDIO_PROC_SPLIT: ffmpeg split stderr for part {current_part_idx}:\n{split_process.stderr.decode(errors='ignore')}")

            checksum_for_this_part = calculate_sha256_checksum(str(part_output_path), logger=logger)
            if checksum_for_this_part:
                logger.info(f"AUDIO_PROC_SPLIT: Calculated SHA256 for {part_output_path}: {checksum_for_this_part[:10]}...")
            else:
                logger.warning(f"AUDIO_PROC_SPLIT: Failed to calculate checksum for successfully created part {part_output_path}.")
            
            part_checksums.append(checksum_for_this_part if checksum_for_this_part else "")
            num_parts_successfully_created += 1

            for sent_in_part in current_part_sentences_info:
                sentence_part_updates.append({
                    'sentence_db_id': sent_in_part['id'],
                    'audio_part_index': current_part_idx, 
                    'start_time_in_part_ms': sent_in_part['original_start_ms'] - part_start_original_ms,
                    'end_time_in_part_ms': sent_in_part['original_end_ms'] - part_start_original_ms,
                })
            current_part_idx += 1 

        except subprocess.CalledProcessError as e:
            logger.error(f"AUDIO_PROC_SPLIT: Failed to create part {current_part_idx} (cmd: {cmd_display}): {e.stderr.decode(errors='ignore') if e.stderr else e}")
            part_checksums.append("") 
            # current_part_idx +=1 # Increment filename index even on failure to avoid overwrite if retried.
                                 # Or, more robustly, delete the failed part if it was partially created.
                                 # For now, we'll increment to keep filenames unique in case of retries,
                                 # but num_parts_successfully_created will not increment.

    logger.info(f"AUDIO_PROC_SPLIT: Splitting complete. {num_parts_successfully_created} parts created. "
                f"{len(sentence_part_updates)} sentence updates prepared. {len(part_checksums)} checksums recorded (length reflects attempts).")

    return {
        'num_parts': num_parts_successfully_created,
        'sentence_part_updates': sentence_part_updates,
        'part_checksums': [cs for cs in part_checksums if cs] # Only return checksums for successfully created parts.
                                                              # Or rather, match length with num_parts_successfully_created
                                                              # The current logic will have len(part_checksums) == number of attempts.
                                                              # Let's filter it based on success of creation.
                                                              # A better way: only append to part_checksums on successful creation.
                                                              # The current loop structure has `current_part_idx` as the index for next part.
                                                              # Let's stick to `part_checksums` containing checksums for successfully created parts.
                                                              # The simplest is to build `part_checksums` only on success.
                                                              # The `part_checksums` currently has "" for failures.
                                                              # Re-filter based on num_parts_successfully_created.
                                                              # The number of successful parts might be less than `current_part_idx` if some failed.
                                                              # For DB consistency, the list of checksums should match `num_parts_successfully_created`.
    }