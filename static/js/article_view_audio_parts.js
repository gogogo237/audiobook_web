// static/js/article_view_audio_parts.js
// Depends on:
// - article_view_config.js (for ARTICLE_ID, NUM_AUDIO_PARTS, expectedChecksumsArray, audioContext, audioBuffer, isAudiobookModeParts, isAudiobookModeFull, currentLoadedAudioPartIndex, isPartsViewActive, and various DOM elements)
// - article_view_ui.js (for updatePartsViewModeUI)
// - article_view_audio.js (for initAudioContextGlobally, stopCurrentAudio - though stopCurrentAudio might be called directly from config.js if it's simple enough)

// Global state variables (NUM_AUDIO_PARTS, ARTICLE_ID, etc.) are expected to be defined in article_view_config.js

function arrayBufferToHexString(buffer) {
    const byteArray = new Uint8Array(buffer);
    let hexString = "";
    for (let i = 0; i < byteArray.length; i++) {
        const hex = byteArray[i].toString(16);
        hexString += (hex.length === 1 ? "0" : "") + hex;
    }
    return hexString;
}

// Event listener logic for audio parts mode (to be called from main.js)
function setupAudioPartsEventListeners() {
    // Uses global DOM elements and state from config.js
    // Calls to global functions like initAudioContextGlobally, stopCurrentAudio (from audio.js)
    // Calls to global functions like updatePartsViewModeUI (from ui.js)

    if (NUM_AUDIO_PARTS > 0) {
        if (switchToPartsViewButton) {
            switchToPartsViewButton.addEventListener('click', () => {
                window.isPartsViewActive = true;
                if (typeof updatePartsViewModeUI === 'function') updatePartsViewModeUI();
                else console.warn("JS_AUDIO_PARTS: updatePartsViewModeUI function not found on switchToPartsViewButton click.");
            });
        }
        if (switchToFullViewButton) {
            switchToFullViewButton.addEventListener('click', () => {
                window.isPartsViewActive = false;
                if (typeof updatePartsViewModeUI === 'function') updatePartsViewModeUI();
                else console.warn("JS_AUDIO_PARTS: updatePartsViewModeUI function not found on switchToFullViewButton click.");
                 // When switching to full view, audiobook mode for full audio should be re-evaluated or enabled by default if a file was loaded.
                // For now, it just switches the UI, user might need to re-enable full audiobook mode explicitly if they switch views.
            });
        }

        const playbackSelectorDiv = document.getElementById('audio-part-selector-playback');
        const downloadSelectorDiv = document.getElementById('audio-part-selector-download');

        if (playbackSelectorDiv && downloadSelectorDiv) {
            for (let i = 0; i < NUM_AUDIO_PARTS; i++) {
                const partNumDisplay = i + 1;
                const rbP = document.createElement('input');
                rbP.type = 'radio';
                rbP.name = 'audio_part_playback';
                rbP.value = i;
                rbP.id = `part_pb_${i}`;
                const lblP = document.createElement('label');
                lblP.htmlFor = `part_pb_${i}`;
                lblP.textContent = `Part ${partNumDisplay}`;
                playbackSelectorDiv.appendChild(rbP);
                playbackSelectorDiv.appendChild(lblP);
                playbackSelectorDiv.appendChild(document.createTextNode(" "));

                const rbD = document.createElement('input');
                rbD.type = 'radio';
                rbD.name = 'audio_part_download';
                rbD.value = i;
                rbD.id = `part_dl_${i}`;
                const lblD = document.createElement('label');
                lblD.htmlFor = `part_dl_${i}`;
                lblD.textContent = `Part ${partNumDisplay}`;
                downloadSelectorDiv.appendChild(rbD);
                downloadSelectorDiv.appendChild(lblD);
                downloadSelectorDiv.appendChild(document.createTextNode(" "));
            }
        }

        if (loadSelectedAudioPartButton) {
            loadSelectedAudioPartButton.addEventListener('click', async () => {
                if (typeof initAudioContextGlobally !== 'function' || !initAudioContextGlobally()) {
                     alert("AudioContext could not be initialized."); return;
                }
                const selInput = document.querySelector('#audio-part-selector-playback input:checked');
                if (!selInput) { alert("Please select a part to load."); return; }
                const partIndex = parseInt(selInput.value, 10);

                if(localAudioPartFileInput) localAudioPartFileInput.value = ""; // Clear local file input
                if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Loading Part ${partIndex + 1} (Server)...`;

                if (typeof stopCurrentAudio === 'function') stopCurrentAudio(); else console.warn("loadSelectedAudioPartButton: stopCurrentAudio not found");
                window.audioBuffer = null;

                try {
                    const response = await fetch(`/article/${ARTICLE_ID}/serve_mp3_part/${partIndex}`);
                    if (!response.ok) throw new Error(`Server error fetching part: ${response.statusText}`);
                    const arrayBuffer = await response.arrayBuffer();
                    window.audioBuffer = await window.audioContext.decodeAudioData(arrayBuffer);
                    if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Loaded Part ${partIndex + 1} (Server)`;
                    window.currentLoadedAudioPartIndex = partIndex;
                    window.isAudiobookModeParts = true;
                    window.isAudiobookModeFull = false; // Ensure full mode is off
                } catch (e) {
                    alert(`Error loading audio part ${partIndex + 1} from server: ${e.message}`);
                    if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Error loading Part ${partIndex + 1}.`;
                    window.audioBuffer = null;
                    window.currentLoadedAudioPartIndex = -1;
                }
            });
        }

        if (loadLocalAudioPartButton && localAudioPartFileInput) {
            loadLocalAudioPartButton.addEventListener('click', () => {
                if (typeof initAudioContextGlobally !== 'function' || !initAudioContextGlobally()) {
                    alert("AudioContext could not be initialized."); return;
                }
                const selInput = document.querySelector('#audio-part-selector-playback input:checked');
                if (!selInput) { alert("Please select a part number using the radio buttons first to associate the local file."); return; }
                localAudioPartFileInput.click();
            });

            localAudioPartFileInput.addEventListener('change', async function(event) {
                if (typeof initAudioContextGlobally !== 'function' || !initAudioContextGlobally()) {
                    alert("AudioContext could not be initialized."); return;
                }
                const file = event.target.files[0];
                if (!file) return;

                const selInput = document.querySelector('#audio-part-selector-playback input:checked');
                if (!selInput) {
                    alert("Error: No part selected via radio button. Cannot associate local file.");
                    localAudioPartFileInput.value=""; // Clear the file input
                    return;
                }
                const partIndex = parseInt(selInput.value, 10);
                const expectedChecksum = (expectedChecksumsArray.length > partIndex && expectedChecksumsArray[partIndex]) ? expectedChecksumsArray[partIndex].trim() : "";

                if (!expectedChecksum) {
                    console.warn(`JS_AUDIO_PARTS: No expected checksum for Part ${partIndex + 1}. Loading local file without verification.`);
                }

                if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Verifying Part ${partIndex + 1} (Local: ${file.name.substring(0,15)}...)...`;

                if (typeof stopCurrentAudio === 'function') stopCurrentAudio(); else console.warn("localAudioPartFileInput change: stopCurrentAudio not found");
                window.audioBuffer = null;

                try {
                    const fileBufferForDecode = await file.arrayBuffer();
                    if (expectedChecksum) { // Only hash if checksum is expected
                        const fileBufferForHash = fileBufferForDecode.slice(0); // Clone for hashing
                        const hashBuffer = await window.crypto.subtle.digest('SHA-256', fileBufferForHash);
                        const calculatedHexChecksum = arrayBufferToHexString(hashBuffer); // Uses local/global function
                        if (calculatedHexChecksum.toLowerCase() !== expectedChecksum.toLowerCase()) {
                            alert(`Checksum mismatch for Part ${partIndex + 1}.\nExpected: ...${expectedChecksum.slice(-10)}\nGot:      ...${calculatedHexChecksum.slice(-10)}`);
                            if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Incorrect file for Part ${partIndex + 1}`;
                            window.currentLoadedAudioPartIndex = -1;
                            localAudioPartFileInput.value = ""; // Clear the file input
                            return;
                        }
                    }
                    window.audioBuffer = await window.audioContext.decodeAudioData(fileBufferForDecode);
                    if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Loaded Part ${partIndex + 1} (Local: ${file.name.substring(0,15)}...)`;
                    window.currentLoadedAudioPartIndex = partIndex;
                    window.isAudiobookModeParts = true;
                    window.isAudiobookModeFull = false; // Ensure full mode is off
                } catch (e) {
                    alert(`Error processing local audio part ${partIndex + 1}: ${e.message}`);
                    if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = `Error loading local Part ${partIndex + 1}.`;
                    window.audioBuffer = null;
                    window.currentLoadedAudioPartIndex = -1;
                }
                localAudioPartFileInput.value = ""; // Clear the file input after processing
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
    }
}

function initializeAudioPartsView() {
    // Uses global: NUM_AUDIO_PARTS, isPartsViewActive (from config.js)
    // Calls global: updatePartsViewModeUI (from ui.js)
    if (NUM_AUDIO_PARTS > 0) {
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
        if (isIOS) { // Simplified: if iOS and parts exist, default to parts view.
            window.isPartsViewActive = true;
        } else {
            window.isPartsViewActive = false; // Default for non-iOS, can be changed by user
        }
        if (typeof updatePartsViewModeUI === 'function') updatePartsViewModeUI();
        else console.warn("JS_AUDIO_PARTS: updatePartsViewModeUI function not found during initialization.");
    } else {
        // Ensure parts-related UI is hidden if there are no parts
        if (switchToPartsViewButton) switchToPartsViewButton.style.display = 'none';
        if (switchToFullViewButton) switchToFullViewButton.style.display = 'none';
        if (partsAudioViewControls) partsAudioViewControls.style.display = 'none';
        if (partsAudioDownloadDiv) partsAudioDownloadDiv.style.display = 'none';
    }
}
