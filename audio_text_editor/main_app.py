import sys
import logging
import logging.handlers
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QListWidget, QPushButton, QInputDialog, QListWidgetItem, QTextEdit, QMessageBox,
                             QDialog, QDialogButtonBox) # Added QDialog, QDialogButtonBox
from PyQt5.QtCore import Qt, QEvent, QUrl, QTimer
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
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
FLASK_BACKEND_URL = "https://localhost:5002" # Reverted to HTTP for local testing; change back to HTTPS if your local server uses a self-signed cert

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
            # For local self-signed certs, verify=False is needed. For production, use a proper cert path.
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

        # Audio Player Setup
        self.player = QMediaPlayer(None, QMediaPlayer.StreamPlayback)
        self.player.error.connect(self.handle_player_error)

        self.playback_timer = QTimer()
        self.playback_timer.timeout.connect(self.update_playback_line_position)

        self._media_status_connected = False # To ensure signal is connected only once
        self.target_start_ms = 0
        self.target_end_ms = 0

        # Playback line on waveform
        self.playback_line = pg.InfiniteLine(angle=90, pen=pg.mkPen('r', width=2), movable=False)
        self.playback_line.hide() # Initially hidden

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
            vb.scene().sigMouseClicked.connect(self.on_waveform_mouse_clicked)
            # Note: pyqtgraph MouseClickEvent is simple, might not directly give button.
            # We'll rely on keyboard modifiers for Ctrl.

        # Add playback line to the plot AFTER other items if layering matters, though usually it's fine.
        self.waveform_plot.addItem(self.playback_line)
        panes_layout.addWidget(self.waveform_plot, 1) # MODIFIED stretch factor

        overall_layout.addLayout(panes_layout)
        central_widget.setLayout(overall_layout)

    def handle_player_error(self, error):
        if logger:
           logger.error(f"MediaPlayer Error: {error} - {self.player.errorString()}", exc_info=False)
        else:
            print(f"MediaPlayer Error: {error} - {self.player.errorString()}")

        self.playback_timer.stop()
        self.playback_line.hide()
        QMessageBox.critical(self, "Playback Error", f"Error during playback: {self.player.errorString()}")

    # --- Playback Methods ---
    def play_audio_segment(self, start_time_ms: int, end_time_ms: int):
        if logger:
            logger.info(f"play_audio_segment called: start_ms={start_time_ms}, end_ms={end_time_ms}")
        else:
            print(f"play_audio_segment called: start_ms={start_time_ms}, end_ms={end_time_ms}")

        if not self.current_audio_path or not os.path.exists(self.current_audio_path):
            msg = f"No valid audio path set or file does not exist: {self.current_audio_path}"
            if logger:
                logger.error(msg)
            else:
                print(f"ERROR: {msg}")
            QMessageBox.warning(self, "Playback Error", "Audio file not available for playback.")
            return

        if self.player.state() == QMediaPlayer.PlayingState or self.player.state() == QMediaPlayer.PausedState:
            self.player.stop()
            self.playback_timer.stop()
            self.playback_line.hide()
            if logger:
                logger.debug("Player stopped, timer stopped, and playback line hidden before new playback segment.")

        self.target_start_ms = start_time_ms
        self.target_end_ms = end_time_ms

        url = QUrl.fromLocalFile(self.current_audio_path)
        content = QMediaContent(url)

        if not self._media_status_connected:
            self.player.mediaStatusChanged.connect(self.on_media_status_changed)
            self._media_status_connected = True
            if logger:
                logger.debug("Connected mediaStatusChanged signal.")

        if logger:
            logger.debug(f"Setting media to: {url.toLocalFile()}")
        self.player.setMedia(content)

    def on_media_status_changed(self, status):
        if logger:
            logger.debug(f"Media status changed: {status}")
        else:
            print(f"Media status changed: {status}")

        if status == QMediaPlayer.LoadedMedia:
            if logger:
                logger.info(f"Media loaded. Setting position to {self.target_start_ms} ms.")
            self.player.setPosition(self.target_start_ms)

            self.playback_line.setValue(self.target_start_ms / 1000.0)
            self.playback_line.show()

            self.player.play()

            self.playback_timer.start(50)
            if logger:
                logger.info(f"Playback started from {self.target_start_ms} ms. Line shown, timer started. Will stop near {self.target_end_ms} ms.")

        elif status == QMediaPlayer.EndOfMedia:
            if logger:
                logger.info("Reached QMediaPlayer.EndOfMedia. Stopping timer and hiding line.")
            self.playback_timer.stop()
            self.playback_line.hide()

        elif status == QMediaPlayer.InvalidMedia:
            err_msg = f"Invalid media: {self.player.errorString()}"
            if logger:
                logger.error(err_msg)
            QMessageBox.critical(self, "Playback Error", f"Could not load the audio for playback: Invalid media. ({self.player.errorString()})")

        elif status == QMediaPlayer.NoMedia:
            if self.player.source() and not self.player.source().isEmpty():
                 err_msg = f"No media loaded, though a source was provided: {self.player.source().url().toLocalFile() if self.player.source() else 'None'}"
                 if logger:
                     logger.error(err_msg)
                 QMessageBox.critical(self, "Playback Error", "Could not load the audio for playback: No media found.")

    def update_playback_line_position(self):
        """
        Called by the playback_timer to update the red line on the waveform.
        Also stops playback when the target end time is reached.
        """
        if self.player.state() != QMediaPlayer.PlayingState:
            return  # Don't do anything if not playing

        current_pos_ms = self.player.position()

        # Check if playback has reached or passed the end of the segment
        # self.target_end_ms > 0 is a safety check to not stop immediately if it's 0
        if self.target_end_ms > 0 and current_pos_ms >= self.target_end_ms:
            if logger:
                logger.info(f"Playback segment ended. Stopping at {current_pos_ms}ms (target was {self.target_end_ms}ms).")
            self.player.stop() # This implicitly stops the timer and hides line via state/media change signals
            # self.playback_timer.stop()
            # self.playback_line.hide()
            return  # Exit the function

        # Update the line position on the waveform
        position_sec = current_pos_ms / 1000.0
        self.playback_line.setValue(position_sec)

        # Ensure the line is visible while playing (it might be hidden by other actions)
        if not self.playback_line.isVisible():
            self.playback_line.show()

    def prompt_load_article(self):
        dialog = ArticleSelectionDialog(self)
        result = dialog.exec_()

        if result == QDialog.Accepted:
            selected_article_id = dialog.get_selected_article_id()
            if selected_article_id is not None:
                self.load_article_from_backend(str(selected_article_id))
            else:
                QMessageBox.warning(self, "Selection Error", "No article was selected from the dialog.")

    def load_article_from_backend(self, article_id_str: str):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            article_id = int(article_id_str)
        except ValueError:
            QMessageBox.warning(self, "Invalid ID", f"Article ID must be an integer. You entered: '{article_id_str}'")
            QApplication.restoreOverrideCursor()
            return

        api_url = f"{FLASK_BACKEND_URL}/api/article/{article_id}"
        print(f"Attempting to load article from: {api_url}")

        try:
            response = requests.get(api_url, timeout=10, verify=False)
            response.raise_for_status()

            if response.status_code == 200:
                article_api_data = response.json()
                print(f"Successfully fetched data for article ID: {article_id}")

                local_audio_path = None
                converted_mp3_url = article_api_data.get('converted_mp3_url')

                if converted_mp3_url:
                    print(f"Attempting to download audio from: {converted_mp3_url}")
                    try:
                        audio_response = requests.get(converted_mp3_url, stream=True, timeout=30, verify=False)
                        audio_response.raise_for_status()

                        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_audio_file:
                            for chunk in audio_response.iter_content(chunk_size=8192):
                                tmp_audio_file.write(chunk)
                            local_audio_path = tmp_audio_file.name
                        print(f"Audio downloaded and saved to temporary file: {local_audio_path}")
                    except requests.exceptions.RequestException as audio_req_ex:
                        error_msg = f"Error downloading audio file: {audio_req_ex}"
                        print(error_msg)
                        QMessageBox.warning(self, "Audio Download Error", error_msg)
                    except Exception as audio_ex:
                        error_msg = f"An unexpected error occurred while downloading audio: {audio_ex}"
                        print(error_msg)
                        QMessageBox.critical(self, "Audio Download Failed", error_msg)
                else:
                    QMessageBox.information(self, "No Audio", "Article data loaded, but no audio URL was provided by the backend.")
                    print("No converted_mp3_url provided in API response.")

                self.process_loaded_article_data(article_api_data, local_audio_path)

        except requests.exceptions.HTTPError as http_err:
            error_message = f"HTTP error occurred: {http_err} - {http_err.response.text if http_err.response else 'No response body'}"
            print(error_message)
            if http_err.response is not None and http_err.response.status_code == 404:
                 QMessageBox.warning(self, "Not Found", f"Article with ID '{article_id}' not found on the server.")
            else:
                 QMessageBox.critical(self, "API Error", error_message)
        except requests.exceptions.RequestException as req_ex:
            error_msg = f"Failed to connect to backend or network error: {req_ex}"
            print(error_msg)
            QMessageBox.critical(self, "Connection Error", error_msg)
        except Exception as e:
            error_msg = f"An unexpected error occurred: {e}"
            print(error_msg)
            QMessageBox.critical(self, "Unexpected Error", error_msg)
        finally:
            QApplication.restoreOverrideCursor()

    def process_loaded_article_data(self, article_api_data: dict, local_audio_path: str | None):
        """
        Processes the fetched article data and populates the UI.
        """
        self.current_article_id = article_api_data.get('id')
        self.current_title = article_api_data.get('filename', f"Article {self.current_article_id}")
        self.current_audio_path = local_audio_path

        self.setWindowTitle(f"Audio-Text Editor - {self.current_title}")
        self.sentence_list_widget.clear()
        self.sentence_editor_textedit.clear()

        api_sentences = article_api_data.get('sentences', [])
        if not api_sentences:
            QMessageBox.information(self, "No Sentences", f"Article '{self.current_title}' loaded, but it contains no sentences.")

        for idx, sentence_api_data in enumerate(api_sentences):
            order_id = idx + 1

            start_time_ms = sentence_api_data.get('start_time_ms')
            end_time_ms = sentence_api_data.get('end_time_ms')

            sentence_data_internal = {
                'sentence_id': sentence_api_data.get('id'),
                'text': sentence_api_data.get('english_text', ''),
                'start_time': start_time_ms / 1000.0 if start_time_ms is not None else 0.0,
                'end_time': end_time_ms / 1000.0 if end_time_ms is not None else 0.0,
                'order_id': order_id
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
        else:
            self.on_sentence_selection_changed(None, None)


    def load_waveform(self):
        self.current_waveform_y = None
        self.current_waveform_sr = None
        self.waveform_plot.clear()

        if not self.current_audio_path:
            print("No audio path available to load waveform.")
            self.waveform_plot.setLabel('left', 'Amplitude')
            self.waveform_plot.setLabel('bottom', 'Time', units='s')
            self.waveform_plot.plot([0], [0], pen=None, symbol='o')
            return

        audio_file_to_load = self.current_audio_path
        if logger:
            logger.info(f"Attempting to load audio from: {audio_file_to_load}")
        else:
            print(f"Attempting to load audio from: {audio_file_to_load}")

        try:
            if not os.path.exists(audio_file_to_load):
                if logger:
                    logger.error(f"Error: Temporary audio file not found at {audio_file_to_load}")
                else:
                    print(f"Error: Temporary audio file not found at {audio_file_to_load}")
                self.waveform_plot.setLabel('left', 'Amplitude')
                self.waveform_plot.setLabel('bottom', 'Time', units='s')
                self.waveform_plot.plot([0],[0], pen=None, symbol='o')
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

        except Exception as e:
            if logger:
                logger.error(f"Error loading audio from {audio_file_to_load}: {e}", exc_info=True)
            else:
                error_msg = f"Error loading audio from temporary file {self.current_audio_path}: {e}"
                print(error_msg)

            self.current_waveform_y = None
            self.current_waveform_sr = None

            error_msg_for_box = f"Error loading audio from temporary file {os.path.basename(audio_file_to_load or 'Unknown File')}: {e}"
            QMessageBox.critical(self, "Waveform Load Error", error_msg_for_box)

            self.waveform_plot.setLabel('left', 'Amplitude')
            self.waveform_plot.setLabel('bottom', 'Time', units='s')
            self.waveform_plot.plot([0],[0], pen=None, symbol='o')

    def on_sentence_selection_changed(self, current_item: QListWidgetItem, previous_item: QListWidgetItem):
        if self.current_sentence_start_line:
            self.waveform_plot.removeItem(self.current_sentence_start_line)
            self.current_sentence_start_line = None
        if self.current_sentence_end_line:
            self.waveform_plot.removeItem(self.current_sentence_end_line)
            self.current_sentence_end_line = None

        if not current_item or self.current_waveform_y is None:
            self.sentence_editor_textedit.setText("")
            return

        current_sentence_data = self.get_sentence_data(current_item)
        if not current_sentence_data:
            self.sentence_editor_textedit.setText("")
            return

        if logger:
            logger.info(f"Sentence selected: {current_sentence_data}")

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

        display_start_time = current_sentence_data['start_time']
        if prev_sentence_data:
            display_start_time = prev_sentence_data['start_time']

        display_end_time = current_sentence_data['end_time']
        if next_sentence_data:
            display_end_time = next_sentence_data['end_time']

        padding_ratio = 0.10
        duration = display_end_time - display_start_time
        padding = duration * padding_ratio
        if duration == 0:
             padding = 0.5

        plot_item = self.waveform_plot.getPlotItem()
        if plot_item:
            if logger:
                logger.debug(f"Setting XRange: start={display_start_time - padding}, end={display_end_time + padding}, padding={padding}")
            plot_item.setXRange(display_start_time - padding, display_end_time + padding, padding=0)


        current_start = current_sentence_data['start_time']
        current_end = current_sentence_data['end_time']

        times_to_check = [display_start_time, display_end_time, current_start, current_end, padding]
        valid_finite = all(np.isfinite(t) for t in times_to_check if t is not None)
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

        start_line_movable = current_idx > 0
        start_pen_color = 'y' if start_line_movable else 'g'
        self.current_sentence_start_line = pg.InfiniteLine(pos=current_start, angle=90, movable=start_line_movable, pen=pg.mkPen(start_pen_color, width=2))
        if logger:
            logger.debug(f"Adding start line at {current_start}, movable={start_line_movable}, color='{start_pen_color}'")
        if start_line_movable and prev_item_widget:
            self.current_sentence_start_line.sigDragged.connect(self.on_start_delimiter_dragged)
            self.current_sentence_start_line.affected_items = (prev_item_widget, current_item)
            self.current_sentence_start_line.original_pos = current_start

        end_line_movable = current_idx < self.sentence_list_widget.count() - 1
        end_pen_color = 'y' if end_line_movable else 'r'
        self.current_sentence_end_line = pg.InfiniteLine(pos=current_end, angle=90, movable=end_line_movable, pen=pg.mkPen(end_pen_color, width=2))
        if logger:
            logger.debug(f"Adding end line at {current_end}, movable={end_line_movable}, color='{end_pen_color}'")
        if end_line_movable and next_item_widget:
            self.current_sentence_end_line.sigDragged.connect(self.on_end_delimiter_dragged)
            self.current_sentence_end_line.affected_items = (current_item, next_item_widget)
            self.current_sentence_end_line.original_pos = current_end

        self.waveform_plot.addItem(self.current_sentence_start_line)
        self.waveform_plot.addItem(self.current_sentence_end_line)
        if logger:
            logger.info(f"Updated waveform view for sentence {current_sentence_data['sentence_id']}: start={current_start}, end={current_end}")
        else:
            print(f"Updated waveform view for sentence {current_sentence_data['sentence_id']}: {current_start}-{current_end}")

    def on_start_delimiter_dragged(self, line):
        new_time = round(line.value(), 3)

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

        buffer = 0.010

        if not (prev_data['start_time'] + buffer <= new_time <= curr_data['end_time'] - buffer):
            print(f"Invalid start delimiter position: {new_time}. Must be between {prev_data['start_time'] + buffer} and {curr_data['end_time'] - buffer}.")
            line.setValue(curr_data['start_time'])
            return

        prev_data_copy = prev_data.copy()
        curr_data_copy = curr_data.copy()

        prev_data_copy['end_time'] = new_time
        curr_data_copy['start_time'] = new_time

        self.update_sentence_data(item_prev, prev_data_copy)
        self.update_sentence_data(item_curr, curr_data_copy)
        line.original_pos = new_time
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

        buffer = 0.010

        if not (curr_data['start_time'] + buffer <= new_time <= next_data['end_time'] - buffer):
            print(f"Invalid end delimiter position: {new_time}. Must be between {curr_data['start_time'] + buffer} and {next_data['end_time'] - buffer}.")
            line.setValue(curr_data['end_time'])
            return

        curr_data_copy = curr_data.copy()
        next_data_copy = next_data.copy()

        curr_data_copy['end_time'] = new_time
        next_data_copy['start_time'] = new_time

        self.update_sentence_data(item_curr, curr_data_copy)
        self.update_sentence_data(item_next, next_data_copy)
        line.original_pos = new_time
        print(f"End delimiter dragged. Curr_end: {new_time}, Next_start: {new_time}")

    def update_current_sentence_text(self):
        current_item = self.sentence_list_widget.currentItem()
        if not current_item:
            print("No sentence selected to update.")
            return

        current_sentence_data = self.get_sentence_data(current_item)
        if not current_sentence_data:
            print("Could not retrieve data for the selected sentence.")
            return

        new_text = self.sentence_editor_textedit.toPlainText().strip()
        if not new_text:
            print("Cannot update with empty text.")
            return

        if new_text == current_sentence_data.get('text'):
            print("Text unchanged, no update performed.")
            return

        updated_data = current_sentence_data.copy()
        updated_data['text'] = new_text

        self.update_sentence_data(current_item, updated_data)
        print(f"Updated sentence {updated_data['sentence_id']} with new text: '{new_text}'")

    def on_waveform_mouse_clicked(self, mouse_event):
        plot_item = self.waveform_plot.getPlotItem()
        if not plot_item.sceneBoundingRect().contains(mouse_event.scenePos()):
            return

        view_coords = plot_item.getViewBox().mapSceneToView(mouse_event.scenePos())
        click_time = round(view_coords.x(), 3)

        if click_time < 0:
            return
        if self.current_waveform_y is not None and self.current_waveform_sr is not None:
            max_time = len(self.current_waveform_y) / self.current_waveform_sr
            if click_time > max_time:
                return
        else:
            return

        modifiers = QtWidgets.QApplication.keyboardModifiers()

        if modifiers & Qt.ControlModifier:
            if logger:
                logger.debug(f"Ctrl-Click detected at {click_time}s for splitting.")
            self.handle_split_action(click_time)
        else:
            if logger:
                logger.info(f"Simple click detected at {click_time}s for playback.")

            playback_initiated = False
            for i in range(self.sentence_list_widget.count()):
                item = self.sentence_list_widget.item(i)
                sentence_data = self.get_sentence_data(item)
                if sentence_data:
                    sentence_start_sec = sentence_data.get('start_time', 0)
                    sentence_end_sec = sentence_data.get('end_time', 0)

                    if sentence_start_sec <= click_time < sentence_end_sec:
                        start_playback_ms = int(click_time * 1000)
                        end_playback_ms = int(sentence_end_sec * 1000)
                        if logger:
                            logger.info(f"Simple click: Initiating playback from {click_time:.3f}s (sentence {sentence_data.get('sentence_id', 'N/A')}) to sentence end {sentence_end_sec:.3f}s.")
                        self.play_audio_segment(start_playback_ms, end_playback_ms)
                        playback_initiated = True
                        break

            if not playback_initiated and logger:
                logger.info(f"Simple click at {click_time:.3f}s is not within any sentence's time range. No playback initiated.")

    def handle_split_action(self, click_time: float):
        """Handles the logic for splitting a sentence at the given click_time."""
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
            if logger:
                logger.warn(f"Split action: Click at {click_time:.3f}s did not fall within any sentence.")
            else:
                print(f"Ctrl+Click at {click_time}s did not fall within any sentence.")
            return

        buffer = 0.050
        if not (original_sentence_data['start_time'] + buffer < click_time < original_sentence_data['end_time'] - buffer):
            if logger:
                logger.warn(f"Split time {click_time:.3f}s is too close to sentence boundaries of sentence {original_sentence_data['sentence_id']} or would create a very short sentence. Min allowed: {original_sentence_data['start_time'] + buffer}, Max allowed: {original_sentence_data['end_time'] - buffer}")
            else:
                print(f"Split time {click_time}s is too close to sentence boundaries or would create a very short sentence.")
            return

        if logger:
            logger.info(f"Splitting sentence {original_sentence_data['sentence_id']} at {click_time:.3f}s.")
        else:
            print(f"Ctrl+Click detected at {click_time}s within sentence {original_sentence_data['sentence_id']}.")

        updated_original_data = original_sentence_data.copy()
        updated_original_data['end_time'] = click_time
        self.update_sentence_data(original_item, updated_original_data)

        new_sentence_text = ""
        new_sentence_id = f"sent_{int(time.time()*1000)}_{np.random.randint(1000, 9999)}"

        new_sentence_data_dict = {
            'sentence_id': new_sentence_id,
            'text': new_sentence_text,
            'start_time': click_time,
            'end_time': original_sentence_data['end_time'],
            'order_id': -1
        }

        new_item = QListWidgetItem()
        self.sentence_list_widget.insertItem(original_idx + 1, new_item)
        new_sentence_data_dict['order_id'] = original_sentence_data['order_id'] +1
        self.update_sentence_data(new_item, new_sentence_data_dict)

        self.update_order_ids()
        self.sentence_list_widget.setCurrentItem(new_item)
        print(f"Sentence {original_sentence_data['sentence_id']} split. New sentence {new_sentence_id} created.")

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
                    if data.get('order_id') != (i + 1):
                        data_copy = data.copy()
                        data_copy['order_id'] = i + 1
                        self.update_sentence_data(item, data_copy)
        print("Order IDs updated.")

    def save_article(self):
        QMessageBox.information(self, "Save Disabled", "Saving changes back to the server is not implemented in this version.")
        print("Save action called, but saving is currently disabled/not implemented for backend integration.")

    # Helper methods for sentence data management
    def get_sentence_data(self, item: QListWidgetItem) -> dict | None:
        if item:
            return item.data(Qt.UserRole)
        return None

    def get_all_sentences_data(self) -> list[dict]:
        all_sentences = []
        for i in range(self.sentence_list_widget.count()):
            item = self.sentence_list_widget.item(i)
            if item:
                sentence_data = self.get_sentence_data(item)
                if sentence_data:
                    all_sentences.append(sentence_data)
        return all_sentences

    def update_sentence_data(self, item: QListWidgetItem, new_data: dict):
        if not item:
            return

        item.setData(Qt.UserRole, new_data)

        current_text_parts = item.text().split(":", 1)
        current_order_id_str = current_text_parts[0]

        new_order_id = new_data.get('order_id', current_order_id_str)
        new_text_content = new_data.get('text', current_text_parts[1].strip() if len(current_text_parts) > 1 else "")

        item.setText(f"{new_order_id}: {new_text_content}")

# --- Logging Setup ---
logger = None

def setup_logging():
    global logger
    logger = logging.getLogger("AudioEditorApp")
    logger.setLevel(logging.DEBUG)

    log_file = "audio_editor.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1*1024*1024, backupCount=3
    )
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Handles uncaught exceptions by logging them.
    """
    if logger:
        logger.error("Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback))
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


if __name__ == '__main__':
    setup_logging()
    sys.excepthook = handle_exception

    logger.info("Application starting...")

    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())