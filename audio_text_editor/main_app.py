import sys
import logging
import logging.handlers
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QListWidget, QPushButton, QInputDialog, QListWidgetItem, QTextEdit, QMessageBox,
                             QDialog, QDialogButtonBox) # Added QDialog, QDialogButtonBox
from PyQt5.QtCore import Qt, QEvent
from PyQt5 import QtWidgets # For QApplication.keyboardModifiers()
import pyqtgraph as pg
# from db_mock import get_article_data, save_article_data # Import save_article_data
import librosa
import numpy as np
import os # For checking file path
import time # For generating unique sentence IDs
import requests # Added
import tempfile # Added

# Constants
FLASK_BACKEND_URL = "https://localhost:5002" # MODIFIED to https

# --- Article Selection Dialog ---
class ArticleSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Article")
        self.setModal(True) # Make it a modal dialog
        self.resize(500, 400) # Adjusted size for better usability

        main_layout = QVBoxLayout(self)

        # Layout for book and article lists
        lists_layout = QHBoxLayout()

        # Book List
        self.book_list_widget = QListWidget()
        self.book_list_widget.currentItemChanged.connect(self.on_book_selected)
        lists_layout.addWidget(self.book_list_widget, 1) # Stretch factor 1

        # Article List
        self.article_list_widget = QListWidget()
        self.article_list_widget.itemDoubleClicked.connect(self.accept) # Double-click to accept
        lists_layout.addWidget(self.article_list_widget, 2) # Stretch factor 2 (more space for articles)

        main_layout.addLayout(lists_layout)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        self.setLayout(main_layout)

        self.books_data = []
        self.load_books_and_articles()

    def load_books_and_articles(self):
        url = f"{FLASK_BACKEND_URL}/api/books_with_articles"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            response = requests.get(url, timeout=10, verify=False)
            response.raise_for_status()
            self.books_data = response.json()

            self.book_list_widget.clear()
            for book_data in self.books_data:
                item = QListWidgetItem(book_data.get('title', 'Untitled Book'))
                item.setData(Qt.UserRole, book_data) # Store full book dict
                self.book_list_widget.addItem(item)

            if self.book_list_widget.count() > 0:
                self.book_list_widget.setCurrentRow(0) # Select first book by default

        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "API Error", f"Failed to load books/articles: {e}")
            self.books_data = [] # Ensure it's empty on error
        except Exception as e: # Catch any other unexpected errors
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")
            self.books_data = []
        finally:
            QApplication.restoreOverrideCursor()


    def on_book_selected(self, current_book_item, previous_book_item):
        self.article_list_widget.clear()
        if not current_book_item:
            return

        book_data = current_book_item.data(Qt.UserRole)
        if book_data and 'articles' in book_data:
            for article_data in book_data['articles']:
                item = QListWidgetItem(article_data.get('filename', 'Untitled Article'))
                item.setData(Qt.UserRole, article_data) # Store article dict (id, filename)
                self.article_list_widget.addItem(item)

    def get_selected_article_id(self):
        selected_article_item = self.article_list_widget.currentItem()
        if selected_article_item:
            article_data = selected_article_item.data(Qt.UserRole)
            if article_data and 'id' in article_data:
                return article_data['id']
        return None

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Audio-Text Editor")
        self.setGeometry(100, 100, 1000, 700)  # x, y, width, height

        # Initialize instance variables for article data
        self.current_article_id = None
        self.current_audio_path = None
        self.current_title = None
        self.current_waveform_y = None # To store loaded audio y-axis data
        self.current_waveform_sr = None # To store loaded audio sampling rate

        # Attributes for waveform markers
        self.current_sentence_start_line = None
        self.current_sentence_end_line = None

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Main layout will be vertical: Button bar + Horizontal panes
        overall_layout = QVBoxLayout()

        # Button bar
        button_layout = QHBoxLayout()
        self.load_article_button = QPushButton("Load Article")
        self.load_article_button.clicked.connect(self.prompt_load_article)
        button_layout.addWidget(self.load_article_button)

        self.save_article_button = QPushButton("Save Article")
        # self.save_article_button.clicked.connect(self.save_article) # Commented out
        self.save_article_button.setEnabled(False) # Disabled
        button_layout.addWidget(self.save_article_button)

        button_layout.addStretch() # Pushes buttons to the left
        overall_layout.addLayout(button_layout)

        # Panes layout (Vertical) - MODIFIED
        panes_layout = QVBoxLayout() # MODIFIED

        # --- Left Pane (Sentences List, Editor, Update Button) ---
        left_pane_layout = QVBoxLayout()

        self.sentence_list_widget = QListWidget()
        self.sentence_list_widget.currentItemChanged.connect(self.on_sentence_selection_changed)
        left_pane_layout.addWidget(self.sentence_list_widget, 3) # Give more stretch to list

        self.sentence_editor_textedit = QTextEdit()
        self.sentence_editor_textedit.setMinimumHeight(80) # Reasonable minimum height
        left_pane_layout.addWidget(self.sentence_editor_textedit, 1) # Less stretch

        self.update_sentence_button = QPushButton("Update Sentence Text")
        self.update_sentence_button.clicked.connect(self.update_current_sentence_text)
        left_pane_layout.addWidget(self.update_sentence_button)

        left_pane_widget = QWidget()
        left_pane_widget.setLayout(left_pane_layout)
        panes_layout.addWidget(left_pane_widget, 3) # MODIFIED stretch factor

        # --- Right Pane (Waveform Display) ---
        self.waveform_plot = pg.PlotWidget()
        self.waveform_plot.setMaximumHeight(250) # ADDED maximum height
        # Add a placeholder plot (will be overwritten on load)
        self.waveform_plot.plot([0], [0], pen='w')
        # Connect click signal for splitting
        vb = self.waveform_plot.getViewBox()
        if vb: # Ensure viewBox is obtained
            vb.scene().sigMouseClicked.connect(self.on_waveform_ctrl_clicked)
            # Note: pyqtgraph MouseClickEvent is simple, might not directly give button.
            # We'll rely on keyboard modifiers for Ctrl.
        panes_layout.addWidget(self.waveform_plot, 1) # MODIFIED stretch factor

        overall_layout.addLayout(panes_layout)
        central_widget.setLayout(overall_layout)

        # Load a default article for testing if needed
        # self.load_article("test_article_1")

    def prompt_load_article(self):
        # QApplication.setOverrideCursor(Qt.WaitCursor) # Set cursor before dialog potentially lengthy ops
        # try:
        dialog = ArticleSelectionDialog(self)
        result = dialog.exec_()

        if result == QDialog.Accepted:
            selected_article_id = dialog.get_selected_article_id()
            if selected_article_id is not None:
                # Wait cursor for load_article_from_backend is handled inside that method
                self.load_article_from_backend(str(selected_article_id))
            else:
                # This case should ideally be prevented by disabling OK if no article selected,
                # but as a fallback:
                QMessageBox.warning(self, "Selection Error", "No article was selected from the dialog.")
        # else: User cancelled
        # finally:
        #     QApplication.restoreOverrideCursor()


    def load_article_from_backend(self, article_id_str: str):
        # Wait cursor is set at the beginning of this method
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            article_id = int(article_id_str)
        except ValueError:
            QMessageBox.warning(self, "Invalid ID", f"Article ID must be an integer. You entered: '{article_id_str}'")
            QApplication.restoreOverrideCursor() # Restore cursor on early exit
            return

        api_url = f"{FLASK_BACKEND_URL}/api/article/{article_id}"
        print(f"Attempting to load article from: {api_url}")
        # QApplication.setOverrideCursor(Qt.WaitCursor) # Show loading cursor - MOVED to start of func

        try:
            response = requests.get(api_url, timeout=10, verify=False) # MODIFIED to add verify=False
            response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)

            if response.status_code == 200:
                article_api_data = response.json()
                print(f"Successfully fetched data for article ID: {article_id}")

                local_audio_path = None
                converted_mp3_url = article_api_data.get('converted_mp3_url')

                if converted_mp3_url:
                    # Ensure the URL for audio download is also HTTPS if it's from the same backend
                    # Or, if it's an external URL, it might have its own scheme.
                    # For now, assuming it's also from localhost and needs similar treatment.
                    # If converted_mp3_url can be http, this might need adjustment or conditional verify=False.
                    # However, url_for(_external=True) in Flask usually respects the request's scheme.
                    # If the API endpoint itself is https, url_for should generate https URLs.
                    print(f"Attempting to download audio from: {converted_mp3_url}")
                    try:
                        audio_response = requests.get(converted_mp3_url, stream=True, timeout=30, verify=False) # MODIFIED to add verify=False
                        audio_response.raise_for_status()

                        # Save to a temporary file
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_audio_file:
                            for chunk in audio_response.iter_content(chunk_size=8192):
                                tmp_audio_file.write(chunk)
                            local_audio_path = tmp_audio_file.name
                        print(f"Audio downloaded and saved to temporary file: {local_audio_path}")
                    except requests.exceptions.RequestException as audio_req_ex:
                        error_msg = f"Error downloading audio file: {audio_req_ex}"
                        print(error_msg)
                        QMessageBox.warning(self, "Audio Download Error", error_msg)
                        # Proceed with loading article data even if audio fails
                    except Exception as audio_ex: # Catch any other exception during download/save
                        error_msg = f"An unexpected error occurred while downloading audio: {audio_ex}"
                        print(error_msg)
                        QMessageBox.critical(self, "Audio Download Failed", error_msg)
                else:
                    QMessageBox.information(self, "No Audio", "Article data loaded, but no audio URL was provided by the backend.")
                    print("No converted_mp3_url provided in API response.")

                self.process_loaded_article_data(article_api_data, local_audio_path)

            # response.raise_for_status() should handle this, but as a fallback:
            # else:
            #     error_msg = f"Failed to load article. Status: {response.status_code}, Response: {response.text}"
            #     print(error_msg)
            #     QMessageBox.warning(self, "Load Error", error_msg)

        except requests.exceptions.HTTPError as http_err:
            error_message = f"HTTP error occurred: {http_err} - {http_err.response.text if http_err.response else 'No response body'}"
            print(error_message)
            if http_err.response is not None and http_err.response.status_code == 404:
                 QMessageBox.warning(self, "Not Found", f"Article with ID '{article_id}' not found on the server.")
            else:
                 QMessageBox.critical(self, "API Error", error_message)
        except requests.exceptions.RequestException as req_ex: # Covers connection errors, timeouts, etc.
            error_msg = f"Failed to connect to backend or network error: {req_ex}"
            print(error_msg)
            QMessageBox.critical(self, "Connection Error", error_msg)
        except Exception as e: # Catch any other unexpected errors
            error_msg = f"An unexpected error occurred: {e}"
            print(error_msg)
            QMessageBox.critical(self, "Unexpected Error", error_msg)
        finally:
            QApplication.restoreOverrideCursor() # Reset cursor - THIS IS IMPORTANT HERE

    def process_loaded_article_data(self, article_api_data: dict, local_audio_path: str | None):
        """
        Processes the fetched article data and populates the UI.
        This method replaces the old load_article method's logic after data retrieval.
        """
        self.current_article_id = article_api_data.get('id')
        self.current_title = article_api_data.get('filename', f"Article {self.current_article_id}") # Fallback title
        self.current_audio_path = local_audio_path # This is now an absolute path to a temp file or None

        self.setWindowTitle(f"Audio-Text Editor - {self.current_title}")
        self.sentence_list_widget.clear()
        self.sentence_editor_textedit.clear() # Clear editor as well

        api_sentences = article_api_data.get('sentences', [])
        if not api_sentences:
            QMessageBox.information(self, "No Sentences", f"Article '{self.current_title}' loaded, but it contains no sentences.")

        # Sort sentences by paragraph_index, then sentence_index_in_paragraph (if available from API)
        # For now, we assume sentences from API are already in correct order or use a simple counter.
        # If API provides paragraph_index and sentence_index_in_paragraph, use them:
        # sorted_sentences = sorted(api_sentences, key=lambda s: (s.get('paragraph_index', 0), s.get('sentence_index_in_paragraph', 0)))
        # For now, let's just use the order they come in and generate order_id.

        for idx, sentence_api_data in enumerate(api_sentences):
            order_id = idx + 1 # Generate order_id sequentially

            # Map API fields to internal data structure
            start_time_ms = sentence_api_data.get('start_time_ms')
            end_time_ms = sentence_api_data.get('end_time_ms')

            sentence_data_internal = {
                'sentence_id': sentence_api_data.get('id'), # Use DB sentence ID
                'text': sentence_api_data.get('english_text', ''), # Use english_text
                'start_time': start_time_ms / 1000.0 if start_time_ms is not None else 0.0,
                'end_time': end_time_ms / 1000.0 if end_time_ms is not None else 0.0,
                'order_id': order_id
                # Add other fields from sentence_api_data if needed by the editor later
                # e.g. 'chinese_text', 'audio_part_index' etc.
            }

            item_text = f"{sentence_data_internal['order_id']}: {sentence_data_internal['text']}"
            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.UserRole, sentence_data_internal)
            self.sentence_list_widget.addItem(list_item)

        print(f"Processed article data: {self.current_title}")
        if self.current_audio_path:
            print(f"Audio available at temporary path: {self.current_audio_path}")
        else:
            print("No local audio path available for this article.")

        self.load_waveform()

        if self.sentence_list_widget.count() > 0:
            first_item = self.sentence_list_widget.item(0)
            if first_item:
                 self.sentence_list_widget.setCurrentItem(first_item)
        else: # No sentences, so ensure waveform markers are cleared
            self.on_sentence_selection_changed(None, None)


    def load_waveform(self):
        # Clear previous waveform data
        self.current_waveform_y = None
        self.current_waveform_sr = None
        self.waveform_plot.clear() # Clear the plot widget itself

        if not self.current_audio_path: # This is now an absolute path or None
            print("No audio path available to load waveform.")
            self.waveform_plot.setLabel('left', 'Amplitude')
            self.waveform_plot.setLabel('bottom', 'Time', units='s')
            self.waveform_plot.plot([0], [0], pen=None, symbol='o') # Plot a single point
            return

        audio_file_to_load = self.current_audio_path # Use the absolute path directly
        if logger:
            logger.info(f"Attempting to load audio from: {audio_file_to_load}")
        else: # Fallback if logger somehow isn't initialized, though it should be.
            print(f"Attempting to load audio from: {audio_file_to_load}")

        try:
            if not os.path.exists(audio_file_to_load): # Should exist if download was successful
                if logger:
                    logger.error(f"Error: Temporary audio file not found at {audio_file_to_load}")
                else:
                    print(f"Error: Temporary audio file not found at {audio_file_to_load}")
                self.waveform_plot.setLabel('left', 'Amplitude')
                self.waveform_plot.setLabel('bottom', 'Time', units='s')
                self.waveform_plot.plot([0],[0], pen=None, symbol='o')
                # Optionally, inform user via QMessageBox, but console log might be enough for this error
                return

            self.current_waveform_y, self.current_waveform_sr = librosa.load(audio_file_to_load, sr=None, mono=True)
            time_axis = np.arange(0, len(self.current_waveform_y)) / self.current_waveform_sr

            plot_data_item = self.waveform_plot.plot(time_axis, self.current_waveform_y, pen='w')
            if plot_data_item:
                plot_data_item.setDownsampling(auto=True, method='peak')
                if logger:
                    logger.debug("Enabled auto-downsampling on waveform plot.")

            self.waveform_plot.setLabel('left', 'Amplitude')
            self.waveform_plot.setLabel('bottom', 'Time', units='s')
            if logger:
                logger.info(f"Successfully loaded waveform. Shape: {self.current_waveform_y.shape}, SR: {self.current_waveform_sr}")
            else:
                print(f"Successfully loaded waveform from {self.current_audio_path}")

        except Exception as e: # Catch librosa.load errors or other issues
            if logger:
                logger.error(f"Error loading audio from {audio_file_to_load}: {e}", exc_info=True)
            else:
                error_msg = f"Error loading audio from temporary file {self.current_audio_path}: {e}" # Keep original error_msg for QMessageBox
                print(error_msg)

            self.current_waveform_y = None # Reset waveform data on error
            self.current_waveform_sr = None # Reset waveform data on error

            # Construct error_msg for QMessageBox if not already done (e.g. if logger was active)
            # This ensures QMessageBox still gets a user-friendly message.
            error_msg_for_box = f"Error loading audio from temporary file {os.path.basename(audio_file_to_load or 'Unknown File')}: {e}"
            QMessageBox.critical(self, "Waveform Load Error", error_msg_for_box)

            self.waveform_plot.setLabel('left', 'Amplitude')
            self.waveform_plot.setLabel('bottom', 'Time', units='s')
            self.waveform_plot.plot([0],[0], pen=None, symbol='o')
        # No finally block to delete temp file here, as it might be needed for playback later
        # It should be cleaned up when a new article is loaded or app closes.
        # However, self.current_audio_path stores this path, so we'd need a list of temp files to clean up.
        # For simplicity now, let OS handle temp file deletion on reboot, or implement explicit cleanup later.

    def on_sentence_selection_changed(self, current_item: QListWidgetItem, previous_item: QListWidgetItem):
        # Remove previous markers first, regardless of current_item
        if self.current_sentence_start_line:
            self.waveform_plot.removeItem(self.current_sentence_start_line)
            self.current_sentence_start_line = None
        if self.current_sentence_end_line:
            self.waveform_plot.removeItem(self.current_sentence_end_line)
            self.current_sentence_end_line = None

        if not current_item or self.current_waveform_y is None: # Corrected condition
            self.sentence_editor_textedit.setText("") # Clear editor if no item or no waveform
            # Potentially reset zoom to full view if desired, or leave as is.
            return

        current_sentence_data = self.get_sentence_data(current_item)
        if not current_sentence_data:
            self.sentence_editor_textedit.setText("") # Clear editor if no data
            return

        if logger:
            logger.info(f"Sentence selected: {current_sentence_data}")

        # Populate the sentence editor
        self.sentence_editor_textedit.setText(current_sentence_data.get('text', ''))

        current_idx = self.sentence_list_widget.row(current_item)

        prev_sentence_data = None
        if current_idx > 0:
            prev_item_widget = self.sentence_list_widget.item(current_idx - 1)
            if prev_item_widget:
                prev_sentence_data = self.get_sentence_data(prev_item_widget)

        next_sentence_data = None
        if current_idx < self.sentence_list_widget.count() - 1:
            next_item_widget = self.sentence_list_widget.item(current_idx + 1)
            if next_item_widget:
                next_sentence_data = self.get_sentence_data(next_item_widget)

        # Calculate display range
        display_start_time = current_sentence_data['start_time']
        if prev_sentence_data:
            display_start_time = prev_sentence_data['start_time']

        display_end_time = current_sentence_data['end_time']
        if next_sentence_data:
            display_end_time = next_sentence_data['end_time']

        padding_ratio = 0.10 # 10% padding
        duration = display_end_time - display_start_time
        padding = duration * padding_ratio
        if duration == 0: # Avoid zero padding if start and end are same (e.g. single sentence context)
             padding = 0.5 # Default fixed padding

        # Update waveform view
        plot_item = self.waveform_plot.getPlotItem()
        if plot_item: # Ensure plot_item is available
            if logger:
                logger.debug(f"Setting XRange: start={display_start_time - padding}, end={display_end_time + padding}, padding={padding}")
            plot_item.setXRange(display_start_time - padding, display_end_time + padding, padding=0)


        # Add new markers for the current sentence's boundaries
        current_start = current_sentence_data['start_time']
        current_end = current_sentence_data['end_time']

        # --- Time Value Validation ---
        times_to_check = [display_start_time, display_end_time, current_start, current_end, padding]
        valid_finite = all(np.isfinite(t) for t in times_to_check if t is not None) # padding can be 0
        valid_order_display = display_start_time <= display_end_time
        valid_order_current = current_start <= current_end

        if not (valid_finite and valid_order_display and valid_order_current):
            error_details = (
                f"display_start={display_start_time}, display_end={display_end_time}, "
                f"current_start={current_start}, current_end={current_end}, padding={padding}. "
                f"Checks: finite={valid_finite}, display_order={valid_order_display}, current_order={valid_order_current}."
            )
            if logger:
                logger.error(f"Invalid time values for waveform update: {error_details} Skipping pyqtgraph updates.")
            else:
                print(f"ERROR: Invalid time values for waveform update: {error_details} Skipping pyqtgraph updates.")
            return
        # --- End Time Value Validation ---

        # Start Line
        start_line_movable = current_idx > 0
        start_pen_color = 'y' if start_line_movable else 'g' # Yellow if movable, Green if fixed
        self.current_sentence_start_line = pg.InfiniteLine(pos=current_start, angle=90, movable=start_line_movable, pen=pg.mkPen(start_pen_color, width=2))
        if logger:
            logger.debug(f"Adding start line at {current_start}, movable={start_line_movable}, color='{start_pen_color}'")
        if start_line_movable and prev_item_widget: # prev_item_widget should exist if start_line_movable
            self.current_sentence_start_line.sigDragged.connect(self.on_start_delimiter_dragged)
            self.current_sentence_start_line.affected_items = (prev_item_widget, current_item)
            self.current_sentence_start_line.original_pos = current_start # Store original position for validation reset

        # End Line
        end_line_movable = current_idx < self.sentence_list_widget.count() - 1
        end_pen_color = 'y' if end_line_movable else 'r' # Yellow if movable, Red if fixed
        self.current_sentence_end_line = pg.InfiniteLine(pos=current_end, angle=90, movable=end_line_movable, pen=pg.mkPen(end_pen_color, width=2))
        if logger:
            logger.debug(f"Adding end line at {current_end}, movable={end_line_movable}, color='{end_pen_color}'")
        if end_line_movable and next_item_widget: # next_item_widget should exist if end_line_movable
            self.current_sentence_end_line.sigDragged.connect(self.on_end_delimiter_dragged)
            self.current_sentence_end_line.affected_items = (current_item, next_item_widget)
            self.current_sentence_end_line.original_pos = current_end # Store original position

        self.waveform_plot.addItem(self.current_sentence_start_line)
        self.waveform_plot.addItem(self.current_sentence_end_line)
        if logger:
            logger.info(f"Updated waveform view for sentence {current_sentence_data['sentence_id']}: start={current_start}, end={current_end}")
        else:
            print(f"Updated waveform view for sentence {current_sentence_data['sentence_id']}: {current_start}-{current_end}")

    def on_start_delimiter_dragged(self, line):
        new_time = round(line.value(), 3) # Round to e.g. milliseconds

        if not hasattr(line, 'affected_items') or not line.affected_items:
            print("Error: Start line affected_items not set.")
            return

        item_prev, item_curr = line.affected_items
        prev_data = self.get_sentence_data(item_prev)
        curr_data = self.get_sentence_data(item_curr)

        if not prev_data or not curr_data:
            print("Error: Could not get data for affected items by start delimiter.")
            if hasattr(line, 'original_pos'): line.setValue(line.original_pos)
            return

        # Validation
        min_time = prev_data['start_time']
        max_time = curr_data['end_time']

        # A small buffer to prevent zero-duration sentences, e.g., 10ms
        buffer = 0.010

        # new_time must be > prev_data.start_time + buffer AND < curr_data.end_time - buffer
        if not (prev_data['start_time'] + buffer <= new_time <= curr_data['end_time'] - buffer):
            print(f"Invalid start delimiter position: {new_time}. Must be between {prev_data['start_time'] + buffer} and {curr_data['end_time'] - buffer}.")
            # Reset to original position of the current sentence's start time
            line.setValue(curr_data['start_time'])
            return

        prev_data_copy = prev_data.copy()
        curr_data_copy = curr_data.copy()

        prev_data_copy['end_time'] = new_time
        curr_data_copy['start_time'] = new_time

        self.update_sentence_data(item_prev, prev_data_copy)
        self.update_sentence_data(item_curr, curr_data_copy)
        line.original_pos = new_time # Update original_pos after successful drag
        print(f"Start delimiter dragged. Prev_end: {new_time}, Curr_start: {new_time}")

    def on_end_delimiter_dragged(self, line):
        new_time = round(line.value(), 3)

        if not hasattr(line, 'affected_items') or not line.affected_items:
            print("Error: End line affected_items not set.")
            return

        item_curr, item_next = line.affected_items
        curr_data = self.get_sentence_data(item_curr)
        next_data = self.get_sentence_data(item_next)

        if not curr_data or not next_data:
            print("Error: Could not get data for affected items by end delimiter.")
            if hasattr(line, 'original_pos'): line.setValue(line.original_pos)
            return

        # Validation
        min_time = curr_data['start_time']
        max_time = next_data['end_time']

        buffer = 0.010 # 10ms buffer

        # new_time must be > curr_data.start_time + buffer AND < next_data.end_time - buffer
        if not (curr_data['start_time'] + buffer <= new_time <= next_data['end_time'] - buffer):
            print(f"Invalid end delimiter position: {new_time}. Must be between {curr_data['start_time'] + buffer} and {next_data['end_time'] - buffer}.")
            # Reset to original position of the current sentence's end time
            line.setValue(curr_data['end_time'])
            return

        curr_data_copy = curr_data.copy()
        next_data_copy = next_data.copy()

        curr_data_copy['end_time'] = new_time
        next_data_copy['start_time'] = new_time

        self.update_sentence_data(item_curr, curr_data_copy)
        self.update_sentence_data(item_next, next_data_copy)
        line.original_pos = new_time # Update original_pos after successful drag
        print(f"End delimiter dragged. Curr_end: {new_time}, Next_start: {new_time}")

    def update_current_sentence_text(self):
        current_item = self.sentence_list_widget.currentItem()
        if not current_item:
            print("No sentence selected to update.")
            # Optionally: show a status bar message
            return

        current_sentence_data = self.get_sentence_data(current_item)
        if not current_sentence_data:
            print("Could not retrieve data for the selected sentence.")
            return

        new_text = self.sentence_editor_textedit.toPlainText().strip()
        if not new_text:
            print("Cannot update with empty text.")
            # Optionally: show a warning dialog or status message
            return

        # Check if text actually changed to avoid unnecessary updates
        if new_text == current_sentence_data.get('text'):
            print("Text unchanged, no update performed.")
            return

        updated_data = current_sentence_data.copy()
        updated_data['text'] = new_text

        self.update_sentence_data(current_item, updated_data)
        print(f"Updated sentence {updated_data['sentence_id']} with new text: '{new_text}'")

    def on_waveform_ctrl_clicked(self, mouse_event):
        # Check for Control key modifier
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if not (modifiers & Qt.ControlModifier): # Use bitwise AND for checking modifier flags
            return

        # Check if the click was within the plot area and get the time
        # mouse_event is a pyqtgraph.GraphicsScene.MouseClickEvent
        # It has pos() (QPointF in item coords) and scenePos() (QPointF in scene coords)
        # For mapSceneToView, we need scenePos.
        # We also only care about left clicks, pyqtgraph's sigMouseClicked usually only fires for left clicks.
        # If it can fire for other buttons, mouse_event.button() might be available.
        # For now, assume left click is implied by sigMouseClicked.

        plot_item = self.waveform_plot.getPlotItem()
        if not plot_item.sceneBoundingRect().contains(mouse_event.scenePos()):
            return

        view_coords = plot_item.getViewBox().mapSceneToView(mouse_event.scenePos())
        click_time = round(view_coords.x(), 3)

        if click_time < 0 : # Clicked before the start of the audio
             return
        if self.current_waveform_y is not None and self.current_waveform_sr is not None:
            max_time = len(self.current_waveform_y) / self.current_waveform_sr
            if click_time > max_time: # Clicked after the end of the audio
                return
        else: # No waveform loaded
            return

        # Identify the sentence under the click
        original_item = None
        original_sentence_data = None
        original_idx = -1

        for i in range(self.sentence_list_widget.count()):
            item = self.sentence_list_widget.item(i)
            data = self.get_sentence_data(item)
            if data and data['start_time'] <= click_time <= data['end_time']:
                original_item = item
                original_sentence_data = data
                original_idx = i
                break

        if not original_sentence_data:
            print(f"Ctrl+Click at {click_time}s did not fall within any sentence.")
            return

        # Validation: Ensure click_time is not too close to existing boundaries
        buffer = 0.050 # 50ms buffer, can be adjusted
        if not (original_sentence_data['start_time'] + buffer < click_time < original_sentence_data['end_time'] - buffer):
            print(f"Split time {click_time}s is too close to sentence boundaries or would create a very short sentence.")
            return

        print(f"Ctrl+Click detected at {click_time}s within sentence {original_sentence_data['sentence_id']}.")

        # 1. Update original sentence
        updated_original_data = original_sentence_data.copy()
        updated_original_data['end_time'] = click_time
        # Text is not truncated automatically here. User has to edit manually.
        self.update_sentence_data(original_item, updated_original_data)

        # 2. Prepare new sentence data
        new_sentence_text = "" # New sentence starts empty
        new_sentence_id = f"sent_{int(time.time()*1000)}_{np.random.randint(1000, 9999)}" # More unique ID

        new_sentence_data_dict = {
            'sentence_id': new_sentence_id,
            'text': new_sentence_text,
            'start_time': click_time, # Starts where original ended
            'end_time': original_sentence_data['end_time'], # Takes original's old end time
            'order_id': -1 # Placeholder, will be fixed by update_order_ids
        }

        # 3. Create and insert new QListWidgetItem for the new sentence
        new_item = QListWidgetItem() # Text will be set by update_sentence_data
        self.sentence_list_widget.insertItem(original_idx + 1, new_item)
        # Now set its data and text (update_sentence_data does both)
        # Temporarily assign order_id before full re-order for display consistency
        new_sentence_data_dict['order_id'] = original_sentence_data['order_id'] +1
        self.update_sentence_data(new_item, new_sentence_data_dict)


        # 4. Re-order all subsequent sentences (update order_id)
        self.update_order_ids()

        # 5. Select the newly created item to trigger UI updates (waveform zoom, markers)
        self.sentence_list_widget.setCurrentItem(new_item)
        print(f"Sentence {original_sentence_data['sentence_id']} split. New sentence {new_sentence_id} created.")
        # TODO: Need to handle cleanup of old self.current_audio_path if a new one is loaded.
        # A list of temp files could be maintained, and cleaned on app exit or new load.

    def update_order_ids(self):
        """
        Iterates through all sentences in the list widget and updates their order_id
        sequentially, starting from 1.
        """
        for i in range(self.sentence_list_widget.count()):
            item = self.sentence_list_widget.item(i)
            if item:
                data = self.get_sentence_data(item)
                if data:
                    if data.get('order_id') != (i + 1): # Only update if necessary
                        data_copy = data.copy()
                        data_copy['order_id'] = i + 1
                        self.update_sentence_data(item, data_copy)
        print("Order IDs updated.")

    def save_article(self):
        # Saving is disabled when fetching from backend for now.
        QMessageBox.information(self, "Save Disabled", "Saving changes back to the server is not implemented in this version.")
        print("Save action called, but saving is currently disabled/not implemented for backend integration.")
        # if not self.current_article_id:
        #     QMessageBox.warning(self, "Warning", "No article loaded to save.")
        #     return
        #
        # all_sentences = self.get_all_sentences_data()
        # if not all_sentences: # Or check if any changes were made
        #     QMessageBox.information(self, "Info", "No sentences to save or no changes made.")
        #     # return # Allow saving even if empty, to effectively clear sentences if desired.
        #
        # print(f"Attempting to save article: {self.current_article_id} with {len(all_sentences)} sentences.")
        #
        # # Ensure db_mock.save_article_data is imported
        # success, message = save_article_data(self.current_article_id, all_sentences)
        #
        # if success:
        #     QMessageBox.information(self, "Success", f"Article '{self.current_article_id}' saved successfully: {message}")
        #     print(f"Save successful: {message}")
        # else:
        #     QMessageBox.critical(self, "Error", f"Failed to save article '{self.current_article_id}': {message}")
        #     print(f"Save failed: {message}")

    # Helper methods for sentence data management
    def get_sentence_data(self, item: QListWidgetItem) -> dict | None:
        """
        Retrieves the data dictionary stored in a QListWidgetItem.
        Returns None if no data is found or item is invalid.
        """
        if item:
            return item.data(Qt.UserRole)
        return None

    def get_all_sentences_data(self) -> list[dict]:
        """
        Retrieves data dictionaries for all sentences in the QListWidget.
        """
        all_sentences = []
        for i in range(self.sentence_list_widget.count()):
            item = self.sentence_list_widget.item(i)
            if item:
                sentence_data = self.get_sentence_data(item)
                if sentence_data:
                    all_sentences.append(sentence_data)
        return all_sentences

    def update_sentence_data(self, item: QListWidgetItem, new_data: dict):
        """
        Updates the data and text of a QListWidgetItem.
        """
        if not item:
            return

        # Ensure all necessary keys are present in new_data before updating
        # For this subtask, we assume new_data is valid.
        # Error checking for key existence can be added later if needed.
        item.setData(Qt.UserRole, new_data)


        # Update the item's text if 'text' or 'order_id' is in new_data
        # (to reflect potential changes)
        current_text_parts = item.text().split(":", 1)
        current_order_id_str = current_text_parts[0]

        new_order_id = new_data.get('order_id', current_order_id_str)
        new_text_content = new_data.get('text', current_text_parts[1].strip() if len(current_text_parts) > 1 else "")

        item.setText(f"{new_order_id}: {new_text_content}")

# --- Logging Setup ---
logger = None # Global logger instance

def setup_logging():
    global logger
    logger = logging.getLogger("AudioEditorApp")
    logger.setLevel(logging.DEBUG)

    # Create a rotating file handler
    log_file = "audio_editor.log"
    # Max 1MB per file, keep 3 backup files
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1*1024*1024, backupCount=3
    )
    file_handler.setLevel(logging.DEBUG)

    # Create a logging format
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(file_handler)

    # Optional: Add a console handler for debugging, if not already handled by basicConfig
    # console_handler = logging.StreamHandler()
    # console_handler.setLevel(logging.INFO) # Or DEBUG
    # console_handler.setFormatter(formatter)
    # logger.addHandler(console_handler)

def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Handles uncaught exceptions by logging them.
    """
    if logger:
        logger.error("Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback))
    # It's important to also call the default excepthook to ensure Python's normal error output
    # is still produced, especially for console applications.
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


if __name__ == '__main__':
    setup_logging() # Call setup_logging here
    sys.excepthook = handle_exception # Set the custom exception hook

    logger.info("Application starting...")

    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    # Example: Automatically load an article on startup for quick testing
    # main_window.load_article("test_article_1")
    sys.exit(app.exec_())
