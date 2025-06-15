// static/js/modules/sentence_selection.js
const SentenceSelectionModule = (function() {
    let _ARTICLE_ID = null;

    // DOM Elements
    let toggleSentenceSelectionBtn = null;
    let sentenceSelectionUIContainer = null;
    let beginningSentenceDisplay = null;
    let endingSentenceDisplay = null;
    let executeSentenceTaskBtn = null;
    let distributeTimestampsBtn = null;

    let _executeSentenceTaskBtnOriginalText = "Update Timestamps for Selection";
    let _distributeTimestampsBtnOriginalText = "Distribute Ending Sentence Time";


    // State
    let isSentenceSelectionUIVisible = false;
    let beginningSentenceText = ""; // Not really used beyond initial thoughts, element content is key
    let endingSentenceText = "";   // Not really used
    let beginningSentenceElement = null;
    let endingSentenceElement = null;
    const placeholderBeginning = "No beginning sentence selected.";
    const placeholderEnding = "No ending sentence selected.";

    // Providers/Callbacks from other modules (to be set in init)
    let _sentenceElementsArrayProviderFunc = null; // () => [...]
    let _getAdjacentSentenceFunc = null;          // (currentSentence, direction) => nextSentence
    let _fetchSentenceDbIdByIndicesFunc = null;   // async (articleId, pIndex, sIndex) => dbId
    let _getAudioBufferProviderFunc = null;       // () => AudioBuffer (for validation in execute task)
    let _isAudiobookModeFullProviderFunc = null;  // () => boolean (for validation)


    function initializeSentenceSelectionDisplays() {
        if (beginningSentenceDisplay) beginningSentenceDisplay.textContent = placeholderBeginning;
        if (endingSentenceDisplay) endingSentenceDisplay.textContent = placeholderEnding;
    }

    function toggleUIVisibility() {
        isSentenceSelectionUIVisible = !isSentenceSelectionUIVisible;
        if (isSentenceSelectionUIVisible) {
            sentenceSelectionUIContainer.style.display = 'flex';
            setTimeout(() => { // Allow display change to be processed before transition
                sentenceSelectionUIContainer.style.transform = 'scale(1)';
                sentenceSelectionUIContainer.style.opacity = '1';
                sentenceSelectionUIContainer.style.pointerEvents = 'auto';
            }, 10);
            toggleSentenceSelectionBtn.textContent = '✅'; // Or some other "active" icon/text
            toggleSentenceSelectionBtn.title = 'Hide Sentence Actions Panel';
        } else {
            sentenceSelectionUIContainer.style.transform = 'scale(0.8)';
            sentenceSelectionUIContainer.style.opacity = '0';
            sentenceSelectionUIContainer.style.pointerEvents = 'none';
            setTimeout(() => {
                sentenceSelectionUIContainer.style.display = 'none';
            }, 200); // Match CSS transition duration
            toggleSentenceSelectionBtn.textContent = '⚙️';
            toggleSentenceSelectionBtn.title = 'Open/Close Sentence Actions Panel';
        }
    }

    function _updateSentenceDisplay(displayElement, sentenceElement, type) {
        const sentenceElementsArray = _sentenceElementsArrayProviderFunc ? _sentenceElementsArrayProviderFunc() : [];
        if (!displayElement || !sentenceElement || !sentenceElementsArray) return;

        const overallIndex = sentenceElementsArray.indexOf(sentenceElement) + 1;
        const shortText = sentenceElement.textContent.trim().split(' ').slice(0, 5).join(' ') + '...';
        displayElement.textContent = `Sentence ${overallIndex}: ${shortText}`;

        // Remove old styling from previous selection of this type
        if (type === 'beginning' && beginningSentenceElement && beginningSentenceElement !== sentenceElement) {
            beginningSentenceElement.classList.remove('selected-beginning-sentence');
        } else if (type === 'ending' && endingSentenceElement && endingSentenceElement !== sentenceElement) {
            endingSentenceElement.classList.remove('selected-ending-sentence');
        }

        sentenceElement.classList.add(type === 'beginning' ? 'selected-beginning-sentence' : 'selected-ending-sentence');
    }


    function setBeginningSentence(sentenceElement) {
        if (!sentenceElement) return;

        // If this sentence was the ending sentence, clear that first
        if (endingSentenceElement === sentenceElement) {
            endingSentenceElement.classList.remove('selected-ending-sentence');
            endingSentenceElement = null;
            if (endingSentenceDisplay) endingSentenceDisplay.textContent = placeholderEnding;
        }

        _updateSentenceDisplay(beginningSentenceDisplay, sentenceElement, 'beginning');
        beginningSentenceElement = sentenceElement;
        console.log("Beginning sentence set. Element:", beginningSentenceElement);
    }

    function setEndingSentence(sentenceElement) {
        if (!sentenceElement) return;

        // If this sentence was the beginning sentence, clear that first
        if (beginningSentenceElement === sentenceElement) {
            beginningSentenceElement.classList.remove('selected-beginning-sentence');
            beginningSentenceElement = null;
            if (beginningSentenceDisplay) beginningSentenceDisplay.textContent = placeholderBeginning;
        }

        _updateSentenceDisplay(endingSentenceDisplay, sentenceElement, 'ending');
        endingSentenceElement = sentenceElement;
        console.log("Ending sentence set. Element:", endingSentenceElement);
    }

    async function _handleDistributeTimestamps() {
        if (!beginningSentenceElement || !endingSentenceElement) {
            alert("Please select both a beginning and an ending sentence.");
            return;
        }

        const segmentStartTimeMsStr = endingSentenceElement.dataset.startTimeMs; // Note: Uses ENDING sentence's times
        const segmentEndTimeMsStr = endingSentenceElement.dataset.endTimeMs;

        if (!segmentStartTimeMsStr || !segmentEndTimeMsStr) {
            alert("The selected ending sentence does not have valid start or end timestamps.");
            return;
        }
        const segmentStartTimeMs = parseInt(segmentStartTimeMsStr, 10);
        const segmentEndTimeMs = parseInt(segmentEndTimeMsStr, 10);

        if (isNaN(segmentStartTimeMs) || isNaN(segmentEndTimeMs)) {
            alert("Ending sentence timestamps are not valid numbers."); return;
        }
        if (segmentStartTimeMs >= segmentEndTimeMs) { // Check if end time is not after start time
             alert("Ending sentence's start time must be before its end time."); return;
        }

        const totalDurationForBlock = segmentEndTimeMs - segmentStartTimeMs;
        if (totalDurationForBlock <= 0) {
            alert("Ending sentence's duration is zero or negative. Cannot distribute time."); return;
        }

        let sentencesInBlock = [];
        let currentIterSentence = beginningSentenceElement;
        let safetyCounter = 0;
        const sentenceElementsArray = _sentenceElementsArrayProviderFunc ? _sentenceElementsArrayProviderFunc() : [];
        const maxSentences = sentenceElementsArray.length;

        while (currentIterSentence) {
            sentencesInBlock.push(currentIterSentence);
            if (currentIterSentence === endingSentenceElement) break;
            if (!_getAdjacentSentenceFunc) {
                alert("Error: GetAdjacentSentence function not available."); return;
            }
            currentIterSentence = _getAdjacentSentenceFunc(currentIterSentence, 'next');
            safetyCounter++;
            if (!currentIterSentence || safetyCounter > maxSentences) {
                alert("Error iterating through selected sentences. Ending sentence may not be reachable or an infinite loop was detected."); return;
            }
        }

        if (sentencesInBlock.length === 0) {
            alert("No sentences found in the selected block."); return;
        }
        if (sentencesInBlock.indexOf(beginningSentenceElement) > sentencesInBlock.indexOf(endingSentenceElement)) {
            alert("Beginning sentence must appear before the ending sentence in the article text."); return;
        }


        const numberOfSentencesInBlock = sentencesInBlock.length;
        const durationPerSentence = totalDurationForBlock / numberOfSentencesInBlock;
        let currentProcessingStartTimeMs = segmentStartTimeMs;
        let timestampUpdatesForBackend = [];

        distributeTimestampsBtn.disabled = true;
        distributeTimestampsBtn.textContent = "Processing...";

        try {
            for (const sentenceElement of sentencesInBlock) {
                let sDbId = sentenceElement.dataset.sentenceDbId;
                if (!sDbId || sDbId === "undefined" || sDbId === "null") {
                    const pIndex = sentenceElement.dataset.paragraphIndex;
                    const sIndex = sentenceElement.dataset.sentenceIndex;
                    if (!_fetchSentenceDbIdByIndicesFunc) {
                         alert("Error: Required function to fetch DB IDs is not available."); throw new Error("fetchSentenceDbIdByIndicesFunc missing");
                    }
                    if (pIndex === undefined || sIndex === undefined) {
                        alert(`Error: Missing paragraph/sentence index for: '${sentenceElement.textContent.substring(0,30)}...'.`); throw new Error("Missing pIndex/sIndex");
                    }
                    const fetchedId = await _fetchSentenceDbIdByIndicesFunc(_ARTICLE_ID, pIndex, sIndex);
                    if (!fetchedId) {
                        alert(`Error fetching DB ID for: '${sentenceElement.textContent.substring(0,30)}...'.`); throw new Error("DB ID fetch failed");
                    }
                    sDbId = fetchedId.toString();
                    sentenceElement.dataset.sentenceDbId = sDbId;
                }

                const newSentenceStartMs = Math.round(currentProcessingStartTimeMs);
                const newSentenceEndMs = Math.round(currentProcessingStartTimeMs + durationPerSentence);
                timestampUpdatesForBackend.push({ 'id': parseInt(sDbId, 10), 'new_start_ms': newSentenceStartMs, 'new_end_ms': newSentenceEndMs });
                currentProcessingStartTimeMs = newSentenceEndMs;
            }

            if (timestampUpdatesForBackend.length > 0) {
                timestampUpdatesForBackend[timestampUpdatesForBackend.length - 1].new_end_ms = segmentEndTimeMs; // Ensure last one matches exactly
            }

            const response = await fetch(`/article/${_ARTICLE_ID}/batch_update_timestamps`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ updates: timestampUpdatesForBackend })
            });
            const jsonData = await response.json();

            if (response.ok && jsonData.status === 'success') {
                for (const updatedItem of timestampUpdatesForBackend) {
                    const elToUpdate = document.querySelector(`.english-sentence[data-sentence-db-id='${updatedItem.id}']`);
                    if (elToUpdate) {
                        elToUpdate.dataset.startTimeMs = updatedItem.new_start_ms;
                        elToUpdate.dataset.endTimeMs = updatedItem.new_end_ms;
                    }
                }
                alert(jsonData.message || `Successfully updated ${timestampUpdatesForBackend.length} sentences.`);
            } else {
                alert(jsonData.message || "An error occurred on the server during batch update.");
            }
        } catch (error) {
            console.error("Error in distributeTimestampsBtn handler:", error);
            alert("An unexpected error occurred: " + error.message);
        } finally {
            distributeTimestampsBtn.disabled = false;
            distributeTimestampsBtn.textContent = _distributeTimestampsBtnOriginalText;
        }
    }

    async function _handleExecuteSentenceTask() {
        if (!beginningSentenceElement || !endingSentenceElement) {
            alert("Please select both a beginning and an ending sentence."); return;
        }

        const segmentStartTimeMs = parseInt(beginningSentenceElement.dataset.startTimeMs, 10);
        const segmentEndTimeMs = parseInt(endingSentenceElement.dataset.endTimeMs, 10);

        if (isNaN(segmentStartTimeMs) || isNaN(segmentEndTimeMs)) {
            alert("Selected sentences are missing timestamp data."); return;
        }
        if (segmentStartTimeMs >= segmentEndTimeMs) {
            alert("Beginning sentence must come before the ending sentence (based on timestamps)."); return;
        }

        const audioBuffer = _getAudioBufferProviderFunc ? _getAudioBufferProviderFunc() : null;
        const isAudiobookModeFull = _isAudiobookModeFullProviderFunc ? _isAudiobookModeFullProviderFunc() : false;
        if (!audioBuffer && isAudiobookModeFull) {
            // alert("Full audio track is not loaded. Please load audio in 'Full Audio' mode if using its timestamps.");
            // This might not be a fatal error if backend extracts audio, but good to warn.
        }
        if (!_ARTICLE_ID) {
            alert("Article ID is missing. Cannot proceed."); return;
        }

        executeSentenceTaskBtn.disabled = true;
        executeSentenceTaskBtn.textContent = "Processing...";

        try {
            const sentenceDataForBackend = [];
            let currentIterSentence = beginningSentenceElement;
            let foundEndingElement = false;
            let iterSafetyCounter = 0;
            const sentenceElementsArray = _sentenceElementsArrayProviderFunc ? _sentenceElementsArrayProviderFunc() : [];
            const maxPossibleSentences = sentenceElementsArray.length;

            while (currentIterSentence) {
                let sDbId = currentIterSentence.dataset.sentenceDbId;
                const sentenceText = currentIterSentence.textContent.trim();
                if (!sDbId || sDbId === "undefined" || sDbId === "null") {
                    const pIndex = currentIterSentence.dataset.paragraphIndex;
                    const sIndex = currentIterSentence.dataset.sentenceIndex;
                    if (!_fetchSentenceDbIdByIndicesFunc) {
                         alert("Error: DB ID fetch function unavailable."); throw new Error("fetch ID func missing");
                    }
                    sDbId = await _fetchSentenceDbIdByIndicesFunc(_ARTICLE_ID, pIndex, sIndex);
                    if (!sDbId) {
                        alert(`Error fetching DB ID for sentence: [P:${pIndex},S:${sIndex}] "${sentenceText.substring(0,30)}...".`); throw new Error("DB ID fetch failed");
                    }
                    currentIterSentence.dataset.sentenceDbId = sDbId;
                }
                sentenceDataForBackend.push({ 'id': parseInt(sDbId, 10), 'text': sentenceText });
                if (currentIterSentence === endingSentenceElement) {
                    foundEndingElement = true; break;
                }
                if (!_getAdjacentSentenceFunc) {
                     alert("Error: GetAdjacentSentence function unavailable."); throw new Error("Adjacent func missing");
                }
                currentIterSentence = _getAdjacentSentenceFunc(currentIterSentence, 'next');
                iterSafetyCounter++;
                if (iterSafetyCounter > maxPossibleSentences + 5) {
                    alert("Error collecting sentences: safety limit exceeded."); throw new Error("Safety limit exceeded");
                }
            }

            if (!foundEndingElement) {
                alert("Ending sentence not found by iterating from beginning."); throw new Error("Ending sentence not found");
            }
            if (sentenceDataForBackend.length === 0) {
                alert("No sentences collected for processing."); throw new Error("No sentences collected");
            }
             if (sentenceElementsArray.indexOf(beginningSentenceElement) > sentenceElementsArray.indexOf(endingSentenceElement)) {
                alert("Beginning sentence must appear before the ending sentence in the article text."); throw new Error("Order invalid");
            }


            const payload = {
                start_time_ms: segmentStartTimeMs,
                end_time_ms: segmentEndTimeMs,
                sentences_data: sentenceDataForBackend
            };
            const response = await fetch(`/article/${_ARTICLE_ID}/execute_task`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const jsonData = await response.json();

            if (response.ok && jsonData.status === 'success') {
                if (jsonData.updated_sentences && Array.isArray(jsonData.updated_sentences)) {
                    jsonData.updated_sentences.forEach(updatedItem => {
                        const elToUpdate = document.querySelector(`.english-sentence[data-sentence-db-id='${updatedItem.id}']`);
                        if (elToUpdate) {
                            elToUpdate.dataset.startTimeMs = updatedItem.new_start_ms;
                            elToUpdate.dataset.endTimeMs = updatedItem.new_end_ms;
                        }
                    });
                }
                alert(jsonData.message || "Timestamps updated successfully.");
            } else {
                throw new Error(jsonData.message || `Server error: ${response.status}`);
            }
        } catch (error) {
            console.error('Error executing task:', error);
            alert(`Error executing task: ${error.message || "An unknown error occurred."}`);
        } finally {
            executeSentenceTaskBtn.disabled = false;
            executeSentenceTaskBtn.textContent = _executeSentenceTaskBtnOriginalText;
        }
    }


    function init(config) {
        _ARTICLE_ID = config.articleId;

        // DOM Elements
        toggleSentenceSelectionBtn = config.elements.toggleSentenceSelectionBtn;
        sentenceSelectionUIContainer = config.elements.sentenceSelectionUIContainer;
        beginningSentenceDisplay = config.elements.beginningSentenceDisplay;
        endingSentenceDisplay = config.elements.endingSentenceDisplay;
        executeSentenceTaskBtn = config.elements.executeSentenceTaskBtn;
        distributeTimestampsBtn = config.elements.distributeTimestampsBtn;

        // Providers/Callbacks
        _sentenceElementsArrayProviderFunc = config.providers.getSentenceElementsArray;
        _getAdjacentSentenceFunc = config.providers.getAdjacentSentence;
        _fetchSentenceDbIdByIndicesFunc = config.callbacks.fetchSentenceDbIdByIndices; // This might come from audio_playback or init
        _getAudioBufferProviderFunc = config.providers.getAudioBuffer;
        _isAudiobookModeFullProviderFunc = config.providers.isAudiobookModeFull;


        if (toggleSentenceSelectionBtn && sentenceSelectionUIContainer) {
            toggleSentenceSelectionBtn.addEventListener('click', toggleUIVisibility);
        }

        if (executeSentenceTaskBtn) {
            _executeSentenceTaskBtnOriginalText = executeSentenceTaskBtn.textContent; // Store original text
            executeSentenceTaskBtn.addEventListener('click', _handleExecuteSentenceTask);
        }
        if (distributeTimestampsBtn) {
            _distributeTimestampsBtnOriginalText = distributeTimestampsBtn.textContent; // Store original text
            distributeTimestampsBtn.addEventListener('click', _handleDistributeTimestamps);
        }

        initializeSentenceSelectionDisplays(); // Initial UI state
    }

    return {
        init: init,
        initializeSentenceSelectionDisplays: initializeSentenceSelectionDisplays, // For init call
        setBeginningSentence: setBeginningSentence,
        setEndingSentence: setEndingSentence,
        isUIVisible: () => isSentenceSelectionUIVisible // Provider function
    };
})();
