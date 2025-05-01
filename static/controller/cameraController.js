/**
 * CameraController.js
 * 
 * A comprehensive JavaScript class to handle camera and audio streaming,
 * camera settings, recording, and device management for the camera application.
 */
class CameraController {
    /**
     * Initialize the CameraController with configuration options
     * @param {Object} options - Configuration options
     * @param {string} options.videoElementId - ID of the video element for displaying the camera stream
     * @param {string} options.audioElementId - ID of the audio element for playing audio
     * @param {string} options.streamUrl - URL for the video stream
     * @param {string} options.audioStreamUrl - URL for the audio stream
     * @param {Object} options.endpoints - API endpoint URLs
     * @param {Array} options.settingsFields - Camera settings fields available for adjustment
     */
    constructor(options) {
      // Required parameters
      this.videoElementId = options.videoElementId || 'camera-stream';
      this.audioElementId = options.audioElementId || 'audio-stream';
      this.streamUrl = options.streamUrl || '/api/stream';
      this.audioStreamUrl = options.audioStreamUrl || '/api/stream/audio';
      
      // API endpoints
      this.endpoints = {
        setSetting: '/set', // Base URL, will append /{setting}/ in the method
        capture: '/capture/',
        startRecord: '/record/start/',
        stopRecord: '/record/stop/',
        cameraFrame: '/camera-frame/',
        switchCamera: '/switch/', // Will append /{idx}/
        switchAudio: '/api/switch-audio/', // Will append /{idx}/
        restart: '/restart/',
        refreshDevices: '/refresh-devices/',
        audioSources: '/api/audio-sources/',
        ...options.endpoints || {}
      };
      
      // Settings
      this.settingsFields = options.settingsFields || [
        'brightness', 'contrast', 'saturation', 'hue', 'gain', 'exposure'
      ];
      
      // State
      this.isRecording = false;
      this.recordingStartTime = null;
      this.recordingTimer = null;
      this.currentCamera = 0;
      this.currentAudio = 0;
      this.isMuted = true;
      
      // Stream elements
      this.videoElement = null;
      this.audioElement = null;
      
      // Callbacks
      this.onCaptureComplete = options.onCaptureComplete || null;
      this.onRecordingStarted = options.onRecordingStarted || null;
      this.onRecordingStopped = options.onRecordingStopped || null;
      this.onSettingChanged = options.onSettingChanged || null;
      this.onCameraSwitch = options.onCameraSwitch || null;
      this.onAudioSwitch = options.onAudioSwitch || null;
      this.onError = options.onError || this._defaultErrorHandler;
      
      // Initialize
      this._init();
    }
    
    /**
     * Initialize the controller, setup stream elements
     * @private
     */
    _init() {
      // Get stream elements
      this.videoElement = document.getElementById(this.videoElementId);
      this.audioElement = document.getElementById(this.audioElementId);
      
      if (!this.videoElement) {
        console.error(`Video element with ID ${this.videoElementId} not found`);
        return;
      }
      
      if (!this.audioElement) {
        console.error(`Audio element with ID ${this.audioElementId} not found`);
        // Create audio element if it doesn't exist
        this.audioElement = document.createElement('audio');
        this.audioElement.id = this.audioElementId;
        this.audioElement.style.display = 'none';
        document.body.appendChild(this.audioElement);
      }
      
      // Setup video stream
      this.videoElement.src = this.streamUrl;
      
      // Setup audio stream
      this.audioElement.src = this.audioStreamUrl;
      this.audioElement.preload = 'auto';
      
      // Setup event handlers
      this._setupEventHandlers();
    }
    
    /**
     * Setup event handlers for stream elements
     * @private
     */
    _setupEventHandlers() {
      // Video stream error handling
      this.videoElement.addEventListener('error', (event) => {
        this.onError('Video stream error: ' + event.target.error.message);
      });
      
      // Audio stream error handling
      this.audioElement.addEventListener('error', (event) => {
        console.warn('Audio stream error: ' + (event.target.error ? event.target.error.message : 'unknown'));
        // Don't trigger main error handler for audio errors as they are non-critical
      });
      
      // Setup audio stream events
      this.audioElement.addEventListener('canplay', () => {
        console.log('Audio stream ready');
      });
    }
    
    /**
     * Default error handler
     * @private
     * @param {string} message - Error message
     */
    _defaultErrorHandler(message) {
      console.error('CameraController error:', message);
      alert('Camera Error: ' + message);
    }
    
    /**
     * Send an API request to the server
     * @private
     * @param {string} endpoint - API endpoint
     * @param {string} method - HTTP method (GET, POST, etc.)
     * @param {Object} data - Data to send with request
     * @returns {Promise} - Promise that resolves with response
     */
    async _apiRequest(endpoint, method = 'GET', data = null) {
      try {
        const options = {
          method: method,
          headers: {
            'X-CSRFToken': this._getCsrfToken(),
            'Content-Type': 'application/x-www-form-urlencoded'
          }
        };
        
        // Add request body if needed
        if (data && (method === 'POST' || method === 'PUT')) {
          if (typeof data === 'object') {
            // Convert object to form data
            const formData = new URLSearchParams();
            for (const key in data) {
              formData.append(key, data[key]);
            }
            options.body = formData;
          } else {
            options.body = data;
          }
        }
        
        const response = await fetch(endpoint, options);
        
        if (!response.ok) {
          throw new Error(`HTTP error ${response.status}: ${response.statusText}`);
        }
        
        return await response.json();
      } catch (error) {
        this.onError(`API request failed: ${error.message}`);
        throw error;
      }
    }
    
