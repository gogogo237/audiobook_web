// static/js/article_view_config.js
// This file should be loaded before other article_view_*.js files

// --- Retrieve Python Data ---
let articleData = {};
const articleDataElement = document.getElementById('article-data-json');
console.log("CONFIG_DEBUG: articleDataElement found:", !!articleDataElement);
if (articleDataElement) {
    try {
        articleData = JSON.parse(articleDataElement.textContent);
    } catch (e) {
        console.error("JS: Error parsing article data JSON:", e);
        articleData = {
            articleId: null, hasTimestamps: false, numAudioParts: 0,
            initialReadingLocation: null, articleAudioPartChecksums: null,
            convertedMp3Path: null, mp3PartsFolderPath: null
        };
    }
} else {
    console.error("JS: article-data-json element not found. Initializing articleData to default.");
    articleData = {
        articleId: null, hasTimestamps: false, numAudioParts: 0,
        initialReadingLocation: null, articleAudioPartChecksums: null,
        convertedMp3Path: null, mp3PartsFolderPath: null
    };
}
console.log("CONFIG_DEBUG: Raw articleData:", articleData);

// --- Global Constants ---
const ARTICLE_ID = articleData.articleId;
console.log("CONFIG_DEBUG: ARTICLE_ID initialized as:", ARTICLE_ID);
const HAS_TIMESTAMPS = articleData.hasTimestamps;
const NUM_AUDIO_PARTS = parseInt(articleData.numAudioParts, 10) || 0;
const INITIAL_READING_LOCATION = articleData.initialReadingLocation;
const ARTICLE_AUDIO_PART_CHECKSUMS_STR = articleData.articleAudioPartChecksums;
const AUDIO_PART_CHECKSUM_DELIMITER_JS = ";";
let expectedChecksumsArray = [];
if (ARTICLE_AUDIO_PART_CHECKSUMS_STR && typeof ARTICLE_AUDIO_PART_CHECKSUMS_STR === 'string') {
    expectedChecksumsArray = ARTICLE_AUDIO_PART_CHECKSUMS_STR.split(AUDIO_PART_CHECKSUM_DELIMITER_JS);
}

// --- DOM Elements ---
const articleContentWrapper = document.getElementById('article-content-wrapper');
console.log("CONFIG_DEBUG: articleContentWrapper found:", !!articleContentWrapper);
const popup = document.getElementById('translation-popup');
const contextualMenu = document.getElementById('contextual-menu');
const goBackButton = document.getElementById('goBackButton');
const goToTopButton = document.getElementById('goToTopButton');
const restoreLocationButton = document.getElementById('restoreLocationButton');
const gamepadStatusEmoji = document.getElementById('gamepad-status-emoji');

// --- Sentence Selection UI Elements ---
const toggleSentenceSelectionBtn = document.getElementById('toggle-sentence-selection-btn');
console.log("CONFIG_DEBUG: toggleSentenceSelectionBtn found:", !!toggleSentenceSelectionBtn);
const sentenceSelectionUIContainer = document.getElementById('sentence-selection-ui-container');
console.log("CONFIG_DEBUG: sentenceSelectionUIContainer found:", !!sentenceSelectionUIContainer);
const beginningSentenceDisplay = document.getElementById('beginning-sentence-display');
const endingSentenceDisplay = document.getElementById('ending-sentence-display');
const executeSentenceTaskBtn = document.getElementById('execute-sentence-task-btn');
if (executeSentenceTaskBtn) {
    executeSentenceTaskBtn.textContent = "Update Timestamps for Selection";
}
console.log("CONFIG_DEBUG: executeSentenceTaskBtn found:", !!executeSentenceTaskBtn);
const distributeTimestampsBtn = document.getElementById('distribute-timestamps-btn');
console.log("CONFIG_DEBUG: distributeTimestampsBtn found:", !!distributeTimestampsBtn);

// --- Audiobook Mode UI Elements ---
const toggleAudiobookModeButton = document.getElementById('toggleAudiobookMode');
const localAudioFileInput = document.getElementById('localAudioFile');
const audioFileNameSpan = document.getElementById('audioFileName');
const audiobookHint = document.getElementById('audiobookHint');

// --- Audio Parts View UI Elements ---
const switchToPartsViewButton = document.getElementById('switchToPartsViewButton');
const switchToFullViewButton = document.getElementById('switchToFullViewButton');
const fullAudioViewControls = document.getElementById('full-audio-view-controls');
const partsAudioViewControls = document.getElementById('parts-audio-view-controls');
const fullAudioDownloadDiv = document.getElementById('full-audio-download');
const partsAudioDownloadDiv = document.getElementById('parts-audio-download');
const loadSelectedAudioPartButton = document.getElementById('loadSelectedAudioPartButton');
const loadLocalAudioPartButton = document.getElementById('loadLocalAudioPartButton');
const localAudioPartFileInput = document.getElementById('localAudioPartFileInput');
const downloadSelectedAudioPartButton = document.getElementById('downloadSelectedAudioPartButton');
const loadedAudioPartNameSpan = document.getElementById('loadedAudioPartName');

// --- State Variables related to UI elements/state primarily used by UI functions ---
let currentPopupTargetSentence = null; // Used by displayPopup, hideTranslationPopup (in ui.js)
let lastScrollTop = 0; // Used by updateGoToTopButtonVisibility (in ui.js)
const scrollThresholdForGoToTop = 150; // Used by updateGoToTopButtonVisibility (in ui.js)

