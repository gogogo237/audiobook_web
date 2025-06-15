// static/js/article_view_sentences.js
// Depends on:
// - article_view_config.js (for ARTICLE_ID, HAS_TIMESTAMPS, sentenceElementsArray, highlightedSentence, lastHighlightedSentenceElement, validClickCounter, CLICK_THRESHOLD_AUTOSAVE, audioContext, audioBuffer, isAudiobookModeFull, isAudiobookModeParts, currentLoadedAudioPartIndex, currentPlayingSentence)
// - article_view_ui.js (for scrollToCenter, updateGoBackButtonVisibility)
// - article_view_audio.js (for playSentenceAudio, stopCurrentAudio - these will be moved later, for now, they are global)

// State variables like highlightedSentence, lastHighlightedSentenceElement, sentenceElementsArray, validClickCounter
// are expected to be defined in article_view_config.js and treated as global here.
// Similarly, constants like ARTICLE_ID, CLICK_THRESHOLD_AUTOSAVE, HAS_TIMESTAMPS are from config.js.

function populateSentenceElementsArray() {
    // Uses global: sentenceElementsArray (from config.js, to be populated here)
    // Uses global: HAS_TIMESTAMPS (from config.js)
    // Uses global: maxSentenceEndTime (from config.js, to be updated here)
    window.sentenceElementsArray = Array.from(document.querySelectorAll('.english-sentence'));
    if (window.HAS_TIMESTAMPS) {
        window.sentenceElementsArray.forEach(s => {
            const endTime = parseInt(s.dataset.endTimeMs, 10);
            if (!isNaN(endTime) && endTime > window.maxSentenceEndTime) {
                window.maxSentenceEndTime = endTime;
            }
        });
    }
}

function getAdjacentSentence(currentSentenceElement, direction) {
    // Uses global: sentenceElementsArray (from config.js)
    if (!window.sentenceElementsArray || window.sentenceElementsArray.length === 0) {
        console.error("JS_SENTENCES: getAdjacentSentence - sentenceElementsArray is not populated or empty.");
        return null;
    }

    const currentIndex = window.sentenceElementsArray.indexOf(currentSentenceElement);

    if (currentIndex === -1) {
        console.error("JS_SENTENCES: getAdjacentSentence - currentSentenceElement not found in sentenceElementsArray.");
        return null;
    }

    if (direction === 'previous') {
        if (currentIndex > 0) {
            return window.sentenceElementsArray[currentIndex - 1];
        } else {
            return null;
        }
    } else if (direction === 'next') {
        if (currentIndex < window.sentenceElementsArray.length - 1) {
            return window.sentenceElementsArray[currentIndex + 1];
        } else {
            return null;
        }
    } else {
        console.error("JS_SENTENCES: getAdjacentSentence - Invalid direction provided:", direction);
        return null;
    }
}

function setActiveSentence(newSentenceElement, source = "unknown_source") {
    // Uses global: highlightedSentence, lastHighlightedSentenceElement, validClickCounter (from config.js)
    // Uses global: currentPlayingSentence (from config.js)
    // Uses global: isAudiobookModeFull, audioContext, audioBuffer, isAudiobookModeParts, currentLoadedAudioPartIndex (from config.js)
    // Calls global: checkAutoSave (this file), saveCurrentLocation (this file)
    // Calls global: scrollToCenter (from ui.js), updateGoBackButtonVisibility (from ui.js)
    // Calls global: playSentenceAudio, stopCurrentAudio (currently in main, will move to audio.js)
    if (!newSentenceElement) return;

    if (window.highlightedSentence && window.highlightedSentence !== newSentenceElement) {
        window.highlightedSentence.classList.remove('highlighted-sentence');
        if (source.startsWith("joystick_") || source === "click_new_sentence") {
            window.validClickCounter++;
            checkAutoSave(); // Call within this module
        }
    }

    if (window.currentPlayingSentence && window.currentPlayingSentence !== newSentenceElement) {
        if (typeof stopCurrentAudio === "function") stopCurrentAudio(); else console.warn("setActiveSentence: stopCurrentAudio not found");
    }

    newSentenceElement.classList.add('highlighted-sentence');
    window.highlightedSentence = newSentenceElement;
    window.lastHighlightedSentenceElement = newSentenceElement;

    if (source !== "initial_page_load_highlight_no_scroll") {
        if (typeof scrollToCenter === "function") scrollToCenter(newSentenceElement); else console.warn("setActiveSentence: scrollToCenter not found");
    }
    if (typeof updateGoBackButtonVisibility === "function") updateGoBackButtonVisibility(); else console.warn("setActiveSentence: updateGoBackButtonVisibility not found");


    if (source === "joystick_next" || source === "joystick_prev" || source === "click_new_sentence" || source === "initial_restore_location_auto_scroll" || source === "manual_menu_save") {
        const pIndex = newSentenceElement.dataset.paragraphIndex;
        const sIndex = newSentenceElement.dataset.sentenceIndex;
        if (pIndex !== undefined && sIndex !== undefined) {
            saveCurrentLocation(parseInt(pIndex), parseInt(sIndex), `setActive_${source}`); // Call within this module
        }
    }

    if ((source === "joystick_next" || source === "joystick_prev")) {
        if (window.isAudiobookModeFull && window.audioContext && window.audioBuffer) {
            if (typeof playSentenceAudio === "function") playSentenceAudio(newSentenceElement, false); else console.warn("setActiveSentence: playSentenceAudio not found for full audio");
        } else if (window.isAudiobookModeParts && window.audioContext && window.audioBuffer) {
            const sentencePartIndexStr = newSentenceElement.dataset.audioPartIndex;
            if (sentencePartIndexStr !== undefined) {
                const sentencePartIndex = parseInt(sentencePartIndexStr, 10);
                if (sentencePartIndex === window.currentLoadedAudioPartIndex) {
                    if (typeof playSentenceAudio === "function") playSentenceAudio(newSentenceElement, true); else console.warn("setActiveSentence: playSentenceAudio not found for part audio");
                } else {
                    console.log(`JS_SENTENCES: Joystick nav to sentence in part ${sentencePartIndex + 1}, but part ${window.currentLoadedAudioPartIndex >= 0 ? window.currentLoadedAudioPartIndex + 1 : 'None'} is loaded.`);
                }
            }
        }
    }
}

