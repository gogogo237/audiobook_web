// static/js/article_view_main.js
// Main orchestrator for the article view page.
// Depends on all other article_view_*.js files being loaded first, especially article_view_config.js.

document.addEventListener('DOMContentLoaded', function() {
    console.log("DEBUG_MAIN_DOMCONTENTLOADED_START: Checking sentenceSelectionUIContainer (direct access):", typeof sentenceSelectionUIContainer !== 'undefined' && !!sentenceSelectionUIContainer);
    console.log("DEBUG_MAIN_DOMCONTENTLOADED_START: Checking window.sentenceSelectionUIContainer:", typeof window.sentenceSelectionUIContainer !== 'undefined' && !!window.sentenceSelectionUIContainer);
    // article_view_config.js should have already initialized global constants, DOM elements, and some state.
    // Functions from other modules will use these global variables (e.g., window.ARTICLE_ID, window.popup).

    // Article Content Interactions (Clicks, Context Menu)
    if (articleContentWrapper) {
        articleContentWrapper.addEventListener('contextmenu', function(event) {
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

        articleContentWrapper.addEventListener('click', function(event) {
            console.log("DEBUG_EVENT: Article content wrapper click listener triggered");
            const targetSentence = event.target.closest('.english-sentence');
            console.log("DEBUG_EVENT: Target sentence found:", !!targetSentence, targetSentence);
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

    // --- Initialization Functions (Order can be important) ---

    // 1. Populate sentence data (from sentences.js)
    console.log("DEBUG_MAIN_BEFORE_POPULATE: sentenceSelectionUIContainer:", typeof sentenceSelectionUIContainer !== 'undefined' && !!sentenceSelectionUIContainer);
    if (typeof populateSentenceElementsArray === 'function') {
        populateSentenceElementsArray();
    } else {
        console.warn("JS_MAIN: populateSentenceElementsArray function not found.");
    }
    console.log("DEBUG_MAIN_AFTER_POPULATE: sentenceSelectionUIContainer:", typeof sentenceSelectionUIContainer !== 'undefined' && !!sentenceSelectionUIContainer);

    // 2. Initialize Sentence Selection UI specific displays (from sentence_selection.js)
    console.log("DEBUG_MAIN_BEFORE_INIT_SENT_DISPLAYS: sentenceSelectionUIContainer:", typeof sentenceSelectionUIContainer !== 'undefined' && !!sentenceSelectionUIContainer);
    if (typeof initializeSentenceSelectionDisplays === 'function') {
        initializeSentenceSelectionDisplays();
    } else {
        console.warn("JS_MAIN: initializeSentenceSelectionDisplays function not found.");
    }
    console.log("DEBUG_MAIN_AFTER_INIT_SENT_DISPLAYS: sentenceSelectionUIContainer:", typeof sentenceSelectionUIContainer !== 'undefined' && !!sentenceSelectionUIContainer);

    // 3. Initialize Audio Context (from audio.js)
    console.log("DEBUG_MAIN_BEFORE_INIT_AUDIO: sentenceSelectionUIContainer:", typeof sentenceSelectionUIContainer !== 'undefined' && !!sentenceSelectionUIContainer);
    if (typeof initAudioContextGlobally === 'function') {
        initAudioContextGlobally();
    } else {
        console.warn("JS_MAIN: initAudioContextGlobally function not found.");
    }
    console.log("DEBUG_MAIN_AFTER_INIT_AUDIO: sentenceSelectionUIContainer:", typeof sentenceSelectionUIContainer !== 'undefined' && !!sentenceSelectionUIContainer);

    // 4. Setup Gamepad (from gamepad.js - this also handles initial icon display)
    console.log("DEBUG_MAIN_BEFORE_SETUP_GAMEPAD: sentenceSelectionUIContainer:", typeof sentenceSelectionUIContainer !== 'undefined' && !!sentenceSelectionUIContainer);
    if (typeof setupGamepadHandlers === 'function') {
        setupGamepadHandlers();
    } else {
        console.warn("JS_MAIN: setupGamepadHandlers function not found.");
        // Fallback for icon if main setup is missing
        if(typeof updateGamepadIconDisplay === 'function') updateGamepadIconDisplay(false);
    }
    console.log("DEBUG_MAIN_AFTER_SETUP_GAMEPAD: sentenceSelectionUIContainer:", typeof sentenceSelectionUIContainer !== 'undefined' && !!sentenceSelectionUIContainer);


    // --- Event Listeners Setup ---

    // Setup Sentence Selection Event Listeners (from sentence_selection.js)
    console.log("DEBUG_MAIN_BEFORE_SETUP_SENT_EVENTS: sentenceSelectionUIContainer:", typeof sentenceSelectionUIContainer !== 'undefined' && !!sentenceSelectionUIContainer);
    if (typeof setupSentenceSelectionEventListeners === 'function') {
        setupSentenceSelectionEventListeners();
    } else {
        console.warn("JS_MAIN: setupSentenceSelectionEventListeners function not found.");
    }
    console.log("DEBUG_MAIN_AFTER_SETUP_SENT_EVENTS: sentenceSelectionUIContainer:", typeof sentenceSelectionUIContainer !== 'undefined' && !!sentenceSelectionUIContainer);

    // Contextual Menu Actions
    if (contextualMenu) { // Ensure direct access for contextualMenu itself
        contextualMenu.addEventListener('click', function(event) {
            event.stopPropagation();
            console.log("DEBUG_CONTEXT_ACTION: Context menu item clicked. Event target:", event.target);
            const actionTarget = event.target.closest('.contextual-menu-item');
            console.log("DEBUG_CONTEXT_ACTION: actionTarget:", actionTarget);

            if (!actionTarget || !highlightedSentence) { // Direct access for highlightedSentence
                if (typeof hideContextualMenu === 'function') hideContextualMenu();
                return;
            }
            // Log details if highlightedSentence is valid
            console.log("DEBUG_CONTEXT_ACTION: highlightedSentence valid:", !!highlightedSentence);
            if(highlightedSentence) {
                console.log("DEBUG_CONTEXT_ACTION: highlightedSentence translation:", highlightedSentence.dataset.translation);
                console.log("DEBUG_CONTEXT_ACTION: highlightedSentence pIndex:", highlightedSentence.dataset.paragraphIndex, "sIndex:", highlightedSentence.dataset.sentenceIndex);
            }

            const action = actionTarget.dataset.action;
            console.log("DEBUG_CONTEXT_ACTION: Action:", action);

            switch (action) {
                case 'show-translation':
                    const translation = highlightedSentence.dataset.translation; // Direct access
                    console.log("DEBUG_CONTEXT_ACTION: Calling displayPopup with target:", highlightedSentence, "and translation:", (highlightedSentence ? highlightedSentence.dataset.translation : "N/A"));
                    if (typeof displayPopup === 'function') displayPopup(highlightedSentence, translation || "No translation available."); // Direct access
                    break;
                case 'save-location':
                    console.log("DEBUG_CONTEXT_ACTION: Calling saveCurrentLocation with pIndex:", (highlightedSentence ? highlightedSentence.dataset.paragraphIndex : "N/A"), "sIndex:", (highlightedSentence ? highlightedSentence.dataset.sentenceIndex : "N/A"));
                    if (typeof saveCurrentLocation === 'function') saveCurrentLocation(parseInt(highlightedSentence.dataset.paragraphIndex), parseInt(highlightedSentence.dataset.sentenceIndex), "manual_menu_save"); // Direct access
                    break;
                case 'play-pause-audio':
                    // This action might be better handled by a dedicated function in audio.js if it gets complex
                    if (typeof initAudioContextGlobally === 'function') initAudioContextGlobally(); // Ensure context
                    let playAsPart = false;
                    let canPlayThis = false;
                    // Direct access for isAudiobookModeFull, audioContext, audioBuffer, HAS_TIMESTAMPS, isAudiobookModeParts, currentLoadedAudioPartIndex
                    if (isAudiobookModeFull && audioContext && audioBuffer && HAS_TIMESTAMPS) {
                        canPlayThis = true; playAsPart = false;
                    } else if (isAudiobookModeParts && audioContext && audioBuffer && HAS_TIMESTAMPS && currentLoadedAudioPartIndex !== -1) {
                        const sentencePartIndex = parseInt(highlightedSentence.dataset.audioPartIndex, 10); // Direct access
                        if (sentencePartIndex === currentLoadedAudioPartIndex) { // Direct access
                            canPlayThis = true; playAsPart = true;
                        }
                    }
                    if (canPlayThis) {
                        const iconSpan = actionTarget.querySelector('.menu-icon');
                        // Direct access for currentPlayingSentence, highlightedSentence, currentSourceNode
                        if (currentPlayingSentence === highlightedSentence && currentSourceNode) {
                            if (typeof stopCurrentAudio === 'function') stopCurrentAudio();
                            if (iconSpan) iconSpan.textContent = "▶️";
                            if (actionTarget) actionTarget.title = "Play Sentence Audio";
                        } else {
                            if (typeof playSentenceAudio === 'function') playSentenceAudio(highlightedSentence, playAsPart); // Direct access
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
                    // Direct access for highlightedSentence and audioBuffer
                    else if (typeof displayWaveform === 'function' && typeof clearExistingWaveform === 'function' && highlightedSentence) {
                        let waveformIsCurrentlyVisible = highlightedSentence.parentElement?.nextElementSibling?.classList.contains('waveform-scroll-container'); // Direct access
                        if (waveformIsCurrentlyVisible) {
                            clearExistingWaveform(highlightedSentence); // Direct access
                        } else {
                            const startTimeMs = parseInt(highlightedSentence.dataset.startTimeMs, 10); // Direct access
                            const endTimeMs = parseInt(highlightedSentence.dataset.endTimeMs, 10); // Direct access
                            if (!isNaN(startTimeMs) && !isNaN(endTimeMs) && audioBuffer) { // Direct access for audioBuffer
                                displayWaveform(highlightedSentence, audioBuffer, startTimeMs, endTimeMs); // Direct access
                            } else {
                                alert("Cannot display waveform: Time data missing or full audio not loaded.");
                            }
                        }
                    } else {
                         console.warn("JS_MAIN: ContextMenu - Waveform edit/display functions not found.");
                    }
                    break;
                case 'set-as-beginning':
                    if (typeof handleSetAsBeginning === 'function') handleSetAsBeginning(highlightedSentence); // Direct access
                    else console.warn("JS_MAIN: ContextMenu - handleSetAsBeginning function not found.");
                    break;
                case 'set-as-ending':
                    if (typeof handleSetAsEnding === 'function') handleSetAsEnding(highlightedSentence); // Direct access
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
        console.log("DEBUG_GLOBAL_CLICK_HIDE_MENU: Checking conditions to hide context menu:");
        console.log("DEBUG_GLOBAL_CLICK_HIDE_MENU: contextualMenu exists:", !!contextualMenu);
        if (contextualMenu) { // Only log style if contextualMenu itself exists
            console.log("DEBUG_GLOBAL_CLICK_HIDE_MENU: contextualMenu.style.display === 'block':", contextualMenu.style.display === 'block');
            console.log("DEBUG_GLOBAL_CLICK_HIDE_MENU: !contextualMenu.contains(event.target):", !contextualMenu.contains(event.target), "event.target:", event.target);
        }
        console.log("DEBUG_GLOBAL_CLICK_HIDE_MENU: !event.target.closest('.english-sentence'):", !event.target.closest('.english-sentence'), "closest sentence:", event.target.closest('.english-sentence'));
        if (contextualMenu && contextualMenu.style.display === 'block' && !contextualMenu.contains(event.target) && !event.target.closest('.english-sentence')) {
            if (typeof hideContextualMenu === 'function') hideContextualMenu();
        }
        // For the popup hiding logic, also ensure contextualMenu is accessed directly
        if (window.popup && window.popup.style.display === 'block' && !window.popup.contains(event.target) && !event.target.closest('.english-sentence') &&
            !(contextualMenu && contextualMenu.style.display === 'block' && contextualMenu.contains(event.target))) {
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
