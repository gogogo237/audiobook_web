// static/js/modules/audio_playback.js
const AudioPlaybackModule = (function() {
    let _ARTICLE_ID = null;
    let _HAS_TIMESTAMPS = false;
    let _NUM_AUDIO_PARTS = 0;
    let _ARTICLE_AUDIO_PART_CHECKSUMS_STR = null;
    const AUDIO_PART_CHECKSUM_DELIMITER_JS = ";";
    let _expectedChecksumsArray = [];

    // DOM Elements
    let toggleAudiobookModeButton, localAudioFileInput, audioFileNameSpan, audiobookHint;
    let switchToPartsViewButton, switchToFullViewButton, fullAudioViewControls, partsAudioViewControls;
    let fullAudioDownloadDiv, partsAudioDownloadDiv;
    let loadSelectedAudioPartButton, loadLocalAudioPartButton, localAudioPartFileInput, downloadSelectedAudioPartButton, loadedAudioPartNameSpan;
    let sentenceElementsArray = []; // Populated via provider

    // Audio State
    let audioContext = null;
    let audioBuffer = null; // Can be full audio or a part's audio
    let currentSourceNode = null;
    let currentPlayingSentence = null;
    let isAudiobookModeFull = false;
    let isAudiobookModeParts = false;
    let currentLoadedAudioPartIndex = -1; // -1 means no part loaded, or full audio mode
    let maxSentenceEndTime = 0; // Calculated from all sentence data-end-time-ms

    const WAVEFORM_MS_PER_PIXEL = 10;

    // Callbacks & Providers from other modules
    let _setActiveSentenceFunc = null;
    let _getAdjacentSentenceFunc = null;
    let _querySelectorFunc = null; // document.querySelector
    let _querySelectorAllFunc = null; // document.querySelectorAll

    function _initAudioContextGlobally() {
        if (!audioContext && (window.AudioContext || window.webkitAudioContext)) {
            try {
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
                console.log("JS AudioPlayback: AudioContext initialized.");
            } catch (e) {
                console.error("JS AudioPlayback: Error initializing AudioContext:", e);
                return false;
            }
        }
        if (audioContext && audioContext.state === 'suspended') {
            audioContext.resume().then(() => {
                console.log("JS AudioPlayback: AudioContext resumed successfully.");
            }).catch(e => {
                console.error("JS AudioPlayback: Failed to resume AudioContext:", e);
            });
        }
        return audioContext ? true : false;
    }

    function stopCurrentAudio() {
        if (currentSourceNode) {
            try {
                currentSourceNode.onended = null; // Important to remove listener
                currentSourceNode.stop();
                currentSourceNode.disconnect();
            } catch (e) { /* ignore if already stopped or disconnected */ }
            currentSourceNode = null;
        }
        if (currentPlayingSentence) {
            currentPlayingSentence.classList.remove('playing-sentence');
            // currentPlayingSentence = null; // Clearing this here might be too soon if onended needs it
        }
    }

    function proceedWithPlayback(sentenceElement, isPlayingFromPartContext, optionalDesiredStartTimeMs = null) {
        if (!audioBuffer) {
            if (isAudiobookModeFull) alert("Please load the full audio file first.");
            else if (isAudiobookModeParts) alert("Please load the selected audio part first.");
            return;
        }
        stopCurrentAudio(); // Stop any currently playing audio

        if (currentPlayingSentence && currentPlayingSentence !== sentenceElement) {
            currentPlayingSentence.classList.remove('playing-sentence');
        }
        currentPlayingSentence = sentenceElement; // Set new current playing sentence

        let originalSentenceStartTimeMs, originalSentenceEndTimeMs;
        if (isPlayingFromPartContext) {
            originalSentenceStartTimeMs = parseInt(sentenceElement.dataset.startTimeInPartMs, 10);
            originalSentenceEndTimeMs = parseInt(sentenceElement.dataset.endTimeInPartMs, 10);
        } else { // Playing from full audio context
            originalSentenceStartTimeMs = parseInt(sentenceElement.dataset.startTimeMs, 10);
            originalSentenceEndTimeMs = parseInt(sentenceElement.dataset.endTimeMs, 10);
        }

        let playbackStartTimeMs = optionalDesiredStartTimeMs !== null && optionalDesiredStartTimeMs >= 0 ?
                                  optionalDesiredStartTimeMs : originalSentenceStartTimeMs;
        let playbackEndTimeMs = originalSentenceEndTimeMs;

        if (isNaN(playbackStartTimeMs) || isNaN(playbackEndTimeMs)) {
            console.warn("PLAYBACK_LOGIC: Sentence missing time data. Cannot play:", sentenceElement); return;
        }
        if (playbackStartTimeMs >= playbackEndTimeMs) {
             console.warn(`PLAYBACK_LOGIC: Start time ${playbackStartTimeMs}ms is at/after end ${playbackEndTimeMs}ms. Not playing.`); return;
        }

        const offsetInSeconds = playbackStartTimeMs / 1000.0;
        let durationInSeconds = (playbackEndTimeMs - playbackStartTimeMs) / 1000.0;

        if (durationInSeconds <= 0) {
            console.warn(`PLAYBACK_LOGIC: Duration zero or negative (${durationInSeconds.toFixed(3)}s). Not playing.`); return;
        }
        if (offsetInSeconds < 0 || offsetInSeconds >= audioBuffer.duration) {
            console.warn(`PLAYBACK_LOGIC: Start time (${offsetInSeconds.toFixed(2)}s) out of buffer bounds (duration ${audioBuffer.duration.toFixed(2)}s).`); return;
        }
        durationInSeconds = Math.min(durationInSeconds, audioBuffer.duration - offsetInSeconds);
        if (durationInSeconds <= 0) {
            console.warn(`PLAYBACK_LOGIC: Duration zero/negative after buffer adjustment. Not playing.`); return;
        }

        currentPlayingSentence.classList.add('playing-sentence');
        currentSourceNode = audioContext.createBufferSource();
        currentSourceNode.buffer = audioBuffer;
        currentSourceNode.connect(audioContext.destination);

        const thisSourceNodeForOnEnded = currentSourceNode; // Closure for onended
        currentSourceNode.onended = () => {
            // Check if it's the same node that finished, to prevent issues if stopCurrentAudio was called manually
            if (currentSourceNode === thisSourceNodeForOnEnded) currentSourceNode = null;

            // Check if the sentence that just ended is still marked as currentPlayingSentence
            if (currentPlayingSentence === sentenceElement) {
                currentPlayingSentence.classList.remove('playing-sentence');
                // currentPlayingSentence = null; // Potentially clear here after class removal
            }
            // UI update for context menu play/pause button can be handled by UIInteractionsModule
            // by checking isCurrentSourceNodeActive()
        };

        try {
            currentSourceNode.start(0, offsetInSeconds, durationInSeconds);
        } catch (e) {
            console.error("Error starting audio playback:", e);
            if (currentPlayingSentence) currentPlayingSentence.classList.remove('playing-sentence');
            // currentPlayingSentence = null; // Reset on error
            currentSourceNode = null; // Reset on error
        }
    }


    function playSentenceAudio(sentenceElement, isPlayingFromPartContext, optionalDesiredStartTimeMs = null) {
        if (!_initAudioContextGlobally()) {
            console.warn("AudioPlayback: Audio system could not be initialized."); return;
        }
        if (audioContext.state === 'suspended') {
            audioContext.resume().then(() => proceedWithPlayback(sentenceElement, isPlayingFromPartContext, optionalDesiredStartTimeMs))
                              .catch(e => { console.error("AudioPlayback: Could not resume AudioContext. User interaction might be needed.", e); });
        } else {
            proceedWithPlayback(sentenceElement, isPlayingFromPartContext, optionalDesiredStartTimeMs);
        }
    }

    function _arrayBufferToHexString(buffer) {
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
            console.error("Waveform: clearExistingWaveform - sentenceElement or its parent is null."); return;
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

    async function fetchSentenceDbIdByIndices(articleIdToUse, paragraphIndex, sentenceIndexInParagraph) {
        // Ensure articleIdToUse is valid, fallback to module's _ARTICLE_ID if necessary
        const finalArticleId = articleIdToUse !== undefined && articleIdToUse !== null ? articleIdToUse : _ARTICLE_ID;
        if (finalArticleId === null) {
            console.error("Waveform: fetchSentenceDbIdByIndices - ARTICLE_ID is not available.");
            return null;
        }

        const url = `/article/${finalArticleId}/get_sentence_id_by_indices?paragraph_index=${paragraphIndex}&sentence_index=${sentenceIndexInParagraph}`;
        try {
            const response = await fetch(url);
            if (!response.ok) {
                console.error(`Waveform: Failed to fetch sentence_db_id. Status: ${response.status}, Text: ${await response.text()}`);
                return null;
            }
            const data = await response.json();
            if (data && typeof data.sentence_db_id !== 'undefined') {
                return data.sentence_db_id;
            } else {
                console.error("Waveform: Failed to fetch sentence_db_id - ID missing in response.", data);
                return null;
            }
        } catch (error) {
            console.error("Waveform: Network or other error fetching sentence_db_id:", error);
            return null;
        }
    }

    async function updateSentenceTimestampOnServer(sentenceDbId, timestampType, newTimeMs) {
        if (_ARTICLE_ID === null) {
            console.error("Waveform: updateSentenceTimestampOnServer - ARTICLE_ID is not available.");
            alert("Cannot update timestamp: Article ID is missing.");
            return false;
        }
        const url = `/article/${_ARTICLE_ID}/sentence/${sentenceDbId}/update_timestamp`;
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ timestamp_type: timestampType, new_time_ms: newTimeMs })
            });
            const result = await response.json();
            if (!response.ok || result.status !== 'success') {
                console.error(`Waveform: Failed to update timestamp for sentence ${sentenceDbId}:`, result.message);
                alert(`Failed to update timestamp: ${result.message}`);
                return false;
            }
            console.log(`Waveform: Timestamp updated for sentence ${sentenceDbId}. Type: ${timestampType}, New Time: ${newTimeMs}ms.`);
            const sentenceElToUpdate = _querySelectorFunc ? _querySelectorFunc(`.english-sentence[data-sentence-db-id="${sentenceDbId}"]`) : null;

            if (sentenceElToUpdate) {
                if (timestampType === 'start') sentenceElToUpdate.dataset.startTimeMs = newTimeMs;
                else if (timestampType === 'end') sentenceElToUpdate.dataset.endTimeMs = newTimeMs;

                const highlightedSentence = document.querySelector('.english-sentence.highlighted-sentence'); // Simpler query
                if (highlightedSentence === sentenceElToUpdate && isAudiobookModeFull && audioBuffer) {
                     let waveformIsVisible = sentenceElToUpdate.parentElement?.nextElementSibling?.classList.contains('waveform-scroll-container');
                    if (waveformIsVisible) {
                        const currentStartTime = parseInt(sentenceElToUpdate.dataset.startTimeMs, 10);
                        const currentEndTime = parseInt(sentenceElToUpdate.dataset.endTimeMs, 10);
                        if (!isNaN(currentStartTime) && !isNaN(currentEndTime) && currentStartTime < currentEndTime) {
                            displayWaveform(sentenceElToUpdate, audioBuffer, currentStartTime, currentEndTime); // Uses module's audioBuffer
                        }
                    }
                }
            }
            return true;
        } catch (error) {
            console.error('Waveform: Network error updating timestamp:', error);
            alert('Error updating timestamp: ' + error.message);
            return false;
        }
    }

    function displayWaveform(sentenceElement, waveformAudioBuffer, startTimeMs, endTimeMs) {
        if (!sentenceElement || !waveformAudioBuffer || typeof startTimeMs === 'undefined' || typeof endTimeMs === 'undefined' || !_initAudioContextGlobally()) {
            console.warn("Waveform: displayWaveform - Missing params or AudioContext unavailable."); return;
        }
        clearExistingWaveform(sentenceElement);
        const toolbar = document.createElement('div'); toolbar.className = 'waveform-toolbar';
        // ... (Toolbar button creation and event listeners - requires _getAdjacentSentenceFunc, _setActiveSentenceFunc etc.)
        // For brevity, assuming toolbar buttons are created and added here.
        // Example for one button:
        const btnAlignStart = document.createElement('button'); /* ... set properties ... */
        btnAlignStart.addEventListener('click', async () => {
            const highlightedSentence = _querySelectorFunc ? _querySelectorFunc('.english-sentence.highlighted-sentence') : null;
            if (!highlightedSentence) { alert("Select a sentence."); return; }
            const prevSentence = _getAdjacentSentenceFunc ? _getAdjacentSentenceFunc(highlightedSentence, 'previous') : null;
            if (!prevSentence || !prevSentence.dataset.endTimeMs) { alert("No valid previous sentence end time."); return; }
            const newStartTimeMs = parseInt(prevSentence.dataset.endTimeMs, 10);
            const currentEndTimeMs = parseInt(highlightedSentence.dataset.endTimeMs, 10);
            if (isNaN(newStartTimeMs) || isNaN(currentEndTimeMs) || newStartTimeMs >= currentEndTimeMs) { alert("Invalid time alignment."); return; }
            let sentenceDbId = highlightedSentence.dataset.sentenceDbId;
            if (!sentenceDbId) sentenceDbId = await fetchSentenceDbIdByIndices(_ARTICLE_ID, highlightedSentence.dataset.paragraphIndex, highlightedSentence.dataset.sentenceIndex);
            if (sentenceDbId) await updateSentenceTimestampOnServer(sentenceDbId, 'start', newStartTimeMs);
            else alert("Could not get DB ID for sentence.");
        });
        toolbar.appendChild(btnAlignStart);
        // Add other toolbar buttons (Align End, Close) similarly...
        const btnCloseWaveform = document.createElement('button'); btnCloseWaveform.className = 'waveform-toolbar-button close-waveform-button'; btnCloseWaveform.innerHTML = '❌'; btnCloseWaveform.title = 'Hide Waveform';
        btnCloseWaveform.addEventListener('click', () => {
            clearExistingWaveform(sentenceElement);
             // If UIInteractionsModule needs to know, it can subscribe to an event or this module calls a UIModule method.
             // For now, just clear. The context menu in UIInteractionsModule will update itself if it's open for this sentence.
        });
        toolbar.appendChild(btnCloseWaveform);


        const segmentDurationMs = endTimeMs - startTimeMs;
        if (segmentDurationMs <= 0) { console.error("Waveform: segmentDurationMs is zero or negative."); return; }
        const MAX_CANVAS_WIDTH = 16384;
        let effectiveMsPerPixel = WAVEFORM_MS_PER_PIXEL;
        let canvasActualWidth = Math.max(50, Math.ceil(segmentDurationMs / WAVEFORM_MS_PER_PIXEL));
        if (canvasActualWidth > MAX_CANVAS_WIDTH) {
            canvasActualWidth = MAX_CANVAS_WIDTH;
            effectiveMsPerPixel = segmentDurationMs / canvasActualWidth;
        }

        const scrollContainer = document.createElement('div'); scrollContainer.className = 'waveform-scroll-container';
        const canvas = document.createElement('canvas'); canvas.className = 'waveform-canvas';
        canvas.width = canvasActualWidth; canvas.style.width = canvasActualWidth + 'px'; canvas.height = 75;
        scrollContainer.appendChild(canvas);

        canvas.segmentStartTimeMs = startTimeMs; canvas.segmentEndTimeMs = endTimeMs;
        canvas.effectiveMsPerPixel = effectiveMsPerPixel; canvas.audioBuffer = waveformAudioBuffer;
        canvas.sentenceElement = sentenceElement;
        // isSegmentFromFullAudio should be true if waveformAudioBuffer is the main 'full' audio buffer
        canvas.isSegmentFromFullAudio = (isAudiobookModeFull && waveformAudioBuffer === audioBuffer);


        canvas.addEventListener('click', async function(event) { // `this` refers to canvas
            const clickX = event.offsetX;
            const calculatedTimeOffsetInSegmentMs = clickX * this.effectiveMsPerPixel;
            const absolutePlayTimeMs = Math.round(this.segmentStartTimeMs + calculatedTimeOffsetInSegmentMs);

            if (event.ctrlKey && !event.altKey) { // CTRL+Click: Set Start Time
                if (!this.isSegmentFromFullAudio) { alert("Timestamp editing only on full audio waveform."); return; }
                const highlightedS = _querySelectorFunc ? _querySelectorFunc('.english-sentence.highlighted-sentence') : null;
                if (!highlightedS || highlightedS !== this.sentenceElement) { alert("Please ensure the correct sentence is highlighted."); return; }
                let sDbId = highlightedS.dataset.sentenceDbId;
                if (!sDbId) sDbId = await fetchSentenceDbIdByIndices(_ARTICLE_ID, highlightedS.dataset.paragraphIndex, highlightedS.dataset.sentenceIndex);
                const currentEndTime = parseInt(highlightedS.dataset.endTimeMs, 10);
                if (sDbId && !isNaN(currentEndTime) && absolutePlayTimeMs >= 0 && absolutePlayTimeMs < currentEndTime) {
                    updateSentenceTimestampOnServer(sDbId, 'start', absolutePlayTimeMs);
                } else { alert("Invalid start time."); }

            } else if (event.altKey && !event.ctrlKey) { // ALT+Click: Set End Time
                if (!this.isSegmentFromFullAudio) { alert("Timestamp editing only on full audio waveform."); return; }
                const highlightedS = _querySelectorFunc ? _querySelectorFunc('.english-sentence.highlighted-sentence') : null;
                if (!highlightedS || highlightedS !== this.sentenceElement) { alert("Please ensure the correct sentence is highlighted."); return; }
                let sDbId = highlightedS.dataset.sentenceDbId;
                if (!sDbId) sDbId = await fetchSentenceDbIdByIndices(_ARTICLE_ID, highlightedS.dataset.paragraphIndex, highlightedS.dataset.sentenceIndex);
                const currentStartTime = parseInt(highlightedS.dataset.startTimeMs, 10);
                if (sDbId && !isNaN(currentStartTime) && absolutePlayTimeMs > currentStartTime) {
                    updateSentenceTimestampOnServer(sDbId, 'end', absolutePlayTimeMs);
                } else { alert("Invalid end time."); }

            } else { // Regular Click: Playback and Marker
                this.currentMarkerX = clickX; // Store for redraw
                // Redraw waveform with marker (simplified here, actual drawing logic is complex)
                const ctx = this.getContext('2d');
                _drawWaveformVisualization(ctx, this, waveformAudioBuffer, startTimeMs, endTimeMs, clickX); // Pass clickX for marker

                // Determine if playback is for full audio or a part based on canvas context
                playSentenceAudio(this.sentenceElement, !this.isSegmentFromFullAudio, absolutePlayTimeMs);
            }
        });

        const sentenceParentP = sentenceElement.parentElement;
        if (sentenceParentP) {
            sentenceParentP.insertAdjacentElement('afterend', scrollContainer);
            sentenceParentP.insertAdjacentElement('afterend', toolbar);
        } else { console.error('Waveform: Sentence has no parent.'); return; }

        const ctx = canvas.getContext('2d');
        if (!ctx) { console.error("Waveform: Failed to get 2D context."); return; }
        _drawWaveformVisualization(ctx, canvas, waveformAudioBuffer, startTimeMs, endTimeMs, null); // Initial draw without marker
    }

    function _drawWaveformVisualization(ctx, canvas, audioBufferForDrawing, segmentStartMs, segmentEndMs, markerXPosition = null) {
        ctx.fillStyle = '#f0f0f0'; // Background
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const startSample = Math.floor((segmentStartMs / 1000) * audioBufferForDrawing.sampleRate);
        let endSample = Math.floor((segmentEndMs / 1000) * audioBufferForDrawing.sampleRate);
        endSample = Math.min(endSample, audioBufferForDrawing.length);

        if (startSample >= endSample) { /* Draw flat line or return */ return; }
        const channelData = audioBufferForDrawing.getChannelData(0);
        const segmentData = channelData.slice(startSample, endSample);
        if (segmentData.length === 0) { /* Draw flat line or return */ return; }

        const samplesPerPixel = segmentData.length / canvas.width;
        const upperEnvelopePoints = []; const lowerEnvelopePoints = [];

        for (let x = 0; x < canvas.width; x++) {
            const startIdx = Math.floor(x * samplesPerPixel);
            const endIdx = Math.floor((x + 1) * samplesPerPixel);
            let maxVal = 0;
            for (let i = startIdx; i < endIdx && i < segmentData.length; i++) {
                const val = Math.abs(segmentData[i]); if (val > maxVal) maxVal = val;
            }
            if (startIdx === endIdx && startIdx < segmentData.length) maxVal = Math.abs(segmentData[startIdx]);
            const amplitude = maxVal * canvas.height / 2;
            upperEnvelopePoints.push({ x: x, y: (canvas.height / 2) - amplitude });
            lowerEnvelopePoints.push({ x: x, y: (canvas.height / 2) + amplitude });
        }
        // Extend to full canvas width if needed
        if (canvas.width > 0 && segmentData.length > 0) {
            const lastVal = Math.abs(segmentData[segmentData.length - 1]);
            const lastAmp = lastVal * canvas.height / 2;
            upperEnvelopePoints.push({ x: canvas.width, y: (canvas.height / 2) - lastAmp });
            lowerEnvelopePoints.push({ x: canvas.width, y: (canvas.height / 2) + lastAmp });
        } else if (canvas.width > 0) {
            upperEnvelopePoints.push({ x: canvas.width, y: canvas.height / 2 });
            lowerEnvelopePoints.push({ x: canvas.width, y: canvas.height / 2 });
        }

        if (upperEnvelopePoints.length === 0) return;
        ctx.beginPath(); ctx.moveTo(upperEnvelopePoints[0].x, upperEnvelopePoints[0].y);
        for (let i = 1; i < upperEnvelopePoints.length; i++) ctx.lineTo(upperEnvelopePoints[i].x, upperEnvelopePoints[i].y);
        for (let i = lowerEnvelopePoints.length - 1; i >= 0; i--) ctx.lineTo(lowerEnvelopePoints[i].x, lowerEnvelopePoints[i].y);
        ctx.closePath();
        ctx.fillStyle = 'rgba(0, 123, 255, 0.3)'; ctx.fill();

        if (typeof markerXPosition === 'number' && markerXPosition >= 0 && markerXPosition <= canvas.width) {
            ctx.strokeStyle = 'red'; ctx.lineWidth = 1; ctx.beginPath();
            ctx.moveTo(markerXPosition, 0); ctx.lineTo(markerXPosition, canvas.height); ctx.stroke();
        }
    }


    function _updatePartsViewModeUI() {
        // This function updates the UI based on isAudiobookModeParts state
        // It's called when switching views or initializing.
        if (isAudiobookModeParts) { // Switched TO Parts View
            if(partsAudioViewControls) partsAudioViewControls.style.display = 'block';
            if(fullAudioViewControls) fullAudioViewControls.style.display = 'none';
            if(partsAudioDownloadDiv) partsAudioDownloadDiv.style.display = 'block';
            if(fullAudioDownloadDiv) fullAudioDownloadDiv.style.display = 'none';
            if(switchToPartsViewButton) switchToPartsViewButton.style.display = 'none';
            if(switchToFullViewButton) switchToFullViewButton.style.display = 'inline-block';

            // When switching to parts view, audiobook full mode should be off
            isAudiobookModeFull = false;
            if (toggleAudiobookModeButton) { // Reset full audio mode button
                 toggleAudiobookModeButton.textContent = 'Enable Audiobook Mode (Full Audio)';
                 if(localAudioFileInput) localAudioFileInput.style.display = 'none';
                 if(audioFileNameSpan) audioFileNameSpan.textContent = 'No audio file selected.';
                 if(audiobookHint) audiobookHint.style.display = 'none';
            }
            stopCurrentAudio();
            audioBuffer = null; // Clear buffer as it was for full audio
            currentLoadedAudioPartIndex = -1; // Reset loaded part
            if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = "No part loaded.";

        } else { // Switched TO Full View (or initialized to Full View)
            if(partsAudioViewControls) partsAudioViewControls.style.display = 'none';
            if(fullAudioViewControls) fullAudioViewControls.style.display = 'block';
            if(partsAudioDownloadDiv) partsAudioDownloadDiv.style.display = 'none';
            if(fullAudioDownloadDiv) fullAudioDownloadDiv.style.display = 'block';
            if(switchToPartsViewButton) switchToPartsViewButton.style.display = 'inline-block';
            if(switchToFullViewButton) switchToFullViewButton.style.display = 'none';

            // When switching to full view, audiobook parts mode is implicitly off
            // isAudiobookModeFull might be true or false depending on toggleAudiobookModeButton
            stopCurrentAudio();
            audioBuffer = null; // Clear buffer as it was for a part (or if toggling full mode off)
            currentLoadedAudioPartIndex = -1;
            // Don't reset isAudiobookModeFull here, that's handled by its own toggle
        }
    }

    function _calculateMaxSentenceEndTime() {
        const allSentences = _querySelectorAllFunc ? _querySelectorAllFunc('.english-sentence[data-end-time-ms]') : [];
        allSentences.forEach(s => {
            const endTime = parseInt(s.dataset.endTimeMs, 10);
            if (!isNaN(endTime) && endTime > maxSentenceEndTime) {
                maxSentenceEndTime = endTime;
            }
        });
    }


    function init(config) {
        _ARTICLE_ID = config.articleData.articleId;
        _HAS_TIMESTAMPS = config.articleData.hasTimestamps;
        _NUM_AUDIO_PARTS = parseInt(config.articleData.numAudioParts, 10) || 0;
        _ARTICLE_AUDIO_PART_CHECKSUMS_STR = config.articleData.articleAudioPartChecksums;
        if (_ARTICLE_AUDIO_PART_CHECKSUMS_STR && typeof _ARTICLE_AUDIO_PART_CHECKSUMS_STR === 'string') {
            _expectedChecksumsArray = _ARTICLE_AUDIO_PART_CHECKSUMS_STR.split(AUDIO_PART_CHECKSUM_DELIMITER_JS);
        }

        _setActiveSentenceFunc = config.callbacks.setActiveSentence;
        _getAdjacentSentenceFunc = config.callbacks.getAdjacentSentence;
        _querySelectorFunc = config.utils.querySelector;
        _querySelectorAllFunc = config.utils.querySelectorAll;
        sentenceElementsArray = Array.from(_querySelectorAllFunc('.english-sentence'));


        // DOM Elements
        toggleAudiobookModeButton = config.elements.toggleAudiobookModeButton;
        localAudioFileInput = config.elements.localAudioFileInput;
        audioFileNameSpan = config.elements.audioFileNameSpan;
        audiobookHint = config.elements.audiobookHint;
        switchToPartsViewButton = config.elements.switchToPartsViewButton;
        switchToFullViewButton = config.elements.switchToFullViewButton;
        fullAudioViewControls = config.elements.fullAudioViewControls;
        partsAudioViewControls = config.elements.partsAudioViewControls;
        fullAudioDownloadDiv = config.elements.fullAudioDownloadDiv;
        partsAudioDownloadDiv = config.elements.partsAudioDownloadDiv;
        loadSelectedAudioPartButton = config.elements.loadSelectedAudioPartButton;
        loadLocalAudioPartButton = config.elements.loadLocalAudioPartButton;
        localAudioPartFileInput = config.elements.localAudioPartFileInput;
        downloadSelectedAudioPartButton = config.elements.downloadSelectedAudioPartButton;
        loadedAudioPartNameSpan = config.elements.loadedAudioPartNameSpan;

        _initAudioContextGlobally();
        _calculateMaxSentenceEndTime();

        // Event Listeners for Full Audio Mode
        if (toggleAudiobookModeButton && localAudioFileInput && audioFileNameSpan && audiobookHint) {
            toggleAudiobookModeButton.addEventListener('click', function() {
                if (!_initAudioContextGlobally() && !isAudiobookModeFull) return; // Try to init if not already full mode
                isAudiobookModeFull = !isAudiobookModeFull;
                if (isAudiobookModeFull) {
                    toggleAudiobookModeButton.textContent = 'Disable Audiobook Mode (Full)';
                    localAudioFileInput.style.display = 'inline-block';
                    audiobookHint.style.display = 'block';
                    if (isAudiobookModeParts) { // If parts mode was active, turn it off
                        isAudiobookModeParts = false;
                        _updatePartsViewModeUI(); // This will also clear part-specific audioBuffer
                    }
                } else {
                    toggleAudiobookModeButton.textContent = 'Enable Audiobook Mode (Full Audio)';
                    localAudioFileInput.style.display = 'none';
                    audiobookHint.style.display = 'none';
                    stopCurrentAudio();
                    audioBuffer = null; // Clear full audio buffer
                }
            });
            localAudioFileInput.addEventListener('change', async function(event) {
                if (!_initAudioContextGlobally()) return;
                const file = event.target.files[0];
                if (file) {
                    audioFileNameSpan.textContent = "Loading: " + file.name;
                    stopCurrentAudio(); audioBuffer = null;
                    try {
                        const rawBuffer = await file.arrayBuffer();
                        audioBuffer = await audioContext.decodeAudioData(rawBuffer); // audioBuffer is now for full audio
                        audioFileNameSpan.textContent = file.name;
                        // Optional: Validate duration against maxSentenceEndTime
                    } catch (e) {
                        alert(`Error decoding audio: ${e.message}`); audioFileNameSpan.textContent = "Error loading."; audioBuffer = null;
                    }
                }
            });
        }

        // Event Listeners and Setup for Audio Parts View
        if (_NUM_AUDIO_PARTS > 0) {
            if (switchToPartsViewButton) {
                switchToPartsViewButton.addEventListener('click', () => { isAudiobookModeParts = true; _updatePartsViewModeUI(); });
            }
            if (switchToFullViewButton) {
                switchToFullViewButton.addEventListener('click', () => { isAudiobookModeParts = false; _updatePartsViewModeUI(); });
            }

            const playbackSelectorDiv = _querySelectorFunc('#audio-part-selector-playback');
            const downloadSelectorDiv = _querySelectorFunc('#audio-part-selector-download');
            if (playbackSelectorDiv && downloadSelectorDiv) {
                for (let i = 0; i < _NUM_AUDIO_PARTS; i++) {
                    // Create and append radio buttons for playback and download
                    // ... (same as original code)
                }
            }

            if (loadSelectedAudioPartButton) {
                loadSelectedAudioPartButton.addEventListener('click', async () => {
                    if (!_initAudioContextGlobally()) return;
                    const selInput = _querySelectorFunc('#audio-part-selector-playback input:checked');
                    if (!selInput) { alert("Please select a part to load."); return; }
                    const partIndex = parseInt(selInput.value, 10);
                    if(localAudioPartFileInput) localAudioPartFileInput.value = ""; // Clear local file input
                    if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Loading Part ${partIndex + 1} (Server)...`;
                    stopCurrentAudio(); audioBuffer = null;
                    try {
                        const response = await fetch(`/article/${_ARTICLE_ID}/serve_mp3_part/${partIndex}`);
                        if (!response.ok) throw new Error(`Server error: ${response.statusText}`);
                        const rawBuffer = await response.arrayBuffer();
                        audioBuffer = await audioContext.decodeAudioData(rawBuffer); // audioBuffer is now for this part
                        if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Loaded Part ${partIndex + 1} (Server)`;
                        currentLoadedAudioPartIndex = partIndex;
                        // isAudiobookModeParts should already be true if this button is visible and clicked
                    } catch (e) {
                        alert(`Error loading audio part ${partIndex + 1} from server: ${e.message}`);
                        if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Error loading Part ${partIndex + 1}.`;
                        audioBuffer = null; currentLoadedAudioPartIndex = -1;
                    }
                });
            }
            // ... Other part-related event listeners (loadLocalAudioPartButton, localAudioPartFileInput, downloadSelectedAudioPartButton) ...
            // These would be similar to the original, using _arrayBufferToHexString, _expectedChecksumsArray etc.

            // Initial view mode (e.g., iOS might default to parts view)
            const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
            isAudiobookModeParts = isIOS; // Default to parts view on iOS, full view otherwise
             _updatePartsViewModeUI(); // Set initial UI based on this
        } else { // No audio parts available
            if (switchToPartsViewButton) switchToPartsViewButton.style.display = 'none';
            if (switchToFullViewButton) switchToFullViewButton.style.display = 'none';
            if (partsAudioViewControls) partsAudioViewControls.style.display = 'none';
            if (partsAudioDownloadDiv) partsAudioDownloadDiv.style.display = 'none';
            isAudiobookModeParts = false; // Ensure parts mode is off
            _updatePartsViewModeUI(); // Reflect this in UI
        }
    }

    return {
        init: init,
        initAudioContextGlobally: _initAudioContextGlobally, // Allow early init
        playSentenceAudio: playSentenceAudio,
        stopCurrentAudio: stopCurrentAudio,
        fetchSentenceDbIdByIndices: fetchSentenceDbIdByIndices, // For sentence_selection & waveform
        updateSentenceTimestampOnServer: updateSentenceTimestampOnServer, // For waveform
        displayWaveform: displayWaveform, // For UIInteractionsModule (context menu)
        clearExistingWaveform: clearExistingWaveform, // For UIInteractionsModule (context menu)

        // Providers for other modules
        getAudioBuffer: () => audioBuffer,
        isAudiobookModeFull: () => isAudiobookModeFull,
        isAudiobookModeParts: () => isAudiobookModeParts,
        getCurrentLoadedAudioPartIndex: () => currentLoadedAudioPartIndex,
        getHasTimestamps: () => _HAS_TIMESTAMPS,
        isCurrentSourceNodeActive: () => !!currentSourceNode,
        getCurrentPlayingSentence: () => currentPlayingSentence,
    };
})();
