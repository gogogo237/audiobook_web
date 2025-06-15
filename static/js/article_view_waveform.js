// static/js/article_view_waveform.js
// Depends on:
// - article_view_config.js (for ARTICLE_ID, WAVEFORM_MS_PER_PIXEL, audioContext, highlightedSentence, isAudiobookModeFull, isAudiobookModeParts, currentLoadedAudioPartIndex, sentenceElementsArray)
// - article_view_sentences.js (for getAdjacentSentence)
// - article_view_audio.js (for playSentenceAudio)
// - article_view_ui.js (for contextualMenu DOM element - for updating menu items)

// Global state variables (ARTICLE_ID, audioContext, etc.) are expected to be defined in article_view_config.js

function clearExistingWaveform(sentenceElement) {
    if (!sentenceElement || !sentenceElement.parentElement) {
        console.error("JS_WAVEFORM: clearExistingWaveform - sentenceElement or its parent is null.");
        return;
    }
    let nextSibling = sentenceElement.parentElement.nextElementSibling;
    if (nextSibling && nextSibling.classList.contains('waveform-toolbar')) {
        nextSibling.remove();
        nextSibling = sentenceElement.parentElement.nextElementSibling;
    }
    if (nextSibling && nextSibling.classList.contains('waveform-scroll-container')) {
        nextSibling.remove();
    }
}

async function fetchSentenceDbIdByIndices(articleId, paragraphIndex, sentenceIndex) {
    // Uses global: ARTICLE_ID (but also takes it as param, good for decoupling if needed)
    const currentArticleId = articleId || window.ARTICLE_ID;
    const url = `/article/${currentArticleId}/get_sentence_id_by_indices?paragraph_index=${paragraphIndex}&sentence_index=${sentenceIndex}`;
    console.log(`JS_WAVEFORM: Fetching sentence_db_id from: ${url}`);
    try {
        const response = await fetch(url);
        if (!response.ok) {
            console.error(`JS_WAVEFORM: Failed to fetch sentence_db_id. Status: ${response.status}, Text: ${await response.text()}`);
            return null;
        }
        const data = await response.json();
        if (data && typeof data.sentence_db_id !== 'undefined') {
            console.log(`JS_WAVEFORM: Successfully fetched sentence_db_id: ${data.sentence_db_id}`);
            return data.sentence_db_id;
        } else {
            console.error("JS_WAVEFORM: Failed to fetch sentence_db_id: ID missing in response.", data);
            return null;
        }
    } catch (error) {
        console.error("JS_WAVEFORM: Network or other error fetching sentence_db_id:", error);
        return null;
    }
}

async function updateSentenceTimestampOnServer(sentenceDbId, timestampType, newTimeMs) {
    // Uses global: ARTICLE_ID, highlightedSentence, isAudiobookModeFull, audioBuffer (from config.js)
    // Calls global: displayWaveform (this file)
    const url = `/article/${window.ARTICLE_ID}/sentence/${sentenceDbId}/update_timestamp`;
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ timestamp_type: timestampType, new_time_ms: newTimeMs })
        });
        const result = await response.json();

        if (!response.ok || result.status !== 'success') {
            console.error(`JS_WAVEFORM: Failed to update timestamp for sentence ${sentenceDbId}:`, result.message);
            alert(`Failed to update timestamp: ${result.message}`);
            return false;
        }

        console.log(`JS_WAVEFORM: Timestamp updated successfully for sentence ${sentenceDbId}. Type: ${timestampType}, New Time: ${newTimeMs}ms.`);
        const sentenceElToUpdate = document.querySelector(`.english-sentence[data-sentence-db-id="${sentenceDbId}"]`);

        if (sentenceElToUpdate) {
            if (timestampType === 'start') {
                sentenceElToUpdate.dataset.startTimeMs = newTimeMs;
            } else if (timestampType === 'end') {
                sentenceElToUpdate.dataset.endTimeMs = newTimeMs;
            }

            if (window.highlightedSentence === sentenceElToUpdate && window.isAudiobookModeFull && window.audioBuffer) {
                let waveformIsVisible = false;
                if (sentenceElToUpdate.parentElement &&
                    sentenceElToUpdate.parentElement.nextElementSibling &&
                    sentenceElToUpdate.parentElement.nextElementSibling.classList.contains('waveform-scroll-container')) {
                    waveformIsVisible = true;
                }
                if (waveformIsVisible) {
                    console.log("JS_WAVEFORM: Refreshing waveform for sentence ID:", sentenceDbId, "after timestamp update.");
                    const currentStartTime = parseInt(sentenceElToUpdate.dataset.startTimeMs, 10);
                    const currentEndTime = parseInt(sentenceElToUpdate.dataset.endTimeMs, 10);
                    if (!isNaN(currentStartTime) && !isNaN(currentEndTime) && currentStartTime < currentEndTime) {
                        displayWaveform(sentenceElToUpdate, window.audioBuffer, currentStartTime, currentEndTime);
                    } else {
                        console.warn("JS_WAVEFORM: Cannot refresh waveform due to invalid new start/end times after update:", sentenceElToUpdate.dataset);
                    }
                }
            }
        }
        return true;
    } catch (error) {
        console.error('JS_WAVEFORM: Network or other error updating timestamp:', error);
        alert('Error updating timestamp: ' + error.message);
        return false;
    }
}

