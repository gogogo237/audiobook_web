// static/js/article_view_sentence_selection.js
// Depends on:
// - article_view_config.js (for DOM elements like toggleSentenceSelectionBtn, sentenceSelectionUIContainer, etc., and state like isSentenceSelectionUIVisible, beginningSentenceElement, etc., ARTICLE_ID, sentenceElementsArray)
// - article_view_sentences.js (for getAdjacentSentence)
// - article_view_waveform.js (for fetchSentenceDbIdByIndices - though this might be better if sentence_selection directly calls the API or if sentences.js handles it)

// State variables like isSentenceSelectionUIVisible, beginningSentenceElement, endingSentenceElement,
// beginningSentenceText, endingSentenceText, placeholderBeginning, placeholderEnding are expected
// to be defined in article_view_config.js and accessed/mutated via window object.

function initializeSentenceSelectionDisplays() {
    // Uses global: beginningSentenceDisplay, endingSentenceDisplay, placeholderBeginning, placeholderEnding (from config.js)
    if (window.beginningSentenceDisplay) window.beginningSentenceDisplay.textContent = window.placeholderBeginning;
    if (window.endingSentenceDisplay) window.endingSentenceDisplay.textContent = window.placeholderEnding;
}

function handleSetAsBeginning(sentenceElement) {
    // Uses global: beginningSentenceElement, endingSentenceElement, beginningSentenceDisplay, endingSentenceDisplay,
    //              placeholderBeginning, placeholderEnding, sentenceElementsArray (from config.js)
    if (!sentenceElement) return;

    if (window.beginningSentenceElement && window.beginningSentenceElement !== sentenceElement) {
        window.beginningSentenceElement.classList.remove('selected-beginning-sentence');
    }
    if (window.endingSentenceElement === sentenceElement) { // If it was the end, clear end
        window.endingSentenceElement.classList.remove('selected-ending-sentence');
        window.endingSentenceElement = null;
        window.endingSentenceText = "";
        if (window.endingSentenceDisplay) window.endingSentenceDisplay.textContent = window.placeholderEnding;
    }

    window.beginningSentenceElement = sentenceElement;
    window.beginningSentenceText = sentenceElement.textContent.trim();
    const overallIndex = window.sentenceElementsArray.indexOf(sentenceElement) + 1;
    const shortText = window.beginningSentenceText.split(' ').slice(0, 5).join(' ') + '...';
    if (window.beginningSentenceDisplay) window.beginningSentenceDisplay.textContent = `Sentence ${overallIndex}: ${shortText}`;
    sentenceElement.classList.add('selected-beginning-sentence');
    console.log("JS_SENT_SELECT: Beginning sentence set - Index:", overallIndex);

    // Hide contextual menu (function should be globally available from ui.js)
    if (typeof hideContextualMenu === 'function') hideContextualMenu();
}

function handleSetAsEnding(sentenceElement) {
    // Uses global: beginningSentenceElement, endingSentenceElement, beginningSentenceDisplay, endingSentenceDisplay,
    //              placeholderBeginning, placeholderEnding, sentenceElementsArray (from config.js)
    if (!sentenceElement) return;

    if (window.endingSentenceElement && window.endingSentenceElement !== sentenceElement) {
        window.endingSentenceElement.classList.remove('selected-ending-sentence');
    }
    if (window.beginningSentenceElement === sentenceElement) { // If it was the beginning, clear beginning
        window.beginningSentenceElement.classList.remove('selected-beginning-sentence');
        window.beginningSentenceElement = null;
        window.beginningSentenceText = "";
        if (window.beginningSentenceDisplay) window.beginningSentenceDisplay.textContent = window.placeholderBeginning;
    }

    window.endingSentenceElement = sentenceElement;
    window.endingSentenceText = sentenceElement.textContent.trim();
    const overallIndex = window.sentenceElementsArray.indexOf(sentenceElement) + 1;
    const shortText = window.endingSentenceText.split(' ').slice(0, 5).join(' ') + '...';
    if (window.endingSentenceDisplay) window.endingSentenceDisplay.textContent = `Sentence ${overallIndex}: ${shortText}`;
    sentenceElement.classList.add('selected-ending-sentence');
    console.log("JS_SENT_SELECT: Ending sentence set - Index:", overallIndex);

    // Hide contextual menu (function should be globally available from ui.js)
    if (typeof hideContextualMenu === 'function') hideContextualMenu();
}


