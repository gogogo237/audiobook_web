import torch
# Assuming your Flask app's config will be accessible or passed where needed
# For now, we'll assume config values are passed or hardcoded for simplicity in this standalone module.
# In a real app, app.config would be used.

# Placeholder for config values - these would ideally come from app.config
# KOKORO_LANG_CODE_ZH = 'z'
# KOKORO_LANG_CODE_EN = 'a' # Or 'b'
# MANDARIN_VOICE = 'YOUR_MANDARIN_VOICE' # Example, replace
# ENGLISH_VOICE = 'YOUR_ENGLISH_VOICE' # Example, replace

try:
    from kokoro import KPipeline
    kokoro_available = True
except ImportError:
    print("Warning: 'kokoro' library not found. TTS functionality will be disabled.")
    kokoro_available = False
    KPipeline = None

kokoro_pipeline_zh = None
kokoro_pipeline_en = None
is_initialized_zh = False
is_initialized_en = False

def initialize_kokoro(lang_code_zh, lang_code_en, logger=None):
    """Initializes both Kokoro pipelines if not already done."""
    global kokoro_pipeline_zh, kokoro_pipeline_en
    global is_initialized_zh, is_initialized_en, kokoro_available

    if not kokoro_available:
        if logger: logger.error("TTS_UTILS: Kokoro library not available, skipping initialization.")
        return False

    success = True

    if not is_initialized_zh:
        try:
            if logger: logger.info(f"TTS_UTILS: Initializing Kokoro Pipeline (Mandarin, lang='{lang_code_zh}')...")
            kokoro_pipeline_zh = KPipeline(lang_code=lang_code_zh)
            is_initialized_zh = True
            if logger: logger.info("TTS_UTILS: Kokoro Mandarin Pipeline Initialized.")
        except Exception as e:
            if logger: logger.error(f"TTS_UTILS: ERROR - Could not initialize Kokoro Mandarin Pipeline: {e}", exc_info=True)
            kokoro_pipeline_zh = None
            is_initialized_zh = False # Explicitly mark as not initialized
            success = False

    if not is_initialized_en:
        try:
            if logger: logger.info(f"TTS_UTILS: Initializing Kokoro Pipeline (English, lang='{lang_code_en}')...")
            kokoro_pipeline_en = KPipeline(lang_code=lang_code_en)
            is_initialized_en = True
            if logger: logger.info("TTS_UTILS: Kokoro English Pipeline Initialized.")
        except Exception as e:
            if logger: logger.error(f"TTS_UTILS: ERROR - Could not initialize Kokoro English Pipeline: {e}", exc_info=True)
            kokoro_pipeline_en = None
            is_initialized_en = False # Explicitly mark as not initialized
            success = False
            
    return success

def get_kokoro_pipeline(lang_code, expected_lang_code_zh, expected_lang_code_en, logger=None):
    """Returns the appropriate initialized pipeline."""
    if lang_code == expected_lang_code_zh:
        if not is_initialized_zh and logger: logger.warning("TTS_UTILS: Requesting ZH pipeline, but it's not initialized.")
        return kokoro_pipeline_zh
    elif lang_code == expected_lang_code_en:
        if not is_initialized_en and logger: logger.warning("TTS_UTILS: Requesting EN pipeline, but it's not initialized.")
        return kokoro_pipeline_en
    else:
        if logger: logger.error(f"TTS_UTILS: Unsupported language code for Kokoro pipeline: {lang_code}")
        raise ValueError(f"Unsupported language code for Kokoro pipeline: {lang_code}")

def generate_audio(pipeline, text, voice, logger=None):
    """
    Generates audio data using the provided Kokoro pipeline.
    Returns: numpy.ndarray: The generated audio data.
    """
    if not pipeline:
        if logger: logger.error("TTS_UTILS: Kokoro pipeline is not initialized or available for generation.")
        raise RuntimeError("Kokoro pipeline is not initialized or available.")
    if not text or not text.strip():
        if logger: logger.warning("TTS_UTILS: Input text for TTS is empty or whitespace.")
        # Return a very short silence array instead of raising an error,
        # as an empty sentence shouldn't break the whole batch.
        # This matches pydub's behavior for empty segments.
        return torch.zeros(1).cpu().numpy() # A single zero sample

    all_audio_segments = []
    try:
        generator = pipeline(text, voice=voice)
        for _, _, audio_segment in generator:
            if isinstance(audio_segment, torch.Tensor):
                 all_audio_segments.append(audio_segment)
            else:
                 if logger: logger.warning(f"TTS_UTILS: Received non-tensor audio segment: {type(audio_segment)} for text: '{text[:30]}...'")
    except Exception as e:
        if logger: logger.error(f"TTS_UTILS: Error during Kokoro TTS generation for text '{text[:30]}...': {e}", exc_info=True)
        raise RuntimeError(f"Kokoro TTS generation failed for text: '{text[:30]}...'") from e


    if not all_audio_segments:
        if logger: logger.warning(f"TTS_UTILS: Kokoro did not produce any audio output for text: '{text[:50]}...'")
        return torch.zeros(1).cpu().numpy() # Return minimal silence

    if len(all_audio_segments) > 1:
        concatenated_audio = torch.cat(all_audio_segments, dim=0)
    else:
        concatenated_audio = all_audio_segments[0]

    return concatenated_audio.cpu().numpy()

def check_voices_configured(mandarin_voice_cfg, english_voice_cfg, logger=None):
    """Checks if placeholder voices are still used."""
    if not kokoro_available: return True # Skip check if library isn't there
    
    if mandarin_voice_cfg is None or english_voice_cfg is None or \
       mandarin_voice_cfg.startswith('YOUR_') or english_voice_cfg.startswith('YOUR_') or \
       not mandarin_voice_cfg.strip() or not english_voice_cfg.strip():
        if logger: logger.warning("TTS_UTILS: Kokoro voices appear to be unconfigured or using placeholder values.")
        return False
    return True