// static/js/modules/gamepad_controls.js
const GamepadControlsModule = (function() {
    let gamepadStatusEmoji = null;

    // Gamepad State
    let gamepadIndex = null;
    let previousButtonStates = [];
    let animationFrameIdGamepad = null;
    let lastGamepadActionTime = 0;

    // Constants
    const GAMEPAD_ACTION_COOLDOWN = 250; // ms
    const BUTTON_A_INDEX = 0; // Typically 'A' on Xbox, 'Cross' on PlayStation
    const BUTTON_B_INDEX = 1; // Typically 'B' on Xbox, 'Circle' on PlayStation
    const BUTTON_X_INDEX = 2; // Typically 'X' on Xbox, 'Square' on PlayStation
    const BUTTON_Y_INDEX = 3; // Typically 'Y' on Xbox, 'Triangle' on PlayStation

    // Callbacks for actions, to be set in init()
    let _selectNextSentenceFunc = null;
    let _selectPreviousSentenceFunc = null;
    let _playPauseAudioForHighlightedFunc = null; // Plays/pauses audio for the currently highlighted sentence
    let _toggleTranslationForHighlightedFunc = null; // Shows/hides translation for highlighted sentence

    function updateGamepadIconDisplay(isConnected, gamepadId = null) {
        if (!gamepadStatusEmoji) return;

        gamepadStatusEmoji.classList.remove('connected', 'error');
        if (isConnected === true && gamepadId) {
            gamepadStatusEmoji.classList.add('connected');
            gamepadStatusEmoji.setAttribute('title', `Gamepad Connected: ${gamepadId.substring(0, 25)}...`);
        } else if (isConnected === 'error') {
            gamepadStatusEmoji.classList.add('error');
            gamepadStatusEmoji.setAttribute('title', 'Gamepad connection issue');
        } else { // false or other
            gamepadStatusEmoji.setAttribute('title', 'No Gamepad Connected');
        }
    }

    function handleGamepadInput() {
        if (gamepadIndex === null) return;
        const gamepad = navigator.getGamepads()[gamepadIndex];

        if (!gamepad) {
            updateGamepadIconDisplay('error');
            if (animationFrameIdGamepad) cancelAnimationFrame(animationFrameIdGamepad);
            animationFrameIdGamepad = null;
            gamepadIndex = null;
            previousButtonStates = [];
            return;
        }

        // Update icon if it somehow reverted from connected state (e.g. browser glitch)
        if (!gamepadStatusEmoji.classList.contains('connected') && !gamepadStatusEmoji.classList.contains('error')) {
             updateGamepadIconDisplay(true, gamepad.id);
        }

        const now = Date.now();
        let actionTakenThisFrame = false;

        // Button A (Next Sentence)
        if (gamepad.buttons[BUTTON_A_INDEX].pressed && (!previousButtonStates[BUTTON_A_INDEX] || !previousButtonStates[BUTTON_A_INDEX].pressed)) {
            if (now - lastGamepadActionTime > GAMEPAD_ACTION_COOLDOWN) {
                if (_selectNextSentenceFunc) _selectNextSentenceFunc();
                lastGamepadActionTime = now;
                actionTakenThisFrame = true;
            }
        }

        // Button X (Previous Sentence)
        if (gamepad.buttons[BUTTON_X_INDEX].pressed && (!previousButtonStates[BUTTON_X_INDEX] || !previousButtonStates[BUTTON_X_INDEX].pressed)) {
            if (now - lastGamepadActionTime > GAMEPAD_ACTION_COOLDOWN) {
                if (_selectPreviousSentenceFunc) _selectPreviousSentenceFunc();
                lastGamepadActionTime = now;
                actionTakenThisFrame = true;
            }
        }

        // Button B (Play/Pause Audio for Highlighted Sentence)
        if (gamepad.buttons[BUTTON_B_INDEX].pressed && (!previousButtonStates[BUTTON_B_INDEX] || !previousButtonStates[BUTTON_B_INDEX].pressed)) {
             if (now - lastGamepadActionTime > GAMEPAD_ACTION_COOLDOWN || !actionTakenThisFrame) { // Allow B if no other action
                if (_playPauseAudioForHighlightedFunc) _playPauseAudioForHighlightedFunc();
                lastGamepadActionTime = now;
                actionTakenThisFrame = true;
            }
        }

        // Button Y (Toggle Translation for Highlighted Sentence)
        if (gamepad.buttons[BUTTON_Y_INDEX].pressed && (!previousButtonStates[BUTTON_Y_INDEX] || !previousButtonStates[BUTTON_Y_INDEX].pressed)) {
            if (now - lastGamepadActionTime > GAMEPAD_ACTION_COOLDOWN || !actionTakenThisFrame) {
                if (_toggleTranslationForHighlightedFunc) _toggleTranslationForHighlightedFunc();
                lastGamepadActionTime = now;
                // actionTakenThisFrame = true; // Y button often doesn't feel like a primary "action" that needs cooldown as much
            }
        }

        // Update previous button states
        gamepad.buttons.forEach((button, index) => {
            if (!previousButtonStates[index]) previousButtonStates[index] = {};
            previousButtonStates[index].pressed = button.pressed;
        });

        animationFrameIdGamepad = requestAnimationFrame(handleGamepadInput);
    }

    function _onGamepadConnected(event) {
        console.log('GamepadControls: Gamepad connected:', event.gamepad.id);
        // If multiple gamepads, this might pick one. Could be enhanced to select specific.
        if (gamepadIndex === null) { // Only take the first one for now
            gamepadIndex = event.gamepad.index;
            updateGamepadIconDisplay(true, event.gamepad.id);
            const gp = navigator.getGamepads()[gamepadIndex];
            if (gp) {
                previousButtonStates = gp.buttons.map(b => ({ pressed: b.pressed, value: b.value }));
            } else {
                previousButtonStates = []; // Should not happen if event.gamepad is valid
            }
            if (animationFrameIdGamepad) cancelAnimationFrame(animationFrameIdGamepad);
            animationFrameIdGamepad = requestAnimationFrame(handleGamepadInput);
        }
    }

    function _onGamepadDisconnected(event) {
        console.log('GamepadControls: Gamepad disconnected:', event.gamepad.id);
        if (event.gamepad.index === gamepadIndex) { // Check if it's the one we were using
            updateGamepadIconDisplay(false);
            if (animationFrameIdGamepad) cancelAnimationFrame(animationFrameIdGamepad);
            animationFrameIdGamepad = null;
            gamepadIndex = null;
            previousButtonStates = [];
        }
    }

    function _checkForAlreadyConnectedGamepads() {
        const initialGamepads = navigator.getGamepads ? navigator.getGamepads() : [];
        let foundInitialGamepad = false;
        // Handle different browser GamepadList types (array-like vs iterable)
        if (initialGamepads && typeof initialGamepads.forEach === 'function') {
            initialGamepads.forEach(gp => {
                if (gp && !foundInitialGamepad) { // Take the first non-null one
                    _onGamepadConnected(new GamepadEvent("gamepadconnected", { gamepad: gp }));
                    foundInitialGamepad = true;
                }
            });
        } else if (initialGamepads) { // For older array-like GamepadList
            for (let i = 0; i < initialGamepads.length; i++) {
                if (initialGamepads[i] && !foundInitialGamepad) {
                    _onGamepadConnected(new GamepadEvent("gamepadconnected", { gamepad: initialGamepads[i] }));
                    foundInitialGamepad = true;
                    break;
                }
            }
        }
        if (!foundInitialGamepad) {
            updateGamepadIconDisplay(false); // Explicitly set to disconnected if none found
        }
    }


    function init(config) {
        gamepadStatusEmoji = config.elements.gamepadStatusEmoji;

        _selectNextSentenceFunc = config.callbacks.selectNextSentence;
        _selectPreviousSentenceFunc = config.callbacks.selectPreviousSentence;
        _playPauseAudioForHighlightedFunc = config.callbacks.playPauseAudioForHighlighted;
        _toggleTranslationForHighlightedFunc = config.callbacks.toggleTranslationForHighlighted;

        window.addEventListener("gamepadconnected", _onGamepadConnected);
        window.addEventListener("gamepaddisconnected", _onGamepadDisconnected);

        // Check if gamepads are already connected at the time of script load
        // Browsers like Chrome might not fire "gamepadconnected" for already present gamepads until interaction
        _checkForAlreadyConnectedGamepads();
    }

    return {
        init: init,
        // Expose updateGamepadIconDisplay if article_init needs to call it for initial state
        // though _checkForAlreadyConnectedGamepads should handle most initial states.
        // updateGamepadIconDisplay: updateGamepadIconDisplay
    };
})();
