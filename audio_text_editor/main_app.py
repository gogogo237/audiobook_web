import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QListWidget, QPushButton, QInputDialog, QListWidgetItem, QTextEdit, QMessageBox) # Added QMessageBox
from PyQt5.QtCore import Qt, QEvent
from PyQt5 import QtWidgets # For QApplication.keyboardModifiers()
import pyqtgraph as pg
from db_mock import get_article_data, save_article_data # Import save_article_data
import librosa
import numpy as np
import os # For checking file path
import time # For generating unique sentence IDs

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
        self.save_article_button.clicked.connect(self.save_article)
        button_layout.addWidget(self.save_article_button)

        button_layout.addStretch() # Pushes buttons to the left
        overall_layout.addLayout(button_layout)

        # Panes layout (Horizontal)
        panes_layout = QHBoxLayout()

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
        panes_layout.addWidget(left_pane_widget, 1) # Left pane gets 1 part of stretch

        # --- Right Pane (Waveform Display) ---
        self.waveform_plot = pg.PlotWidget()
        # Add a placeholder plot (will be overwritten on load)
        self.waveform_plot.plot([0], [0], pen='w')
        # Connect click signal for splitting
        vb = self.waveform_plot.getViewBox()
        if vb: # Ensure viewBox is obtained
            vb.scene().sigMouseClicked.connect(self.on_waveform_ctrl_clicked)
            # Note: pyqtgraph MouseClickEvent is simple, might not directly give button.
            # We'll rely on keyboard modifiers for Ctrl.
        panes_layout.addWidget(self.waveform_plot, 2) # Assign stretch factor

        overall_layout.addLayout(panes_layout)
        central_widget.setLayout(overall_layout)

        # Load a default article for testing if needed
        # self.load_article("test_article_1")

    def prompt_load_article(self):
        # For now, we'll hardcode the article ID.
        # Later, this could use QInputDialog:
        # article_id, ok = QInputDialog.getText(self, 'Load Article', 'Enter Article ID:')
        # if ok and article_id:
        #     self.load_article(article_id)
        self.load_article("test_article_1")

    def load_article(self, article_id: str):
        article_data = get_article_data(article_id)
        if not article_data:
            print(f"Error: Article ID '{article_id}' not found.")
            # Optionally, show a QMessageBox to the user
            return

        self.current_article_id = article_data['article_id']
        self.current_title = article_data['title']
        self.current_audio_path = article_data['audio_file_path']

        self.setWindowTitle(f"Audio-Text Editor - {self.current_title}")
        self.sentence_list_widget.clear()

        # Sort sentences by order_id before displaying
        sorted_sentences = sorted(article_data['sentences'], key=lambda s: s['order_id'])

        for sentence_data in sorted_sentences:
            # Consistent item text format
            item_text = f"{sentence_data['order_id']}: {sentence_data['text']}"
            list_item = QListWidgetItem(item_text)

            # Store the full sentence data dictionary in the item
            # This sentence_data comes from db_mock and includes all required keys:
            # sentence_id, text, start_time, end_time, order_id
            list_item.setData(Qt.UserRole, sentence_data)
            self.sentence_list_widget.addItem(list_item)

        print(f"Loaded article: {self.current_title}")
        print(f"Audio path: {self.current_audio_path}")
        # You could add a print statement here to show sentences loaded for debugging in headless env
        # for i in range(self.sentence_list_widget.count()):
        #    item = self.sentence_list_widget.item(i)
        #    data = item.data(Qt.UserRole)
        #    print(data['text'])

        # Load and display waveform
        self.load_waveform() # This loads data but doesn't plot the initial view based on selection yet

        # After loading sentences and waveform, select the first sentence
        if self.sentence_list_widget.count() > 0:
            first_item = self.sentence_list_widget.item(0)
            if first_item: # Ensure item exists
                 self.sentence_list_widget.setCurrentItem(first_item)
        # self.on_sentence_selection_changed will be called due to setCurrentItem,
        # so initial view and markers will be set.
        # If no sentences, on_sentence_selection_changed(None, None) should handle it.

    def load_waveform(self):
        # Clear previous waveform data
        self.current_waveform_y = None
        self.current_waveform_sr = None
        self.waveform_plot.clear() # Clear the plot widget itself

        if not self.current_audio_path:
            print("Error: Audio path is not set.")
            # self.waveform_plot.clear() # Already cleared
            self.waveform_plot.setLabel('left', 'Amplitude')
            self.waveform_plot.setLabel('bottom', 'Time', units='s')
            self.waveform_plot.plot([0], [0], pen=None, symbol='o') # Plot a single point
            return

        # Construct the full path to the audio file, assuming it's in the same directory as the script or project root
        # For the subtask, sample_audio.wav is in audio_text_editor directory.
        # If main_app.py is in audio_text_editor, then self.current_audio_path can be relative like "sample_audio.wav"
        # If running from outside, an absolute path or more robust relative path might be needed.
        # For now, assume current_audio_path is directly usable or relative to the app's execution dir.

        # Construct the full path to the audio file.
        # __file__ is the path to the current script (main_app.py)
        # os.path.dirname(__file__) is the directory audio_text_editor/
        # self.current_audio_path is "sample_audio.wav"
        # So, this should correctly point to audio_text_editor/sample_audio.wav
        audio_file_to_load = os.path.join(os.path.dirname(__file__), self.current_audio_path)

        try:
            print(f"Attempting to load audio from: {audio_file_to_load}")
            # Ensure the file exists before trying to load
            if not os.path.exists(audio_file_to_load):
                print(f"Error: Audio file not found at {audio_file_to_load}")
                # self.waveform_plot.clear() # Already cleared
                self.waveform_plot.setLabel('left', 'Amplitude')
                self.waveform_plot.setLabel('bottom', 'Time', units='s')
                self.waveform_plot.plot([0],[0], pen=None, symbol='o')
                return

            self.current_waveform_y, self.current_waveform_sr = librosa.load(audio_file_to_load, sr=None, mono=True)
            time_axis = np.arange(0, len(self.current_waveform_y)) / self.current_waveform_sr

            # self.waveform_plot.clear() # Already cleared
            self.waveform_plot.plot(time_axis, self.current_waveform_y, pen='w') # Plot the full waveform initially
            self.waveform_plot.setLabel('left', 'Amplitude')
            self.waveform_plot.setLabel('bottom', 'Time', units='s')
            print(f"Successfully loaded waveform for {self.current_audio_path}")

        except FileNotFoundError:
            print(f"Error: Audio file not found at {audio_file_to_load}.")
            # self.waveform_plot.clear() # Already cleared
            self.waveform_plot.setLabel('left', 'Amplitude')
            self.waveform_plot.setLabel('bottom', 'Time', units='s')
            self.waveform_plot.plot([0],[0], pen=None, symbol='o')
        except Exception as e:
            print(f"Error loading audio file {self.current_audio_path}: {e}")
            # self.waveform_plot.clear() # Already cleared
            self.waveform_plot.setLabel('left', 'Amplitude')
            self.waveform_plot.setLabel('bottom', 'Time', units='s')
            self.waveform_plot.plot([0],[0], pen=None, symbol='o')

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
             plot_item.setXRange(display_start_time - padding, display_end_time + padding, padding=0)


        # Add new markers for the current sentence's boundaries
        current_start = current_sentence_data['start_time']
        current_end = current_sentence_data['end_time']

        # Start Line
        start_line_movable = current_idx > 0
        start_pen_color = 'y' if start_line_movable else 'g' # Yellow if movable, Green if fixed
        self.current_sentence_start_line = pg.InfiniteLine(pos=current_start, angle=90, movable=start_line_movable, pen=pg.mkPen(start_pen_color, width=2))
        if start_line_movable and prev_item_widget: # prev_item_widget should exist if start_line_movable
            self.current_sentence_start_line.sigDragged.connect(self.on_start_delimiter_dragged)
            self.current_sentence_start_line.affected_items = (prev_item_widget, current_item)
            self.current_sentence_start_line.original_pos = current_start # Store original position for validation reset

        # End Line
        end_line_movable = current_idx < self.sentence_list_widget.count() - 1
        end_pen_color = 'y' if end_line_movable else 'r' # Yellow if movable, Red if fixed
        self.current_sentence_end_line = pg.InfiniteLine(pos=current_end, angle=90, movable=end_line_movable, pen=pg.mkPen(end_pen_color, width=2))
        if end_line_movable and next_item_widget: # next_item_widget should exist if end_line_movable
            self.current_sentence_end_line.sigDragged.connect(self.on_end_delimiter_dragged)
            self.current_sentence_end_line.affected_items = (current_item, next_item_widget)
            self.current_sentence_end_line.original_pos = current_end # Store original position

        self.waveform_plot.addItem(self.current_sentence_start_line)
        self.waveform_plot.addItem(self.current_sentence_end_line)
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
                    if data['order_id'] != (i + 1): # Only update if necessary
                        data_copy = data.copy()
                        data_copy['order_id'] = i + 1
                        self.update_sentence_data(item, data_copy)
        print("Order IDs updated.")

    def save_article(self):
        if not self.current_article_id:
            QMessageBox.warning(self, "Warning", "No article loaded to save.")
            return

        all_sentences = self.get_all_sentences_data()
        if not all_sentences: # Or check if any changes were made
            QMessageBox.information(self, "Info", "No sentences to save or no changes made.")
            # return # Allow saving even if empty, to effectively clear sentences if desired.

        print(f"Attempting to save article: {self.current_article_id} with {len(all_sentences)} sentences.")

        # Ensure db_mock.save_article_data is imported
        success, message = save_article_data(self.current_article_id, all_sentences)

        if success:
            QMessageBox.information(self, "Success", f"Article '{self.current_article_id}' saved successfully: {message}")
            print(f"Save successful: {message}")
        else:
            QMessageBox.critical(self, "Error", f"Failed to save article '{self.current_article_id}': {message}")
            print(f"Save failed: {message}")

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


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    # Example: Automatically load an article on startup for quick testing
    # main_window.load_article("test_article_1")
    sys.exit(app.exec_())
