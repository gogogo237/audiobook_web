// static/js/article_view_ui.js
// Depends on article_view_config.js for DOM elements and some state variables.
// Depends on article_view_main.js (or equivalent) for some state variables like
// isAudiobookModeFull, audioBuffer, audioContext, HAS_TIMESTAMPS, currentLoadedAudioPartIndex,
// currentPlayingSentence, currentSourceNode, isSentenceSelectionUIVisible.
// These will need to be passed or accessed globally.

// --- UI Helper Functions ---
function scrollToCenter(element) {
    if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
    }
}

function updateGoBackButtonVisibility() {
    // Depends on: goBackButton (DOM), lastHighlightedSentenceElement (State from main/config)
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

function updateGoToTopButtonVisibility() {
    // Depends on: goToTopButton (DOM), lastScrollTop (State from config), scrollThresholdForGoToTop (Const from config)
    if (!goToTopButton) return;
    let st = window.pageYOffset || document.documentElement.scrollTop;
    if (st < lastScrollTop && st > scrollThresholdForGoToTop) {
        goToTopButton.classList.add('visible');
    } else {
        goToTopButton.classList.remove('visible');
    }
    lastScrollTop = st <= 0 ? 0 : st; // Update lastScrollTop (global/config scope)
}

// --- Popups and Contextual Menu ---
function displayPopup(targetElement, content) {
    // Depends on: popup (DOM), currentPopupTargetSentence (State from config)
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
    currentPopupTargetSentence = targetElement; // Update currentPopupTargetSentence (global/config scope)
}

function hideContextualMenu() {
    // Depends on: contextualMenu (DOM)
    if (contextualMenu) {
        contextualMenu.style.opacity = '0';
        contextualMenu.style.transform = 'scale(0.95)';
        setTimeout(() => { contextualMenu.style.display = 'none'; }, 100);
    }
}

function hideTranslationPopup() {
    // Depends on: popup (DOM), currentPopupTargetSentence (State from config)
    if (popup) {
        popup.style.display = 'none';
        if (currentPopupTargetSentence && popup.innerHTML === currentPopupTargetSentence.dataset.translation) {
             currentPopupTargetSentence = null; // Update currentPopupTargetSentence (global/config scope)
        }
    }
}

function populateAndShowContextualMenu(sentenceElement, clickX) {
    // Depends on: contextualMenu (DOM)
    // Depends on global states: isAudiobookModeFull, audioBuffer, HAS_TIMESTAMPS,
    // audioContext, currentLoadedAudioPartIndex, currentPlayingSentence, currentSourceNode,
    // isSentenceSelectionUIVisible (from config/main)
    if (!contextualMenu || !sentenceElement) return;

    let menuHTML = `<div class="contextual-menu-item" data-action="show-translation" title="Show Chinese Translation"><span class="menu-icon">💬</span><span class="menu-text">Translate</span></div>`;
    menuHTML += `<div class="contextual-menu-item" data-action="save-location" title="Save this reading location"><span class="menu-icon">💾</span><span class="menu-text">Save Spot</span></div>`;

    // Waveform edit option (check if waveform is visible for *this* sentenceElement)
    // This check needs to access the DOM structure relative to sentenceElement.
    let waveformIsVisible = false;
    if (sentenceElement.parentElement) {
        const potentialContainer = sentenceElement.parentElement.nextElementSibling;
        if (potentialContainer && potentialContainer.classList.contains('waveform-scroll-container')) {
            waveformIsVisible = true;
        }
    }

    // The 'edit-audio-clip' option should be available if full audio mode is on and buffer exists.
    // The text/icon changes based on whether the waveform for *this* sentence is currently visible.
    console.log("DEBUG_CONTEXT_MENU: 'Edit Clip' check: isAudiobookModeFull:", typeof isAudiobookModeFull !== 'undefined' && isAudiobookModeFull, "audioBuffer exists:", !!audioBuffer, "sentenceElement exists:", !!sentenceElement);
    if (isAudiobookModeFull && audioBuffer && sentenceElement) { // audioBuffer for global audioBuffer
        let editActionText = "Edit Clip";
        let editActionIcon = "✏️";
        if (waveformIsVisible) {
            editActionText = "Hide Waveform";
            editActionIcon = "🗑️";
        }
        menuHTML += `<div class="contextual-menu-item" data-action="edit-audio-clip" title="${editActionText} for this sentence"><span class="menu-icon">${editActionIcon}</span><span class="menu-text">${editActionText}</span></div>`;
    }

    console.log("DEBUG_CONTEXT_MENU: 'Play/Pause Audio' check: isAudiobookModeFull:", typeof isAudiobookModeFull !== 'undefined' && isAudiobookModeFull, "isAudiobookModeParts:", typeof isAudiobookModeParts !== 'undefined' && isAudiobookModeParts, "audioContext exists:", !!audioContext, "audioBuffer exists:", !!audioBuffer, "HAS_TIMESTAMPS:", typeof HAS_TIMESTAMPS !== 'undefined' && HAS_TIMESTAMPS);
    if (typeof isAudiobookModeParts !== 'undefined' && isAudiobookModeParts) {
        console.log("DEBUG_CONTEXT_MENU: 'Play/Pause Audio' (Parts detail): currentLoadedAudioPartIndex:", typeof currentLoadedAudioPartIndex !== 'undefined' ? currentLoadedAudioPartIndex : 'undefined', "sentence part index:", sentenceElement ? sentenceElement.dataset.audioPartIndex : 'N/A');
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

    // Sentence Selection Submenu
    // isSentenceSelectionUIVisible needs to be globally accessible (e.g., from config or main)
    console.log("DEBUG_CONTEXT_MENU: 'Assign Sentence' check: isSentenceSelectionUIVisible:", typeof isSentenceSelectionUIVisible !== 'undefined' && isSentenceSelectionUIVisible, "sentenceElement exists:", !!sentenceElement);
    if (isSentenceSelectionUIVisible && sentenceElement) {
        menuHTML += `<div class="contextual-menu-item contextual-menu-item-assign" data-action="assign-sentence-submenu">
                        <span class="menu-icon">🎯</span>
                        <span class="menu-text">Assign Sentence...</span>
                        <span class="submenu-arrow">▶</span>
                        <div class="contextual-submenu">
                            <div class="contextual-menu-item" data-action="set-as-beginning" title="Set this sentence as the beginning">
                                <span class="menu-icon">🟢</span> <span class="menu-text">Set as Beginning</span>
                            </div>
                            <div class="contextual-menu-item" data-action="set-as-ending" title="Set this sentence as the ending">
                                <span class="menu-icon">🔴</span> <span class="menu-text">Set as Ending</span>
                            </div>
                        </div>
                    </div>`;
    }

    contextualMenu.innerHTML = menuHTML;
    const rect = sentenceElement.getBoundingClientRect();
    let menuTop = rect.bottom + window.scrollY + 5;
    let menuLeft = clickX + window.scrollX - (contextualMenu.offsetWidth / 2);

    if (menuLeft < 10) menuLeft = 10;
    if (menuLeft + contextualMenu.offsetWidth > window.innerWidth - 10) {
        menuLeft = window.innerWidth - 10 - contextualMenu.offsetWidth;
    }
    // Adjust if menu goes off bottom of viewport
    if (menuTop + contextualMenu.offsetHeight > window.innerHeight + window.scrollY - 10) {
        menuTop = rect.top + window.scrollY - contextualMenu.offsetHeight - 5;
    }

    contextualMenu.style.top = menuTop + 'px';
    contextualMenu.style.left = menuLeft + 'px';
    contextualMenu.style.display = 'block';
    setTimeout(() => {
         contextualMenu.style.opacity = '1';
         contextualMenu.style.transform = 'scale(1)';
    }, 10);
}

// --- Audio Parts View UI (specific part) ---
// This function changes UI based on whether "Parts View" is active or not.
// It relies on several DOM elements from config.js and state variables (isPartsViewActive, etc.)
function updatePartsViewModeUI() {
    // DOM elements from config.js:
    // partsAudioViewControls, fullAudioViewControls, partsAudioDownloadDiv, fullAudioDownloadDiv,
    // switchToPartsViewButton, switchToFullViewButton, toggleAudiobookModeButton,
    // localAudioFileInput, audioFileNameSpan, audiobookHint, loadedAudioPartNameSpan

    // State variables (should be global or passed):
    // isPartsViewActive, isAudiobookModeParts, isAudiobookModeFull,
    // currentLoadedAudioPartIndex, audioBuffer

    // Functions it calls (should be global or passed):
    // stopCurrentAudio (from audio.js)

    if (window.isPartsViewActive) { // Assuming isPartsViewActive is a global state
        if(partsAudioViewControls) partsAudioViewControls.style.display = 'block';
        if(fullAudioViewControls) fullAudioViewControls.style.display = 'none';
        if(partsAudioDownloadDiv) partsAudioDownloadDiv.style.display = 'block';
        if(fullAudioDownloadDiv) fullAudioDownloadDiv.style.display = 'none';
        if(switchToPartsViewButton) switchToPartsViewButton.style.display = 'none';
        if(switchToFullViewButton) switchToFullViewButton.style.display = 'inline-block';

        window.isAudiobookModeParts = true; // global state
        window.isAudiobookModeFull = false; // global state
        if (toggleAudiobookModeButton) {
             toggleAudiobookModeButton.textContent = 'Enable Audiobook Mode (Full Audio)';
             if(localAudioFileInput) localAudioFileInput.style.display = 'none';
             if(audioFileNameSpan) audioFileNameSpan.textContent = 'No audio file selected.';
             if(audiobookHint) audiobookHint.style.display = 'none';
        }
        if (typeof stopCurrentAudio === 'function') stopCurrentAudio(); else console.warn("updatePartsViewModeUI: stopCurrentAudio function not found.");

        if(loadedAudioPartNameSpan) loadedAudioPartNameSpan.textContent = "No part loaded.";
        window.currentLoadedAudioPartIndex = -1; // global state
        window.audioBuffer = null; // global state, clear buffer when switching to parts view initially

    } else { // Switching to Full View (or default view)
        if(partsAudioViewControls) partsAudioViewControls.style.display = 'none';
        if(fullAudioViewControls) fullAudioViewControls.style.display = 'block';
        if(partsAudioDownloadDiv) partsAudioDownloadDiv.style.display = 'none';
        if(fullAudioDownloadDiv) fullAudioDownloadDiv.style.display = 'block';
        if(switchToPartsViewButton) switchToPartsViewButton.style.display = 'inline-block';
        if(switchToFullViewButton) switchToFullViewButton.style.display = 'none';

        window.isAudiobookModeParts = false; // global state
        // isAudiobookModeFull remains as it was, or could be set by toggleAudiobookModeButton
        if (typeof stopCurrentAudio === 'function') stopCurrentAudio(); else console.warn("updatePartsViewModeUI: stopCurrentAudio function not found.");
        // Do not nullify audioBuffer here as user might be switching back to full audio mode with a loaded full audio.
    }
}
