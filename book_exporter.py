import os
import json
import shutil
import tempfile
import zipfile
from werkzeug.utils import secure_filename
import db_manager # Assuming db_manager.py is in the same directory or accessible

def generate_manifest_data(book_id, app_logger):
    '''
    Generates the manifest data dictionary for a given book_id.
    '''
    app_logger.info(f"BOOK_EXPORTER: Starting manifest generation for book_id: {book_id}")

    book_details = db_manager.get_book_by_id(book_id, app_logger=app_logger)
    if not book_details:
        app_logger.error(f"BOOK_EXPORTER: Book with id {book_id} not found.")
        return None

    manifest = {
        "book_title": book_details['title'],
        "book_id_original": book_id,
        "articles": []
    }

    articles_from_db = db_manager.get_articles_for_book(book_id, app_logger=app_logger)
    if not articles_from_db:
        app_logger.warning(f"BOOK_EXPORTER: No articles found for book_id: {book_id}.")
        return manifest # Return manifest with empty articles list

    for article_row in articles_from_db:
        article_id = article_row['id']
        original_article_title = article_row['filename'] 
        article_safe_title = secure_filename(original_article_title)
        
        relative_audio_path = None
        if article_row['converted_mp3_path'] and os.path.exists(article_row['converted_mp3_path']):
            relative_audio_path = f"articles/{article_safe_title}/audio.mp3"
        else:
            if not article_row['converted_mp3_path']:
                app_logger.info(f"BOOK_EXPORTER: No converted_mp3_path for article_id: {article_id} ('{original_article_title}'). Audio will be null in manifest.")
            else:
                app_logger.warning(f"BOOK_EXPORTER: Audio file {article_row['converted_mp3_path']} not found for article_id: {article_id} ('{original_article_title}'). Audio will be null in manifest.")

        article_data_for_manifest = {
            "article_title": original_article_title,
            "article_id_original": article_id,
            "audio_file_path": relative_audio_path,
            # Temporary fields for create_book_package to use:
            "_article_safe_title_internal": article_safe_title, 
            "_original_converted_mp3_path_internal": article_row['converted_mp3_path'],
            "sentences": []
        }
        
        sentences_from_db = db_manager.get_sentences_for_article(article_id, app_logger=app_logger)
        if not sentences_from_db:
            app_logger.warning(f"BOOK_EXPORTER: No sentences found for article_id: {article_id} ('{original_article_title}').")
        
        for sentence_row in sentences_from_db:
            sentence_data = {
                "paragraph_index": sentence_row['paragraph_index'],
                "sentence_index_in_paragraph": sentence_row['sentence_index_in_paragraph'],
                "english_text": sentence_row['english_text'],
                "chinese_text": sentence_row['chinese_text'],
                "start_time_ms": sentence_row['start_time_ms'],
                "end_time_ms": sentence_row['end_time_ms']
            }
            article_data_for_manifest["sentences"].append(sentence_data)
        
        manifest["articles"].append(article_data_for_manifest)

    app_logger.info(f"BOOK_EXPORTER: Successfully generated manifest data for book_id: {book_id}")
    return manifest

