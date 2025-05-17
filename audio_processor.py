import os
import subprocess
import tempfile 
import re
import shlex
from pathlib import Path 
import locale 
import math
import hashlib # Added for checksum calculation

from pydub import AudioSegment # Keep for now, might be used if direct ffmpeg fails or for other tasks
from pydub.exceptions import CouldntEncodeError, CouldntDecodeError

def calculate_sha256_checksum(file_path_str, logger=None):
    """Calculates SHA256 checksum of a file and returns it as a hex string."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path_str, "rb") as f:
            # Read and update hash string value in blocks of 4K
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except IOError as e:
        if logger: logger.error(f"AUDIO_PROC: Error reading file {file_path_str} for checksum: {e}")
        return None

def extract_english_sentences_for_aeneas(bilingual_file_content_string, logger=None):
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


def create_plain_text_file_from_list(english_sentence_list, output_path, logger=None):
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            for sentence in english_sentence_list:
                f.write(sentence.strip() + "\n")
        if logger: logger.info(f"AUDIO_PROC: Created plain text file for Aeneas: {output_path}")
    except IOError as e:
        if logger: logger.error(f"AUDIO_PROC: Failed to write plain text file {output_path}: {e}")
        raise


def srt_time_to_ms(time_str):
    try:
        time_str_normalized = time_str.replace('.', ',')
        h, m, s_ms = time_str_normalized.split(':')
        s, ms = s_ms.split(',')
        return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)
    except ValueError:
        raise ValueError(f"Invalid SRT time format: {time_str}")


def convert_to_mp3(source_path_str, output_dir_str, logger=None):
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
        "ffmpeg",
        "-i", str(source_path),
        "-vn",
        "-c:a", "libmp3lame",
        "-q:a", "2", # VBR quality, 0-9, 2 is very good.
        "-y", # Overwrite output without asking
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


def run_aeneas_alignment(audio_mp3_path_str, plain_english_text_path_str, srt_output_path_str, 
                         python_executable_str, logger=None):
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


def parse_aeneas_srt_file(srt_path_str, logger=None):
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


def generate_bilingual_srt(article_id, original_sentences_data, srt_timestamps, output_srt_path_str, logger=None):
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
        srt_content_lines.append(f"{eng_text} | {chn_text}")
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


def ms_to_srt_time(ms_total):
    if ms_total is None or ms_total < 0: ms_total = 0
    ms = int(ms_total % 1000)
    s_total = int(ms_total // 1000)
    s = int(s_total % 60)
    m_total = int(s_total // 60)
    m = int(m_total % 60)
    h = int(m_total // 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def get_audio_duration_ms(audio_path_str, logger=None):
    """Gets audio duration in milliseconds using ffprobe."""
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


def split_mp3_by_sentence_duration(original_mp3_path, sentences_info, 
                                   max_part_size_bytes, output_parts_dir, 
                                   article_filename_base, logger=None):
    """
    Splits an MP3 file into parts based on sentence durations, aiming for max_part_size_bytes.
    sentences_info: list of dicts like {'id': sentence_db_id, 'original_start_ms': X, 'original_end_ms': Y}
    Returns: {'num_parts': N, 'sentence_part_updates': list_of_db_updates, 'part_checksums': list_of_checksum_strings}
    """
    if not sentences_info:
        if logger: logger.warning("AUDIO_PROC: No sentences_info provided for splitting. Aborting.")
        return {'num_parts': 0, 'sentence_part_updates': [], 'part_checksums': []}

    original_mp3_path_obj = Path(original_mp3_path)
    output_parts_dir_obj = Path(output_parts_dir)
    output_parts_dir_obj.mkdir(parents=True, exist_ok=True)

    total_original_duration_ms = get_audio_duration_ms(original_mp3_path, logger=logger)
    original_file_size_bytes = original_mp3_path_obj.stat().st_size

    if total_original_duration_ms is None or total_original_duration_ms == 0:
        if logger: logger.error(f"AUDIO_PROC: Could not determine duration or duration is zero for {original_mp3_path}. Cannot split.")
        return {'num_parts': 0, 'sentence_part_updates': [], 'part_checksums': []}

    if original_file_size_bytes == 0:
        if logger: logger.error(f"AUDIO_PROC: Original MP3 file {original_mp3_path} has zero size. Cannot determine split ratio.")
        return {'num_parts': 0, 'sentence_part_updates': [], 'part_checksums': []}
        
    target_duration_ms_per_part = math.floor((max_part_size_bytes / original_file_size_bytes) * total_original_duration_ms)
    if logger: logger.info(f"AUDIO_PROC: Splitting {original_mp3_path}. Original size: {original_file_size_bytes}B, duration: {total_original_duration_ms}ms. Target part size: {max_part_size_bytes}B, target part duration: {target_duration_ms_per_part}ms.")

    sentence_part_updates = []
    current_part_idx = 0
    sentence_cursor = 0
    parts_created_paths = []
    part_checksums = [] # List to store checksums of successfully created parts

    while sentence_cursor < len(sentences_info):
        part_sentences = []
        current_part_accumulated_duration_ms = 0
        part_start_original_ms = sentences_info[sentence_cursor]['original_start_ms']
        
        while sentence_cursor < len(sentences_info):
            sentence = sentences_info[sentence_cursor]
            sentence_duration_ms = sentence['original_end_ms'] - sentence['original_start_ms']
            if sentence_duration_ms < 0: sentence_duration_ms = 0 
            if sentence_duration_ms == 0: sentence_duration_ms = 50 

            if part_sentences and (current_part_accumulated_duration_ms + sentence_duration_ms > target_duration_ms_per_part):
                break 
            
            part_sentences.append(sentence)
            current_part_accumulated_duration_ms += sentence_duration_ms
            sentence_cursor += 1
            
            if len(part_sentences) == 1 and current_part_accumulated_duration_ms >= target_duration_ms_per_part * 0.9:
                break

        if not part_sentences: 
            if logger: logger.warning("AUDIO_PROC: No sentences collected for a part, breaking split loop.")
            break

        part_end_original_ms = part_sentences[-1]['original_end_ms']
        part_output_filename = f"{article_filename_base}_part_{current_part_idx}.mp3"
        part_output_path = output_parts_dir_obj / part_output_filename

        ffmpeg_start_sec = max(0, part_start_original_ms / 1000.0)
        ffmpeg_to_sec = min(total_original_duration_ms / 1000.0, part_end_original_ms / 1000.0)
        
        if ffmpeg_to_sec <= ffmpeg_start_sec : 
            if logger: logger.warning(f"AUDIO_PROC: Calculated zero or negative duration for part {current_part_idx} (start: {ffmpeg_start_sec}s, to: {ffmpeg_to_sec}s). Skipping this part extraction.")
            continue 

        cmd_split = [
            "ffmpeg", "-y", "-i", str(original_mp3_path_obj),
            "-ss", str(ffmpeg_start_sec),
            "-to", str(ffmpeg_to_sec),
            "-c", "copy", 
            str(part_output_path)
        ]
        if logger: logger.info(f"AUDIO_PROC: Splitting command: {' '.join(shlex.quote(c) for c in cmd_split)}")
        
        checksum_for_this_part = None # Initialize for this part
        try:
            split_process = subprocess.run(cmd_split, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if logger: 
                logger.info(f"AUDIO_PROC: Created part {part_output_path}")
                if split_process.stderr: logger.debug(f"AUDIO_PROC: ffmpeg split stderr: {split_process.stderr.decode(errors='ignore')}")
            
            # Calculate checksum for the successfully created part
            checksum_for_this_part = calculate_sha256_checksum(str(part_output_path), logger=logger)
            if checksum_for_this_part:
                if logger: logger.info(f"AUDIO_PROC: Calculated SHA256 for {part_output_path}: {checksum_for_this_part[:10]}...")
            else:
                if logger: logger.warning(f"AUDIO_PROC: Failed to calculate checksum for successfully created part {part_output_path}.")
            
            parts_created_paths.append(str(part_output_path))
            part_checksums.append(checksum_for_this_part if checksum_for_this_part else "") # Add checksum or "" if failed

            for sent_in_part in part_sentences:
                sentence_part_updates.append({
                    'sentence_db_id': sent_in_part['id'],
                    'audio_part_index': current_part_idx,
                    'start_time_in_part_ms': sent_in_part['original_start_ms'] - part_start_original_ms,
                    'end_time_in_part_ms': sent_in_part['original_end_ms'] - part_start_original_ms,
                })
        except subprocess.CalledProcessError as e:
            if logger: logger.error(f"AUDIO_PROC: Failed to create part {current_part_idx} (cmd: {' '.join(shlex.quote(c) for c in cmd_split)}): {e.stderr.decode(errors='ignore') if e.stderr else e}")
            # If part creation fails, we don't add to parts_created_paths or part_checksums

        current_part_idx += 1

    num_parts_successfully_created = len(parts_created_paths)
    # Ensure part_checksums list has the same length as successfully created parts
    if len(part_checksums) != num_parts_successfully_created:
        if logger: logger.error(f"AUDIO_PROC: Mismatch between number of created parts ({num_parts_successfully_created}) and checksums generated ({len(part_checksums)}). This should not happen.")
        # Potentially adjust part_checksums here if strict alignment is needed, though current logic should align.

    if logger: logger.info(f"AUDIO_PROC: Splitting complete. {num_parts_successfully_created} parts created. {len(sentence_part_updates)} sentence updates prepared. {len(part_checksums)} checksums recorded.")
    
    return {
        'num_parts': num_parts_successfully_created, 
        'sentence_part_updates': sentence_part_updates,
        'part_checksums': part_checksums # List of checksum strings (or "" for failures)
    }