// static/js/article_view.js
document.addEventListener('DOMContentLoaded', function() {
    // --- Retrieve Python Data ---
    let articleData = {};
    const articleDataElement = document.getElementById('article-data-json');
    if (articleDataElement) {
        try {
            articleData = JSON.parse(articleDataElement.textContent);
        } catch (e) {
            console.error("JS: Error parsing article data JSON:", e);
            articleData = {
                articleId: null, hasTimestamps: false, numAudioParts: 0,
                initialReadingLocation: null, articleAudioPartChecksums: null,
                convertedMp3Path: null, mp3PartsFolderPath: null
            };
        }
    }
    const ARTICLE_ID = articleData.articleId;
    const HAS_TIMESTAMPS = articleData.hasTimestamps;
    const NUM_AUDIO_PARTS = parseInt(articleData.numAudioParts, 10) || 0;
    const INITIAL_READING_LOCATION = articleData.initialReadingLocation;
    const ARTICLE_AUDIO_PART_CHECKSUMS_STR = articleData.articleAudioPartChecksums;
    const AUDIO_PART_CHECKSUM_DELIMITER_JS = ";";
    let expectedChecksumsArray = [];
    if (ARTICLE_AUDIO_PART_CHECKSUMS_STR && typeof ARTICLE_AUDIO_PART_CHECKSUMS_STR === 'string') {
        expectedChecksumsArray = ARTICLE_AUDIO_PART_CHECKSUMS_STR.split(AUDIO_PART_CHECKSUM_DELIMITER_JS);
    }

    // --- DOM Elements ---
    const articleContentWrapper = document.getElementById('article-content-wrapper');
    const popup = document.getElementById('translation-popup');
    const contextualMenu = document.getElementById('contextual-menu');
    const goBackButton = document.getElementById('goBackButton');
    const goToTopButton = document.getElementById('goToTopButton');
    const restoreLocationButton = document.getElementById('restoreLocationButton');
    const gamepadStatusEmoji = document.getElementById('gamepad-status-emoji'); // Changed from gamepadStatusIndicator

    const toggleAudiobookModeButton = document.getElementById('toggleAudiobookMode');
    const localAudioFileInput = document.getElementById('localAudioFile');
    const audioFileNameSpan = document.getElementById('audioFileName');
    const audiobookHint = document.getElementById('audiobookHint');

    const switchToPartsViewButton = document.getElementById('switchToPartsViewButton');
    const switchToFullViewButton = document.getElementById('switchToFullViewButton');
    const fullAudioViewControls = document.getElementById('full-audio-view-controls');
    const partsAudioViewControls = document.getElementById('parts-audio-view-controls');
    const fullAudioDownloadDiv = document.getElementById('full-audio-download');
    const partsAudioDownloadDiv = document.getElementById('parts-audio-download');
    const loadSelectedAudioPartButton = document.getElementById('loadSelectedAudioPartButton');
    const loadLocalAudioPartButton = document.getElementById('loadLocalAudioPartButton');
    const localAudioPartFileInput = document.getElementById('localAudioPartFileInput');
    const downloadSelectedAudioPartButton = document.getElementById('downloadSelectedAudioPartButton');
    const loadedAudioPartNameSpan = document.getElementById('loadedAudioPartName');

    // --- State Variables ---
    let highlightedSentence = null;
    let lastHighlightedSentenceElement = null;
    let currentPopupTargetSentence = null;
    let sentenceElementsArray = [];
    let audioContext = null;
    let audioBuffer = null;
    let currentSourceNode = null;
    let isAudiobookModeFull = false;
    let isAudiobookModeParts = false;
    let currentPlayingSentence = null;
    let maxSentenceEndTime = 0;
    let currentLoadedAudioPartIndex = -1;
    let validClickCounter = 0;
    const CLICK_THRESHOLD_AUTOSAVE = 5;
    const WAVEFORM_MS_PER_PIXEL = 10; // Each pixel represents 10ms of audio

    // --- Gamepad State ---
    let gamepadIndex = null;
    let previousButtonStates = [];
    let animationFrameIdGamepad = null;
    let lastGamepadActionTime = 0;
    const GAMEPAD_ACTION_COOLDOWN = 250;
    const BUTTON_A_INDEX = 0;
    const BUTTON_B_INDEX = 1;
    const BUTTON_X_INDEX = 2;
    const BUTTON_Y_INDEX = 3;

    // --- Initialization Functions ---
    function populateSentenceElementsArray() {
        sentenceElementsArray = Array.from(document.querySelectorAll('.english-sentence'));
        if (HAS_TIMESTAMPS) {
            sentenceElementsArray.forEach(s => {
                const endTime = parseInt(s.dataset.endTimeMs, 10);
                if (!isNaN(endTime) && endTime > maxSentenceEndTime) {
                    maxSentenceEndTime = endTime;
                }
            });
        }
    }

    function initAudioContextGlobally() {
        if (!audioContext && (window.AudioContext || window.webkitAudioContext)) {
            try {
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
                console.log("JS: AudioContext initialized.");
            } catch (e) {
                console.error("JS: Error initializing AudioContext:", e);
                return false;
            }
        }
        if (audioContext && audioContext.state === 'suspended') {
            audioContext.resume().then(() => {
                console.log("JS: AudioContext resumed successfully.");
            }).catch(e => {
                console.error("JS: Failed to resume AudioContext:", e);
            });
        }
        return audioContext ? true : false;
    }

    // --- UI Helper Functions ---
    function scrollToCenter(element) {
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
        }
    }

    function updateGoBackButtonVisibility() {
        if (!goBackButton) return;
        if (lastHighlightedSentenceElement && (window.scrollY > 100 || document.documentElement.scrollTop > 100)) {
            const sentenceRect = lastHighlightedSentenceElement.getBoundingClientRect();
            if (sentenceRect.bottom < 0 || sentenceRect.top > window.innerHeight || Math.abs(window.scrollY - lastHighlightedSentenceElement.offsetTop) > window.innerHeight / 1.5) {
                goBackButton.classList.add('visible');
            } else {
                goBackButton.classList.remove('visible');
            }
        } else {
            goBackButton.classList.remove('visible');
        }
    }
    
    let lastScrollTop = 0;
    const scrollThresholdForGoToTop = 150;
    function updateGoToTopButtonVisibility() {
        if (!goToTopButton) return;
        let st = window.pageYOffset || document.documentElement.scrollTop;
        if (st < lastScrollTop && st > scrollThresholdForGoToTop) {
            goToTopButton.classList.add('visible');
        } else {
            goToTopButton.classList.remove('visible');
        }
        lastScrollTop = st <= 0 ? 0 : st;
    }

    // --- Core Sentence Management ---
    function setActiveSentence(newSentenceElement, source = "unknown_source") {
        if (!newSentenceElement) return;

        if (highlightedSentence && highlightedSentence !== newSentenceElement) {
            highlightedSentence.classList.remove('highlighted-sentence');
            if (source.startsWith("joystick_") || source === "click_new_sentence") {
                validClickCounter++;
                checkAutoSave();
            }
        }

        if (currentPlayingSentence && currentPlayingSentence !== newSentenceElement) {
            stopCurrentAudio();
        }

        newSentenceElement.classList.add('highlighted-sentence');
        highlightedSentence = newSentenceElement;
        lastHighlightedSentenceElement = newSentenceElement;

        if (source !== "initial_page_load_highlight_no_scroll") {
             scrollToCenter(newSentenceElement);
        }
        updateGoBackButtonVisibility();

        if (source === "joystick_next" || source === "joystick_prev" || source === "click_new_sentence" || source === "initial_restore_location_auto_scroll" || source === "manual_menu_save") {
            const pIndex = newSentenceElement.dataset.paragraphIndex;
            const sIndex = newSentenceElement.dataset.sentenceIndex;
            if (pIndex !== undefined && sIndex !== undefined) {
                saveCurrentLocation(parseInt(pIndex), parseInt(sIndex), `setActive_${source}`);
            }
        }

        if ((source === "joystick_next" || source === "joystick_prev")) {
            if (isAudiobookModeFull && audioContext && audioBuffer) {
                playSentenceAudio(newSentenceElement, false);
            } else if (isAudiobookModeParts && audioContext && audioBuffer) {
                const sentencePartIndexStr = newSentenceElement.dataset.audioPartIndex;
                if (sentencePartIndexStr !== undefined) {
                    const sentencePartIndex = parseInt(sentencePartIndexStr, 10);
                    if (sentencePartIndex === currentLoadedAudioPartIndex) {
                        playSentenceAudio(newSentenceElement, true);
                    } else {
                        console.log(`JS: Joystick nav to sentence in part ${sentencePartIndex + 1}, but part ${currentLoadedAudioPartIndex >= 0 ? currentLoadedAudioPartIndex + 1 : 'None'} is loaded.`);
                    }
                }
            }
        }
    }

    function selectNextSentence() {
        if (sentenceElementsArray.length === 0) return;
        let currentIndex = -1;
        if (highlightedSentence) {
            currentIndex = sentenceElementsArray.indexOf(highlightedSentence);
        }
        let nextIndex = currentIndex + 1;
        if (nextIndex >= sentenceElementsArray.length) nextIndex = 0;
        if (sentenceElementsArray[nextIndex]) {
           setActiveSentence(sentenceElementsArray[nextIndex], "joystick_next");
        }
    }

    function selectPreviousSentence() {
        if (sentenceElementsArray.length === 0) return;
        let currentIndex = 0;
        if (highlightedSentence) {
            currentIndex = sentenceElementsArray.indexOf(highlightedSentence);
        }
        let prevIndex = currentIndex - 1;
        if (prevIndex < 0) prevIndex = sentenceElementsArray.length - 1;
        if (sentenceElementsArray[prevIndex]) {
            setActiveSentence(sentenceElementsArray[prevIndex], "joystick_prev");
        }
    }

    // --- Reading Location ---
    function findSentenceElement(pIndex, sIndex) {
        return document.querySelector(`.english-sentence[data-paragraph-index="${pIndex}"][data-sentence-index="${sIndex}"]`);
    }

    async function saveCurrentLocation(pIndex, sIndex, source = "unknown") {
        if (ARTICLE_ID === null || pIndex === undefined || sIndex === undefined) {
            console.warn("JS: saveCurrentLocation called with invalid data.", { ARTICLE_ID, pIndex, sIndex });
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
                console.error("JS: Failed to save location:", result.message);
            }
        } catch (error) {
            console.error("JS: Error sending save location request:", error);
        }
    }

    function checkAutoSave() {
        if (validClickCounter >= CLICK_THRESHOLD_AUTOSAVE && highlightedSentence) {
            const pIndex = highlightedSentence.dataset.paragraphIndex;
            const sIndex = highlightedSentence.dataset.sentenceIndex;
            if (pIndex !== undefined && sIndex !== undefined) {
                saveCurrentLocation(parseInt(pIndex), parseInt(sIndex), "auto_threshold");
                validClickCounter = 0;
            }
        }
    }

    // --- Popups and Contextual Menu ---
    function displayPopup(targetElement, content) {
        if (!popup || !targetElement) return;
        popup.innerHTML = content;
        const rect = targetElement.getBoundingClientRect();
        let popupTop = rect.bottom + window.scrollY + 8;
        let popupLeft = rect.left + window.scrollX + (rect.width / 2) - (popup.offsetWidth / 2);
        if (popupLeft < 10) popupLeft = 10;
        if (popupLeft + popup.offsetWidth > window.innerWidth - 10) {
            popupLeft = window.innerWidth - 10 - popup.offsetWidth;
        }
        popup.style.top = popupTop + 'px';
        popup.style.left = popupLeft + 'px';
        popup.style.display = 'block';
        currentPopupTargetSentence = targetElement;
    }

    function hideContextualMenu() {
        if (contextualMenu) {
            contextualMenu.style.opacity = '0';
            contextualMenu.style.transform = 'scale(0.95)';
            setTimeout(() => { contextualMenu.style.display = 'none'; }, 100);
        }
    }

    function hideTranslationPopup() {
        if (popup) {
            popup.style.display = 'none';
            if (currentPopupTargetSentence && popup.innerHTML === currentPopupTargetSentence.dataset.translation) {
                 currentPopupTargetSentence = null;
            }
        }
    }
    function populateAndShowContextualMenu(sentenceElement, clickX) {
        if (!contextualMenu || !sentenceElement) return;
        let menuHTML = `<div class="contextual-menu-item" data-action="show-translation" title="Show Chinese Translation"><span class="menu-icon">💬</span><span class="menu-text">Translate</span></div>`;
        menuHTML += `<div class="contextual-menu-item" data-action="save-location" title="Save this reading location"><span class="menu-icon">💾</span><span class="menu-text">Save Spot</span></div>`;

        if (isAudiobookModeFull && audioBuffer && sentenceElement) { // Ensure sentenceElement is available for check
            let editActionText = "Edit Clip";
            let editActionIcon = "✏️";
            let waveformIsVisible = false;
            if (sentenceElement.parentElement) {
                const potentialContainer = sentenceElement.parentElement.nextElementSibling;
                if (potentialContainer && potentialContainer.classList.contains('waveform-scroll-container')) {
                    waveformIsVisible = true;
                }
            }

            if (waveformIsVisible) {
                editActionText = "Hide Waveform";
                editActionIcon = "🗑️";
            }
            // Note: Default is "Edit Clip" / "✏️", so no 'else' block needed for that.
            menuHTML += `<div class="contextual-menu-item" data-action="edit-audio-clip" title="${editActionText} for this sentence"><span class="menu-icon">${editActionIcon}</span><span class="menu-text">${editActionText}</span></div>`;
        }

        const canPlayAudio = (isAudiobookModeFull && audioContext && audioBuffer && HAS_TIMESTAMPS) ||
                             (isAudiobookModeParts && audioContext && audioBuffer && HAS_TIMESTAMPS && currentLoadedAudioPartIndex !== -1 &&
                              sentenceElement.dataset.audioPartIndex !== undefined && parseInt(sentenceElement.dataset.audioPartIndex, 10) === currentLoadedAudioPartIndex);

        if (canPlayAudio) {
            let audioIcon = "▶️";
            let audioTitle = "Play Sentence Audio";
            if (currentPlayingSentence === sentenceElement && currentSourceNode) {
                audioIcon = "⏹️";
                audioTitle = "Stop Sentence Audio";
            }
            menuHTML += `<div class="contextual-menu-item" data-action="play-pause-audio" title="${audioTitle}"><span class="menu-icon">${audioIcon}</span><span class="menu-text">Audio</span></div>`;
        }
        contextualMenu.innerHTML = menuHTML;
        const rect = sentenceElement.getBoundingClientRect();
        let menuTop = rect.bottom + window.scrollY + 5;
        let menuLeft = clickX + window.scrollX - (contextualMenu.offsetWidth / 2);
        if (menuLeft < 10) menuLeft = 10;
        if (menuLeft + contextualMenu.offsetWidth > window.innerWidth - 10) menuLeft = window.innerWidth - 10 - contextualMenu.offsetWidth;
        if (menuTop + contextualMenu.offsetHeight > window.innerHeight + window.scrollY - 10) menuTop = rect.top + window.scrollY - contextualMenu.offsetHeight - 5;

        contextualMenu.style.top = menuTop + 'px';
        contextualMenu.style.left = menuLeft + 'px';
        contextualMenu.style.display = 'block';
        setTimeout(() => {
             contextualMenu.style.opacity = '1';
             contextualMenu.style.transform = 'scale(1)';
        }, 10);
    }

    // --- Audio Processing ---
    function playSentenceAudio(sentenceElement, isPlayingFromPart, optionalDesiredStartTimeMs = null) {
        if (!initAudioContextGlobally()) {
            console.warn("Audio system could not be initialized for playSentenceAudio.");
            return;
        }
        if (audioContext.state === 'suspended') {
            audioContext.resume().then(() => proceedWithPlayback(sentenceElement, isPlayingFromPart, optionalDesiredStartTimeMs))
                              .catch(e => { console.error("Could not start audio playback. User interaction might be needed.", e); });
        } else {
            proceedWithPlayback(sentenceElement, isPlayingFromPart, optionalDesiredStartTimeMs);
        }
    }

    function proceedWithPlayback(sentenceElement, isPlayingFromPart, optionalDesiredStartTimeMs = null) {
        if (!audioBuffer) {
            // This check refers to the globally loaded audioBuffer, which might be full or a part.
            // The waveform's click handler should ideally ensure the correct buffer is loaded if it's different.
            // For now, we assume the buffer active (globally) is the one to be used.
            if (isAudiobookModeFull) alert("Please load the full audio file first.");
            else if (isAudiobookModeParts) alert("Please load the selected audio part first.");
            return;
        }
        stopCurrentAudio();

        if (currentPlayingSentence && currentPlayingSentence !== sentenceElement) {
            currentPlayingSentence.classList.remove('playing-sentence');
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
        let playbackEndTimeMs = originalSentenceEndTimeMs; // Default: play until the original end of the sentence

        if (optionalDesiredStartTimeMs !== null && optionalDesiredStartTimeMs >= 0) {
            // We have a specific start time, likely from a waveform click.
            // This optionalDesiredStartTimeMs is ALREADY an absolute time within the currently loaded audioBuffer
            // (either full audio or a specific part's buffer).
            playbackStartTimeMs = optionalDesiredStartTimeMs;

            // Ensure playbackStartTimeMs is not after or too close to the sentence's original end time within the same buffer.
            // Also, ensure it's not before the sentence's original start time if we strictly want to stay within the sentence.
            // For now, the primary concern is not starting after the original end.
            if (playbackStartTimeMs >= playbackEndTimeMs) {
                console.warn(`PLAYBACK_LOGIC: Desired start time ${playbackStartTimeMs}ms is at or after sentence end ${playbackEndTimeMs}ms. Not playing.`);
                return;
            }
            // Optional: if you want to ensure the click doesn't make it start before the *original* start of sentence.
            // This depends on desired UX. For now, allowing earlier start if click is on waveform padding for that sentence.
            // if (playbackStartTimeMs < originalSentenceStartTimeMs) {
            //     playbackStartTimeMs = originalSentenceStartTimeMs;
            // }

        } else {
            // Standard playback: use the sentence's defined start time.
            playbackStartTimeMs = originalSentenceStartTimeMs;
        }

        if (isNaN(playbackStartTimeMs) || isNaN(playbackEndTimeMs)) {
            console.warn("PLAYBACK_LOGIC: Sentence missing time data for playback. Cannot play audio for:", sentenceElement);
            return;
        }

        const offsetInSeconds = playbackStartTimeMs / 1000.0;
        let durationInSeconds = (playbackEndTimeMs - playbackStartTimeMs) / 1000.0;

        if (durationInSeconds <= 0) {
             console.warn(`PLAYBACK_LOGIC: Calculated playback duration (${durationInSeconds.toFixed(3)}s) is zero or negative. Not playing.`);
             return;
        }

        // Validate against the audioBuffer's properties
        if (offsetInSeconds < 0 || offsetInSeconds >= audioBuffer.duration) {
            console.warn(`PLAYBACK_LOGIC: Calculated playback start time (${offsetInSeconds.toFixed(2)}s) is out of audio buffer bounds (duration ${audioBuffer.duration.toFixed(2)}s).`);
            return;
        }
        durationInSeconds = Math.min(durationInSeconds, audioBuffer.duration - offsetInSeconds);
         if (durationInSeconds <= 0) { // Check again after Math.min
             console.warn(`PLAYBACK_LOGIC: Calculated playback duration (${durationInSeconds.toFixed(3)}s) became zero/negative after buffer adjustment. Not playing.`);
             return;
        }


        currentPlayingSentence = sentenceElement;
        currentPlayingSentence.classList.add('playing-sentence');

        currentSourceNode = audioContext.createBufferSource();
        currentSourceNode.buffer = audioBuffer;
        currentSourceNode.connect(audioContext.destination);
        const thisSourceNodeForOnEnded = currentSourceNode;

        currentSourceNode.onended = () => {
            if (currentSourceNode === thisSourceNodeForOnEnded) currentSourceNode = null;
            if (currentPlayingSentence === sentenceElement) {
                currentPlayingSentence.classList.remove('playing-sentence');
            }
            if (contextualMenu.style.display === 'block' && highlightedSentence === sentenceElement) {
                const audioButtonIcon = contextualMenu.querySelector('.contextual-menu-item[data-action="play-pause-audio"] .menu-icon');
                if (audioButtonIcon) audioButtonIcon.textContent = "▶️";
                const audioButton = contextualMenu.querySelector('.contextual-menu-item[data-action="play-pause-audio"]');
                if(audioButton) audioButton.title = "Play Sentence Audio";
            }
        };
        try {
            currentSourceNode.start(0, offsetInSeconds, durationInSeconds);
        } catch (e) {
            console.error("Error starting audio playback:", e);
            if (currentPlayingSentence) currentPlayingSentence.classList.remove('playing-sentence');
            currentPlayingSentence = null;
            currentSourceNode = null;
        }
    }

    function stopCurrentAudio() {
        if (currentSourceNode) {
            try {
                currentSourceNode.onended = null;
                currentSourceNode.stop();
                currentSourceNode.disconnect();
            } catch (e) { /* ignore */ }
            currentSourceNode = null;
        }
        if (currentPlayingSentence) {
            currentPlayingSentence.classList.remove('playing-sentence');
        }
    }

    function arrayBufferToHexString(buffer) {
        const byteArray = new Uint8Array(buffer);
        let hexString = "";
        for (let i = 0; i < byteArray.length; i++) {
            const hex = byteArray[i].toString(16);
            hexString += (hex.length === 1 ? "0" : "") + hex;
        }
        return hexString;
    }

function clearExistingWaveform(sentenceElement) {
    if (!sentenceElement || !sentenceElement.parentElement) {
        console.error("clearExistingWaveform: sentenceElement or its parent is null.");
        return;
    }
    const potentialContainer = sentenceElement.parentElement.nextElementSibling;
    if (potentialContainer && potentialContainer.classList.contains('waveform-scroll-container')) {
        potentialContainer.remove();
    }
}

async function fetchSentenceDbIdByIndices(articleId, paragraphIndex, sentenceIndex) {
    const url = `/article/${articleId}/get_sentence_id_by_indices?paragraph_index=${paragraphIndex}&sentence_index=${sentenceIndex}`;
    console.log(`JS: Fetching sentence_db_id from: ${url}`);
    try {
        const response = await fetch(url);
        if (!response.ok) {
            console.error(`JS: Failed to fetch sentence_db_id. Status: ${response.status}, Text: ${await response.text()}`);
            return null;
        }
        const data = await response.json();
        if (data && typeof data.sentence_db_id !== 'undefined') {
            console.log(`JS: Successfully fetched sentence_db_id: ${data.sentence_db_id}`);
            return data.sentence_db_id;
        } else {
            console.error("JS: Failed to fetch sentence_db_id: ID missing in response.", data);
            return null;
        }
    } catch (error) {
        console.error("JS: Network or other error fetching sentence_db_id:", error);
        return null;
    }
}

async function updateSentenceTimestampOnServer(sentenceDbId, timestampType, newTimeMs) {
    const url = `/article/${ARTICLE_ID}/sentence/${sentenceDbId}/update_timestamp`;
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                // TODO: Include CSRF token if Django setup requires it for POST requests
                // 'X-CSRFToken': getCookie('csrftoken') // Example: You'd need a getCookie function
            },
            body: JSON.stringify({
                timestamp_type: timestampType,
                new_time_ms: newTimeMs
            })
        });
        const result = await response.json();

        if (!response.ok || result.status !== 'success') {
            console.error(`Failed to update timestamp for sentence ${sentenceDbId}:`, result.message);
            alert(`Failed to update timestamp: ${result.message}`);
            return false;
        }

        console.log(`Timestamp updated successfully for sentence ${sentenceDbId}. Type: ${timestampType}, New Time: ${newTimeMs}ms.`);
        const sentenceElToUpdate = document.querySelector(`.english-sentence[data-sentence-db-id="${sentenceDbId}"]`);

        if (sentenceElToUpdate) {
            if (timestampType === 'start') {
                sentenceElToUpdate.dataset.startTimeMs = newTimeMs;
            } else if (timestampType === 'end') {
                sentenceElToUpdate.dataset.endTimeMs = newTimeMs;
            }

            // If this updated sentence is the currently highlighted one and its waveform is visible, refresh it.
            // This uses the global audioBuffer, assuming it's the full audio track if isAudiobookModeFull is true.
            if (highlightedSentence === sentenceElToUpdate && isAudiobookModeFull && window.audioBuffer) {
                let waveformIsVisible = false;
                if (sentenceElToUpdate.parentElement &&
                    sentenceElToUpdate.parentElement.nextElementSibling &&
                    sentenceElToUpdate.parentElement.nextElementSibling.classList.contains('waveform-scroll-container')) {
                    waveformIsVisible = true;
                }

                if (waveformIsVisible) {
                    console.log("JS: Refreshing waveform for sentence ID:", sentenceDbId, "after timestamp update.");
                    const currentStartTime = parseInt(sentenceElToUpdate.dataset.startTimeMs, 10);
                    const currentEndTime = parseInt(sentenceElToUpdate.dataset.endTimeMs, 10);
                    if (!isNaN(currentStartTime) && !isNaN(currentEndTime) && currentStartTime < currentEndTime) {
                        // Pass the global audioBuffer which should be the full track in this context
                        displayWaveform(sentenceElToUpdate, window.audioBuffer, currentStartTime, currentEndTime);
                    } else {
                        console.warn("JS: Cannot refresh waveform due to invalid new start/end times after update:", sentenceElToUpdate.dataset);
                    }
                }
            }
        }
        return true;
    } catch (error) {
        console.error('Network or other error updating timestamp:', error);
        alert('Error updating timestamp: ' + error.message);
        return false;
    }
}

