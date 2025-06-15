// static/js/article_init.js
document.addEventListener('DOMContentLoaded', function() {
    // --- Retrieve Python Data ---
    let articleData = { /* Default empty object */ };
    const articleDataElement = document.getElementById('article-data-json');
    if (articleDataElement) {
        try {
            articleData = JSON.parse(articleDataElement.textContent);
        } catch (e) {
            console.error("JS Init: Error parsing article data JSON:", e);
            // Provide a fallback structure to prevent widespread errors if JSON is malformed
            articleData = {
                articleId: null, hasTimestamps: false, numAudioParts: 0,
                initialReadingLocation: null, articleAudioPartChecksums: null,
                convertedMp3Path: null, mp3PartsFolderPath: null
            };
        }
    }
    const ARTICLE_ID = articleData.articleId;

    // --- Global DOM Query Utilities (passed to modules) ---
    const querySelector = (selector) => document.querySelector(selector);
    const querySelectorAll = (selector) => document.querySelectorAll(selector);

    // --- DOM Elements Cache (primarily for init, modules can re-query if needed or get them passed) ---
    const elements = {
        // Reading Location
        restoreLocationButton: querySelector('#restoreLocationButton'),
        // UI Interactions
        popup: querySelector('#translation-popup'),
        contextualMenu: querySelector('#contextual-menu'),
        goBackButton: querySelector('#goBackButton'),
        goToTopButton: querySelector('#goToTopButton'),
        articleContentWrapper: querySelector('#article-content-wrapper'),
        // Sentence Selection
        toggleSentenceSelectionBtn: querySelector('#toggle-sentence-selection-btn'),
        sentenceSelectionUIContainer: querySelector('#sentence-selection-ui-container'),
        beginningSentenceDisplay: querySelector('#beginning-sentence-display'),
        endingSentenceDisplay: querySelector('#ending-sentence-display'),
        executeSentenceTaskBtn: querySelector('#execute-sentence-task-btn'),
        distributeTimestampsBtn: querySelector('#distribute-timestamps-btn'),
        // Audio Playback
        toggleAudiobookModeButton: querySelector('#toggleAudiobookMode'),
        localAudioFileInput: querySelector('#localAudioFile'),
        audioFileNameSpan: querySelector('#audioFileName'),
        audiobookHint: querySelector('#audiobookHint'),
        switchToPartsViewButton: querySelector('#switchToPartsViewButton'),
        switchToFullViewButton: querySelector('#switchToFullViewButton'),
        fullAudioViewControls: querySelector('#full-audio-view-controls'),
        partsAudioViewControls: querySelector('#parts-audio-view-controls'),
        fullAudioDownloadDiv: querySelector('#full-audio-download'),
        partsAudioDownloadDiv: querySelector('#parts-audio-download'),
        loadSelectedAudioPartButton: querySelector('#loadSelectedAudioPartButton'),
        loadLocalAudioPartButton: querySelector('#loadLocalAudioPartButton'),
        localAudioPartFileInput: querySelector('#localAudioPartFileInput'),
        downloadSelectedAudioPartButton: querySelector('#downloadSelectedAudioPartButton'),
        loadedAudioPartNameSpan: querySelector('#loadedAudioPartNameSpan'),
        // Gamepad
        gamepadStatusEmoji: querySelector('#gamepad-status-emoji'),
    };

    // --- Core State & Helper Functions ---
    let highlightedSentence = null;
    let lastHighlightedSentenceElement = null;
    let sentenceElementsArray = [];

    function populateSentenceElementsArray() {
        sentenceElementsArray = Array.from(querySelectorAll('.english-sentence'));
    }

    function getAdjacentSentence(currentSentenceElement, direction) {
        if (!sentenceElementsArray || sentenceElementsArray.length === 0) return null;
        const currentIndex = sentenceElementsArray.indexOf(currentSentenceElement);
        if (currentIndex === -1) return null;
        if (direction === 'previous') return currentIndex > 0 ? sentenceElementsArray[currentIndex - 1] : null;
        if (direction === 'next') return currentIndex < sentenceElementsArray.length - 1 ? sentenceElementsArray[currentIndex + 1] : null;
        return null;
    }

    // setActiveSentence: This is a complex function that interacts with multiple modules.
    // It needs to:
    // 1. Update `highlightedSentence` and `lastHighlightedSentenceElement`.
    // 2. Add/remove 'highlighted-sentence' class.
    // 3. Call `ReadingLocationModule.incrementValidClickCounter()` and `ReadingLocationModule.checkAutoSave()`.
    // 4. Call `ReadingLocationModule.saveCurrentLocation()` for certain sources.
    // 5. Call `AudioPlaybackModule.stopCurrentAudio()` if a different sentence is now active.
    // 6. Potentially call `AudioPlaybackModule.playSentenceAudio()` (e.g., for joystick).
    // 7. Call `UIInteractionsModule.updateGoBackButtonVisibility()`.
    // 8. Scroll to center (UIInteractionsModule can provide this, or keep it here).
    function _scrollToCenter(element) { // Keep private utility here
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
        }
    }

    function setActiveSentence(newSentenceElement, source = "unknown_source") {
        if (!newSentenceElement) return;

        // 1. Update classes and internal state
        if (highlightedSentence && highlightedSentence !== newSentenceElement) {
            highlightedSentence.classList.remove('highlighted-sentence');
            if (source.startsWith("joystick_") || source === "click_new_sentence") {
                ReadingLocationModule.incrementValidClickCounter();
                ReadingLocationModule.checkAutoSave(); // checkAutoSave will use its provider for highlightedSentence
            }
        }

        // 2. Stop audio if changing sentence
        // Check currentPlayingSentence from AudioPlaybackModule BEFORE stopping
        const currentPlayingAudioSentence = AudioPlaybackModule.getCurrentPlayingSentence();
        if (currentPlayingAudioSentence && currentPlayingAudioSentence !== newSentenceElement) {
             AudioPlaybackModule.stopCurrentAudio();
        }

        newSentenceElement.classList.add('highlighted-sentence');
        highlightedSentence = newSentenceElement; // Update after checkAutoSave if it relies on previous state
        lastHighlightedSentenceElement = newSentenceElement;


        // 3. Scroll (unless specified not to)
        if (source !== "initial_page_load_highlight_no_scroll" && source !== "initial_restore_location_no_scroll") {
             _scrollToCenter(newSentenceElement);
        }

        // 4. Update UI elements that depend on the highlighted sentence
        // UIInteractionsModule's scroll/resize listeners will call its updateGoBackButtonVisibility.
        // Manual call might be needed if those events don't fire immediately.
        // For now, assume event listeners in UIInteractions are sufficient.

        // 5. Save location for specific sources
        if (source === "joystick_next" || source === "joystick_prev" ||
            source === "click_new_sentence" || source === "initial_restore_location_auto_scroll" ||
            source === "manual_menu_save" || source === "restore_button_click_auto_scroll") {
            const pIndex = newSentenceElement.dataset.paragraphIndex;
            const sIndex = newSentenceElement.dataset.sentenceIndex;
            if (pIndex !== undefined && sIndex !== undefined) {
                ReadingLocationModule.saveCurrentLocation(parseInt(pIndex, 10), parseInt(sIndex, 10), `setActive_${source}`);
            }
        }

        // 6. Auto-play for joystick navigation if conditions met
        if ((source === "joystick_next" || source === "joystick_prev")) {
            const apm = AudioPlaybackModule; // Alias for less typing
            if (apm.isAudiobookModeFull() && apm.getAudioBuffer()) {
                apm.playSentenceAudio(newSentenceElement, false, null); // false for not-from-part
            } else if (apm.isAudiobookModeParts() && apm.getAudioBuffer()) {
                const sentencePartIndexStr = newSentenceElement.dataset.audioPartIndex;
                if (sentencePartIndexStr !== undefined) {
                    const sentencePartIndex = parseInt(sentencePartIndexStr, 10);
                    if (sentencePartIndex === apm.getCurrentLoadedAudioPartIndex()) {
                        apm.playSentenceAudio(newSentenceElement, true, null); // true for from-part
                    }
                }
            }
        }
    }

    // Helper function for gamepad to play/pause current highlighted sentence
    function playPauseAudioForHighlightedSentence() {
        if (!highlightedSentence) return;
        const apm = AudioPlaybackModule;
        if (apm.isCurrentSourceNodeActive() && apm.getCurrentPlayingSentence() === highlightedSentence) {
            apm.stopCurrentAudio();
        } else {
            // Determine if playing from part or full
            let playAsPart = false;
            let canPlay = false;
            if (apm.isAudiobookModeFull() && apm.getAudioBuffer() && articleData.hasTimestamps) {
                canPlay = true; playAsPart = false;
            } else if (apm.isAudiobookModeParts() && apm.getAudioBuffer() && articleData.hasTimestamps && apm.getCurrentLoadedAudioPartIndex() !== -1) {
                const sentencePartIndex = parseInt(highlightedSentence.dataset.audioPartIndex, 10);
                if (sentencePartIndex === apm.getCurrentLoadedAudioPartIndex()) {
                    canPlay = true; playAsPart = true;
                }
            }
            if (canPlay) {
                apm.playSentenceAudio(highlightedSentence, playAsPart, null);
            } else {
                console.log("Gamepad: Audio not ready or sentence part mismatch for highlighted sentence.");
            }
        }
    }

    // Helper function for gamepad to toggle translation
    function toggleTranslationForHighlightedSentence() {
        if (!highlightedSentence) return;
        // Check if popup is already shown for this sentence
        const popupElement = elements.popup; // from `elements` cache
        if (popupElement.style.display === 'block' && popupElement.innerHTML.includes(highlightedSentence.dataset.translation)) {
            UIInteractionsModule.hideTranslationPopup();
        } else {
            UIInteractionsModule.displayPopup(highlightedSentence, highlightedSentence.dataset.translation || "No translation.");
        }
    }

    // --- Initialize Modules ---
    populateSentenceElementsArray(); // Populate early, as modules might need it during init

    ReadingLocationModule.init(
        ARTICLE_ID,
        articleData.initialReadingLocation,
        setActiveSentence, // Pass the main setActiveSentence function
        querySelector,
        () => highlightedSentence // Provider for current highlighted sentence
    );

    AudioPlaybackModule.init({
        articleData: articleData,
        elements: { // Pass relevant DOM elements
            toggleAudiobookModeButton: elements.toggleAudiobookModeButton,
            localAudioFileInput: elements.localAudioFileInput,
            audioFileNameSpan: elements.audioFileNameSpan,
            audiobookHint: elements.audiobookHint,
            switchToPartsViewButton: elements.switchToPartsViewButton,
            switchToFullViewButton: elements.switchToFullViewButton,
            fullAudioViewControls: elements.fullAudioViewControls,
            partsAudioViewControls: elements.partsAudioViewControls,
            fullAudioDownloadDiv: elements.fullAudioDownloadDiv,
            partsAudioDownloadDiv: elements.partsAudioDownloadDiv,
            loadSelectedAudioPartButton: elements.loadSelectedAudioPartButton,
            loadLocalAudioPartButton: elements.loadLocalAudioPartButton,
            localAudioPartFileInput: elements.localAudioPartFileInput,
            downloadSelectedAudioPartButton: elements.downloadSelectedAudioPartButton,
            loadedAudioPartNameSpan: elements.loadedAudioPartNameSpan,
        },
        callbacks: { // Pass callbacks needed by AudioPlaybackModule
            setActiveSentence: setActiveSentence,
            getAdjacentSentence: getAdjacentSentence,
        },
        utils: { querySelector: querySelector, querySelectorAll: querySelectorAll }
    });

    SentenceSelectionModule.init({
        articleId: ARTICLE_ID,
        elements: {
            toggleSentenceSelectionBtn: elements.toggleSentenceSelectionBtn,
            sentenceSelectionUIContainer: elements.sentenceSelectionUIContainer,
            beginningSentenceDisplay: elements.beginningSentenceDisplay,
            endingSentenceDisplay: elements.endingSentenceDisplay,
            executeSentenceTaskBtn: elements.executeSentenceTaskBtn,
            distributeTimestampsBtn: elements.distributeTimestampsBtn,
        },
        providers: {
            getSentenceElementsArray: () => sentenceElementsArray,
            getAdjacentSentence: getAdjacentSentence,
            getAudioBuffer: AudioPlaybackModule.getAudioBuffer, // For validation
            isAudiobookModeFull: AudioPlaybackModule.isAudiobookModeFull, // For validation
        },
        callbacks: {
            fetchSentenceDbIdByIndices: AudioPlaybackModule.fetchSentenceDbIdByIndices,
        }
    });

    UIInteractionsModule.init({
        elements: {
            popup: elements.popup,
            contextualMenu: elements.contextualMenu,
            goBackButton: elements.goBackButton,
            goToTopButton: elements.goToTopButton,
            articleContentWrapper: elements.articleContentWrapper,
        },
        providers: {
            getHighlightedSentence: () => highlightedSentence,
            getLastHighlightedSentenceElement: () => lastHighlightedSentenceElement,
            isAudiobookModeFull: AudioPlaybackModule.isAudiobookModeFull,
            isAudiobookModeParts: AudioPlaybackModule.isAudiobookModeParts,
            getAudioBuffer: AudioPlaybackModule.getAudioBuffer,
            getCurrentLoadedAudioPartIndex: AudioPlaybackModule.getCurrentLoadedAudioPartIndex,
            getHasTimestamps: AudioPlaybackModule.getHasTimestamps,
            isSentenceSelectionUIVisible: SentenceSelectionModule.isUIVisible,
            isCurrentSourceNodeActive: AudioPlaybackModule.isCurrentSourceNodeActive,
            getCurrentPlayingSentence: AudioPlaybackModule.getCurrentPlayingSentence,
        },
        callbacks: {
            setActiveSentence: setActiveSentence,
            saveCurrentLocation: ReadingLocationModule.saveCurrentLocation,
            playSentenceAudio: AudioPlaybackModule.playSentenceAudio,
            stopCurrentAudio: AudioPlaybackModule.stopCurrentAudio,
            displayWaveform: AudioPlaybackModule.displayWaveform,
            clearExistingWaveform: AudioPlaybackModule.clearExistingWaveform,
            setBeginningSentence: SentenceSelectionModule.setBeginningSentence,
            setEndingSentence: SentenceSelectionModule.setEndingSentence,
        }
    });

    GamepadControlsModule.init({
        elements: { gamepadStatusEmoji: elements.gamepadStatusEmoji },
        callbacks: {
            selectNextSentence: () => {
                const current = highlightedSentence || sentenceElementsArray[0];
                const next = getAdjacentSentence(current, 'next') || sentenceElementsArray[0];
                if(next) setActiveSentence(next, "joystick_next");
            },
            selectPreviousSentence: () => {
                const current = highlightedSentence || sentenceElementsArray[0];
                const prev = getAdjacentSentence(current, 'previous') || sentenceElementsArray[sentenceElementsArray.length - 1];
                 if(prev) setActiveSentence(prev, "joystick_prev");
            },
            playPauseAudioForHighlighted: playPauseAudioForHighlightedSentence,
            toggleTranslationForHighlighted: toggleTranslationForHighlightedSentence,
        }
    });

    // --- Initial Page Setup Calls ---
    AudioPlaybackModule.initAudioContextGlobally(); // Initialize audio context early
    SentenceSelectionModule.initializeSentenceSelectionDisplays();

    // Restore initial reading location (if any) or highlight the first sentence.
    // This will also call setActiveSentence with appropriate source.
    let restoredSentence = ReadingLocationModule.restoreInitialLocation();
    if (!restoredSentence) { // If no location was restored (e.g. first visit)
        if (sentenceElementsArray.length > 0) {
            // Highlight first sentence without auto-scrolling, but save it as the initial position.
            setActiveSentence(sentenceElementsArray[0], "initial_page_load_highlight_no_scroll");
            const pIdx = sentenceElementsArray[0].dataset.paragraphIndex;
            const sIdx = sentenceElementsArray[0].dataset.sentenceIndex;
            if (pIdx !== undefined && sIdx !== undefined) {
                 ReadingLocationModule.saveCurrentLocation(parseInt(pIdx, 10), parseInt(sIdx, 10), "initial_highlight_first");
            }
        }
    } else {
        // If location WAS restored, lastHighlightedSentenceElement is already set by setActiveSentence.
        // Ensure go back button visibility is updated based on this initial state.
        // UIInteractionsModule's init already calls its update methods, so this might be redundant
        // but explicit call after potential scroll due to restore doesn't hurt.
        // setTimeout(UIInteractionsModule.updateGoBackButtonVisibility, 100); // Small delay for scroll to finish
    }

    console.log("JS Init: All modules initialized.");
});
