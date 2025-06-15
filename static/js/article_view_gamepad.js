// static/js/article_view_gamepad.js
// Depends on:
// - article_view_config.js (for gamepadIndex, previousButtonStates, animationFrameIdGamepad, lastGamepadActionTime, GAMEPAD_ACTION_COOLDOWN, BUTTON_A_INDEX, etc., gamepadStatusEmoji, highlightedSentence, popup, currentPopupTargetSentence)
// - article_view_sentences.js (for selectNextSentence, selectPreviousSentence)
// - article_view_ui.js (for displayPopup, hideTranslationPopup)
// - article_view_audio.js (for playSentenceAudio, initAudioContextGlobally - though initAudioContextGlobally might be called by playSentenceAudio itself)

// All state variables (gamepadIndex, etc.) and constants (GAMEPAD_ACTION_COOLDOWN, etc.)
// are expected to be defined in article_view_config.js and accessed via the window object.

function updateGamepadIconDisplay(isConnected, gamepadId = null) {
    // Uses global: gamepadStatusEmoji (from config.js)
    if (window.gamepadStatusEmoji) {
        window.gamepadStatusEmoji.classList.remove('connected', 'error');
        if (isConnected && gamepadId) {
            window.gamepadStatusEmoji.classList.add('connected');
            window.gamepadStatusEmoji.setAttribute('title', `Gamepad Connected: ${gamepadId.substring(0,25)}...`);
        } else if (isConnected === 'error') { // Special case for error state
            window.gamepadStatusEmoji.classList.add('error');
            window.gamepadStatusEmoji.setAttribute('title', 'Gamepad connection issue');
        } else {
            window.gamepadStatusEmoji.setAttribute('title', 'No Gamepad Connected');
        }
    }
}

function handleGamepadInput() {
    // Uses global state: gamepadIndex, animationFrameIdGamepad, previousButtonStates, lastGamepadActionTime, GAMEPAD_ACTION_COOLDOWN (from config.js)
    // Uses global DOM: gamepadStatusEmoji (from config.js)
    // Calls functions: updateGamepadIconDisplay (this file), selectNextSentence, selectPreviousSentence (from sentences.js),
    //                  playSentenceAudio (from audio.js), displayPopup, hideTranslationPopup (from ui.js)
    // Accesses global state: highlightedSentence, popup, currentPopupTargetSentence, isAudiobookModeParts, currentLoadedAudioPartIndex (from config.js)


    if (window.gamepadIndex === null) return;
    const gamepad = navigator.getGamepads()[window.gamepadIndex];

    if (!gamepad) {
        updateGamepadIconDisplay('error'); // Pass 'error' to indicate a problem
        if (window.animationFrameIdGamepad) cancelAnimationFrame(window.animationFrameIdGamepad);
        window.animationFrameIdGamepad = null;
        window.gamepadIndex = null;
        window.previousButtonStates = [];
        return;
    }

    // Update icon if it's not already showing connected/error (e.g. if it was cleared by disconnect)
    if (window.gamepadStatusEmoji && !window.gamepadStatusEmoji.classList.contains('connected') && !window.gamepadStatusEmoji.classList.contains('error')) {
         updateGamepadIconDisplay(true, gamepad.id);
    }

    const now = Date.now();
    // Check for cooldown first to avoid processing multiple events if already on cooldown
    if (now - window.lastGamepadActionTime < window.GAMEPAD_ACTION_COOLDOWN) {
        window.animationFrameIdGamepad = requestAnimationFrame(handleGamepadInput);
        return;
    }

    let actionTaken = false;

    if (gamepad.buttons[window.BUTTON_A_INDEX].pressed && (!window.previousButtonStates[window.BUTTON_A_INDEX] || !window.previousButtonStates[window.BUTTON_A_INDEX].pressed)) {
        if (typeof selectNextSentence === "function") selectNextSentence(); else console.warn("JS_GAMEPAD: selectNextSentence not found");
        actionTaken = true;
    } else if (gamepad.buttons[window.BUTTON_X_INDEX].pressed && (!window.previousButtonStates[window.BUTTON_X_INDEX] || !window.previousButtonStates[window.BUTTON_X_INDEX].pressed)) {
        if (typeof selectPreviousSentence === "function") selectPreviousSentence(); else console.warn("JS_GAMEPAD: selectPreviousSentence not found");
        actionTaken = true;
    } else if (gamepad.buttons[window.BUTTON_B_INDEX].pressed && (!window.previousButtonStates[window.BUTTON_B_INDEX] || !window.previousButtonStates[window.BUTTON_B_INDEX].pressed)) {
        if (window.highlightedSentence) {
            // Ensure audio context is ready (playSentenceAudio should handle this internally too)
            if(typeof initAudioContextGlobally === 'function') initAudioContextGlobally();

            let playAsPart = false;
            let canPlayThisSentence = false;

            if (window.isAudiobookModeParts && window.currentLoadedAudioPartIndex !== -1 &&
                window.highlightedSentence.dataset.audioPartIndex !== undefined &&
                parseInt(window.highlightedSentence.dataset.audioPartIndex, 10) === window.currentLoadedAudioPartIndex) {
                playAsPart = true;
                canPlayThisSentence = window.audioContext && window.audioBuffer;
            } else if (window.isAudiobookModeFull) {
                playAsPart = false;
                canPlayThisSentence = window.audioContext && window.audioBuffer;
            }

            if (canPlayThisSentence && typeof playSentenceAudio === "function") {
                playSentenceAudio(window.highlightedSentence, playAsPart);
            } else {
                // console.warn("JS_GAMEPAD: B button - Audio not ready or conditions not met.");
            }
        }
        actionTaken = true;
    } else if (gamepad.buttons[window.BUTTON_Y_INDEX].pressed && (!window.previousButtonStates[window.BUTTON_Y_INDEX] || !window.previousButtonStates[window.BUTTON_Y_INDEX].pressed)) {
        if (window.highlightedSentence) {
            if (window.popup && window.popup.style.display === 'block' && window.currentPopupTargetSentence === window.highlightedSentence) {
                if(typeof hideTranslationPopup === "function") hideTranslationPopup(); else console.warn("JS_GAMEPAD: hideTranslationPopup not found");
            } else {
                const translation = window.highlightedSentence.dataset.translation;
                if(typeof displayPopup === "function") displayPopup(window.highlightedSentence, translation || "No translation available."); else console.warn("JS_GAMEPAD: displayPopup not found");
            }
        }
        actionTaken = true;
    }

    if(actionTaken){
        window.lastGamepadActionTime = now;
    }

    gamepad.buttons.forEach((button, index) => {
        if (!window.previousButtonStates[index]) window.previousButtonStates[index] = {};
        window.previousButtonStates[index].pressed = button.pressed;
    });

    window.animationFrameIdGamepad = requestAnimationFrame(handleGamepadInput);
}

