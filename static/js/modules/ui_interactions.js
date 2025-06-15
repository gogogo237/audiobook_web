// static/js/modules/ui_interactions.js
const UIInteractionsModule = (function() {
    let popup = null;
    let contextualMenu = null;
    let goBackButton = null;
    let goToTopButton = null;
    let articleContentWrapper = null;

    let _highlightedSentenceProviderFunc = null; // () => highlightedSentence
    let _lastHighlightedSentenceElementProviderFunc = null; // () => lastHighlightedSentenceElement
    let _setActiveSentenceFunc = null;           // (element, source) => void
    let _saveCurrentLocationFunc = null;         // (pIndex, sIndex, source) => void
    let _playSentenceAudioFunc = null;           // (element, isPlayingFromPart, optionalStartTimeMs) => void
    let _stopCurrentAudioFunc = null;            // () => void
    let _isAudiobookModeFullProviderFunc = null; // () => boolean
    let _isAudiobookModePartsProviderFunc = null; // () => boolean
    let _getAudioBufferProviderFunc = null;      // () => AudioBuffer
    let _getCurrentLoadedAudioPartIndexProviderFunc = null; // () => number
    let _getHasTimestampsProviderFunc = null; // () => boolean
    let _isSentenceSelectionUIVisibleProviderFunc = null; // () => boolean
    let _displayWaveformFunc = null;             // (sentenceElement, audioBuffer, startTimeMs, endTimeMs) => void
    let _clearExistingWaveformFunc = null;       // (sentenceElement) => void
    // Callbacks for sentence selection via context menu
    let _setBeginningSentenceFunc = null; // (sentenceElement) => void
    let _setEndingSentenceFunc = null;   // (sentenceElement) => void
    let _isCurrentSourceNodeActiveFunc = null; // () => boolean (checks if currentSourceNode is active)
    let _getCurrentPlayingSentenceFunc = null; // () => HTMLElement (returns currentPlayingSentence)


    let currentPopupTargetSentence = null;
    let lastScrollTop = 0;
    const SCROLL_THRESHOLD_FOR_GO_TO_TOP = 150; // pixels

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

    function hideTranslationPopup() {
        if (popup) {
            popup.style.display = 'none';
            if (currentPopupTargetSentence && popup.innerHTML === currentPopupTargetSentence.dataset.translation) {
                 currentPopupTargetSentence = null;
            }
        }
    }

    function hideContextualMenu() {
        if (contextualMenu) {
            contextualMenu.style.opacity = '0';
            contextualMenu.style.transform = 'scale(0.95)';
            setTimeout(() => { contextualMenu.style.display = 'none'; }, 100); // Transition time
        }
    }

    function scrollToCenter(element) {
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
        }
    }

    function updateGoBackButtonVisibility() {
        if (!goBackButton) return;
        const lastHighlightedSentenceElement = _lastHighlightedSentenceElementProviderFunc ? _lastHighlightedSentenceElementProviderFunc() : null;
        if (lastHighlightedSentenceElement && (window.scrollY > 100 || document.documentElement.scrollTop > 100)) {
            const sentenceRect = lastHighlightedSentenceElement.getBoundingClientRect();
            // Show if sentence is off-screen OR if scrolled significantly away (more than 1.5 viewport heights)
            if (sentenceRect.bottom < 0 || sentenceRect.top > window.innerHeight ||
                (lastHighlightedSentenceElement.offsetTop > 0 && Math.abs(window.scrollY - lastHighlightedSentenceElement.offsetTop) > window.innerHeight * 1.5)
            ) {
                goBackButton.classList.add('visible');
            } else {
                goBackButton.classList.remove('visible');
            }
        } else {
            goBackButton.classList.remove('visible');
        }
    }

    function updateGoToTopButtonVisibility() {
        if (!goToTopButton) return;
        let st = window.pageYOffset || document.documentElement.scrollTop;
        if (st < lastScrollTop && st > SCROLL_THRESHOLD_FOR_GO_TO_TOP) { // If scrolling UP and past threshold
            goToTopButton.classList.add('visible');
        } else if (st > lastScrollTop || st <= SCROLL_THRESHOLD_FOR_GO_TO_TOP) { // If scrolling DOWN or at top
            goToTopButton.classList.remove('visible');
        }
        lastScrollTop = st <= 0 ? 0 : st;
    }

    function populateAndShowContextualMenu(sentenceElement, clickX) {
        if (!contextualMenu || !sentenceElement) return;

        const highlightedSentence = _highlightedSentenceProviderFunc ? _highlightedSentenceProviderFunc() : null;
        if (sentenceElement !== highlightedSentence) {
            // This case should ideally be handled before calling this,
            // e.g., by setting the active sentence first.
            console.warn("Context menu target doesn't match highlighted sentence.");
            // return;
        }

        let menuHTML = `<div class="contextual-menu-item" data-action="show-translation" title="Show Chinese Translation"><span class="menu-icon">💬</span><span class="menu-text">Translate</span></div>`;
        menuHTML += `<div class="contextual-menu-item" data-action="save-location" title="Save this reading location"><span class="menu-icon">💾</span><span class="menu-text">Save Spot</span></div>`;

        const isAudiobookModeFull = _isAudiobookModeFullProviderFunc ? _isAudiobookModeFullProviderFunc() : false;
        const audioBuffer = _getAudioBufferProviderFunc ? _getAudioBufferProviderFunc() : null;

        if (isAudiobookModeFull && audioBuffer && sentenceElement) {
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
            menuHTML += `<div class="contextual-menu-item" data-action="edit-audio-clip" title="${editActionText} for this sentence"><span class="menu-icon">${editActionIcon}</span><span class="menu-text">${editActionText}</span></div>`;
        }

        const isAudiobookModeParts = _isAudiobookModePartsProviderFunc ? _isAudiobookModePartsProviderFunc() : false;
        const currentLoadedAudioPartIndex = _getCurrentLoadedAudioPartIndexProviderFunc ? _getCurrentLoadedAudioPartIndexProviderFunc() : -1;
        const hasTimestamps = _getHasTimestampsProviderFunc ? _getHasTimestampsProviderFunc() : false;

        const canPlayAudio = (isAudiobookModeFull && audioBuffer && hasTimestamps) ||
                             (isAudiobookModeParts && audioBuffer && hasTimestamps && currentLoadedAudioPartIndex !== -1 &&
                              sentenceElement.dataset.audioPartIndex !== undefined && parseInt(sentenceElement.dataset.audioPartIndex, 10) === currentLoadedAudioPartIndex);

        if (canPlayAudio) {
            let audioIcon = "▶️";
            let audioTitle = "Play Sentence Audio";
            const currentPlayingSentence = _getCurrentPlayingSentenceFunc ? _getCurrentPlayingSentenceFunc() : null;
            const isCurrentSourceActive = _isCurrentSourceNodeActiveFunc ? _isCurrentSourceNodeActiveFunc() : false;

            if (currentPlayingSentence === sentenceElement && isCurrentSourceActive) {
                audioIcon = "⏹️";
                audioTitle = "Stop Sentence Audio";
            }
            menuHTML += `<div class="contextual-menu-item" data-action="play-pause-audio" title="${audioTitle}"><span class="menu-icon">${audioIcon}</span><span class="menu-text">Audio</span></div>`;
        }

        const isSentenceSelectionUIVisible = _isSentenceSelectionUIVisibleProviderFunc ? _isSentenceSelectionUIVisibleProviderFunc() : false;
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
        let menuLeft = clickX + window.scrollX - (contextualMenu.offsetWidth / 2); // Initial centered attempt

        // Adjust if too close to edges
        if (menuLeft < 10) menuLeft = 10;
        if (menuLeft + contextualMenu.offsetWidth > window.innerWidth - 10) {
            menuLeft = window.innerWidth - 10 - contextualMenu.offsetWidth;
        }
        // Adjust if menu goes below viewport fold
        if (menuTop + contextualMenu.offsetHeight > window.innerHeight + window.scrollY - 10) {
            menuTop = rect.top + window.scrollY - contextualMenu.offsetHeight - 5; // Place above
        }

        contextualMenu.style.top = menuTop + 'px';
        contextualMenu.style.left = menuLeft + 'px';
        contextualMenu.style.display = 'block';
        setTimeout(() => { // For CSS transition
             contextualMenu.style.opacity = '1';
             contextualMenu.style.transform = 'scale(1)';
        }, 10);
    }

    function _handleArticleContentWrapperContextClick(event, isContextMenu) {
        const targetSentence = event.target.closest('.english-sentence');
        const highlightedSentence = _highlightedSentenceProviderFunc ? _highlightedSentenceProviderFunc() : null;

        if (targetSentence) {
            if (isContextMenu) event.preventDefault();
            event.stopPropagation(); // Stop propagation for both click types if on a sentence

            hideTranslationPopup(); // Hide translation first

            if (highlightedSentence !== targetSentence) {
                if (_setActiveSentenceFunc) _setActiveSentenceFunc(targetSentence, isContextMenu ? "contextmenu_highlight" : "click_new_sentence");
            } else {
                // If it's the same sentence, ensure it's centered (especially for context menu)
                if (isContextMenu) scrollToCenter(targetSentence);
            }

            // Now, decide what to do based on click type
            if (isContextMenu) { // Right-click
                populateAndShowContextualMenu(targetSentence, event.clientX);
            } else { // Left-click
                if (highlightedSentence === targetSentence) { // Clicked on already highlighted sentence
                    if (contextualMenu.style.display === 'block' && contextualMenu.style.opacity === '1') {
                        hideContextualMenu();
                    } else {
                        populateAndShowContextualMenu(targetSentence, event.clientX);
                    }
                } else {
                    // If it was a new sentence, setActiveSentence was already called.
                    // Now, decide if we should play audio or show context menu.
                    // Current behavior: play audio if not waveform, otherwise new sentence is just highlighted.
                    // For this refactor, let's stick to: new sentence click just highlights and hides menus.
                    // If audio playback on new sentence click is desired, audio_playback module can listen for a custom event.
                    hideContextualMenu();

                    // The original code had logic to play audio here if it's not a waveform.
                    // This is better handled by the audio module or by specific interactions.
                    // For now, simply highlighting and hiding menus is the main action.
                }
            }
        } else { // Click was not on a sentence (inside wrapper but outside any sentence span)
            if (!contextualMenu.contains(event.target)) hideContextualMenu();
            if (!popup.contains(event.target)) hideTranslationPopup();
        }
    }


    function init(config) {
        popup = config.elements.popup;
        contextualMenu = config.elements.contextualMenu;
        goBackButton = config.elements.goBackButton;
        goToTopButton = config.elements.goToTopButton;
        articleContentWrapper = config.elements.articleContentWrapper;

        _highlightedSentenceProviderFunc = config.providers.getHighlightedSentence;
        _lastHighlightedSentenceElementProviderFunc = config.providers.getLastHighlightedSentenceElement;
        _setActiveSentenceFunc = config.callbacks.setActiveSentence;
        _saveCurrentLocationFunc = config.callbacks.saveCurrentLocation;
        _playSentenceAudioFunc = config.callbacks.playSentenceAudio;
        _stopCurrentAudioFunc = config.callbacks.stopCurrentAudio;
        _isAudiobookModeFullProviderFunc = config.providers.isAudiobookModeFull;
        _isAudiobookModePartsProviderFunc = config.providers.isAudiobookModeParts;
        _getAudioBufferProviderFunc = config.providers.getAudioBuffer;
        _getCurrentLoadedAudioPartIndexProviderFunc = config.providers.getCurrentLoadedAudioPartIndex;
        _getHasTimestampsProviderFunc = config.providers.getHasTimestamps;
        _isSentenceSelectionUIVisibleProviderFunc = config.providers.isSentenceSelectionUIVisible;
        _displayWaveformFunc = config.callbacks.displayWaveform;
        _clearExistingWaveformFunc = config.callbacks.clearExistingWaveform;
        _setBeginningSentenceFunc = config.callbacks.setBeginningSentence;
        _setEndingSentenceFunc = config.callbacks.setEndingSentence;
        _isCurrentSourceNodeActiveFunc = config.providers.isCurrentSourceNodeActive;
        _getCurrentPlayingSentenceFunc = config.providers.getCurrentPlayingSentence;


        if (articleContentWrapper) {
            articleContentWrapper.addEventListener('contextmenu', function(event) {
                 _handleArticleContentWrapperContextClick(event, true);
            });
            articleContentWrapper.addEventListener('click', function(event) {
                 _handleArticleContentWrapperContextClick(event, false);
            });
        }

        if (contextualMenu) {
            contextualMenu.addEventListener('click', function(event) {
                event.stopPropagation(); // Prevent document click listener from hiding menu immediately
                const actionTarget = event.target.closest('.contextual-menu-item');
                const highlightedSentence = _highlightedSentenceProviderFunc ? _highlightedSentenceProviderFunc() : null;

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
                        if (_saveCurrentLocationFunc) {
                            const pIndex = highlightedSentence.dataset.paragraphIndex;
                            const sIndex = highlightedSentence.dataset.sentenceIndex;
                            if (pIndex !== undefined && sIndex !== undefined) {
                                _saveCurrentLocationFunc(parseInt(pIndex, 10), parseInt(sIndex, 10), "manual_menu_save");
                            }
                        }
                        break;
                    case 'play-pause-audio':
                        const isAudiobookModeFull = _isAudiobookModeFullProviderFunc ? _isAudiobookModeFullProviderFunc() : false;
                        const isAudiobookModeParts = _isAudiobookModePartsProviderFunc ? _isAudiobookModePartsProviderFunc() : false;
                        const audioBuffer = _getAudioBufferProviderFunc ? _getAudioBufferProviderFunc() : null;
                        const hasTimestamps = _getHasTimestampsProviderFunc ? _getHasTimestampsProviderFunc() : false;
                        const currentLoadedAudioPartIndex = _getCurrentLoadedAudioPartIndexProviderFunc ? _getCurrentLoadedAudioPartIndexProviderFunc() : -1;
                        const currentPlayingSentence = _getCurrentPlayingSentenceFunc ? _getCurrentPlayingSentenceFunc() : null;
                        const isCurrentSourceActive = _isCurrentSourceNodeActiveFunc ? _isCurrentSourceNodeActiveFunc() : false;

                        let playAsPart = false;
                        let canPlayThis = false;

                        if (isAudiobookModeFull && audioBuffer && hasTimestamps) {
                            canPlayThis = true; playAsPart = false;
                        } else if (isAudiobookModeParts && audioBuffer && hasTimestamps && currentLoadedAudioPartIndex !== -1) {
                            const sentencePartIndex = parseInt(highlightedSentence.dataset.audioPartIndex, 10);
                            if (sentencePartIndex === currentLoadedAudioPartIndex) {
                                canPlayThis = true; playAsPart = true;
                            }
                        }

                        if (canPlayThis) {
                            const iconSpan = actionTarget.querySelector('.menu-icon');
                            if (currentPlayingSentence === highlightedSentence && isCurrentSourceActive) {
                                if (_stopCurrentAudioFunc) _stopCurrentAudioFunc();
                                if (iconSpan) iconSpan.textContent = "▶️";
                                if (actionTarget) actionTarget.title = "Play Sentence Audio";
                            } else {
                                if (_playSentenceAudioFunc) _playSentenceAudioFunc(highlightedSentence, playAsPart, null);
                                if (iconSpan) iconSpan.textContent = "⏹️";
                                 if (actionTarget) actionTarget.title = "Stop Sentence Audio";
                            }
                        } else { alert("Audio not ready or sentence part mismatch."); }
                        break;
                    case 'edit-audio-clip':
                        if (!highlightedSentence) break;
                        let waveformIsCurrentlyVisible = false;
                        if (highlightedSentence.parentElement) {
                            const potentialContainer = highlightedSentence.parentElement.nextElementSibling;
                            if (potentialContainer && potentialContainer.classList.contains('waveform-scroll-container')) {
                                waveformIsCurrentlyVisible = true;
                            }
                        }
                        if (waveformIsCurrentlyVisible) {
                            if (_clearExistingWaveformFunc) _clearExistingWaveformFunc(highlightedSentence);
                            // Reset context menu item text/icon if it's still visible for this sentence
                            const editClipMenuItem = contextualMenu.querySelector('.contextual-menu-item[data-action="edit-audio-clip"]');
                            if (editClipMenuItem) {
                                const menuIcon = editClipMenuItem.querySelector('.menu-icon');
                                const menuText = editClipMenuItem.querySelector('.menu-text');
                                if (menuIcon) menuIcon.innerHTML = '✏️';
                                if (menuText) menuText.innerHTML = 'Edit Clip';
                                editClipMenuItem.title = 'Edit Clip for this sentence';
                            }
                        } else {
                            const currentAudioBuffer = _getAudioBufferProviderFunc ? _getAudioBufferProviderFunc() : null;
                            if (!currentAudioBuffer) {
                                alert("Full audio buffer is not loaded. Please load the audio in 'Audiobook Mode (Full Audio)' first.");
                                break;
                            }
                            const startTimeMs = parseInt(highlightedSentence.dataset.startTimeMs, 10);
                            const endTimeMs = parseInt(highlightedSentence.dataset.endTimeMs, 10);
                            if (isNaN(startTimeMs) || isNaN(endTimeMs)) {
                                alert("Sentence is missing valid time data for waveform display."); break;
                            }
                            if (_displayWaveformFunc) _displayWaveformFunc(highlightedSentence, currentAudioBuffer, startTimeMs, endTimeMs);
                             // Update context menu item text/icon
                            const editClipMenuItem = contextualMenu.querySelector('.contextual-menu-item[data-action="edit-audio-clip"]');
                            if (editClipMenuItem) {
                                const menuIcon = editClipMenuItem.querySelector('.menu-icon');
                                const menuText = editClipMenuItem.querySelector('.menu-text');
                                if (menuIcon) menuIcon.innerHTML = '🗑️'; // Trash can icon
                                if (menuText) menuText.innerHTML = 'Hide Waveform';
                                editClipMenuItem.title = 'Hide Waveform for this sentence';
                            }
                        }
                        break;
                    case 'set-as-beginning':
                        if (_setBeginningSentenceFunc) _setBeginningSentenceFunc(highlightedSentence);
                        break;
                    case 'set-as-ending':
                        if (_setEndingSentenceFunc) _setEndingSentenceFunc(highlightedSentence);
                        break;
                }
                // Hide menu unless it was a submenu parent click
                if (action !== 'assign-sentence-submenu') {
                     hideContextualMenu();
                }
            });
        }

        // Global click listener to hide popups if click is outside
        document.addEventListener('click', function(event) {
            const isClickInsideMenu = contextualMenu && contextualMenu.style.display === 'block' && contextualMenu.contains(event.target);
            const isClickInsidePopup = popup && popup.style.display === 'block' && popup.contains(event.target);
            const isClickOnSentence = event.target.closest('.english-sentence');

            if (!isClickInsideMenu && !isClickOnSentence) {
                hideContextualMenu();
            }
            if (!isClickInsidePopup && !isClickOnSentence && !isClickInsideMenu) {
                // (don't hide popup if click was to open context menu on same sentence)
                if (currentPopupTargetSentence && event.target.closest('.english-sentence') === currentPopupTargetSentence &&
                    contextualMenu.style.display === 'block') {
                    // This case is tricky: if popup is for sentence X, and user right-clicks X to open menu, don't hide popup.
                    // The current logic in _handleArticleContentWrapperContextClick already hides previous popup.
                } else {
                    hideTranslationPopup();
                }
            }
        });

        if (goBackButton) {
            goBackButton.addEventListener('click', function() {
                const lastHighlightedSentenceElement = _lastHighlightedSentenceElementProviderFunc ? _lastHighlightedSentenceElementProviderFunc() : null;
                if (lastHighlightedSentenceElement && _setActiveSentenceFunc) {
                    _setActiveSentenceFunc(lastHighlightedSentenceElement, "go_back_button");
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

        // Initial visibility updates
        updateGoBackButtonVisibility();
        updateGoToTopButtonVisibility();
    }

    return {
        init: init,
        displayPopup: displayPopup, // May be called by other modules (e.g. gamepad)
        hideTranslationPopup: hideTranslationPopup, // May be called by other modules
        hideContextualMenu: hideContextualMenu // May be called by other modules
        // populateAndShowContextualMenu is mostly internal, triggered by events
    };
})();
