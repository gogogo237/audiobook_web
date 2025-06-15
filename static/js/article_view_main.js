// static/js/article_view_main.js
// Main orchestrator for the article view page.
// Depends on all other article_view_*.js files being loaded first, especially article_view_config.js.

document.addEventListener('DOMContentLoaded', function() {
    // article_view_config.js should have already initialized global constants, DOM elements, and some state.
    // Functions from other modules will use these global variables (e.g., window.ARTICLE_ID, window.popup).

    // --- Initialization Functions (Order can be important) ---

    // 1. Populate sentence data (from sentences.js)
    if (typeof populateSentenceElementsArray === 'function') {
        populateSentenceElementsArray();
    } else {
        console.warn("JS_MAIN: populateSentenceElementsArray function not found.");
    }

    // 2. Initialize Sentence Selection UI specific displays (from sentence_selection.js)
    if (typeof initializeSentenceSelectionDisplays === 'function') {
        initializeSentenceSelectionDisplays();
    } else {
        console.warn("JS_MAIN: initializeSentenceSelectionDisplays function not found.");
    }

    // 3. Initialize Audio Context (from audio.js)
    if (typeof initAudioContextGlobally === 'function') {
        initAudioContextGlobally();
    } else {
        console.warn("JS_MAIN: initAudioContextGlobally function not found.");
    }

    // 4. Setup Gamepad (from gamepad.js - this also handles initial icon display)
    if (typeof setupGamepadHandlers === 'function') {
        setupGamepadHandlers();
    } else {
        console.warn("JS_MAIN: setupGamepadHandlers function not found.");
        // Fallback for icon if main setup is missing
        if(typeof updateGamepadIconDisplay === 'function') updateGamepadIconDisplay(false);
    }


    // --- Event Listeners Setup ---

    // Setup Sentence Selection Event Listeners (from sentence_selection.js)
    if (typeof setupSentenceSelectionEventListeners === 'function') {
        setupSentenceSelectionEventListeners();
    } else {
        console.warn("JS_MAIN: setupSentenceSelectionEventListeners function not found.");
    }

    // Article Content Interactions (Clicks, Context Menu)
    if (window.articleContentWrapper) {
        window.articleContentWrapper.addEventListener('contextmenu', function(event) {
            const targetSentence = event.target.closest('.english-sentence');
            if (targetSentence) {
                event.preventDefault();
                if (typeof hideContextualMenu === 'function') hideContextualMenu();
                const translation = targetSentence.dataset.translation;
                if (typeof displayPopup === 'function') displayPopup(targetSentence, translation || "No translation.");

                if (window.highlightedSentence !== targetSentence) {
                    if (typeof setActiveSentence === 'function') setActiveSentence(targetSentence, "contextmenu_highlight");
                } else {
                    if (typeof scrollToCenter === 'function') scrollToCenter(targetSentence);
                }
            } else {
                if (typeof hideTranslationPopup === 'function') hideTranslationPopup();
            }
        });

        window.articleContentWrapper.addEventListener('click', function(event) {
            const targetSentence = event.target.closest('.english-sentence');
            if (targetSentence) {
                event.stopPropagation();
                if (typeof hideTranslationPopup === 'function') hideTranslationPopup();

                if (window.highlightedSentence === targetSentence) {
                    if (window.contextualMenu && window.contextualMenu.style.display === 'block' && window.contextualMenu.style.opacity === '1') {
                        if (typeof hideContextualMenu === 'function') hideContextualMenu();
                    } else {
                        if (typeof populateAndShowContextualMenu === 'function') populateAndShowContextualMenu(targetSentence, event.clientX);
                    }
                } else {
                    if (typeof setActiveSentence === 'function') setActiveSentence(targetSentence, "click_new_sentence");
                    if (typeof hideContextualMenu === 'function') hideContextualMenu();

                    let waveformIsVisible = targetSentence.parentElement?.nextElementSibling?.classList.contains('waveform-scroll-container');
                    if (!waveformIsVisible && typeof playSentenceAudio === 'function') {
                         // Determine if playing from part or full based on current mode and sentence data
                         let playAsPartForClick = false;
                         if (window.isAudiobookModeParts && window.currentLoadedAudioPartIndex !== -1 &&
                             targetSentence.dataset.audioPartIndex !== undefined &&
                             parseInt(targetSentence.dataset.audioPartIndex, 10) === window.currentLoadedAudioPartIndex) {
                             playAsPartForClick = true;
                         }
                         playSentenceAudio(targetSentence, playAsPartForClick, null); // null for optionalDesiredStartTimeMs to play from beginning
                    }
                }
            } else {
                // Click was not on a sentence
                if (window.contextualMenu && !window.contextualMenu.contains(event.target) && typeof hideContextualMenu === 'function') {
                    hideContextualMenu();
                }
                if (window.popup && !window.popup.contains(event.target) && typeof hideTranslationPopup === 'function') {
                    hideTranslationPopup();
                }
            }
        });
    }

    // Contextual Menu Actions
    if (window.contextualMenu) {
        window.contextualMenu.addEventListener('click', function(event) {
            event.stopPropagation();
            const actionTarget = event.target.closest('.contextual-menu-item');
            if (!actionTarget || !window.highlightedSentence) {
                if (typeof hideContextualMenu === 'function') hideContextualMenu();
                return;
            }
            const action = actionTarget.dataset.action;

            switch (action) {
                case 'show-translation':
                    const translation = window.highlightedSentence.dataset.translation;
                    if (typeof displayPopup === 'function') displayPopup(window.highlightedSentence, translation || "No translation available.");
                    break;
                case 'save-location':
                    if (typeof saveCurrentLocation === 'function') saveCurrentLocation(parseInt(window.highlightedSentence.dataset.paragraphIndex), parseInt(window.highlightedSentence.dataset.sentenceIndex), "manual_menu_save");
                    break;
                case 'play-pause-audio':
                    // This action might be better handled by a dedicated function in audio.js if it gets complex
                    if (typeof initAudioContextGlobally === 'function') initAudioContextGlobally(); // Ensure context
                    let playAsPart = false;
                    let canPlayThis = false;
                    if (window.isAudiobookModeFull && window.audioContext && window.audioBuffer && window.HAS_TIMESTAMPS) {
                        canPlayThis = true; playAsPart = false;
                    } else if (window.isAudiobookModeParts && window.audioContext && window.audioBuffer && window.HAS_TIMESTAMPS && window.currentLoadedAudioPartIndex !== -1) {
                        const sentencePartIndex = parseInt(window.highlightedSentence.dataset.audioPartIndex, 10);
                        if (sentencePartIndex === window.currentLoadedAudioPartIndex) {
                            canPlayThis = true; playAsPart = true;
                        }
                    }
                    if (canPlayThis) {
                        const iconSpan = actionTarget.querySelector('.menu-icon');
                        if (window.currentPlayingSentence === window.highlightedSentence && window.currentSourceNode) {
                            if (typeof stopCurrentAudio === 'function') stopCurrentAudio();
                            if (iconSpan) iconSpan.textContent = "▶️";
                            if (actionTarget) actionTarget.title = "Play Sentence Audio";
                        } else {
                            if (typeof playSentenceAudio === 'function') playSentenceAudio(window.highlightedSentence, playAsPart);
                            if (iconSpan) iconSpan.textContent = "⏹️";
                            if (actionTarget) actionTarget.title = "Stop Sentence Audio";
                        }
                    } else {
                        alert("Audio not ready or sentence part mismatch for direct play.");
                    }
                    break;
                case 'edit-audio-clip':
                     // This action would call a function from waveform.js
                    if (typeof handleEditAudioClipContextMenu === 'function') handleEditAudioClipContextMenu();
                    else if (typeof displayWaveform === 'function' && typeof clearExistingWaveform === 'function' && window.highlightedSentence) { // Fallback to direct calls if specific handler not found
                        let waveformIsCurrentlyVisible = window.highlightedSentence.parentElement?.nextElementSibling?.classList.contains('waveform-scroll-container');
                        if (waveformIsCurrentlyVisible) {
                            clearExistingWaveform(window.highlightedSentence);
                        } else {
                            const startTimeMs = parseInt(window.highlightedSentence.dataset.startTimeMs, 10);
                            const endTimeMs = parseInt(window.highlightedSentence.dataset.endTimeMs, 10);
                            if (!isNaN(startTimeMs) && !isNaN(endTimeMs) && window.audioBuffer) { // Ensure audioBuffer is the full one
                                displayWaveform(window.highlightedSentence, window.audioBuffer, startTimeMs, endTimeMs);
                            } else {
                                alert("Cannot display waveform: Time data missing or full audio not loaded.");
                            }
                        }
                    } else {
                         console.warn("JS_MAIN: ContextMenu - Waveform edit/display functions not found.");
                    }
                    break;
                case 'set-as-beginning':
                    if (typeof handleSetAsBeginning === 'function') handleSetAsBeginning(window.highlightedSentence);
                    else console.warn("JS_MAIN: ContextMenu - handleSetAsBeginning function not found.");
                    break;
                case 'set-as-ending':
                    if (typeof handleSetAsEnding === 'function') handleSetAsEnding(window.highlightedSentence);
                    else console.warn("JS_MAIN: ContextMenu - handleSetAsEnding function not found.");
                    break;
            }
            if (action !== 'assign-sentence-submenu' && typeof hideContextualMenu === 'function') {
                hideContextualMenu();
            }
        });
    }

    // Global Click Listener (for hiding popups)
    document.addEventListener('click', function(event) {
        if (window.contextualMenu && window.contextualMenu.style.display === 'block' && !window.contextualMenu.contains(event.target) && !event.target.closest('.english-sentence')) {
            if (typeof hideContextualMenu === 'function') hideContextualMenu();
        }
        if (window.popup && window.popup.style.display === 'block' && !window.popup.contains(event.target) && !event.target.closest('.english-sentence') &&
            !(window.contextualMenu && window.contextualMenu.style.display === 'block' && window.contextualMenu.contains(event.target))) {
            if (typeof hideTranslationPopup === 'function') hideTranslationPopup();
        }
    });

    // Navigation Buttons
    if (window.restoreLocationButton) {
        if (window.INITIAL_READING_LOCATION && typeof window.INITIAL_READING_LOCATION.paragraph_index !== 'undefined') {
            window.restoreLocationButton.style.display = 'inline-block';
            window.restoreLocationButton.addEventListener('click', function() {
                if (typeof findSentenceElement === 'function' && typeof setActiveSentence === 'function') {
                    const targetS = findSentenceElement(window.INITIAL_READING_LOCATION.paragraph_index, window.INITIAL_READING_LOCATION.sentence_index_in_paragraph);
                    if (targetS) setActiveSentence(targetS, "initial_restore_location_auto_scroll");
                } else {
                    console.warn("JS_MAIN: restoreLocationButton - findSentenceElement or setActiveSentence not found.");
                }
            });
        } else {
            window.restoreLocationButton.style.display = 'none';
        }
    }

    if (window.goBackButton) {
        window.goBackButton.addEventListener('click', function() {
            if (window.lastHighlightedSentenceElement && typeof setActiveSentence === 'function') {
                setActiveSentence(window.lastHighlightedSentenceElement, "go_back_button");
            } else {
                 console.warn("JS_MAIN: goBackButton - lastHighlightedSentenceElement or setActiveSentence not found.");
            }
        });
    }
    if (window.goToTopButton) {
        window.goToTopButton.addEventListener('click', function() { window.scrollTo({ top: 0, behavior: 'smooth' }); });
    }

    // Scroll and Resize Listeners for UI updates
    window.addEventListener('scroll', () => {
        if (typeof updateGoBackButtonVisibility === 'function') updateGoBackButtonVisibility();
        if (typeof updateGoToTopButtonVisibility === 'function') updateGoToTopButtonVisibility();
    });
    window.addEventListener('resize', () => {
        if (typeof updateGoBackButtonVisibility === 'function') updateGoBackButtonVisibility();
        if (typeof updateGoToTopButtonVisibility === 'function') updateGoToTopButtonVisibility();
    });

    // Setup Audio Mode Event Listeners (from audio.js and audio_parts.js)
    if (typeof setupFullAudioModeEventListeners === 'function') {
        setupFullAudioModeEventListeners();
    } else {
        console.warn("JS_MAIN: setupFullAudioModeEventListeners function not found.");
    }
    if (typeof setupAudioPartsEventListeners === 'function') {
        setupAudioPartsEventListeners();
    } else {
        console.warn("JS_MAIN: setupAudioPartsEventListeners function not found.");
    }
    if (typeof initializeAudioPartsView === 'function') { // This initializes UI based on NUM_AUDIO_PARTS and iOS
        initializeAudioPartsView();
    } else {
        console.warn("JS_MAIN: initializeAudioPartsView function not found.");
    }

    // Final UI Updates & Initial State
    // Initial sentence highlight based on saved location or first sentence
    if (window.INITIAL_READING_LOCATION && typeof window.INITIAL_READING_LOCATION.paragraph_index !== 'undefined' && typeof findSentenceElement === 'function') {
        const targetSentence = findSentenceElement(window.INITIAL_READING_LOCATION.paragraph_index, window.INITIAL_READING_LOCATION.sentence_index_in_paragraph);
        if (targetSentence) {
            targetSentence.classList.add('highlighted-sentence');
            window.highlightedSentence = targetSentence;
            window.lastHighlightedSentenceElement = targetSentence;
            if (window.restoreLocationButton) window.restoreLocationButton.style.display = 'inline-block'; // Ensure button is visible if location restored
        } else if (window.sentenceElementsArray && window.sentenceElementsArray.length > 0 && typeof setActiveSentence === 'function') {
            // If saved location is invalid, highlight the first sentence without scrolling.
            setActiveSentence(window.sentenceElementsArray[0], "initial_page_load_highlight_no_scroll");
        }
    } else if (window.sentenceElementsArray && window.sentenceElementsArray.length > 0) {
        // No saved location, highlight the first sentence without scrolling.
        window.sentenceElementsArray[0].classList.add('highlighted-sentence');
        window.highlightedSentence = window.sentenceElementsArray[0];
        window.lastHighlightedSentenceElement = window.sentenceElementsArray[0];
    }

    // Initial visibility for scroll-dependent buttons
    if (typeof updateGoBackButtonVisibility === 'function') updateGoBackButtonVisibility();
    if (typeof updateGoToTopButtonVisibility === 'function') updateGoToTopButtonVisibility();

    console.log("JS_MAIN: Main DOMContentLoaded setup complete.");
});