function setupSentenceSelectionEventListeners() {
    console.log("DEBUG_SETUP: In setupSentenceSelectionEventListeners. Checking sentenceSelectionUIContainer (direct access):", typeof sentenceSelectionUIContainer !== 'undefined' && !!sentenceSelectionUIContainer);
    // Uses global DOM elements from config.js
    // Uses global state: isSentenceSelectionUIVisible, beginningSentenceElement, endingSentenceElement, ARTICLE_ID, sentenceElementsArray
    // Calls functions from this file or other modules (getAdjacentSentence, fetchSentenceDbIdByIndices)

    if (toggleSentenceSelectionBtn && sentenceSelectionUIContainer) {
        toggleSentenceSelectionBtn.addEventListener('click', () => {
            console.log("DEBUG_EVENT: Toggle button listener triggered");
            isSentenceSelectionUIVisible = !isSentenceSelectionUIVisible;
            if (isSentenceSelectionUIVisible) {
                sentenceSelectionUIContainer.style.display = 'flex';
                setTimeout(() => {
                    sentenceSelectionUIContainer.style.transform = 'scale(1)';
                    sentenceSelectionUIContainer.style.opacity = '1';
                    sentenceSelectionUIContainer.style.pointerEvents = 'auto';
                }, 10);
                toggleSentenceSelectionBtn.textContent = '✅';
                toggleSentenceSelectionBtn.title = 'Hide Sentence Actions Panel';
            } else {
                sentenceSelectionUIContainer.style.transform = 'scale(0.8)';
                sentenceSelectionUIContainer.style.opacity = '0';
                sentenceSelectionUIContainer.style.pointerEvents = 'none';
                setTimeout(() => {
                    sentenceSelectionUIContainer.style.display = 'none';
                }, 200);
                toggleSentenceSelectionBtn.textContent = '⚙️';
                toggleSentenceSelectionBtn.title = 'Open/Close Sentence Actions Panel';
            }
        });
    }

    console.log("DEBUG_SETUP: Checking distributeTimestampsBtn (direct access):", typeof distributeTimestampsBtn !== 'undefined' && !!distributeTimestampsBtn);
    if (distributeTimestampsBtn) {
        distributeTimestampsBtn.addEventListener('click', async () => {
            if (!window.beginningSentenceElement || !window.endingSentenceElement) {
                alert("Please select both a beginning and an ending sentence."); return;
            }
            // ... (Full implementation of distributeTimestampsBtn click listener from original file)
            // Ensure getAdjacentSentence and fetchSentenceDbIdByIndices are correctly called (e.g. window.getAdjacentSentence if moved)
            // For now, assuming the logic will be pasted here and work with global functions/variables.
            // This is a complex function, its full body needs to be included.
            // For brevity here, I'll add a placeholder and assume the full logic is correctly implemented.
             console.log("JS_SENT_SELECT: distributeTimestampsBtn clicked. Original logic needs to be here.");
            // --- Start of distributeTimestampsBtn logic from original file ---
            const segmentStartTimeMsStr = window.endingSentenceElement.dataset.startTimeMs; // Use ending sentence for the reference block
            const segmentEndTimeMsStr = window.endingSentenceElement.dataset.endTimeMs;

            if (!segmentStartTimeMsStr || !segmentEndTimeMsStr) {
                alert("The selected ending sentence does not have valid start or end timestamps for reference."); return;
            }
            const segmentStartTimeMs = parseInt(segmentStartTimeMsStr, 10);
            const segmentEndTimeMs = parseInt(segmentEndTimeMsStr, 10);

            if (isNaN(segmentStartTimeMs) || isNaN(segmentEndTimeMs) || segmentEndTimeMs <= segmentStartTimeMs) {
                alert("Ending sentence timestamps are not valid or duration is zero/negative."); return;
            }
            const totalDurationForBlock = segmentEndTimeMs - segmentStartTimeMs;

            let sentencesInBlock = [];
            let currentIterSentence = window.beginningSentenceElement;
            const maxSentences = window.sentenceElementsArray.length;
            let safetyCounter = 0;
            while (currentIterSentence) {
                sentencesInBlock.push(currentIterSentence);
                if (currentIterSentence === window.endingSentenceElement) break;
                currentIterSentence = typeof getAdjacentSentence === 'function' ? getAdjacentSentence(currentIterSentence, 'next') : null;
                safetyCounter++;
                if (!currentIterSentence || safetyCounter > maxSentences) {
                    alert("Error iterating through selected sentences."); return;
                }
            }
            if (sentencesInBlock.length === 0) { alert("No sentences found in the selected block."); return; }

            const durationPerSentence = totalDurationForBlock / sentencesInBlock.length;
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
                        if (pIndex === undefined || sIndex === undefined) { throw new Error("Missing pIndex or sIndex for DB ID fetch"); }
                        const fetchedId = typeof fetchSentenceDbIdByIndices === 'function' ? await fetchSentenceDbIdByIndices(window.ARTICLE_ID, pIndex, sIndex) : null;
                        if (!fetchedId) { throw new Error("DB ID fetch failed for one or more sentences."); }
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
                const response = await fetch(`/article/${window.ARTICLE_ID}/batch_update_timestamps`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ updates: timestampUpdatesForBackend })
                });
                const jsonData = await response.json();
                if (response.ok && jsonData.status === 'success') {
                    timestampUpdatesForBackend.forEach(item => {
                        const el = document.querySelector(`.english-sentence[data-sentence-db-id='${item.id}']`);
                        if (el) { el.dataset.startTimeMs = item.new_start_ms; el.dataset.endTimeMs = item.new_end_ms; }
                    });
                    alert(jsonData.message || `Successfully updated ${timestampUpdatesForBackend.length} sentences.`);
                } else { alert(jsonData.message || "An error occurred during batch update."); }
            } catch (error) {
                console.error("Error in distributeTimestampsBtn handler:", error); alert("An unexpected error occurred: " + error.message);
            } finally {
                distributeTimestampsBtn.disabled = false; distributeTimestampsBtn.textContent = "Distribute Ending Sentence Time";
            }
            // --- End of distributeTimestampsBtn logic ---
        });
    } else {
        console.warn("DEBUG_SETUP: distributeTimestampsBtn is null or undefined, listener not attached.");
    }

    console.log("DEBUG_SETUP: Checking executeSentenceTaskBtn (direct access):", typeof executeSentenceTaskBtn !== 'undefined' && !!executeSentenceTaskBtn);
    if (executeSentenceTaskBtn) {
        executeSentenceTaskBtn.addEventListener('click', async () => {
            if (!window.beginningSentenceElement || !window.endingSentenceElement) {
                alert("Please select both a beginning and an ending sentence."); return;
            }
            // ... (Full implementation of executeSentenceTaskBtn click listener from original file)
            // Ensure getAdjacentSentence and fetchSentenceDbIdByIndices are correctly called.
            // This is a complex function, its full body needs to be included.
            // For brevity here, I'll add a placeholder and assume the full logic is correctly implemented.
            console.log("JS_SENT_SELECT: executeSentenceTaskBtn clicked. Original logic needs to be here.");
            // --- Start of executeSentenceTaskBtn logic from original file ---
            const segmentStartTimeMs = parseInt(window.beginningSentenceElement.dataset.startTimeMs, 10); // From beginning sentence
            const segmentEndTimeMs = parseInt(window.endingSentenceElement.dataset.endTimeMs, 10); // From ending sentence

            if (isNaN(segmentStartTimeMs) || isNaN(segmentEndTimeMs)) { alert("Selected sentences are missing timestamp data."); return; }
            if (segmentStartTimeMs >= segmentEndTimeMs) { alert("Beginning sentence must come before ending sentence."); return; }
            if (!window.ARTICLE_ID) { alert("Article ID missing."); return; }

            executeSentenceTaskBtn.disabled = true;
            executeSentenceTaskBtn.textContent = "Processing...";
            try {
                const sentenceDataForBackend = [];
                let currentIterSentence = window.beginningSentenceElement;
                let foundEndingElement = false;
                const maxSentences = window.sentenceElementsArray.length;
                let iterSafetyCounter = 0;
                while (currentIterSentence) {
                    let sDbId = currentIterSentence.dataset.sentenceDbId;
                    const sentenceText = currentIterSentence.textContent.trim();
                    if (!sDbId || sDbId === "undefined" || sDbId === "null") {
                        const pIndex = currentIterSentence.dataset.paragraphIndex;
                        const sIndex = currentIterSentence.dataset.sentenceIndex;
                        if (pIndex === undefined || sIndex === undefined) { throw new Error("Missing pIndex or sIndex for DB ID fetch"); }
                        const fetchedId = typeof fetchSentenceDbIdByIndices === 'function' ? await fetchSentenceDbIdByIndices(window.ARTICLE_ID, pIndex, sIndex) : null;
                        if (!fetchedId) { throw new Error(`DB ID fetch failed for P:${pIndex},S:${sIndex}`);}
                        sDbId = fetchedId.toString();
                        currentIterSentence.dataset.sentenceDbId = sDbId;
                    }
                    sentenceDataForBackend.push({ 'id': parseInt(sDbId, 10), 'text': sentenceText });
                    if (currentIterSentence === window.endingSentenceElement) { foundEndingElement = true; break; }
                    currentIterSentence = typeof getAdjacentSentence === 'function' ? getAdjacentSentence(currentIterSentence, 'next') : null;
                    iterSafetyCounter++;
                    if (!currentIterSentence || iterSafetyCounter > maxSentences + 5) { throw new Error("Ending sentence not found or loop safety break."); }
                }
                if (!foundEndingElement) { throw new Error("Ending sentence was not reached."); }
                if (sentenceDataForBackend.length === 0) { alert("No sentences collected."); return; }

                const payload = { start_time_ms: segmentStartTimeMs, end_time_ms: segmentEndTimeMs, sentences_data: sentenceDataForBackend };
                const response = await fetch(`/article/${window.ARTICLE_ID}/execute_task`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json', }, body: JSON.stringify(payload)
                });
                const jsonData = await response.json();
                if (response.ok && jsonData.status === 'success') {
                    if (jsonData.updated_sentences && Array.isArray(jsonData.updated_sentences)) {
                        jsonData.updated_sentences.forEach(item => {
                            const el = document.querySelector(`.english-sentence[data-sentence-db-id='${item.id}']`);
                            if (el) { el.dataset.startTimeMs = item.new_start_ms; el.dataset.endTimeMs = item.new_end_ms; }
                        });
                    }
                    alert(jsonData.message || "Timestamps updated successfully.");
                } else { throw new Error(jsonData.message || `Server error: ${response.status}`); }
            } catch (error) {
                console.error('Error executing task:', error); alert(`Error: ${error.message}`);
            } finally {
                executeSentenceTaskBtn.disabled = false; executeSentenceTaskBtn.textContent = "Update Timestamps for Selection";
            }
            // --- End of executeSentenceTaskBtn logic ---
        });
    } else {
        console.warn("DEBUG_SETUP: executeSentenceTaskBtn is null or undefined, listener not attached.");
    }
}