    /**
     * Get CSRF token from cookies
     * @private
     * @returns {string} - CSRF token
     */
    _getCsrfToken() {
      const name = 'csrftoken';
      let cookieValue = null;
      if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
          const cookie = cookies[i].trim();
          if (cookie.substring(0, name.length + 1) === (name + '=')) {
            cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
            break;
          }
        }
      }
      return cookieValue;
    }
    
    /**
     * Format time duration in MM:SS format
     * @private
     * @param {number} seconds - Time in seconds
     * @returns {string} - Formatted time string
     */
    _formatTime(seconds) {
      const mins = Math.floor(seconds / 60);
      const secs = Math.floor(seconds % 60);
      return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    
    /**
     * Update recording timer display
     * @private
     * @param {HTMLElement} element - Element to update
     */
    _updateRecordingTimer(element) {
      if (!element || !this.recordingStartTime) return;
      
      const now = new Date();
      const elapsedSeconds = Math.floor((now - this.recordingStartTime) / 1000);
      element.textContent = this._formatTime(elapsedSeconds);
    }
    
    /**
     * Toggle audio playback (mute/unmute)
     * @returns {boolean} - New mute state
     */
    toggleAudio() {
      this.isMuted = !this.isMuted;
      this.audioElement.muted = this.isMuted;
      
      if (!this.isMuted && this.audioElement.paused) {
        // If unmuting and audio is paused, try to play
        this.audioElement.play().catch(error => {
          console.warn('Could not play audio:', error);
        });
      }
      
      return this.isMuted;
    }
    
    /**
     * Start or resume audio playback
     */
    playAudio() {
      if (this.audioElement) {
        this.audioElement.play().catch(error => {
          console.warn('Could not play audio:', error);
        });
        this.isMuted = this.audioElement.muted;
      }
    }
    
    /**
     * Pause audio playback
     */
    pauseAudio() {
      if (this.audioElement) {
        this.audioElement.pause();
      }
    }
    
    /**
     * Capture a photo from the current camera stream
     * @returns {Promise} - Promise that resolves with the response
     */
    async capturePhoto() {
      try {
        // Send request to capture endpoint
        const response = await this._apiRequest(this.endpoints.capture, 'GET');
        
        // Call the callback if provided
        if (this.onCaptureComplete) {
          this.onCaptureComplete(response);
        }
        
        return response;
      } catch (error) {
        this.onError('Failed to capture photo: ' + error.message);
        throw error;
      }
    }
    
    /**
     * Start recording video with audio
     * @param {Object} options - Recording options
     * @param {number} options.audioIdx - Audio device index to use
     * @param {HTMLElement} options.timerElement - Element to display recording time
     * @returns {Promise} - Promise that resolves when recording starts
     */
    async startRecording(options = {}) {
      if (this.isRecording) {
        console.warn('Recording already in progress');
        return;
      }
      
      try {
        const data = {};
        if (options.audioIdx !== undefined) {
          data.audio_idx = options.audioIdx;
        }
        
        // Send request to start recording
        const response = await this._apiRequest(this.endpoints.startRecord, 'POST', data);
        
        this.isRecording = true;
        this.recordingStartTime = new Date();
        
        // Start timer if timerElement is provided
        if (options.timerElement) {
          this._updateRecordingTimer(options.timerElement);
          this.recordingTimer = setInterval(() => {
            this._updateRecordingTimer(options.timerElement);
          }, 1000);
        }
        
        // Call the callback if provided
        if (this.onRecordingStarted) {
          this.onRecordingStarted(response);
        }
        
        return response;
      } catch (error) {
        this.onError('Failed to start recording: ' + error.message);
        throw error;
      }
    }
    
    /**
     * Stop current recording
     * @returns {Promise} - Promise that resolves with the recorded video info
     */
    async stopRecording() {
      if (!this.isRecording) {
        console.warn('No recording in progress');
        return;
      }
      
      try {
        // Send request to stop recording
        const response = await this._apiRequest(this.endpoints.stopRecord, 'POST');
        
        this.isRecording = false;
        this.recordingStartTime = null;
        
        // Clear timer if it exists
        if (this.recordingTimer) {
          clearInterval(this.recordingTimer);
          this.recordingTimer = null;
        }
        
        // Call the callback if provided
        if (this.onRecordingStopped) {
          this.onRecordingStopped(response);
        }
        
        return response;
      } catch (error) {
        this.onError('Failed to stop recording: ' + error.message);
        throw error;
      }
    }
    
    /**
     * Change a camera setting
     * @param {string} setting - Setting name
     * @param {number|boolean} value - Setting value
     * @returns {Promise} - Promise that resolves with the response
     */
    async changeSetting(setting, value) {
      if (!this.settingsFields.includes(setting) && setting !== 'auto_exposure') {
        console.warn(`Unknown camera setting: ${setting}`);
        return;
      }
      
      try {
        // Send request to change setting
        const endpoint = `${this.endpoints.setSetting}/${setting}/`;
        const response = await this._apiRequest(endpoint, 'POST', { value: value });
        
        // Call the callback if provided
        if (this.onSettingChanged) {
          this.onSettingChanged(setting, value, response);
        }
        
        return response;
      } catch (error) {
        this.onError(`Failed to change setting ${setting}: ${error.message}`);
        throw error;
      }
    }
    
    /**
     * Switch to a different camera
     * @param {number} cameraIdx - Camera index to switch to
     * @returns {Promise} - Promise that resolves with the response
     */
    async switchCamera(cameraIdx) {
      try {
        // Send request to switch camera
        const endpoint = `${this.endpoints.switchCamera}${cameraIdx}/`;
        const response = await this._apiRequest(endpoint, 'POST');
        
        this.currentCamera = cameraIdx;
        
        // Call the callback if provided
        if (this.onCameraSwitch) {
          this.onCameraSwitch(cameraIdx, response);
        }
        
        return response;
      } catch (error) {
        this.onError(`Failed to switch camera: ${error.message}`);
        throw error;
      }
    }
    
    /**
     * Switch to a different audio input device
     * @param {number} audioIdx - Audio device index to switch to
     * @returns {Promise} - Promise that resolves with the response
     */
    async switchAudio(audioIdx) {
      try {
        // Send request to switch audio
        const endpoint = `${this.endpoints.switchAudio}${audioIdx}/`;
        const response = await this._apiRequest(endpoint, 'POST');
        
        this.currentAudio = audioIdx;
        
        // Reload the audio stream
        this.audioElement.load();
        
        // Call the callback if provided
        if (this.onAudioSwitch) {
          this.onAudioSwitch(audioIdx, response);
        }
        
        return response;
      } catch (error) {
        this.onError(`Failed to switch audio: ${error.message}`);
        throw error;
      }
    }
    
    /**
     * Restart the camera service
     * @returns {Promise} - Promise that resolves with the response
     */
    async restartCamera() {
      try {
        // Send request to restart camera
        const response = await this._apiRequest(this.endpoints.restart, 'POST');
        return response;
      } catch (error) {
        this.onError(`Failed to restart camera: ${error.message}`);
        throw error;
      }
    }
    
    /**
     * Refresh the list of available devices
     * @returns {Promise} - Promise that resolves with the available devices
     */
    async refreshDevices() {
      try {
        // Send request to refresh devices
        const response = await this._apiRequest(this.endpoints.refreshDevices, 'POST');
        return response;
      } catch (error) {
        this.onError(`Failed to refresh devices: ${error.message}`);
        throw error;
      }
    }
    
    /**
     * Get the list of available audio sources
     * @returns {Promise} - Promise that resolves with the available audio sources
     */
    async getAudioSources() {
      try {
        // Send request to get audio sources
        const response = await this._apiRequest(this.endpoints.audioSources, 'GET');
        return response;
      } catch (error) {
        this.onError(`Failed to get audio sources: ${error.message}`);
        throw error;
      }
    }
    
    /**
     * Get a single frame from the camera as a base64 encoded JPEG
     * @returns {Promise<string>} - Promise that resolves with the base64 encoded image
     */
    async getCameraFrame() {
      try {
        // Send request to get a camera frame
        const response = await this._apiRequest(this.endpoints.cameraFrame, 'GET');
        return response.frame; // base64 encoded image
      } catch (error) {
        this.onError(`Failed to get camera frame: ${error.message}`);
        throw error;
      }
    }
    
    /**
     * Check if the camera is currently online and streaming
     * @returns {boolean} - True if the video element is playing and not in an error state
     */
    isCameraOnline() {
      return this.videoElement && 
             !this.videoElement.paused && 
             !this.videoElement.ended && 
             this.videoElement.readyState > 2;
    }
    
    /**
     * Check if audio is currently available and can be played
     * @returns {boolean} - True if the audio element is ready to play
     */
    isAudioAvailable() {
      return this.audioElement && this.audioElement.readyState > 2;
    }
    
    /**
     * Clean up resources used by the controller
     */
    destroy() {
      // Stop recording if in progress
      if (this.isRecording) {
        this.stopRecording().catch(console.error);
      }
      
      // Clear timer if it exists
      if (this.recordingTimer) {
        clearInterval(this.recordingTimer);
        this.recordingTimer = null;
      }
      
      // Pause streams
      if (this.videoElement) {
        this.videoElement.pause();
      }
      
      if (this.audioElement) {
        this.audioElement.pause();
      }
      
      // Remove any created elements
      if (this.audioElement && this.audioElement.parentNode && 
          this.audioElement.id === this.audioElementId) {
        this.audioElement.parentNode.removeChild(this.audioElement);
      }
    }
  }
  
  // Export the class for module use if needed
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = CameraController;
  }