def create_book_package(book_id, output_package_path, app_logger, temp_files_base_folder):
    '''
    Creates a .bookpkg zip archive for the given book_id.
    '''
    app_logger.info(f"BOOK_EXPORTER: Starting package creation for book_id: {book_id} -> {output_package_path}")
    
    manifest_data = generate_manifest_data(book_id, app_logger)
    if manifest_data is None:
        app_logger.error(f"BOOK_EXPORTER: Failed to generate manifest data for book_id: {book_id}. Aborting package creation.")
        return False

    # Create a temporary directory for package contents
    # Ensure temp_files_base_folder exists, if not, create it or log error.
    if not os.path.exists(temp_files_base_folder):
        try:
            os.makedirs(temp_files_base_folder)
            app_logger.info(f"BOOK_EXPORTER: Created temp_files_base_folder: {temp_files_base_folder}")
        except OSError as e:
            app_logger.error(f"BOOK_EXPORTER: Could not create temp_files_base_folder '{temp_files_base_folder}': {e}. Aborting.")
            return False
            
    temp_package_dir = None
    try:
        temp_package_dir = tempfile.mkdtemp(dir=temp_files_base_folder, prefix=f"bookpkg_{book_id}_")
        app_logger.info(f"BOOK_EXPORTER: Created temporary package directory: {temp_package_dir}")

        # Prepare the final manifest for writing (remove temporary internal fields)
        final_manifest_for_json = {
            "book_title": manifest_data["book_title"],
            "book_id_original": manifest_data["book_id_original"],
            "articles": []
        }
        for article_in_manifest in manifest_data["articles"]:
            # Copy all but internal fields
            clean_article = {k: v for k, v in article_in_manifest.items() if not k.startswith('_')}
            final_manifest_for_json["articles"].append(clean_article)

        # Write manifest.json
        manifest_file_path = os.path.join(temp_package_dir, "manifest.json")
        with open(manifest_file_path, 'w', encoding='utf-8') as mf:
            json.dump(final_manifest_for_json, mf, indent=4, ensure_ascii=False)
        app_logger.info(f"BOOK_EXPORTER: Written manifest.json to {manifest_file_path}")

        # Create articles directory and copy audio files
        articles_base_dir_in_temp = os.path.join(temp_package_dir, "articles")
        
        for article_data in manifest_data["articles"]: # Use original manifest_data with internal fields
            if article_data["audio_file_path"]: # This implies _original_converted_mp3_path_internal exists and file was found
                article_safe_title = article_data["_article_safe_title_internal"]
                original_audio_full_path = article_data["_original_converted_mp3_path_internal"]

                if not original_audio_full_path or not os.path.exists(original_audio_full_path):
                    app_logger.warning(f"BOOK_EXPORTER: Article '{article_safe_title}' (ID: {article_data['article_id_original']}) has audio_file_path in manifest, but original source path '{original_audio_full_path}' is missing or invalid. Skipping audio copy.")
                    continue

                article_specific_dir_in_temp = os.path.join(articles_base_dir_in_temp, article_safe_title)
                if not os.path.exists(article_specific_dir_in_temp):
                    os.makedirs(article_specific_dir_in_temp)
                
                destination_audio_path_in_temp = os.path.join(article_specific_dir_in_temp, "audio.mp3")
                
                try:
                    shutil.copy2(original_audio_full_path, destination_audio_path_in_temp)
                    app_logger.info(f"BOOK_EXPORTER: Copied audio for '{article_safe_title}' to {destination_audio_path_in_temp}")
                except Exception as e:
                    app_logger.error(f"BOOK_EXPORTER: Failed to copy audio file from {original_audio_full_path} to {destination_audio_path_in_temp} for article '{article_safe_title}': {e}")
                    # Decide if this is a fatal error or if we continue packaging without this audio
                    # For now, we log and continue. The manifest will still point to the file.
                    # The client app will need to handle missing audio.

        # Create ZIP file
        app_logger.info(f"BOOK_EXPORTER: Creating ZIP file at {output_package_path}")
        with zipfile.ZipFile(output_package_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(temp_package_dir):
                for file_name in files:
                    file_path_abs = os.path.join(root, file_name)
                    # arcname should be relative to temp_package_dir
                    arcname = os.path.relpath(file_path_abs, temp_package_dir)
                    zf.write(file_path_abs, arcname)
        
        app_logger.info(f"BOOK_EXPORTER: Successfully created book package: {output_package_path}")
        return True

    except Exception as e:
        app_logger.error(f"BOOK_EXPORTER: Error during package creation for book_id {book_id}: {e}", exc_info=True)
        # If output_package_path exists and an error occurred, try to remove it
        if os.path.exists(output_package_path):
            try:
                os.remove(output_package_path)
                app_logger.info(f"BOOK_EXPORTER: Removed partially created package file {output_package_path} due to error.")
            except OSError as oe:
                app_logger.error(f"BOOK_EXPORTER: Could not remove partially created package {output_package_path}: {oe}")
        return False
    finally:
        if temp_package_dir and os.path.exists(temp_package_dir):
            try:
                shutil.rmtree(temp_package_dir)
                app_logger.info(f"BOOK_EXPORTER: Successfully cleaned up temporary directory: {temp_package_dir}")
            except Exception as e:
                app_logger.error(f"BOOK_EXPORTER: Failed to clean up temporary directory {temp_package_dir}: {e}")