// --- Debug Logging for DOM Elements in Config ---
// console.log("DEBUG_CONFIG: articleContentWrapper:", !!articleContentWrapper);
// console.log("DEBUG_CONFIG: popup:", !!popup);
// console.log("DEBUG_CONFIG: contextualMenu:", !!contextualMenu);
// console.log("DEBUG_CONFIG: goBackButton:", !!goBackButton);
// console.log("DEBUG_CONFIG: goToTopButton:", !!goToTopButton);
// console.log("DEBUG_CONFIG: restoreLocationButton:", !!restoreLocationButton);
// console.log("DEBUG_CONFIG: gamepadStatusEmoji:", !!gamepadStatusEmoji);
// console.log("DEBUG_CONFIG: toggleSentenceSelectionBtn:", !!toggleSentenceSelectionBtn);
// console.log("DEBUG_CONFIG: sentenceSelectionUIContainer:", !!sentenceSelectionUIContainer);
// console.log("DEBUG_CONFIG: beginningSentenceDisplay:", !!beginningSentenceDisplay);
// console.log("DEBUG_CONFIG: endingSentenceDisplay:", !!endingSentenceDisplay);
// console.log("DEBUG_CONFIG: executeSentenceTaskBtn:", !!executeSentenceTaskBtn);
// console.log("DEBUG_CONFIG: distributeTimestampsBtn:", !!distributeTimestampsBtn);
// console.log("DEBUG_CONFIG: toggleAudiobookModeButton:", !!toggleAudiobookModeButton);
// console.log("DEBUG_CONFIG: localAudioFileInput:", !!localAudioFileInput);
// console.log("DEBUG_CONFIG: audioFileNameSpan:", !!audioFileNameSpan);
// console.log("DEBUG_CONFIG: audiobookHint:", !!audiobookHint);
// console.log("DEBUG_CONFIG: switchToPartsViewButton:", !!switchToPartsViewButton);
// console.log("DEBUG_CONFIG: switchToFullViewButton:", !!switchToFullViewButton);
// console.log("DEBUG_CONFIG: fullAudioViewControls:", !!fullAudioViewControls);
// console.log("DEBUG_CONFIG: partsAudioViewControls:", !!partsAudioViewControls);
// console.log("DEBUG_CONFIG: fullAudioDownloadDiv:", !!fullAudioDownloadDiv);
// console.log("DEBUG_CONFIG: partsAudioDownloadDiv:", !!partsAudioDownloadDiv);
// console.log("DEBUG_CONFIG: loadSelectedAudioPartButton:", !!loadSelectedAudioPartButton);
// console.log("DEBUG_CONFIG: loadLocalAudioPartButton:", !!loadLocalAudioPartButton);
// console.log("DEBUG_CONFIG: localAudioPartFileInput:", !!localAudioPartFileInput);
// console.log("DEBUG_CONFIG: downloadSelectedAudioPartButton:", !!downloadSelectedAudioPartButton);
// console.log("DEBUG_CONFIG: loadedAudioPartNameSpan:", !!loadedAudioPartNameSpan);

// --- Constants for Gamepad (might move to gamepad.js later if it becomes complex) ---
const GAMEPAD_ACTION_COOLDOWN = 250;
const BUTTON_A_INDEX = 0;
const BUTTON_B_INDEX = 1;
const BUTTON_X_INDEX = 2;
const BUTTON_Y_INDEX = 3;

// --- Constants for Audio Processing ---
const CLICK_THRESHOLD_AUTOSAVE = 5; // For auto-saving reading location
const WAVEFORM_MS_PER_PIXEL = 10; // Each pixel represents 10ms of audio (original)

// --- Constants for Sentence Selection ---
const placeholderBeginning = "No beginning sentence selected.";
const placeholderEnding = "No ending sentence selected.";

// --- Global State Variables (to be evaluated if they belong here or in main.js) ---
// These are more general state, not directly tied to a single DOM element's config
let highlightedSentence = null;
let lastHighlightedSentenceElement = null; // Used by UI helper updateGoBackButtonVisibility
let sentenceElementsArray = []; // Populated in main, used by many functions
let audioContext = null; // Global AudioContext
let audioBuffer = null;  // Global AudioBuffer (for full or part audio)
let currentSourceNode = null; // Current playing AudioBufferSourceNode
let isAudiobookModeFull = false;
let isAudiobookModeParts = false;
let currentPlayingSentence = null;
let maxSentenceEndTime = 0; // Calculated once, based on HAS_TIMESTAMPS
let currentLoadedAudioPartIndex = -1; // For parts mode
let validClickCounter = 0; // For auto-save reading location

// Sentence Selection State (might move to sentence_selection.js)
let isSentenceSelectionUIVisible = false;
let beginningSentenceText = "";
let endingSentenceText = "";
let beginningSentenceElement = null;
let endingSentenceElement = null;

// Gamepad State (might move to gamepad.js)
let gamepadIndex = null;
let previousButtonStates = [];
let animationFrameIdGamepad = null;
let lastGamepadActionTime = 0;

// Audio Parts View State (might move to audio_parts.js)
let isPartsViewActive = false; // Initial state, can be overridden by iOS check in main