function displayWaveform(sentenceElement, audioBufferToDisplay, startTimeMs, endTimeMs) {
    // Uses global: audioContext, WAVEFORM_MS_PER_PIXEL, contextualMenu, highlightedSentence, ARTICLE_ID,
    //              isAudiobookModeFull, isAudiobookModeParts, currentLoadedAudioPartIndex (from config.js)
    // Calls global: clearExistingWaveform (this file), getAdjacentSentence (from sentences.js),
    //              fetchSentenceDbIdByIndices (this file), updateSentenceTimestampOnServer (this file),
    //              playSentenceAudio (from audio.js)
    if (!sentenceElement || !audioBufferToDisplay || typeof startTimeMs === 'undefined' || typeof endTimeMs === 'undefined') {
        console.warn("JS_WAVEFORM: displayWaveform - Missing required parameters.");
        return;
    }
    if (!window.audioContext) {
        console.warn("JS_WAVEFORM: displayWaveform - AudioContext not available.");
        return;
    }

    clearExistingWaveform(sentenceElement);

    const toolbar = document.createElement('div');
    toolbar.className = 'waveform-toolbar';

    const btnAlignStart = document.createElement('button');
    btnAlignStart.className = 'waveform-toolbar-button align-start-prev-end';
    btnAlignStart.innerHTML = '⏮️|';
    btnAlignStart.title = 'Align start with previous sentence\'s end';
    btnAlignStart.addEventListener('click', async () => {
        if (!window.highlightedSentence) { alert("Please select a sentence first."); return; }
        const prevSentence = typeof getAdjacentSentence === 'function' ? getAdjacentSentence(window.highlightedSentence, 'previous') : null;
        if (!prevSentence) { alert("No previous sentence found."); return; }
        const prevEndTimeMsStr = prevSentence.dataset.endTimeMs;
        if (!prevEndTimeMsStr) { alert("Previous sentence does not have an end time."); return; }
        const prevEndTimeMs = parseInt(prevEndTimeMsStr, 10);
        const currentEndTimeMs = parseInt(window.highlightedSentence.dataset.endTimeMs, 10);
        if (isNaN(prevEndTimeMs) || isNaN(currentEndTimeMs) || prevEndTimeMs >= currentEndTimeMs) {
            alert("Invalid time data or new start would be after current end."); return;
        }
        let sentenceDbId = window.highlightedSentence.dataset.sentenceDbId;
        if (!sentenceDbId) sentenceDbId = await fetchSentenceDbIdByIndices(window.ARTICLE_ID, window.highlightedSentence.dataset.paragraphIndex, window.highlightedSentence.dataset.sentenceIndex);
        if (sentenceDbId) {
            await updateSentenceTimestampOnServer(sentenceDbId, 'start', prevEndTimeMs);
        } else { alert("Failed to get sentence DB ID."); }
    });
    toolbar.appendChild(btnAlignStart);

    const btnAlignEnd = document.createElement('button');
    btnAlignEnd.className = 'waveform-toolbar-button align-end-next-start';
    btnAlignEnd.innerHTML = '|⏭️';
    btnAlignEnd.title = 'Align end with next sentence\'s start';
    btnAlignEnd.addEventListener('click', async () => {
        if (!window.highlightedSentence) { alert("Please select a sentence first."); return; }
        const nextSentence = typeof getAdjacentSentence === 'function' ? getAdjacentSentence(window.highlightedSentence, 'next') : null;
        if (!nextSentence) { alert("No next sentence found."); return; }
        const nextStartTimeMsStr = nextSentence.dataset.startTimeMs;
        if (!nextStartTimeMsStr) { alert("Next sentence does not have a start time."); return; }
        const nextStartTimeMs = parseInt(nextStartTimeMsStr, 10);
        const currentStartTimeMs = parseInt(window.highlightedSentence.dataset.startTimeMs, 10);
        if (isNaN(nextStartTimeMs) || isNaN(currentStartTimeMs) || nextStartTimeMs <= currentStartTimeMs) {
            alert("Invalid time data or new end would be before current start."); return;
        }
        let sentenceDbId = window.highlightedSentence.dataset.sentenceDbId;
        if (!sentenceDbId) sentenceDbId = await fetchSentenceDbIdByIndices(window.ARTICLE_ID, window.highlightedSentence.dataset.paragraphIndex, window.highlightedSentence.dataset.sentenceIndex);
        if (sentenceDbId) {
            await updateSentenceTimestampOnServer(sentenceDbId, 'end', nextStartTimeMs);
        } else { alert("Failed to get sentence DB ID."); }
    });
    toolbar.appendChild(btnAlignEnd);

    const btnCloseWaveform = document.createElement('button');
    btnCloseWaveform.className = 'waveform-toolbar-button close-waveform-button';
    btnCloseWaveform.innerHTML = '❌';
    btnCloseWaveform.title = 'Hide Waveform';
    btnCloseWaveform.addEventListener('click', () => {
        clearExistingWaveform(sentenceElement);
        if (window.contextualMenu && window.contextualMenu.style.display === 'block' && window.highlightedSentence === sentenceElement) {
            const editClipMenuItem = window.contextualMenu.querySelector('.contextual-menu-item[data-action="edit-audio-clip"]');
            if (editClipMenuItem) {
                const menuIcon = editClipMenuItem.querySelector('.menu-icon');
                const menuText = editClipMenuItem.querySelector('.menu-text');
                if (menuIcon) menuIcon.innerHTML = '✏️';
                if (menuText) menuText.innerHTML = 'Edit Clip';
                editClipMenuItem.title = 'Edit Clip for this sentence';
            }
        }
    });
    toolbar.appendChild(btnCloseWaveform);

    const ORIGINAL_WAVEFORM_MS_PER_PIXEL = window.WAVEFORM_MS_PER_PIXEL || 10;
    const MAX_CANVAS_WIDTH = 16384;
    let effectiveMsPerPixel = ORIGINAL_WAVEFORM_MS_PER_PIXEL;
    const segmentDurationMs = endTimeMs - startTimeMs;
    if (segmentDurationMs <= 0) { console.error("JS_WAVEFORM: displayWaveform - segmentDurationMs zero or negative."); return; }

    let finalCanvasWidth = Math.max(50, Math.ceil(segmentDurationMs / ORIGINAL_WAVEFORM_MS_PER_PIXEL));
    if (finalCanvasWidth > MAX_CANVAS_WIDTH) {
        finalCanvasWidth = MAX_CANVAS_WIDTH;
        effectiveMsPerPixel = segmentDurationMs / finalCanvasWidth;
    }

    const scrollContainer = document.createElement('div');
    scrollContainer.className = 'waveform-scroll-container';
    const canvas = document.createElement('canvas');
    canvas.className = 'waveform-canvas';
    canvas.width = finalCanvasWidth;
    canvas.style.width = finalCanvasWidth + 'px';
    canvas.height = 75;
    scrollContainer.appendChild(canvas);

    canvas.segmentStartTimeMs = startTimeMs;
    canvas.segmentEndTimeMs = endTimeMs;
    canvas.effectiveMsPerPixel = effectiveMsPerPixel;
    canvas.audioBuffer = audioBufferToDisplay;
    canvas.sentenceElement = sentenceElement;
    canvas.isSegmentFromFullAudio = window.isAudiobookModeFull; // Important for click handling context

    canvas.addEventListener('click', async function(event) {
        const clickX = event.offsetX;
        const calculatedTimeOffsetInSegmentMs = clickX * this.effectiveMsPerPixel;
        let sentenceDbId;

        if (event.ctrlKey && !event.altKey && !event.shiftKey && !event.metaKey) { // CTRL + Click = Set Start
            if (!this.isSegmentFromFullAudio) { alert("Timestamp editing only on full audio waveform."); return; }
            sentenceDbId = this.sentenceElement.dataset.sentenceDbId || await fetchSentenceDbIdByIndices(window.ARTICLE_ID, this.sentenceElement.dataset.paragraphIndex, this.sentenceElement.dataset.sentenceIndex);
            if (!sentenceDbId) { alert("Could not get sentence DB ID."); return; }
            const currentEndTimeMs = parseInt(this.sentenceElement.dataset.endTimeMs, 10);
            const newStartTimeMs = Math.round(this.segmentStartTimeMs + calculatedTimeOffsetInSegmentMs);
            if (newStartTimeMs >= 0 && newStartTimeMs < currentEndTimeMs) {
                updateSentenceTimestampOnServer(sentenceDbId, 'start', newStartTimeMs);
            } else { console.warn("JS_WAVEFORM: Invalid new start time."); }
        } else if (event.altKey && !event.ctrlKey && !event.shiftKey && !event.metaKey) { // ALT + Click = Set End
            if (!this.isSegmentFromFullAudio) { alert("Timestamp editing only on full audio waveform."); return; }
            sentenceDbId = this.sentenceElement.dataset.sentenceDbId || await fetchSentenceDbIdByIndices(window.ARTICLE_ID, this.sentenceElement.dataset.paragraphIndex, this.sentenceElement.dataset.sentenceIndex);
            if (!sentenceDbId) { alert("Could not get sentence DB ID."); return; }
            const currentStartTimeMs = parseInt(this.sentenceElement.dataset.startTimeMs, 10);
            const newEndTimeMs = Math.round(this.segmentStartTimeMs + calculatedTimeOffsetInSegmentMs);
            if (newEndTimeMs > currentStartTimeMs) {
                updateSentenceTimestampOnServer(sentenceDbId, 'end', newEndTimeMs);
            } else { console.warn("JS_WAVEFORM: Invalid new end time."); }
        } else { // Default Click = Playback
            let timeOffsetInSegmentMs = calculatedTimeOffsetInSegmentMs;
            const segmentDurationOnCanvasMs = this.segmentEndTimeMs - this.segmentStartTimeMs;
            if (timeOffsetInSegmentMs < 0) timeOffsetInSegmentMs = 0;
            if (timeOffsetInSegmentMs > segmentDurationOnCanvasMs) timeOffsetInSegmentMs = segmentDurationOnCanvasMs;
            const absolutePlayTimeMs = this.segmentStartTimeMs + timeOffsetInSegmentMs;

            this.currentMarkerX = clickX; // Store for re-draw
            drawWaveformOnCanvas(this, this.audioBuffer, this.segmentStartTimeMs, this.segmentEndTimeMs, clickX); // Redraw with marker

            if (typeof playSentenceAudio === 'function') {
                 // Determine if context is part or full based on how waveform was generated
                const isPlayingFromPartContext = !this.isSegmentFromFullAudio && window.isAudiobookModeParts && parseInt(this.sentenceElement.dataset.audioPartIndex,10) === window.currentLoadedAudioPartIndex;
                playSentenceAudio(this.sentenceElement, isPlayingFromPartContext, absolutePlayTimeMs);
            } else {
                console.warn("JS_WAVEFORM: playSentenceAudio function not found.");
            }
        }
    });

    const sentenceParentP = sentenceElement.parentElement;
    if (sentenceParentP) {
        sentenceParentP.insertAdjacentElement('afterend', scrollContainer);
        sentenceParentP.insertAdjacentElement('afterend', toolbar);
    } else { console.error('JS_WAVEFORM: displayWaveform - Sentence element has no parent.'); return; }

    drawWaveformOnCanvas(canvas, audioBufferToDisplay, startTimeMs, endTimeMs, canvas.currentMarkerX);
}

