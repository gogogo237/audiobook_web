// static/js/article_view_audio.js
// Depends on:
// - article_view_config.js (for audioContext, audioBuffer, currentSourceNode, isAudiobookModeFull, currentPlayingSentence, maxSentenceEndTime, HAS_TIMESTAMPS, contextualMenu, toggleAudiobookModeButton, localAudioFileInput, audioFileNameSpan, audiobookHint, isPartsViewActive)
// - article_view_ui.js (for updatePartsViewModeUI)
// - article_view_sentences.js (for getAdjacentSentence - though direct calls might be refactored later)

// Global state variables (audioContext, audioBuffer, etc.) are expected to be defined in article_view_config.js

function initAudioContextGlobally() {
    // Uses global: audioContext (from config.js)
    if (!window.audioContext && (window.AudioContext || window.webkitAudioContext)) {
        try {
            window.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            console.log("JS_AUDIO: AudioContext initialized.");
        } catch (e) {
            console.error("JS_AUDIO: Error initializing AudioContext:", e);
            return false;
        }
    }
    if (window.audioContext && window.audioContext.state === 'suspended') {
        window.audioContext.resume().then(() => {
            console.log("JS_AUDIO: AudioContext resumed successfully.");
        }).catch(e => {
            console.error("JS_AUDIO: Failed to resume AudioContext:", e);
        });
    }
    return window.audioContext ? true : false;
}

function playSentenceAudio(sentenceElement, isPlayingFromPart, optionalDesiredStartTimeMs = null) {
    // Uses global: audioContext (from config.js)
    // Calls global: initAudioContextGlobally (this file), proceedWithPlayback (this file)
    if (!initAudioContextGlobally()) {
        console.warn("JS_AUDIO: Audio system could not be initialized for playSentenceAudio.");
        return;
    }
    if (window.audioContext.state === 'suspended') {
        window.audioContext.resume().then(() => proceedWithPlayback(sentenceElement, isPlayingFromPart, optionalDesiredStartTimeMs))
                          .catch(e => { console.error("JS_AUDIO: Could not start audio playback. User interaction might be needed.", e); });
    } else {
        proceedWithPlayback(sentenceElement, isPlayingFromPart, optionalDesiredStartTimeMs);
    }
}

function proceedWithPlayback(sentenceElement, isPlayingFromPart, optionalDesiredStartTimeMs = null) {
    // Uses global: audioBuffer, isAudiobookModeFull, isAudiobookModeParts, currentPlayingSentence,
    //              currentSourceNode, audioContext, highlightedSentence, contextualMenu (all from config.js)
    // Calls global: stopCurrentAudio (this file)
    if (!window.audioBuffer) {
        if (window.isAudiobookModeFull) alert("Please load the full audio file first.");
        else if (window.isAudiobookModeParts) alert("Please load the selected audio part first.");
        return;
    }
    stopCurrentAudio(); // stop any currently playing audio

    if (window.currentPlayingSentence && window.currentPlayingSentence !== sentenceElement) {
        window.currentPlayingSentence.classList.remove('playing-sentence');
    }

    let originalSentenceStartTimeMs, originalSentenceEndTimeMs;
    if (isPlayingFromPart) {
        originalSentenceStartTimeMs = parseInt(sentenceElement.dataset.startTimeInPartMs, 10);
        originalSentenceEndTimeMs = parseInt(sentenceElement.dataset.endTimeInPartMs, 10);
    } else {
        originalSentenceStartTimeMs = parseInt(sentenceElement.dataset.startTimeMs, 10);
        originalSentenceEndTimeMs = parseInt(sentenceElement.dataset.endTimeMs, 10);
    }

    let playbackStartTimeMs;
    let playbackEndTimeMs = originalSentenceEndTimeMs;

    if (optionalDesiredStartTimeMs !== null && optionalDesiredStartTimeMs >= 0) {
        playbackStartTimeMs = optionalDesiredStartTimeMs;
        if (playbackStartTimeMs >= playbackEndTimeMs) {
            console.warn(`JS_AUDIO: Desired start time ${playbackStartTimeMs}ms is at or after sentence end ${playbackEndTimeMs}ms. Not playing.`);
            return;
        }
    } else {
        playbackStartTimeMs = originalSentenceStartTimeMs;
    }

    if (isNaN(playbackStartTimeMs) || isNaN(playbackEndTimeMs)) {
        console.warn("JS_AUDIO: Sentence missing time data for playback. Cannot play audio for:", sentenceElement.textContent.substring(0, 50) + "...");
        return;
    }

    const offsetInSeconds = playbackStartTimeMs / 1000.0;
    let durationInSeconds = (playbackEndTimeMs - playbackStartTimeMs) / 1000.0;

    if (durationInSeconds <= 0) {
         console.warn(`JS_AUDIO: Calculated playback duration (${durationInSeconds.toFixed(3)}s) is zero or negative. Not playing.`);
         return;
    }

    if (offsetInSeconds < 0 || offsetInSeconds >= window.audioBuffer.duration) {
        console.warn(`JS_AUDIO: Calculated playback start time (${offsetInSeconds.toFixed(2)}s) is out of audio buffer bounds (duration ${window.audioBuffer.duration.toFixed(2)}s).`);
        return;
    }
    durationInSeconds = Math.min(durationInSeconds, window.audioBuffer.duration - offsetInSeconds);
     if (durationInSeconds <= 0) {
         console.warn(`JS_AUDIO: Calculated playback duration (${durationInSeconds.toFixed(3)}s) became zero/negative after buffer adjustment. Not playing.`);
         return;
    }

    window.currentPlayingSentence = sentenceElement;
    window.currentPlayingSentence.classList.add('playing-sentence');

    window.currentSourceNode = window.audioContext.createBufferSource();
    window.currentSourceNode.buffer = window.audioBuffer;
    window.currentSourceNode.connect(window.audioContext.destination);
    const thisSourceNodeForOnEnded = window.currentSourceNode; // Closure for onended

    window.currentSourceNode.onended = () => {
        if (window.currentSourceNode === thisSourceNodeForOnEnded) window.currentSourceNode = null; // Clear only if it's the same node
        if (window.currentPlayingSentence === sentenceElement) {
            window.currentPlayingSentence.classList.remove('playing-sentence');
            // Update contextual menu if it's visible for this sentence
            if (window.contextualMenu && window.contextualMenu.style.display === 'block' && window.highlightedSentence === sentenceElement) {
                const audioButtonIcon = window.contextualMenu.querySelector('.contextual-menu-item[data-action="play-pause-audio"] .menu-icon');
                if (audioButtonIcon) audioButtonIcon.textContent = "▶️";
                 const audioButton = window.contextualMenu.querySelector('.contextual-menu-item[data-action="play-pause-audio"]');
                if(audioButton) audioButton.title = "Play Sentence Audio";
            }
        }
    };
    try {
        window.currentSourceNode.start(0, offsetInSeconds, durationInSeconds);
    } catch (e) {
        console.error("JS_AUDIO: Error starting audio playback:", e);
        if (window.currentPlayingSentence) window.currentPlayingSentence.classList.remove('playing-sentence');
        window.currentPlayingSentence = null;
        window.currentSourceNode = null;
    }
}

