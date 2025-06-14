# Renamed MOCK_DB_DATA to MOCK_ARTICLES_DATA for clarity
MOCK_ARTICLES_DATA = {
    "test_article_1": {
        "article_id": "test_article_1",
        "title": "The Adventures of a Mock Audio File",
        "audio_file_path": "sample_audio.wav", # Changed to sample_audio.wav
        "sentences": [
            {
                "sentence_id": "sent_1_1",
                "text": "This is the first sentence of the first article.",
                "start_time": 0.5,
                "end_time": 3.2,
                "order_id": 1,
            },
            {
                "sentence_id": "sent_1_2",
                "text": "And here comes the second sentence, a bit longer.",
                "start_time": 3.5,
                "end_time": 7.8,
                "order_id": 2,
            },
            {
                "sentence_id": "sent_1_3",
                "text": "Finally, the third one to conclude.",
                "start_time": 8.0,
                "end_time": 10.1,
                "order_id": 3,
            },
        ],
    },
    "test_article_2": {
        "article_id": "test_article_2",
        "title": "Another Tale from the Mock Database",
        "audio_file_path": "sample_audio_2.flac",
        "sentences": [
            {
                "sentence_id": "sent_2_1",
                "text": "Sentence A from article two.",
                "start_time": 1.0,
                "end_time": 2.8,
                "order_id": 1,
            },
            {
                "sentence_id": "sent_2_2",
                "text": "Sentence B, following up.",
                "start_time": 3.0,
                "end_time": 5.5,
                "order_id": 2,
            },
        ],
    },
}

def get_article_data(article_id: str):
    """
    Simulates fetching article data from a database.
    Returns None if the article_id is not found.
    """
    # To ensure modifications in a session can be seen if reloaded (without true persistence)
    # we return a deepcopy if we want to simulate that get_article_data always fetches fresh from "DB"
    # For now, returning direct reference is fine as save will update this global dict.
    return MOCK_ARTICLES_DATA.get(article_id)

def save_article_data(article_id: str, sentences_data: list[dict]) -> tuple[bool, str]:
    """
    Simulates saving article sentences data to the mock database.
    Updates the in-memory MOCK_ARTICLES_DATA.
    """
    if article_id not in MOCK_ARTICLES_DATA:
        return False, f"Article ID '{article_id}' not found in mock DB. Cannot save."

    try:
        # Ensure data is sorted by order_id, as get_all_sentences_data should provide it in list order
        # which should correspond to order_id after updates.
        # For robustness, explicitly sort here if necessary, but typically not if UI maintains order.
        # sorted_sentences = sorted(sentences_data, key=lambda s: s['order_id'])
        # MOCK_ARTICLES_DATA[article_id]['sentences'] = sorted_sentences

        # Assuming sentences_data is already in correct order from get_all_sentences_data
        MOCK_ARTICLES_DATA[article_id]['sentences'] = sentences_data

        print(f"\n--- Mock DB Save for Article ID: {article_id} ---")
        print(f"Saved {len(sentences_data)} sentences.")
        # for sentence in sentences_data:
        #     print(f"  Order {sentence.get('order_id')}: {sentence.get('text')[:30]}... ({sentence.get('start_time')}-{sentence.get('end_time')})")
        print("--- End Mock DB Save ---")

        return True, f"Article '{article_id}' data updated in mock DB."
    except Exception as e:
        return False, f"An error occurred during mock save: {str(e)}"


if __name__ == '__main__':
    # Example usage:
    article1_data_before_save = get_article_data("test_article_1")
    if article1_data_before_save:
        print("--- Before Save ---")
        print(f"Title: {article1_data_before_save['title']}")
        for sentence in article1_data_before_save['sentences']:
            print(f" - [{sentence['order_id']}] {sentence['text']} ({sentence['start_time']}-{sentence['end_time']})")

        # Simulate some changes
        modified_sentences = [s.copy() for s in article1_data_before_save['sentences']]
        if len(modified_sentences) > 1:
            modified_sentences[0]['text'] = "This is the MODIFIED first sentence."
            modified_sentences[1]['end_time'] = 9.99
            # Add a new sentence
            modified_sentences.append({
                "sentence_id": "sent_1_new",
                "text": "A newly added sentence during test.",
                "start_time": modified_sentences[-2]['end_time'] + 0.1 if len(modified_sentences)>1 else 10.2, # Use previous sentence's end_time
                "end_time": modified_sentences[-2]['end_time'] + 2.0 if len(modified_sentences)>1 else 12.2,
                "order_id": len(modified_sentences),
            })
            # Fix order_id for the previously last sentence if a new one was appended
            if len(modified_sentences) > 1 and modified_sentences[-2]['order_id'] >= modified_sentences[-1]['order_id']:
                 modified_sentences[-2]['order_id'] = len(modified_sentences) -1


        success, message = save_article_data("test_article_1", modified_sentences)
        print(f"\nSave operation: Success={success}, Message='{message}'")

        article1_data_after_save = get_article_data("test_article_1")
        if article1_data_after_save:
            print("\n--- After Save (loading again) ---")
            print(f"Title: {article1_data_after_save['title']}")
            for sentence in article1_data_after_save['sentences']:
                print(f" - [{sentence['order_id']}] {sentence['text']} ({sentence['start_time']}-{sentence['end_time']})")

    article_non_existent = get_article_data("non_existent_id")
    if article1:
        print(f"Title: {article1['title']}")
        for sentence in article1['sentences']:
            print(f" - [{sentence['order_id']}] {sentence['text']} ({sentence['start_time']}-{sentence['end_time']})")

    article_non_existent = get_article_data("non_existent_id")
    if not article_non_existent:
        print("\nSuccessfully handled non-existent article ID.")