// Helper function for drawing the waveform visualization
function drawWaveformOnCanvas(canvas, audioBufferToDisplay, segmentStartTimeMs, segmentEndTimeMs, markerX = null) {
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#f0f0f0';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const startSample = Math.floor((segmentStartTimeMs / 1000) * audioBufferToDisplay.sampleRate);
    let endSample = Math.floor((segmentEndTimeMs / 1000) * audioBufferToDisplay.sampleRate);
    endSample = Math.min(endSample, audioBufferToDisplay.length);

    if (startSample >= endSample) { console.warn("JS_WAVEFORM: drawWaveformOnCanvas - startSample >= endSample."); return; }

    const channelData = audioBufferToDisplay.getChannelData(0);
    const segmentData = channelData.slice(startSample, endSample);

    if (segmentData.length === 0) { console.warn("JS_WAVEFORM: drawWaveformOnCanvas - segmentData is empty."); return; }

    const samplesPerPixel = segmentData.length / canvas.width;
    const upperEnvelopePoints = [];
    const lowerEnvelopePoints = [];

    for (let x = 0; x < canvas.width; x++) {
        const startIdx = Math.floor(x * samplesPerPixel);
        const endIdx = Math.floor((x + 1) * samplesPerPixel);
        let maxVal = 0;
        for (let i = startIdx; i < endIdx && i < segmentData.length; i++) {
            const val = Math.abs(segmentData[i]);
            if (val > maxVal) maxVal = val;
        }
         if (startIdx === endIdx && startIdx < segmentData.length) { // Handle case where samplesPerPixel < 1
             maxVal = Math.abs(segmentData[startIdx]);
        }
        const amplitude = maxVal * canvas.height / 2;
        upperEnvelopePoints.push({ x: x, y: (canvas.height / 2) - amplitude });
        lowerEnvelopePoints.push({ x: x, y: (canvas.height / 2) + amplitude });
    }
    if (canvas.width > 0 && segmentData.length > 0) { // Ensure last point reaches canvas edge
        const lastSampleIdx = segmentData.length - 1;
        const lastVal = Math.abs(segmentData[lastSampleIdx]);
        const last_amplitude = lastVal * canvas.height / 2;
        upperEnvelopePoints.push({ x: canvas.width, y: (canvas.height / 2) - last_amplitude });
        lowerEnvelopePoints.push({ x: canvas.width, y: (canvas.height / 2) + last_amplitude });
    }


    if (upperEnvelopePoints.length > 0) {
        ctx.beginPath();
        ctx.moveTo(upperEnvelopePoints[0].x, upperEnvelopePoints[0].y);
        for (let i = 1; i < upperEnvelopePoints.length; i++) {
            ctx.lineTo(upperEnvelopePoints[i].x, upperEnvelopePoints[i].y);
        }
        for (let i = lowerEnvelopePoints.length - 1; i >= 0; i--) {
            ctx.lineTo(lowerEnvelopePoints[i].x, lowerEnvelopePoints[i].y);
        }
        ctx.closePath();
        ctx.fillStyle = 'rgba(0, 123, 255, 0.3)';
        ctx.fill();
    }

    if (typeof markerX === 'number' && markerX >= 0 && markerX <= canvas.width) {
        ctx.strokeStyle = 'red';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(markerX, 0);
        ctx.lineTo(markerX, canvas.height);
        ctx.stroke();
    }
}
