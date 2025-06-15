// static/js/modules/reading_location.js
const ReadingLocationModule = (function() {
    let _ARTICLE_ID = null;
    let _INITIAL_READING_LOCATION = null;
    let _setActiveSentenceFunc = null; // Function to set the active sentence
    let _querySelectorFunc = null; // Function to query DOM elements (e.g., document.querySelector)
    let _highlightedSentenceProviderFunc = null; // Function to get the current highlighted sentence

    const CLICK_THRESHOLD_AUTOSAVE = 5;
    let validClickCounter = 0;
    let restoreLocationButton = null;

    function findSentenceElement(pIndex, sIndex) {
        if (!_querySelectorFunc) {
            console.error("ReadingLocationModule: querySelectorFunc not initialized.");
            return null;
        }
        return _querySelectorFunc(`.english-sentence[data-paragraph-index="${pIndex}"][data-sentence-index="${sIndex}"]`);
    }

    async function saveCurrentLocation(pIndex, sIndex, source = "unknown") {
        if (_ARTICLE_ID === null || pIndex === undefined || sIndex === undefined) {
            console.warn("JS: saveCurrentLocation called with invalid data.", { articleId: _ARTICLE_ID, pIndex, sIndex });
            return;
        }
        try {
            const response = await fetch(`/article/${_ARTICLE_ID}/save_location`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ paragraph_index: pIndex, sentence_index_in_paragraph: sIndex })
            });
            const result = await response.json();
            if (!response.ok || result.status !== 'success') {
                console.error("JS: Failed to save location:", result.message);
            } else {
                // console.log(`JS: Location saved successfully via ${source} for P:${pIndex}, S:${sIndex}`);
            }
        } catch (error) {
            console.error("JS: Error sending save location request:", error);
        }
    }

    function checkAutoSave() {
        if (validClickCounter >= CLICK_THRESHOLD_AUTOSAVE) {
            const highlightedSentence = _highlightedSentenceProviderFunc ? _highlightedSentenceProviderFunc() : null;
            if (highlightedSentence) {
                const pIndex = highlightedSentence.dataset.paragraphIndex;
                const sIndex = highlightedSentence.dataset.sentenceIndex;
                if (pIndex !== undefined && sIndex !== undefined) {
                    saveCurrentLocation(parseInt(pIndex, 10), parseInt(sIndex, 10), "auto_threshold");
                    validClickCounter = 0; // Reset after saving
                }
            }
        }
    }

    function incrementValidClickCounter() {
        validClickCounter++;
    }

    function resetValidClickCounter() {
        validClickCounter = 0;
    }

    function restoreInitialLocation() {
        if (_INITIAL_READING_LOCATION && typeof _INITIAL_READING_LOCATION.paragraph_index !== 'undefined') {
            const targetSentence = findSentenceElement(_INITIAL_READING_LOCATION.paragraph_index, _INITIAL_READING_LOCATION.sentence_index_in_paragraph);
            if (targetSentence && _setActiveSentenceFunc) {
                _setActiveSentenceFunc(targetSentence, "initial_restore_location_auto_scroll");
                return targetSentence; // Return the sentence that was set
            }
        }
        return null; // Return null if no location restored or no sentence found
    }

    function init(articleId, initialLocationData, setActiveSentenceFunc, querySelectorFunc, getHighlightedSentenceFunc) {
        _ARTICLE_ID = articleId;
        _INITIAL_READING_LOCATION = initialLocationData;
        _setActiveSentenceFunc = setActiveSentenceFunc;
        _querySelectorFunc = querySelectorFunc;
        _highlightedSentenceProviderFunc = getHighlightedSentenceFunc;

        restoreLocationButton = _querySelectorFunc('#restoreLocationButton');

        if (restoreLocationButton) {
            if (_INITIAL_READING_LOCATION && typeof _INITIAL_READING_LOCATION.paragraph_index !== 'undefined') {
                restoreLocationButton.style.display = 'inline-block';
                restoreLocationButton.addEventListener('click', function() {
                    const targetSentence = findSentenceElement(_INITIAL_READING_LOCATION.paragraph_index, _INITIAL_READING_LOCATION.sentence_index_in_paragraph);
                    if (targetSentence && _setActiveSentenceFunc) {
                        _setActiveSentenceFunc(targetSentence, "restore_button_click_auto_scroll");
                    }
                });
            } else {
                restoreLocationButton.style.display = 'none';
            }
        }
    }

    return {
        init: init,
        saveCurrentLocation: saveCurrentLocation,
        checkAutoSave: checkAutoSave,
        incrementValidClickCounter: incrementValidClickCounter,
        resetValidClickCounter: resetValidClickCounter,
        findSentenceElement: findSentenceElement, // Mostly for internal/init use, but can be exposed
        restoreInitialLocation: restoreInitialLocation // To be called by article_init.js
    };
})();