function setupGamepadHandlers() {
    window.addEventListener("gamepadconnected", (event) => {
        console.log('JS_GAMEPAD: Gamepad connected:', event.gamepad.id);
        updateGamepadIconDisplay(true, event.gamepad.id);
        window.gamepadIndex = event.gamepad.index;
        const gp = navigator.getGamepads()[window.gamepadIndex];
        window.previousButtonStates = gp ? gp.buttons.map(b => ({ pressed: b.pressed })) : [];
        if (window.animationFrameIdGamepad) cancelAnimationFrame(window.animationFrameIdGamepad);
        window.animationFrameIdGamepad = requestAnimationFrame(handleGamepadInput);
    });

    window.addEventListener("gamepaddisconnected", (event) => {
        console.log('JS_GAMEPAD: Gamepad disconnected:', event.gamepad.id);
        if (event.gamepad.index === window.gamepadIndex) {
            updateGamepadIconDisplay(false);
            if (window.animationFrameIdGamepad) cancelAnimationFrame(window.animationFrameIdGamepad);
            window.animationFrameIdGamepad = null;
            window.gamepadIndex = null;
            window.previousButtonStates = [];
        }
    });

    // Initial gamepad detection
    const initialGamepads = navigator.getGamepads ? navigator.getGamepads() : (navigator.webkitGetGamepads ? navigator.webkitGetGamepads() : []);
    let foundInitialGamepad = false;
    if (initialGamepads) { // Check if initialGamepads is not null
        for (let i = 0; i < initialGamepads.length; i++) {
            if (initialGamepads[i]) { // Check if specific gamepad entry is not null
                // Dispatch a new GamepadEvent. Note: The GamepadEvent constructor might not be available in all environments or might need a polyfill.
                // However, for modern browsers, this should generally work for re-triggering the connection logic.
                try {
                    const connectEvent = new GamepadEvent("gamepadconnected", { gamepad: initialGamepads[i] });
                    window.dispatchEvent(connectEvent);
                    foundInitialGamepad = true;
                    console.log("JS_GAMEPAD: Initial gamepad check - dispatched connection for:", initialGamepads[i].id);
                    break; // Found one, no need to check others
                } catch (e) {
                    console.warn("JS_GAMEPAD: Could not dispatch GamepadEvent for initial check (อาจจะไม่ใช่ปัญหาใหญ่):", e);
                    // Fallback for environments where GamepadEvent constructor is problematic
                    // Directly call parts of the connection logic if necessary, though this is less clean.
                    // For now, we rely on the event dispatch.
                }
            }
        }
    }
    if (!foundInitialGamepad) {
        updateGamepadIconDisplay(false); // Ensure icon is set to disconnected if no gamepads found initially
    }
}