function stopCurrentAudio() {
    // Uses global: currentSourceNode, currentPlayingSentence (from config.js)
    if (window.currentSourceNode) {
        try {
            window.currentSourceNode.onended = null; // Important to remove previous onended handler
            window.currentSourceNode.stop();
            window.currentSourceNode.disconnect();
        } catch (e) { /* ignore if already stopped or disconnected */ }
        window.currentSourceNode = null;
    }
    if (window.currentPlayingSentence) {
        window.currentPlayingSentence.classList.remove('playing-sentence');
        // currentPlayingSentence will be set to null by the next play or naturally if playback ends
    }
}

// Event listener logic for full audio mode (to be called from main.js)
function setupFullAudioModeEventListeners() {
    // Uses global DOM elements and state from config.js
    if (toggleAudiobookModeButton && localAudioFileInput && audioFileNameSpan && audiobookHint) {
        toggleAudiobookModeButton.addEventListener('click', function() {
            // Uses global: isAudiobookModeFull, isPartsViewActive (from config.js)
            // Calls global: initAudioContextGlobally (this file), stopCurrentAudio (this file)
            // Calls global: updatePartsViewModeUI (from ui.js)
            if (!initAudioContextGlobally() && !window.isAudiobookModeFull) {
                alert("AudioContext could not be initialized. Please interact with the page and try again.");
                return;
            }
            window.isAudiobookModeFull = !window.isAudiobookModeFull;
            if (window.isAudiobookModeFull) {
                toggleAudiobookModeButton.textContent = 'Disable Audiobook Mode (Full)';
                localAudioFileInput.style.display = 'inline-block';
                audiobookHint.style.display = 'block';
                window.isAudiobookModeParts = false; // Ensure parts mode is off
                if (window.isPartsViewActive) { // If parts view was active, deactivate it
                    window.isPartsViewActive = false;
                    if (typeof updatePartsViewModeUI === 'function') updatePartsViewModeUI();
                    else console.warn("JS_AUDIO: updatePartsViewModeUI function not found for full audio toggle.");
                }
                 // Potentially clear part-specific states if any were set directly
                if(window.loadedAudioPartNameSpan) window.loadedAudioPartNameSpan.textContent = "No part loaded.";
                window.currentLoadedAudioPartIndex = -1;

            } else {
                toggleAudiobookModeButton.textContent = 'Enable Audiobook Mode (Full Audio)';
                localAudioFileInput.style.display = 'none';
                audiobookHint.style.display = 'none';
                stopCurrentAudio();
                // audioBuffer is not nulled here, user might re-enable with same file.
            }
        });

        localAudioFileInput.addEventListener('change', async function(event) {
            // Uses global: audioFileNameSpan, audioBuffer, audioContext, maxSentenceEndTime (from config.js)
            // Calls global: initAudioContextGlobally (this file), stopCurrentAudio (this file)
            if (!initAudioContextGlobally()) {
                 alert("AudioContext could not be initialized. Please interact with the page and try again.");
                 return;
            }
            const file = event.target.files[0];
            if (file) {
                audioFileNameSpan.textContent = "Loading: " + file.name;
                stopCurrentAudio();
                window.audioBuffer = null; // Clear previous buffer
                try {
                    const arrayBuffer = await file.arrayBuffer();
                    window.audioBuffer = await window.audioContext.decodeAudioData(arrayBuffer);
                    audioFileNameSpan.textContent = file.name;
                    // Check if audio is shorter than the article's max timestamp
                    if (window.maxSentenceEndTime > 0 && (window.audioBuffer.duration * 1000 < window.maxSentenceEndTime)) {
                        console.warn(`JS_AUDIO: Audio duration (${(window.audioBuffer.duration).toFixed(2)}s) is less than max sentence end time (${(window.maxSentenceEndTime/1000).toFixed(2)}s). Some sentences may not be playable.`);
                        // Optionally alert the user here too
                    }
                } catch (e) {
                    alert(`Error decoding audio: ${e.message}`);
                    audioFileNameSpan.textContent = "Error loading audio.";
                    window.audioBuffer = null;
                }
            }
        });
    }
}
