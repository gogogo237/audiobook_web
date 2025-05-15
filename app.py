# bilingual_app/app.py
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
import db_manager  # Assuming db_manager.py is in the same directory or python path
import text_parser # Assuming text_parser.py is in the same directory or python path

# Configuration
UPLOAD_FOLDER = 'uploads' # This is not strictly used if we process file content in memory
ALLOWED_EXTENSIONS = {'txt'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'your_very_secret_key_here_please_change_me' # IMPORTANT: Change for production

# --- Database Initialization ---
# This ensures the DB is initialized when the app starts
# and the init_db function has access to the app's logger.
with app.app_context():
    db_manager.init_db(app) # Pass the app instance for logging

def allowed_file(filename):
    """Checks if the uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part in the request.', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected for uploading.', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename) # Sanitize filename
            
            try:
                # Read file content directly from the stream
                file_content_string = file.stream.read().decode('utf-8')
            except UnicodeDecodeError:
                flash('The uploaded file is not UTF-8 encoded. Please ensure it is.', 'danger')
                return redirect(request.url)
            except Exception as e:
                app.logger.error(f"Error reading file stream for {filename}: {e}")
                flash(f'Error reading file: {str(e)}', 'danger')
                return redirect(request.url)

            if not file_content_string.strip():
                flash(f'The file "{filename}" appears to be empty.', 'warning')
                return redirect(request.url)

            try:
                # Add article to DB (or get existing ID, clearing old sentences)
                article_id = db_manager.add_article(filename)
                
                # Collect sentences to be added in batch
                sentences_to_add = []
                for p_idx, s_idx, en, zh in text_parser.parse_bilingual_file_content(file_content_string):
                    sentences_to_add.append((p_idx, s_idx, en, zh)) # (paragraph_index, sentence_index, english, chinese)
                
                sentences_added_count = 0
                if sentences_to_add:
                    # Add all collected sentences in a single batch operation
                    sentences_added_count = db_manager.add_sentences_batch(article_id, sentences_to_add)
                
                if sentences_added_count > 0:
                    flash(f'File "{filename}" processed successfully. {sentences_added_count} sentence pairs added/updated.', 'success')
                else:
                    flash(f'File "{filename}" was processed, but no valid sentence pairs were found. Please check the file format.', 'warning')

            except Exception as e:
                app.logger.error(f"Error processing file content for {filename}: {e}")
                flash(f'An error occurred while processing the file "{filename}": {str(e)}', 'danger')
            
            return redirect(url_for('index')) # Redirect to clear POST data and show updated list
        else:
            flash('Invalid file type. Only .txt files are allowed.', 'danger')
            return redirect(request.url)

    # For GET requests, display the list of articles
    try:
        articles = db_manager.get_all_articles()
    except Exception as e:
        app.logger.error(f"Error fetching articles from database: {e}")
        flash("Could not retrieve articles from the database.", "danger")
        articles = [] # Present an empty list on error
        
    return render_template('index.html', articles=articles)

@app.route('/article/<int:article_id>')
def view_article(article_id):
    try:
        article_filename = db_manager.get_article_filename(article_id)
        if not article_filename:
            flash('Article not found.', 'danger')
            return redirect(url_for('index'))

        raw_sentences = db_manager.get_sentences_for_article(article_id)
        
        structured_article = []
        if raw_sentences: 
            current_paragraph_idx = -1
            current_paragraph_sentences = []

            for sentence in raw_sentences:
                if sentence['paragraph_index'] != current_paragraph_idx:
                    if current_paragraph_sentences: 
                        structured_article.append(current_paragraph_sentences)
                    current_paragraph_idx = sentence['paragraph_index']
                    current_paragraph_sentences = [] 
                
                current_paragraph_sentences.append({
                    'english': sentence['english_text'],
                    'chinese': sentence['chinese_text']
                })
            
            if current_paragraph_sentences: 
                structured_article.append(current_paragraph_sentences)
            
        return render_template('article.html', 
                               article_filename=article_filename, 
                               structured_article=structured_article,
                               article_id=article_id)
    except Exception as e:
        app.logger.error(f"Error displaying article {article_id}: {e}")
        flash(f"An error occurred while trying to display the article: {str(e)}", "danger")
        return redirect(url_for('index'))

if __name__ == '__main__':
    # Ensure instance folder exists for the SQLite DB
    instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)
    
    # Ensure UPLOAD_FOLDER exists (though not strictly used for in-memory processing)
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        
    print("Starting Flask development server...")
    print(f"Flask app is running on http://0.0.0.0:5000/")
    print(f"To access from another device on the LAN, find this computer's IP address and use http://<YOUR_IP_ADDRESS>:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)