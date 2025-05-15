# bilingual_app/text_parser.py
import re

# --- Punctuation Conversion ---
# Mapping of Chinese punctuation (and some full-width variants) to English counterparts
CHINESE_TO_ENGLISH_PUNCTUATION_MAP = {
    '，': ',',  # Fullwidth Comma
    '。': '.',  # Ideographic Full Stop
    '“': '"',  # Left Double Quotation Mark (Chinese style)
    '”': '"',  # Right Double Quotation Mark (Chinese style)
    '‘': "'",  # Left Single Quotation Mark (Chinese style)
    '’': "'",  # Right Single Quotation Mark (Chinese style)
    '：': ':',  # Fullwidth Colon
    '；': ';',  # Fullwidth Semicolon
    '？': '?',  # Fullwidth Question Mark
    '！': '!',  # Fullwidth Exclamation Mark
    '（': '(',  # Fullwidth Left Parenthesis
    '）': ')',  # Fullwidth Right Parenthesis
    '、': ',',  # Ideographic Comma (often used like a standard comma)
    # '　': ' ', # Ideographic Space (U+3000) - uncomment if you want to convert full-width spaces too
}

# Create a translation table for efficient replacement
# This should be created once when the module is loaded.
TRANSLATION_TABLE_PUNCTUATION = str.maketrans(CHINESE_TO_ENGLISH_PUNCTUATION_MAP)

def convert_punctuation_in_english_text(text):
    """
    Converts specified Chinese/full-width punctuation marks in a text string
    to their common English equivalents.
    """
    if not text:
        return text
    return text.translate(TRANSLATION_TABLE_PUNCTUATION)

def parse_bilingual_file_content(file_content_string):
    """
    Parses the string content of a bilingual file.
    Expects paragraphs marked by <paragraph>...</paragraph>
    and English/Chinese sentences on alternating lines within.
    Yields: (paragraph_index, sentence_index_in_paragraph, english_text, chinese_text)
    """
    paragraphs = file_content_string.strip().split('<paragraph>')
    
    paragraph_index = 0
    for para_block in paragraphs:
        if not para_block.strip(): # Skip empty splits (e.g., before the first <paragraph>)
            continue

        # Remove the closing tag if present and any surrounding whitespace
        clean_para_block = para_block.replace('</paragraph>', '').strip()
        
        if not clean_para_block: # Skip if paragraph becomes empty after cleaning
            continue
            
        lines = [line.strip() for line in clean_para_block.splitlines() if line.strip()]
        
        sentence_index_in_paragraph = 0
        i = 0
        while i < len(lines) -1: # Need at least two lines for a pair
            english_text = lines[i]
            chinese_text = lines[i+1]
            
            # Convert Chinese punctuation to English in the English text
            english_text = convert_punctuation_in_english_text(english_text)

            # Basic validation: ensure we don't accidentally pair non-text lines
            if english_text and chinese_text:
                 yield (paragraph_index, sentence_index_in_paragraph, english_text, chinese_text)
                 sentence_index_in_paragraph += 1
            i += 2 # Move to the next pair
        
        if sentence_index_in_paragraph > 0: # Only increment if sentences were found
            paragraph_index += 1

# --- Example Usage (for testing the parser) ---
if __name__ == '__main__':
    sample_text_with_chinese_punc = """
<paragraph>
First sentence here。
第一句在这里。
This is a “test”，with various marks： like this！ and this？
这是一个“测试”，带有各种标记：像这样！还有这个？
And also（parentheses） and ‘single’ quotes and the ideographic comma、 for listing.
还有（括号）和‘单’引号以及顿号、用于列举。
</paragraph>
<paragraph>
Another paragraph。
另一段。
</paragraph>
    """
    print("--- Testing Punctuation Conversion ---")
    for p_idx, s_idx, en, zh in parse_bilingual_file_content(sample_text_with_chinese_punc):
        print(f"P:{p_idx}, S:{s_idx} -> EN: '{en}' | ZH: '{zh}'")

    print("\n--- Original Sample Test ---")
    sample_text = """
<paragraph>
William Stoner entered the University of Missouri as a freshman in the year 1910, at the age of nineteen.  
威廉·斯通纳于1910年进入密苏里大学成为一名新生，时年十九岁。  
Eight years later, during the height of World War I, he received his Doctor of Philosophy degree and accepted an instructorship at the same University, where he taught until his death in 1956.  
八年后，在第一次世界大战最激烈的时候，他获得了哲学博士学位，并接受了同一所大学的讲师职位，在那里他一直任教到1956年去世。  
</paragraph>
<paragraph>
An occasional student who comes upon the name may wonder idly who William Stoner was, but he seldom pursues his curiosity beyond a casual question.  
偶尔有学生看到这个名字，可能会漫不经心地想知道威廉·斯通纳是谁，但他很少会将这份好奇心延伸到随口一问之外。  
</paragraph>
    """
    for p_idx, s_idx, en, zh in parse_bilingual_file_content(sample_text):
        print(f"P:{p_idx}, S:{s_idx} -> EN: '{en}' | ZH: '{zh}'")