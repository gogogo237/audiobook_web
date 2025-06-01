import os
import unittest
import json
import zipfile
import tempfile
import shutil
from unittest.mock import patch, MagicMock, call # Import call

# Add project root to sys.path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import book_exporter

class TestBookExporter(unittest.TestCase):

    def setUp(self):
        self.app_logger_mock = MagicMock()
        self.temp_dir = tempfile.mkdtemp() # Base for all test-specific temp files
        self.temp_files_base_for_pkg_creation = os.path.join(self.temp_dir, "pkg_creation_sandbox") # This is passed to create_book_package
        os.makedirs(self.temp_files_base_for_pkg_creation, exist_ok=True)

        self.dummy_audio_content = b"dummy audio data"
        self.dummy_audio_source_dir = os.path.join(self.temp_dir, "original_audio_files") # Where dummy source audio lives
        os.makedirs(self.dummy_audio_source_dir, exist_ok=True)

        self.article1_orig_audio_name = "article1_source_audio.mp3"
        self.dummy_article1_audio_path = os.path.join(self.dummy_audio_source_dir, self.article1_orig_audio_name)
        with open(self.dummy_article1_audio_path, 'wb') as f:
            f.write(self.dummy_audio_content)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch('book_exporter.db_manager')
    def test_generate_manifest_data_success_with_audio(self, mock_db_manager):
        # This test remains the same as it was passing and tests generate_manifest_data logic well.
        mock_db_manager.get_book_by_id.return_value = {'id': 1, 'title': 'Test Book 1'}
        mock_db_manager.get_articles_for_book.return_value = [
            {'id': 101, 'filename': 'Article 1 Title', 'converted_mp3_path': self.dummy_article1_audio_path},
            {'id': 102, 'filename': 'Article 2 No Audio', 'converted_mp3_path': None},
            {'id': 103, 'filename': 'Article 3 Audio Path Missing', 'converted_mp3_path': '/path/to/non_existent_audio.mp3'}
        ]
        mock_db_manager.get_sentences_for_article.side_effect = lambda article_id, app_logger: [
            {'paragraph_index': 0, 'sentence_index_in_paragraph': 0, 'english_text': 'Hello.', 'chinese_text': '你好。', 'start_time_ms': 100, 'end_time_ms': 200},
            {'paragraph_index': 0, 'sentence_index_in_paragraph': 1, 'english_text': 'World.', 'chinese_text': '世界。', 'start_time_ms': 250, 'end_time_ms': 350}
        ] if article_id == 101 else []

        manifest = book_exporter.generate_manifest_data(1, self.app_logger_mock)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest['book_title'], 'Test Book 1')
        article1_manifest = manifest['articles'][0]
        self.assertEqual(article1_manifest['audio_file_path'], 'articles/Article_1_Title/audio.mp3')
        self.assertEqual(article1_manifest['_original_converted_mp3_path_internal'], self.dummy_article1_audio_path)
        article3_manifest = manifest['articles'][2] # Audio path points to non_existent_audio.mp3
        # So os.path.exists(article_row['converted_mp3_path']) in generate_manifest_data should be false
        self.assertIsNone(article3_manifest['audio_file_path'])


    @patch('book_exporter.db_manager')
    def test_generate_manifest_data_book_not_found(self, mock_db_manager): # Was passing
        mock_db_manager.get_book_by_id.return_value = None
        manifest = book_exporter.generate_manifest_data(999, self.app_logger_mock)
        self.assertIsNone(manifest)

    @patch('book_exporter.db_manager')
    def test_generate_manifest_data_no_articles(self, mock_db_manager): # Was passing
        mock_db_manager.get_book_by_id.return_value = {'id': 2, 'title': 'Book With No Articles'}
        mock_db_manager.get_articles_for_book.return_value = []
        manifest = book_exporter.generate_manifest_data(2, self.app_logger_mock)
        self.assertIsNotNone(manifest)
        self.assertEqual(len(manifest['articles']), 0)

    @patch('book_exporter.generate_manifest_data')
    def test_create_book_package_success(self, mock_generate_manifest):
        book_id = 1
        output_package_path = os.path.join(self.temp_dir, "test_book.bookpkg")

        mock_manifest = {
            "book_title": "Test Book Package", "book_id_original": book_id,
            "articles": [
                {
                    "article_title": "Audio Article 1", "article_id_original": 101,
                    "audio_file_path": "articles/Audio_Article_1/audio.mp3",
                    "_article_safe_title_internal": "Audio_Article_1",
                    "_original_converted_mp3_path_internal": self.dummy_article1_audio_path, # Valid, existing path
                    "sentences": [{"english_text": "Sentence 1", "chinese_text": "句子1"}]
                },
                {
                    "article_title": "No Audio Article", "article_id_original": 102,
                    "audio_file_path": None, "_article_safe_title_internal": "No_Audio_Article",
                    "_original_converted_mp3_path_internal": None, "sentences": []
                },
                {
                    "article_title": "Audio Source Missing", "article_id_original": 103,
                    "audio_file_path": "articles/Audio_Source_Missing/audio.mp3",
                    "_article_safe_title_internal": "Audio_Source_Missing",
                    "_original_converted_mp3_path_internal": os.path.join(self.dummy_audio_source_dir, "non_existent.mp3"),
                    "sentences": []
                }
            ]
        }
        mock_generate_manifest.return_value = mock_manifest
        self.assertTrue(os.path.exists(self.dummy_article1_audio_path), "Dummy audio file for test setup is missing")

        result = book_exporter.create_book_package(book_id, output_package_path, self.app_logger_mock, self.temp_files_base_for_pkg_creation)

        self.assertTrue(result)
        mock_generate_manifest.assert_called_once_with(book_id, self.app_logger_mock)

        self.assertTrue(os.path.exists(output_package_path))
        with zipfile.ZipFile(output_package_path, 'r') as zf:
            zip_contents = zf.namelist()
            self.assertIn("manifest.json", zip_contents)
            self.assertIn("articles/Audio_Article_1/audio.mp3", zip_contents)
            self.assertNotIn("articles/No_Audio_Article/audio.mp3", zip_contents)
            self.assertNotIn("articles/Audio_Source_Missing/audio.mp3", zip_contents)

            with zf.open("manifest.json") as mf:
                manifest_in_zip = json.load(mf)
                self.assertEqual(manifest_in_zip['book_title'], "Test Book Package")
                self.assertEqual(len(manifest_in_zip['articles']), 3)
                self.assertNotIn('_article_safe_title_internal', manifest_in_zip['articles'][0])

        found_warning_log = False
        for call_item in self.app_logger_mock.warning.call_args_list:
            args, _ = call_item
            if args and "Skipping audio copy" in args[0] and "Audio_Source_Missing" in args[0]:
                found_warning_log = True
                break
        self.assertTrue(found_warning_log, "Expected warning log for missing audio source not found.")


    @patch('book_exporter.generate_manifest_data', return_value=None)
    def test_create_book_package_manifest_generation_fails(self, mock_generate_manifest):
        result = book_exporter.create_book_package(1, "dummy.bookpkg", self.app_logger_mock, self.temp_files_base_for_pkg_creation)
        self.assertFalse(result)

    @patch('book_exporter.generate_manifest_data')
    @patch('shutil.copy2', side_effect=Exception("Disk full test error"))
    def test_create_book_package_audio_copy_fails(self, mock_shutil_copy, mock_generate_manifest):
        book_id = 1
        output_package_path = os.path.join(self.temp_dir, "copy_fail.bookpkg")
        mock_manifest = {
            "book_title": "Copy Fail Book", "book_id_original": book_id,
            "articles": [{
                "article_title": "Audio Article", "article_id_original": 101,
                "audio_file_path": "articles/Audio_Article/audio.mp3",
                "_article_safe_title_internal": "Audio_Article",
                "_original_converted_mp3_path_internal": self.dummy_article1_audio_path,
                "sentences": []
            }]
        }
        mock_generate_manifest.return_value = mock_manifest
        self.assertTrue(os.path.exists(self.dummy_article1_audio_path))

        result = book_exporter.create_book_package(book_id, output_package_path, self.app_logger_mock, self.temp_files_base_for_pkg_creation)
        self.assertTrue(result)
        mock_shutil_copy.assert_called_once()

        found_error_log = False
        expected_log_part = f"Failed to copy audio file from {self.dummy_article1_audio_path}"
        expected_exception_text = "Disk full test error"
        for call_item in self.app_logger_mock.error.call_args_list:
            args, _ = call_item
            if args and expected_log_part in args[0] and expected_exception_text in args[0]:
                found_error_log = True
                break
        self.assertTrue(found_error_log, f"Expected error log containing '{expected_log_part}' and '{expected_exception_text}' not found. Log calls: {self.app_logger_mock.error.call_args_list}")

        self.assertTrue(os.path.exists(output_package_path))
        with zipfile.ZipFile(output_package_path, 'r') as zf:
            zip_contents = zf.namelist()
            self.assertIn("manifest.json", zip_contents)
            self.assertNotIn("articles/Audio_Article/audio.mp3", zip_contents)

    def test_create_book_package_temp_folder_creation_fails(self):
        uncreatable_temp_base = os.path.join(self.temp_dir, "uncreatable_base_temp_folder_file")
        with open(uncreatable_temp_base, 'w') as f:
            f.write("I am a file, not a directory.")

        with patch('book_exporter.generate_manifest_data') as mock_gen_manifest:
            mock_gen_manifest.return_value = {"book_title": "Test", "book_id_original": 1, "articles": []}
            result = book_exporter.create_book_package(1, "dummy.bookpkg", self.app_logger_mock, uncreatable_temp_base)
            self.assertFalse(result)

            found_error_log = False
            # This error is caught by the general "except Exception as e" block in create_book_package,
            # because os.makedirs is skipped (path exists as a file), and tempfile.mkdtemp fails.
            expected_log_part1 = f"Error during package creation for book_id {1}"
            expected_log_part2 = "[Errno 20] Not a directory" # Or similar, depending on OS for NotADirectoryError
            expected_log_part3 = uncreatable_temp_base # The path of the problematic file/directory argument

            for call_item in self.app_logger_mock.error.call_args_list:
                args, kwargs = call_item
                logged_message = args[0]
                logged_exc_info = kwargs.get('exc_info', False)

                if expected_log_part1 in logged_message and \
                   expected_log_part2 in logged_message and \
                   expected_log_part3 in logged_message and \
                   logged_exc_info is True:
                    found_error_log = True
                    break
            self.assertTrue(found_error_log, f"Expected error log for mkdtemp failure not found or message mismatch. Log calls: {self.app_logger_mock.error.call_args_list}")

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