function displayWaveform(sentenceElement, audioBuffer, startTimeMs, endTimeMs) {
    if (!sentenceElement || !audioBuffer || typeof startTimeMs === 'undefined' || typeof endTimeMs === 'undefined') {
        console.warn("displayWaveform: Missing required parameters.");
        return;
    }
    if (!audioContext) { // Ensure audioContext is available
        console.warn("displayWaveform: AudioContext not available.");
        return;
    }

    clearExistingWaveform(sentenceElement); // This will be updated later to target the container

    const ORIGINAL_WAVEFORM_MS_PER_PIXEL = WAVEFORM_MS_PER_PIXEL; // Should be 10
    const MAX_CANVAS_WIDTH = 16384; // Max width based on common browser limits (e.g., Safari)
    let effectiveMsPerPixel = ORIGINAL_WAVEFORM_MS_PER_PIXEL;

    const segmentDurationMs = endTimeMs - startTimeMs;
    console.log("WAVEFORM_DEBUG: segmentDurationMs =", segmentDurationMs);
    if (segmentDurationMs <= 0) {
        console.error("displayWaveform: segmentDurationMs is zero or negative.");
        return;
    }

    const canvasActualWidth = Math.max(50, Math.ceil(segmentDurationMs / ORIGINAL_WAVEFORM_MS_PER_PIXEL));
    console.log("WAVEFORM_DEBUG: canvasActualWidth =", canvasActualWidth);

    // Cap canvas width to prevent issues with extremely long sentences / large canvases.
    // If capped, adjust the ms per pixel factor to fit the entire waveform.
    let finalCanvasWidth = canvasActualWidth;
    if (canvasActualWidth > MAX_CANVAS_WIDTH) {
        console.warn(`WAVEFORM_INFO: Original calculated width ${canvasActualWidth}px exceeded MAX_CANVAS_WIDTH ${MAX_CANVAS_WIDTH}px. Capping width.`);
        finalCanvasWidth = MAX_CANVAS_WIDTH;
        effectiveMsPerPixel = segmentDurationMs / finalCanvasWidth;
        console.log(`WAVEFORM_DEBUG: Capped width to ${finalCanvasWidth}px, new effectiveMsPerPixel = ${effectiveMsPerPixel}`);
    } else {
        effectiveMsPerPixel = ORIGINAL_WAVEFORM_MS_PER_PIXEL;
    }

    const scrollContainer = document.createElement('div');
    scrollContainer.className = 'waveform-scroll-container';

    const canvas = document.createElement('canvas');
    canvas.className = 'waveform-canvas';
    canvas.width = finalCanvasWidth;  // Internal drawing surface width
    canvas.style.width = finalCanvasWidth + 'px'; // CSS width for scrolling
    canvas.height = 75; // Keep existing height
    canvas.currentMarkerX = null; // Initialize marker position

    scrollContainer.appendChild(canvas);

    // Store data on the canvas for the click handler and future playback
    canvas.segmentStartTimeMs = startTimeMs;
    canvas.segmentEndTimeMs = endTimeMs;
    canvas.effectiveMsPerPixel = effectiveMsPerPixel;
    canvas.audioBuffer = audioBuffer; // The full audio buffer used for this waveform display
    canvas.sentenceElement = sentenceElement;

    // Determine if playback for this sentence context is from a part or full audio
    let isPlayingFromPartContext = false;
    if (isAudiobookModeParts && sentenceElement.dataset.audioPartIndex !== undefined) {
        const sentencePartIdx = parseInt(sentenceElement.dataset.audioPartIndex, 10);
        if (sentencePartIdx === currentLoadedAudioPartIndex) {
            isPlayingFromPartContext = true;
        }
    } else if (isAudiobookModeFull) {
        isPlayingFromPartContext = false;
    }
    // If neither mode is active but waveform is shown (e.g. via 'edit clip' on full audio mode but then toggling off),
    // assume it's based on the full audio times.
    // The crucial aspect is that canvas.audioBuffer is the one currently loaded and matching sentence times.
    // The playSentenceAudio function takes an isPlayingFromPart boolean.
    // For click, we need to know if the segmentStartTimeMs/segmentEndTimeMs are relative to 'full' or 'part'.
    // The parameters startTimeMs and endTimeMs passed to displayWaveform are already adjusted for this.
    // So, the isPlayingFromPart for playSentenceAudio must match how sentenceElement time attributes are set.

    // For the click handler, the key is that segmentStartTimeMs and segmentEndTimeMs are the 'true' start/end for the current audioBuffer.
    // The `playSentenceAudio` function itself will use the sentenceElement's data attributes to get the correct times based on its own `isPlayingFromPart` argument.
    // What we need for the click handler is to correctly *initiate* playback, respecting the original context.
    // Let's check how playSentenceAudio is called from the 'edit-audio-clip' context menu
    // displayWaveform(highlightedSentence, audioBuffer, startTimeMs, endTimeMs); -- here startTimeMs, endTimeMs are from full audio.
    // So, if the waveform was generated from full audio, clicks should refer to full audio times.
    // If it was generated in parts mode (hypothetically, not current implementation for 'edit clip'), it would use part times.
    // The current 'edit-audio-clip' always uses the main audioBuffer and its associated startTimeMs/endTimeMs.
    // So, isPlayingFromPart for the purpose of interpreting click should align with this.
    // The global isAudiobookModeFull can indicate this.
    canvas.isSegmentFromFullAudio = isAudiobookModeFull; // True if these times are for the full audio.

    canvas.addEventListener('click', async function(event) { // Made async
        const clickX = event.offsetX; // Used by all modes
        const calculatedTimeOffsetInSegmentMs = clickX * this.effectiveMsPerPixel; // Raw offset from canvas start

        if (event.ctrlKey && !event.altKey && !event.shiftKey && !event.metaKey) {
            // --- CTRL+Click: Set Start Time ---
            if (!highlightedSentence) {
                console.warn("Waveform CTRL+Click: No sentence selected globally for editing.");
                return;
            }
            if (this.sentenceElement !== highlightedSentence) {
                console.warn("Waveform CTRL+Click: Waveform's sentence doesn't match globally highlighted sentence.");
                return;
            }
            if (!this.isSegmentFromFullAudio) { // Check if waveform is for full audio
                console.log("Waveform CTRL+Click: Timestamp editing via waveform click is currently only supported on the full audio view.");
                return;
            }
            let sentenceDbId = highlightedSentence.dataset.sentenceDbId;
            if (!sentenceDbId) {
                const pIndex = highlightedSentence.dataset.paragraphIndex;
                const sIndex = highlightedSentence.dataset.sentenceIndex;
                if (typeof ARTICLE_ID === 'undefined' || ARTICLE_ID === null) {
                    console.error("Waveform CTRL+Click: ARTICLE_ID is not available globally.");
                    return;
                }
                if (pIndex !== undefined && sIndex !== undefined) {
                    console.log(`Waveform CTRL+Click: sentence_db_id missing. Fetching for p:${pIndex}, s:${sIndex}`);
                    const newSentenceDbId = await fetchSentenceDbIdByIndices(ARTICLE_ID, pIndex, sIndex);
                    if (newSentenceDbId) {
                        highlightedSentence.dataset.sentenceDbId = newSentenceDbId;
                        sentenceDbId = newSentenceDbId; // Use the newly fetched ID
                        console.log(`Waveform CTRL+Click: Successfully fetched sentence_db_id: ${sentenceDbId}`);
                    } else {
                        console.error(`Waveform CTRL+Click: Could not retrieve sentence_db_id for p:${pIndex}, s:${sIndex}. Timestamp update aborted.`);
                        return;
                    }
                } else {
                    console.error("Waveform CTRL+Click: Cannot fetch sentence_db_id because paragraphIndex or sentenceIndex is missing from dataset.");
                    return;
                }
            }

            const currentEndTimeMsStr = highlightedSentence.dataset.endTimeMs;
            if (!currentEndTimeMsStr) {
                 console.error("Waveform CTRL+Click: Original end time (data-end-time-ms) missing on highlighted sentence.");
                 return;
            }
            const currentEndTimeMs = parseInt(currentEndTimeMsStr, 10);
            if (isNaN(currentEndTimeMs)) {
                console.error("Waveform CTRL+Click: Original end time (data-end-time-ms) is not a valid number for highlighted sentence.");
                return;
            }

            // newStartTimeMs is absolute time in the full audio context
            const newStartTimeMs = Math.round(this.segmentStartTimeMs + calculatedTimeOffsetInSegmentMs);

            if (newStartTimeMs >= 0 && newStartTimeMs < currentEndTimeMs) {
                updateSentenceTimestampOnServer(sentenceDbId, 'start', newStartTimeMs);
            } else {
                console.warn(`Waveform CTRL+Click: Invalid new start time: ${newStartTimeMs}ms. Must be >= 0 and < current end time (${currentEndTimeMs}ms).`);
            }

        } else if (event.altKey && !event.ctrlKey && !event.shiftKey && !event.metaKey) {
            // --- ALT+Click: Set End Time ---
            if (!highlightedSentence) {
                console.warn("Waveform ALT+Click: No sentence selected globally for editing.");
                return;
            }
            if (this.sentenceElement !== highlightedSentence) {
                console.warn("Waveform ALT+Click: Waveform's sentence doesn't match globally highlighted sentence.");
                return;
            }
            if (!this.isSegmentFromFullAudio) { // Check if waveform is for full audio
                console.log("Waveform ALT+Click: Timestamp editing via waveform click is currently only supported on the full audio view.");
                return;
            }
            let sentenceDbId = highlightedSentence.dataset.sentenceDbId;
            if (!sentenceDbId) {
                const pIndex = highlightedSentence.dataset.paragraphIndex;
                const sIndex = highlightedSentence.dataset.sentenceIndex;
                if (typeof ARTICLE_ID === 'undefined' || ARTICLE_ID === null) {
                    console.error("Waveform ALT+Click: ARTICLE_ID is not available globally.");
                    return;
                }
                if (pIndex !== undefined && sIndex !== undefined) {
                    console.log(`Waveform ALT+Click: sentence_db_id missing. Fetching for p:${pIndex}, s:${sIndex}`);
                    const newSentenceDbId = await fetchSentenceDbIdByIndices(ARTICLE_ID, pIndex, sIndex);
                    if (newSentenceDbId) {
                        highlightedSentence.dataset.sentenceDbId = newSentenceDbId;
                        sentenceDbId = newSentenceDbId; // Use the newly fetched ID
                        console.log(`Waveform ALT+Click: Successfully fetched sentence_db_id: ${sentenceDbId}`);
                    } else {
                        console.error(`Waveform ALT+Click: Could not retrieve sentence_db_id for p:${pIndex}, s:${sIndex}. Timestamp update aborted.`);
                        return;
                    }
                } else {
                    console.error("Waveform ALT+Click: Cannot fetch sentence_db_id because paragraphIndex or sentenceIndex is missing from dataset.");
                    return;
                }
            }

            const currentStartTimeMsStr = highlightedSentence.dataset.startTimeMs;
             if (!currentStartTimeMsStr) {
                 console.error("Waveform ALT+Click: Original start time (data-start-time-ms) missing on highlighted sentence.");
                 return;
            }
            const currentStartTimeMs = parseInt(currentStartTimeMsStr, 10);
            if (isNaN(currentStartTimeMs)) {
                console.error("Waveform ALT+Click: Original start time (data-start-time-ms) is not a valid number for highlighted sentence.");
                return;
            }

            // newEndTimeMs is absolute time in the full audio context
            const newEndTimeMs = Math.round(this.segmentStartTimeMs + calculatedTimeOffsetInSegmentMs);

            if (newEndTimeMs > currentStartTimeMs) {
                updateSentenceTimestampOnServer(sentenceDbId, 'end', newEndTimeMs);
            } else {
                console.warn(`Waveform ALT+Click: Invalid new end time: ${newEndTimeMs}ms. Must be > current start time (${currentStartTimeMs}ms).`);
            }

        } else if (!event.ctrlKey && !event.altKey && !event.shiftKey && !event.metaKey) {
            // --- Default Click: Playback and Marker Update ---
            let timeOffsetInSegmentMs = calculatedTimeOffsetInSegmentMs; // Use the already calculated offset
            const segmentDurationOnCanvasMs = this.segmentEndTimeMs - this.segmentStartTimeMs;

            if (timeOffsetInSegmentMs < 0) timeOffsetInSegmentMs = 0;
            if (timeOffsetInSegmentMs > segmentDurationOnCanvasMs) {
                timeOffsetInSegmentMs = segmentDurationOnCanvasMs;
            }
            const absolutePlayTimeMs = this.segmentStartTimeMs + timeOffsetInSegmentMs;

            let logIsPlayingFromPart; // For console logging context
            if (isAudiobookModeParts) {
                const sentencePartIdx = parseInt(this.sentenceElement.dataset.audioPartIndex, 10);
                logIsPlayingFromPart = (sentencePartIdx === currentLoadedAudioPartIndex);
            } else {
                logIsPlayingFromPart = false;
            }

            console.log(
                "Waveform Regular Click at X:", clickX,
                "Calculated time offset in segment (ms):", timeOffsetInSegmentMs.toFixed(2),
                "Absolute play time for this waveform's buffer (ms):", absolutePlayTimeMs.toFixed(2),
                "Waveform segment's original context was based on 'full' audio:", this.isSegmentFromFullAudio,
                "Current playback context would be 'from part':", logIsPlayingFromPart
            );

            this.currentMarkerX = clickX;
            const ctx = this.getContext('2d');
            ctx.fillStyle = '#f0f0f0'; // Background
            ctx.fillRect(0, 0, this.width, this.height);

            const waveformStartSample = Math.floor((this.segmentStartTimeMs / 1000) * this.audioBuffer.sampleRate);
            let waveformEndSample = Math.floor((this.segmentEndTimeMs / 1000) * this.audioBuffer.sampleRate);
            if (waveformEndSample > this.audioBuffer.length) waveformEndSample = this.audioBuffer.length;

            if (waveformStartSample >= waveformEndSample) {
                console.warn("Waveform click redraw: startSample >= endSample");
                if (typeof this.currentMarkerX === 'number') {
                    ctx.strokeStyle = 'red'; ctx.lineWidth = 1; ctx.beginPath();
                    ctx.moveTo(this.currentMarkerX, 0); ctx.lineTo(this.currentMarkerX, this.height); ctx.stroke();
                }
                return;
            }
            const currentSegmentData = this.audioBuffer.getChannelData(0).slice(waveformStartSample, waveformEndSample);

            if (currentSegmentData.length === 0) {
                console.warn("Waveform click redraw: currentSegmentData is empty.");
                if (typeof this.currentMarkerX === 'number') {
                    ctx.strokeStyle = 'red'; ctx.lineWidth = 1; ctx.beginPath();
                    ctx.moveTo(this.currentMarkerX, 0); ctx.lineTo(this.currentMarkerX, this.height); ctx.stroke();
                }
                return;
            }

            const currentSamplesPerPixel = currentSegmentData.length / this.width;
            const currentUpperEnvelopePoints = [];
            const currentLowerEnvelopePoints = [];
            for (let x_coord = 0; x_coord < this.width; x_coord++) {
                const startIdx = Math.floor(x_coord * currentSamplesPerPixel);
                const endIdx = Math.floor((x_coord + 1) * currentSamplesPerPixel);
                let maxVal = 0;
                for (let i = startIdx; i < endIdx && i < currentSegmentData.length; i++) {
                    const val = Math.abs(currentSegmentData[i]);
                    if (val > maxVal) maxVal = val;
                }
                if (startIdx === endIdx && startIdx < currentSegmentData.length) {
                     maxVal = Math.abs(currentSegmentData[startIdx]);
                }
                const v = maxVal;
                const amplitude = v * this.height / 2;
                currentUpperEnvelopePoints.push({ x: x_coord, y: (this.height / 2) - amplitude });
                currentLowerEnvelopePoints.push({ x: x_coord, y: (this.height / 2) + amplitude });
            }

            if (this.width > 0 && currentSegmentData.length > 0) {
                const lastSampleIdx = currentSegmentData.length - 1;
                const lastVal = Math.abs(currentSegmentData[lastSampleIdx]);
                const last_amplitude = lastVal * this.height / 2;
                currentUpperEnvelopePoints.push({ x: this.width, y: (this.height / 2) - last_amplitude });
                currentLowerEnvelopePoints.push({ x: this.width, y: (this.height / 2) + last_amplitude });
            } else if (this.width > 0) {
                currentUpperEnvelopePoints.push({ x: this.width, y: this.height / 2 });
                currentLowerEnvelopePoints.push({ x: this.width, y: this.height / 2 });
            }

            if (currentUpperEnvelopePoints.length > 0) {
                ctx.beginPath();
                ctx.moveTo(currentUpperEnvelopePoints[0].x, currentUpperEnvelopePoints[0].y);
                for (let i = 1; i < currentUpperEnvelopePoints.length; i++) {
                    ctx.lineTo(currentUpperEnvelopePoints[i].x, currentUpperEnvelopePoints[i].y);
                }
                for (let i = currentLowerEnvelopePoints.length - 1; i >= 0; i--) {
                    ctx.lineTo(currentLowerEnvelopePoints[i].x, currentLowerEnvelopePoints[i].y);
                }
                ctx.closePath();
                ctx.fillStyle = 'rgba(0, 123, 255, 0.3)';
                ctx.fill();
            }

            ctx.strokeStyle = 'red';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(this.currentMarkerX, 0);
            ctx.lineTo(this.currentMarkerX, this.height);
            ctx.stroke();
            console.log("WAVEFORM_MARKER: Drew new marker at X:", this.currentMarkerX);

            const isPlayingFromPartArgument = !this.isSegmentFromFullAudio;
            playSentenceAudio(this.sentenceElement, isPlayingFromPartArgument, absolutePlayTimeMs);
        }
    });

    if (sentenceElement.parentElement) {
        sentenceElement.parentElement.insertAdjacentElement('afterend', scrollContainer);
    } else {
        console.error('displayWaveform: Sentence element has no parent. Cannot insert waveform container.');
        return;
    }

    // Ensure canvas has a positive width, otherwise drawing makes no sense.
    // This check should now use canvasActualWidth or canvas.width
    if (canvas.width <= 0) {
        console.warn("displayWaveform: Calculated canvas width is 0 or negative. Aborting waveform display.");
        return;
    }

    console.log("WAVEFORM_DEBUG: Canvas dimensions before getContext: width =", canvas.width, "height =", canvas.height);
    const ctx = canvas.getContext('2d');
    if (!ctx) {
        console.error("displayWaveform: Failed to get 2D rendering context.");
        return;
    }

    // Extract Audio Data
    const startSample = Math.floor((startTimeMs / 1000) * audioBuffer.sampleRate);
    let endSample = Math.floor((endTimeMs / 1000) * audioBuffer.sampleRate);

    // Ensure endSample does not exceed audioBuffer.length
    if (endSample > audioBuffer.length) {
        endSample = audioBuffer.length;
    }
    // Ensure startSample is not greater than or equal to endSample
    if (startSample >= endSample) {
        console.warn("displayWaveform: startSample is greater than or equal to endSample. Nothing to display.");
        // Optionally draw a flat line or some indicator
        ctx.fillStyle = '#f0f0f0';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.strokeStyle = 'rgb(0, 123, 255)';
        ctx.beginPath();
        ctx.moveTo(0, canvas.height / 2);
        ctx.lineTo(canvas.width, canvas.height / 2);
        ctx.stroke();
        return;
    }


    const channelData = audioBuffer.getChannelData(0); // Assuming mono or taking the first channel
    const segmentData = channelData.slice(startSample, endSample);

    if (segmentData.length === 0) {
        console.warn("displayWaveform: segmentData is empty. Nothing to draw.");
         // Optionally draw a flat line or some indicator
        ctx.fillStyle = '#f0f0f0';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.strokeStyle = 'rgb(0, 123, 255)';
        ctx.beginPath();
        ctx.moveTo(0, canvas.height / 2);
        ctx.lineTo(canvas.width, canvas.height / 2);
        ctx.stroke();
        return;
    }

    // Draw the Waveform
    ctx.fillStyle = '#f0f0f0'; // Background color for the canvas
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // ctx.lineWidth = 1; // No longer needed for fill only
    // ctx.strokeStyle = 'rgb(0, 123, 255)'; // Will be replaced by fillStyle

    if (segmentData.length === 0) { // Should have been caught earlier, but defensive
        // For an empty segment, just show the background, or a flat line if desired.
        // A flat line might be confusing if it's the same color as a potential fill.
        // The background is already filled, so just return.
        // If a line is truly desired for empty segments:
        ctx.strokeStyle = 'rgb(150, 150, 150)'; // A neutral color for empty line
        ctx.beginPath();
        ctx.moveTo(0, canvas.height / 2);
        ctx.lineTo(canvas.width, canvas.height / 2);
        ctx.stroke();
        console.warn("WAVEFORM_DEBUG: segmentData was empty, drew flat grey line.");
        return;
    }

    const samplesPerPixel = segmentData.length / canvas.width;
    const upperEnvelopePoints = [];
    const lowerEnvelopePoints = [];

    for (let x = 0; x < canvas.width; x++) {
        const startIdx = Math.floor(x * samplesPerPixel);
        const endIdx = Math.floor((x + 1) * samplesPerPixel);
        let maxVal = 0;

        for (let i = startIdx; i < endIdx && i < segmentData.length; i++) {
            const val = Math.abs(segmentData[i]);
            if (val > maxVal) {
                maxVal = val;
            }
        }
        if (startIdx === endIdx && startIdx < segmentData.length) {
             maxVal = Math.abs(segmentData[startIdx]);
        }

        const v = maxVal;
        const amplitude = v * canvas.height / 2;
        upperEnvelopePoints.push({ x: x, y: (canvas.height / 2) - amplitude });
        lowerEnvelopePoints.push({ x: x, y: (canvas.height / 2) + amplitude });
    }

    // Handle extensions for the last point to canvas.width
    if (canvas.width > 0 && segmentData.length > 0) {
        const lastSampleIdx = segmentData.length - 1;
        const lastVal = Math.abs(segmentData[lastSampleIdx]);
        const last_amplitude = lastVal * canvas.height / 2;
        upperEnvelopePoints.push({ x: canvas.width, y: (canvas.height / 2) - last_amplitude });
        lowerEnvelopePoints.push({ x: canvas.width, y: (canvas.height / 2) + last_amplitude });
    } else if (canvas.width > 0) { // segmentData is empty (already handled) or canvas.width is 0
        // This case might be redundant if segmentData.length === 0 is handled,
        // but good for safety if canvas.width > 0 but points arrays are empty.
        upperEnvelopePoints.push({ x: canvas.width, y: canvas.height / 2 });
        lowerEnvelopePoints.push({ x: canvas.width, y: canvas.height / 2 });
    }

    // Ensure there are points to draw to prevent errors
    if (upperEnvelopePoints.length === 0) {
        console.warn("WAVEFORM_DEBUG: No points to draw for filled waveform.");
        return; // Or draw a flat line as in the segmentData.length === 0 case
    }

    ctx.beginPath();
    ctx.moveTo(upperEnvelopePoints[0].x, upperEnvelopePoints[0].y);

    for (let i = 1; i < upperEnvelopePoints.length; i++) {
        ctx.lineTo(upperEnvelopePoints[i].x, upperEnvelopePoints[i].y);
    }

    // Line to the last point of the lower envelope (which is at canvas.width)
    // then draw backwards along the lower envelope
    for (let i = lowerEnvelopePoints.length - 1; i >= 0; i--) {
        ctx.lineTo(lowerEnvelopePoints[i].x, lowerEnvelopePoints[i].y);
    }

    ctx.closePath(); // This will connect the first point of lower (at x=0) to first point of upper (at x=0)

    ctx.fillStyle = 'rgba(0, 123, 255, 0.3)'; // Semi-transparent fill
    ctx.fill();

    // Optional: if an outline on top of the fill is desired
    // ctx.strokeStyle = 'rgb(0, 123, 255)';
    // ctx.lineWidth = 1;
    // ctx.stroke();

    console.log("WAVEFORM_DEBUG: Filled waveform drawing completed.");

    // After main drawing, if there's a marker position stored, draw it
    if (typeof canvas.currentMarkerX === 'number' && canvas.currentMarkerX >= 0 && canvas.currentMarkerX <= canvas.width) {
        // Get context again, as it might be out of scope if drawing logic becomes more complex/refactored
        const markerCtx = canvas.getContext('2d');
        markerCtx.strokeStyle = 'red';
        markerCtx.lineWidth = 1;
        markerCtx.beginPath();
        markerCtx.moveTo(canvas.currentMarkerX, 0);
        markerCtx.lineTo(canvas.currentMarkerX, canvas.height);
        markerCtx.stroke();
        console.log("WAVEFORM_MARKER: Re-drew marker at X:", canvas.currentMarkerX, "during displayWaveform call.");
    }
}

    // --- Audio Parts View UI ---
    let isPartsViewActive = false;
    function updatePartsViewModeUI() {
        if (isPartsViewActive) {
            if(partsAudioViewControls) partsAudioViewControls.style.display = 'block';
            if(fullAudioViewControls) fullAudioViewControls.style.display = 'none';
            if(partsAudioDownloadDiv) partsAudioDownloadDiv.style.display = 'block';
            if(fullAudioDownloadDiv) fullAudioDownloadDiv.style.display = 'none';
            if(switchToPartsViewButton) switchToPartsViewButton.style.display = 'none';
            if(switchToFullViewButton) switchToFullViewButton.style.display = 'inline-block';

            isAudiobookModeParts = true;
            isAudiobookModeFull = false;
            if (toggleAudiobookModeButton) {
                 toggleAudiobookModeButton.textContent = 'Enable Audiobook Mode (Full Audio)';
                 if(localAudioFileInput) localAudioFileInput.style.display = 'none';
                 if(audioFileNameSpan) audioFileNameSpan.textContent = 'No audio file selected.';
                 if(audiobookHint) audiobookHint.style.display = 'none';
            }
            stopCurrentAudio();
            if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = "No part loaded.";
            currentLoadedAudioPartIndex = -1;
            audioBuffer = null;

        } else {
            if(partsAudioViewControls) partsAudioViewControls.style.display = 'none';
            if(fullAudioViewControls) fullAudioViewControls.style.display = 'block';
            if(partsAudioDownloadDiv) partsAudioDownloadDiv.style.display = 'none';
            if(fullAudioDownloadDiv) fullAudioDownloadDiv.style.display = 'block';
            if(switchToPartsViewButton) switchToPartsViewButton.style.display = 'inline-block';
            if(switchToFullViewButton) switchToFullViewButton.style.display = 'none';
            
            isAudiobookModeParts = false;
            stopCurrentAudio();
        }
    }

    // --- Gamepad Logic ---
    function updateGamepadIconDisplay(isConnected, gamepadId = null) { // Renamed to avoid conflict
        if (gamepadStatusEmoji) {
            gamepadStatusEmoji.classList.remove('connected', 'error'); 

            if (isConnected && gamepadId) {
                gamepadStatusEmoji.classList.add('connected');
                gamepadStatusEmoji.setAttribute('title', `Gamepad Connected: ${gamepadId.substring(0,25)}...`);
            } else if (isConnected === 'error') {
                gamepadStatusEmoji.classList.add('error');
                gamepadStatusEmoji.setAttribute('title', 'Gamepad connection issue');
            } else { 
                gamepadStatusEmoji.setAttribute('title', 'No Gamepad Connected');
            }
        }
    }

    function handleGamepadInput() {
        if (gamepadIndex === null) return;
        const gamepad = navigator.getGamepads()[gamepadIndex];
        if (!gamepad) {
            updateGamepadIconDisplay('error');
            if (animationFrameIdGamepad) cancelAnimationFrame(animationFrameIdGamepad);
            animationFrameIdGamepad = null;
            gamepadIndex = null;
            previousButtonStates = [];
            return;
        }

        if (!gamepadStatusEmoji.classList.contains('connected') && !gamepadStatusEmoji.classList.contains('error')) {
             updateGamepadIconDisplay(true, gamepad.id);
        }

        const now = Date.now();

        if (gamepad.buttons[BUTTON_A_INDEX].pressed && (!previousButtonStates[BUTTON_A_INDEX] || !previousButtonStates[BUTTON_A_INDEX].pressed)) {
            if (now - lastGamepadActionTime > GAMEPAD_ACTION_COOLDOWN) {
                selectNextSentence();
                lastGamepadActionTime = now;
            }
        }
        if (gamepad.buttons[BUTTON_X_INDEX].pressed && (!previousButtonStates[BUTTON_X_INDEX] || !previousButtonStates[BUTTON_X_INDEX].pressed)) {
            if (now - lastGamepadActionTime > GAMEPAD_ACTION_COOLDOWN) {
                selectPreviousSentence();
                lastGamepadActionTime = now;
            }
        }
        if (gamepad.buttons[BUTTON_B_INDEX].pressed && (!previousButtonStates[BUTTON_B_INDEX] || !previousButtonStates[BUTTON_B_INDEX].pressed)) {
            if (highlightedSentence) {
                initAudioContextGlobally();
                let playAsPart = false;
                let canPlayThisSentence = false;
                if (isAudiobookModeParts && currentLoadedAudioPartIndex !== -1 &&
                    highlightedSentence.dataset.audioPartIndex !== undefined &&
                    parseInt(highlightedSentence.dataset.audioPartIndex, 10) === currentLoadedAudioPartIndex) {
                    playAsPart = true;
                    canPlayThisSentence = audioContext && audioBuffer;
                } else if (isAudiobookModeFull) {
                    playAsPart = false;
                    canPlayThisSentence = audioContext && audioBuffer;
                }
                if (canPlayThisSentence) {
                    playSentenceAudio(highlightedSentence, playAsPart);
                } else {
                    if (!HAS_TIMESTAMPS) console.warn("JS: B button - Timestamps not available.");
                    else if (isAudiobookModeFull && (!audioContext || !audioBuffer)) console.warn("JS: B button - Full audio mode, but audio not loaded.");
                    else if (isAudiobookModeParts) console.warn("JS: B button - Part audio mode issue (not loaded/mismatch).");
                    else console.log("JS: B button pressed, but audio not ready/configured.");
                }
            }
        }
        if (gamepad.buttons[BUTTON_Y_INDEX].pressed && (!previousButtonStates[BUTTON_Y_INDEX] || !previousButtonStates[BUTTON_Y_INDEX].pressed)) {
            if (highlightedSentence) {
                if (popup.style.display === 'block' && currentPopupTargetSentence === highlightedSentence) {
                    hideTranslationPopup();
                } else {
                    const translation = highlightedSentence.dataset.translation;
                    displayPopup(highlightedSentence, translation || "No translation available.");
                }
            }
        }

        gamepad.buttons.forEach((button, index) => {
            if (!previousButtonStates[index]) previousButtonStates[index] = {};
            previousButtonStates[index].pressed = button.pressed;
        });
        animationFrameIdGamepad = requestAnimationFrame(handleGamepadInput);
    }

    window.addEventListener("gamepadconnected", (event) => {
        console.log('JS: Gamepad connected:', event.gamepad.id);
        updateGamepadIconDisplay(true, event.gamepad.id);
        gamepadIndex = event.gamepad.index;
        const gp = navigator.getGamepads()[gamepadIndex];
        if (gp) {
            previousButtonStates = gp.buttons.map(b => ({ pressed: b.pressed }));
        } else {
            previousButtonStates = [];
        }
        if (animationFrameIdGamepad) cancelAnimationFrame(animationFrameIdGamepad);
        animationFrameIdGamepad = requestAnimationFrame(handleGamepadInput);
    });

    window.addEventListener("gamepaddisconnected", (event) => {
        console.log('JS: Gamepad disconnected:', event.gamepad.id);
        if (event.gamepad.index === gamepadIndex) {
            updateGamepadIconDisplay(false);
            if (animationFrameIdGamepad) cancelAnimationFrame(animationFrameIdGamepad);
            animationFrameIdGamepad = null;
            gamepadIndex = null;
            previousButtonStates = [];
        }
    });

    // --- Initial Setup Calls ---
    populateSentenceElementsArray();
    initAudioContextGlobally();
    updateGamepadIconDisplay(false); // Set initial icon state

    // Event Listeners Setup
    if (articleContentWrapper) {
        articleContentWrapper.addEventListener('contextmenu', function(event) {
            const targetSentence = event.target.closest('.english-sentence');
            if (targetSentence) {
                event.preventDefault();
                hideContextualMenu();
                const translation = targetSentence.dataset.translation;
                displayPopup(targetSentence, translation || "No translation.");
                if (highlightedSentence !== targetSentence) {
                    setActiveSentence(targetSentence, "contextmenu_highlight");
                } else {
                    scrollToCenter(targetSentence);
                }
            } else {
                hideTranslationPopup();
            }
        });
        articleContentWrapper.addEventListener('click', function(event) {
            const targetSentence = event.target.closest('.english-sentence');
            if (targetSentence) {
                event.stopPropagation();
                hideTranslationPopup();
                if (highlightedSentence === targetSentence) {
                    if (contextualMenu.style.display === 'block' && contextualMenu.style.opacity === '1') {
                        hideContextualMenu();
                    } else {
                        populateAndShowContextualMenu(targetSentence, event.clientX);
                    }
                } else {
                    setActiveSentence(targetSentence, "click_new_sentence");
                    hideContextualMenu();

                    let waveformIsVisibleForThisSentence = false;
                    if (targetSentence.parentElement &&
                        targetSentence.parentElement.nextElementSibling &&
                        targetSentence.parentElement.nextElementSibling.classList.contains('waveform-scroll-container')) {
                        waveformIsVisibleForThisSentence = true;
                    }
                    // console.log("Sentence clicked. Waveform visible:", waveformIsVisibleForThisSentence);

                    if (!waveformIsVisibleForThisSentence) {
                        if (isAudiobookModeFull && audioContext && audioBuffer) {
                            playSentenceAudio(targetSentence, false, null); // Play from beginning
                        } else if (isAudiobookModeParts && audioContext && audioBuffer) {
                            const sentencePartIndexStr = targetSentence.dataset.audioPartIndex;
                            if (sentencePartIndexStr !== undefined) {
                                const sentencePartIndex = parseInt(sentencePartIndexStr, 10);
                                if (sentencePartIndex === currentLoadedAudioPartIndex) {
                                    playSentenceAudio(targetSentence, true, null); // Play from beginning
                                } else {
                                    // If part doesn't match, select the radio button for that part, don't auto-play.
                                    const radioToSelect = document.querySelector(`#audio-part-selector-playback input[name="audio_part_playback"][value="${sentencePartIndex}"]`);
                                    if (radioToSelect) radioToSelect.checked = true;
                                }
                            }
                        }
                    }
                }
            } else {
                if (!contextualMenu.contains(event.target)) hideContextualMenu();
                if (!popup.contains(event.target)) hideTranslationPopup();
            }
        });
    }
    if (contextualMenu) {
        contextualMenu.addEventListener('click', function(event) {
            event.stopPropagation();
            const actionTarget = event.target.closest('.contextual-menu-item');
            if (!actionTarget || !highlightedSentence) {
                hideContextualMenu(); return;
            }
            const action = actionTarget.dataset.action;
            switch (action) {
                case 'show-translation':
                    const translation = highlightedSentence.dataset.translation;
                    displayPopup(highlightedSentence, translation || "No translation available.");
                    break;
                case 'save-location':
                    const pIndex = highlightedSentence.dataset.paragraphIndex;
                    const sIndex = highlightedSentence.dataset.sentenceIndex;
                    if (pIndex !== undefined && sIndex !== undefined) {
                        saveCurrentLocation(parseInt(pIndex), parseInt(sIndex), "manual_menu_save");
                    }
                    break;
                case 'play-pause-audio':
                    initAudioContextGlobally();
                    let playAsPart = false;
                    let canPlayThis = false;
                    if (isAudiobookModeFull && audioContext && audioBuffer && HAS_TIMESTAMPS) {
                        canPlayThis = true; playAsPart = false;
                    } else if (isAudiobookModeParts && audioContext && audioBuffer && HAS_TIMESTAMPS && currentLoadedAudioPartIndex !== -1) {
                        const sentencePartIndex = parseInt(highlightedSentence.dataset.audioPartIndex, 10);
                        if (sentencePartIndex === currentLoadedAudioPartIndex) {
                            canPlayThis = true; playAsPart = true;
                        }
                    }
                    if (canPlayThis) {
                        const iconSpan = actionTarget.querySelector('.menu-icon');
                        if (currentPlayingSentence === highlightedSentence && currentSourceNode) {
                            stopCurrentAudio();
                            if (iconSpan) iconSpan.textContent = "▶️";
                            if (actionTarget) actionTarget.title = "Play Sentence Audio";
                        } else {
                            playSentenceAudio(highlightedSentence, playAsPart);
                            if (iconSpan) iconSpan.textContent = "⏹️";
                            if (actionTarget) actionTarget.title = "Stop Sentence Audio";
                        }
                    } else { alert("Audio not ready or sentence part mismatch."); }
                    break;
                case 'edit-audio-clip':
                    if (!highlightedSentence) {
                        break;
                    }
                    let waveformIsCurrentlyVisible = false;
                    if (highlightedSentence.parentElement) {
                        const potentialContainer = highlightedSentence.parentElement.nextElementSibling;
                        if (potentialContainer && potentialContainer.classList.contains('waveform-scroll-container')) {
                            waveformIsCurrentlyVisible = true;
                        }
                    }

                    if (waveformIsCurrentlyVisible) {
                        clearExistingWaveform(highlightedSentence);
                        break;
                    } else {
                        // Waveform is not visible, so display it
                        const startTimeMsStr = highlightedSentence.dataset.startTimeMs;
                    const endTimeMsStr = highlightedSentence.dataset.endTimeMs;

                    if (!startTimeMsStr || !endTimeMsStr) {
                        console.error("Edit Clip: Time data missing for the sentence.");
                        break;
                    }
                    const startTimeMs = parseInt(startTimeMsStr, 10);
                    const endTimeMs = parseInt(endTimeMsStr, 10);

                    if (isNaN(startTimeMs) || isNaN(endTimeMs)) {
                        console.error("Edit Clip: Invalid time data for the sentence.");
                        break;
                    }
                    if (!audioBuffer) {
                        console.error("Edit Clip: Audio buffer not available for waveform generation.");
                        // Potentially alert the user or provide more feedback
                        alert("Audio buffer is not loaded. Please load the full audio first.");
                        break;
                    }
                    displayWaveform(highlightedSentence, audioBuffer, startTimeMs, endTimeMs);
                    break;
                }
            }
            hideContextualMenu();
        });
    }
    document.addEventListener('click', function(event) {
        if (contextualMenu.style.display === 'block' && !contextualMenu.contains(event.target) && !event.target.closest('.english-sentence')) {
            hideContextualMenu();
        }
        if (popup.style.display === 'block' && !popup.contains(event.target) && !event.target.closest('.english-sentence') && !(contextualMenu.style.display === 'block' && contextualMenu.contains(event.target))) {
            hideTranslationPopup();
        }
    });

    if (restoreLocationButton) {
        if (INITIAL_READING_LOCATION && INITIAL_READING_LOCATION.paragraph_index !== undefined) {
            restoreLocationButton.style.display = 'inline-block';
            restoreLocationButton.addEventListener('click', function() {
                const targetSentence = findSentenceElement(INITIAL_READING_LOCATION.paragraph_index, INITIAL_READING_LOCATION.sentence_index_in_paragraph);
                if (targetSentence) {
                    setActiveSentence(targetSentence, "initial_restore_location_auto_scroll");
                }
            });
        } else {
            restoreLocationButton.style.display = 'none';
        }
    }
    
    if (goBackButton) {
        goBackButton.addEventListener('click', function() {
            if (lastHighlightedSentenceElement) {
                setActiveSentence(lastHighlightedSentenceElement, "go_back_button");
            }
        });
    }
    if (goToTopButton) {
        goToTopButton.addEventListener('click', function() { window.scrollTo({ top: 0, behavior: 'smooth' }); });
    }
    window.addEventListener('scroll', () => {
        updateGoBackButtonVisibility();
        updateGoToTopButtonVisibility();
    });
    window.addEventListener('resize', () => {
        updateGoBackButtonVisibility();
        updateGoToTopButtonVisibility();
    });

    if (toggleAudiobookModeButton && localAudioFileInput && audioFileNameSpan && audiobookHint) {
        toggleAudiobookModeButton.addEventListener('click', function() {
            if (!initAudioContextGlobally() && !isAudiobookModeFull) return;
            isAudiobookModeFull = !isAudiobookModeFull;
            if (isAudiobookModeFull) {
                toggleAudiobookModeButton.textContent = 'Disable Audiobook Mode (Full)';
                localAudioFileInput.style.display = 'inline-block';
                audiobookHint.style.display = 'block';
                isAudiobookModeParts = false;
                if (isPartsViewActive) {
                    isPartsViewActive = false;
                    updatePartsViewModeUI();
                }
            } else {
                toggleAudiobookModeButton.textContent = 'Enable Audiobook Mode (Full Audio)';
                localAudioFileInput.style.display = 'none';
                audiobookHint.style.display = 'none';
                stopCurrentAudio();
            }
        });
        localAudioFileInput.addEventListener('change', async function(event) {
            if (!initAudioContextGlobally()) return;
            const file = event.target.files[0];
            if (file) {
                audioFileNameSpan.textContent = "Loading: " + file.name;
                stopCurrentAudio(); audioBuffer = null;
                try {
                    const arrayBuffer = await file.arrayBuffer();
                    audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
                    audioFileNameSpan.textContent = file.name;
                    if (maxSentenceEndTime > 0 && (audioBuffer.duration * 1000 < maxSentenceEndTime)) {
                        console.warn(`Audio duration (${(audioBuffer.duration).toFixed(2)}s) vs max sentence end (${(maxSentenceEndTime/1000).toFixed(2)}s).`);
                    }
                } catch (e) {
                    alert(`Error decoding audio: ${e.message}`); audioFileNameSpan.textContent = "Error loading."; audioBuffer = null;
                }
            }
        });
    }

    if (NUM_AUDIO_PARTS > 0) {
        if (switchToPartsViewButton) {
            switchToPartsViewButton.addEventListener('click', () => { isPartsViewActive = true; updatePartsViewModeUI(); });
        }
        if (switchToFullViewButton) {
            switchToFullViewButton.addEventListener('click', () => { isPartsViewActive = false; updatePartsViewModeUI(); });
        }
        const playbackSelectorDiv = document.getElementById('audio-part-selector-playback');
        const downloadSelectorDiv = document.getElementById('audio-part-selector-download');
        if (playbackSelectorDiv && downloadSelectorDiv) {
            for (let i = 0; i < NUM_AUDIO_PARTS; i++) {
                const partNumDisplay = i + 1;
                const rbP = document.createElement('input'); rbP.type = 'radio'; rbP.name = 'audio_part_playback'; rbP.value = i; rbP.id = `part_pb_${i}`;
                const lblP = document.createElement('label'); lblP.htmlFor = `part_pb_${i}`; lblP.textContent = `Part ${partNumDisplay}`;
                playbackSelectorDiv.appendChild(rbP); playbackSelectorDiv.appendChild(lblP); playbackSelectorDiv.appendChild(document.createTextNode(" "));
                const rbD = document.createElement('input'); rbD.type = 'radio'; rbD.name = 'audio_part_download'; rbD.value = i; rbD.id = `part_dl_${i}`;
                const lblD = document.createElement('label'); lblD.htmlFor = `part_dl_${i}`; lblD.textContent = `Part ${partNumDisplay}`;
                downloadSelectorDiv.appendChild(rbD); downloadSelectorDiv.appendChild(lblD); downloadSelectorDiv.appendChild(document.createTextNode(" "));
            }
        }
        if (loadSelectedAudioPartButton) {
            loadSelectedAudioPartButton.addEventListener('click', async () => {
                if (!initAudioContextGlobally()) return;
                const selInput = document.querySelector('#audio-part-selector-playback input:checked');
                if (!selInput) { alert("Please select a part to load."); return; }
                const partIndex = parseInt(selInput.value, 10);
                if(localAudioPartFileInput) localAudioPartFileInput.value = "";
                if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Loading Part ${partIndex + 1} (Server)...`;
                stopCurrentAudio(); audioBuffer = null;
                try {
                    const response = await fetch(`/article/${ARTICLE_ID}/serve_mp3_part/${partIndex}`);
                    if (!response.ok) throw new Error(`Server error fetching part: ${response.statusText}`);
                    const arrayBuffer = await response.arrayBuffer();
                    audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
                    if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Loaded Part ${partIndex + 1} (Server)`;
                    currentLoadedAudioPartIndex = partIndex;
                    isAudiobookModeParts = true; isAudiobookModeFull = false;
                } catch (e) {
                    alert(`Error loading audio part ${partIndex + 1} from server: ${e.message}`);
                    if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Error loading Part ${partIndex + 1}.`;
                    audioBuffer = null; currentLoadedAudioPartIndex = -1;
                }
            });
        }
        if (loadLocalAudioPartButton && localAudioPartFileInput) {
            loadLocalAudioPartButton.addEventListener('click', () => {
                if (!initAudioContextGlobally()) return;
                const selInput = document.querySelector('#audio-part-selector-playback input:checked');
                if (!selInput) { alert("Please select a part number using the radio buttons first."); return; }
                localAudioPartFileInput.click();
            });
            localAudioPartFileInput.addEventListener('change', async function(event) {
                if (!initAudioContextGlobally()) return;
                const file = event.target.files[0];
                if (!file) return;
                const selInput = document.querySelector('#audio-part-selector-playback input:checked');
                if (!selInput) { alert("Error: No part selected radio button. Cannot associate local file."); localAudioPartFileInput.value=""; return; }
                const partIndex = parseInt(selInput.value, 10);
                const expectedChecksum = (expectedChecksumsArray.length > partIndex && expectedChecksumsArray[partIndex]) ? expectedChecksumsArray[partIndex].trim() : "";
                if (expectedChecksumsArray.length === 0 || partIndex >= expectedChecksumsArray.length || !expectedChecksum) {
                    console.warn(`No expected checksum for Part ${partIndex + 1}. Loading local file without verification.`);
                }
                if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Verifying Part ${partIndex + 1} (Local: ${file.name.substring(0,15)}...)...`;
                stopCurrentAudio(); audioBuffer = null;
                try {
                    const fileBufferForDecode = await file.arrayBuffer();
                    const fileBufferForHash = fileBufferForDecode.slice(0);
                    if (expectedChecksum) {
                        const hashBuffer = await window.crypto.subtle.digest('SHA-256', fileBufferForHash);
                        const calculatedHexChecksum = arrayBufferToHexString(hashBuffer);
                        if (calculatedHexChecksum.toLowerCase() !== expectedChecksum.toLowerCase()) {
                            alert(`Checksum mismatch for Part ${partIndex + 1}.\nExpected: ...${expectedChecksum.slice(-10)}\nGot:      ...${calculatedHexChecksum.slice(-10)}`);
                            if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Incorrect file for Part ${partIndex + 1}`;
                            currentLoadedAudioPartIndex = -1; localAudioPartFileInput.value = ""; return;
                        }
                    }
                    audioBuffer = await audioContext.decodeAudioData(fileBufferForDecode);
                    if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Loaded Part ${partIndex + 1} (Local: ${file.name.substring(0,15)}...)`;
                    currentLoadedAudioPartIndex = partIndex;
                    isAudiobookModeParts = true; isAudiobookModeFull = false;
                } catch (e) {
                    alert(`Error processing local audio part ${partIndex + 1}: ${e.message}`);
                    if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Error loading local Part ${partIndex + 1}.`;
                    audioBuffer = null; currentLoadedAudioPartIndex = -1;
                }
                localAudioPartFileInput.value = "";
            });
        }
        if (downloadSelectedAudioPartButton) {
            downloadSelectedAudioPartButton.addEventListener('click', () => {
                const selInput = document.querySelector('#audio-part-selector-download input:checked');
                if (!selInput) { alert("Please select an audio part to download."); return; }
                const partIndex = selInput.value;
                window.open(`/article/${ARTICLE_ID}/serve_mp3_part/${partIndex}?download=true`, '_blank');
            });
        }
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
        if (isIOS && NUM_AUDIO_PARTS > 0) {
            isPartsViewActive = true;
        } else {
            isPartsViewActive = false;
        }
        updatePartsViewModeUI();
    } else {
        if (switchToPartsViewButton) switchToPartsViewButton.style.display = 'none';
        if (switchToFullViewButton) switchToFullViewButton.style.display = 'none';
        if (partsAudioViewControls) partsAudioViewControls.style.display = 'none';
        if (partsAudioDownloadDiv) partsAudioDownloadDiv.style.display = 'none';
    }

    if (INITIAL_READING_LOCATION && INITIAL_READING_LOCATION.paragraph_index !== undefined) {
        const targetSentence = findSentenceElement(INITIAL_READING_LOCATION.paragraph_index, INITIAL_READING_LOCATION.sentence_index_in_paragraph);
        if (targetSentence) {
            targetSentence.classList.add('highlighted-sentence');
            highlightedSentence = targetSentence;
            lastHighlightedSentenceElement = targetSentence;
            updateGoBackButtonVisibility(); // Update based on this initial highlight
            if (restoreLocationButton) restoreLocationButton.style.display = 'inline-block';
            console.log("JS: Initial location highlighted without scrolling:", INITIAL_READING_LOCATION);
        } else if (sentenceElementsArray.length > 0) {
            setActiveSentence(sentenceElementsArray[0], "initial_page_load_highlight_no_scroll");
            console.log("JS: Saved location invalid, first sentence highlighted without scrolling.");
        }
    } else if (sentenceElementsArray.length > 0) {
        sentenceElementsArray[0].classList.add('highlighted-sentence');
        highlightedSentence = sentenceElementsArray[0];
        lastHighlightedSentenceElement = sentenceElementsArray[0];
        updateGoBackButtonVisibility();
        console.log("JS: No initial location, first sentence highlighted without scrolling.");
    }

    updateGoBackButtonVisibility();
    updateGoToTopButtonVisibility();

    const initialGamepads = navigator.getGamepads();
    let foundInitialGamepad = false;
    if (initialGamepads && typeof initialGamepads.forEach === 'function') {
        initialGamepads.forEach(gp => {
            if (gp && !foundInitialGamepad) {
                window.dispatchEvent(new GamepadEvent("gamepadconnected", { gamepad: gp }));
                foundInitialGamepad = true;
            }
        });
    } else if (initialGamepads) {
        for (let i=0; i<initialGamepads.length; i++) {
            if (initialGamepads[i] && !foundInitialGamepad) {
                 window.dispatchEvent(new GamepadEvent("gamepadconnected", { gamepad: initialGamepads[i] }));
                 foundInitialGamepad = true;
                 break;
            }
        }
    }
    if (!foundInitialGamepad) {
        updateGamepadIconDisplay(false);
    }
});