function selectNextSentence() {
    // Uses global: sentenceElementsArray, highlightedSentence (from config.js)
    // Calls global: setActiveSentence (this file)
    if (window.sentenceElementsArray.length === 0) return;
    let currentIndex = -1;
    if (window.highlightedSentence) {
        currentIndex = window.sentenceElementsArray.indexOf(window.highlightedSentence);
    }
    let nextIndex = currentIndex + 1;
    if (nextIndex >= window.sentenceElementsArray.length) nextIndex = 0;
    if (window.sentenceElementsArray[nextIndex]) {
       setActiveSentence(window.sentenceElementsArray[nextIndex], "joystick_next");
    }
}

function selectPreviousSentence() {
    // Uses global: sentenceElementsArray, highlightedSentence (from config.js)
    // Calls global: setActiveSentence (this file)
    if (window.sentenceElementsArray.length === 0) return;
    let currentIndex = 0;
    if (window.highlightedSentence) {
        currentIndex = window.sentenceElementsArray.indexOf(window.highlightedSentence);
    }
    let prevIndex = currentIndex - 1;
    if (prevIndex < 0) prevIndex = window.sentenceElementsArray.length - 1;
    if (window.sentenceElementsArray[prevIndex]) {
        setActiveSentence(window.sentenceElementsArray[prevIndex], "joystick_prev");
    }
}

function findSentenceElement(pIndex, sIndex) {
    return document.querySelector(`.english-sentence[data-paragraph-index="${pIndex}"][data-sentence-index="${sIndex}"]`);
}

async function saveCurrentLocation(pIndex, sIndex, source = "unknown") {
    console.log("DEBUG_SENTENCES_SAVE: saveCurrentLocation called. ARTICLE_ID:", ARTICLE_ID, "pIndex:", pIndex, "sIndex:", sIndex, "Source:", source);
    // Uses global: ARTICLE_ID (from config.js)
    if (ARTICLE_ID === null || pIndex === undefined || sIndex === undefined) {
        console.warn("JS_SENTENCES: saveCurrentLocation called with invalid data.", { ARTICLE_ID: ARTICLE_ID, pIndex, sIndex });
        return;
    }
    try {
        const response = await fetch(`/article/${ARTICLE_ID}/save_location`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paragraph_index: pIndex, sentence_index_in_paragraph: sIndex })
        });
        const result = await response.json();
        if (!response.ok || result.status !== 'success') {
            console.error("JS_SENTENCES: Failed to save location:", result.message);
        }
    } catch (error) {
        console.error("JS_SENTENCES: Error sending save location request:", error);
    }
}

function checkAutoSave() {
    // Uses global: validClickCounter, CLICK_THRESHOLD_AUTOSAVE, highlightedSentence (from config.js)
    // Calls global: saveCurrentLocation (this file)
    if (window.validClickCounter >= window.CLICK_THRESHOLD_AUTOSAVE && window.highlightedSentence) {
        const pIndex = window.highlightedSentence.dataset.paragraphIndex;
        const sIndex = window.highlightedSentence.dataset.sentenceIndex;
        if (pIndex !== undefined && sIndex !== undefined) {
            saveCurrentLocation(parseInt(pIndex), parseInt(sIndex), "auto_threshold");
            window.validClickCounter = 0; // Reset counter
        }
    }
}
