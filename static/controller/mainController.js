/**
 * Main Controller
 * 
 * This script initializes the appropriate controllers based on the current page
 * and serves as the entry point for the camera application.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize the main CameraController instance
    const config = window.CameraConfig || {};
    
    // Merge default endpoints with custom endpoints
    const defaultEndpoints = {
      setSetting: '/set',
      capture: '/capture/',
      startRecord: '/record/start/',
      stopRecord: '/record/stop/',
      cameraFrame: '/camera-frame/',
      switchCamera: '/switch/',
      switchAudio: '/api/switch-audio/',
      restart: '/restart/',
      refreshDevices: '/refresh-devices/',
      audioSources: '/api/audio-sources/'
    };
    
    config.endpoints = Object.assign({}, defaultEndpoints, config.endpoints || {});
    
    // Create the controller instance
    window.controller = new CameraController(config);
    
    // Initialize page-specific controllers
    initializePageControllers();
    
    // Initialize common UI elements
    initializeCommonUI();
  });
  
  /**
   * Initialize page-specific controllers based on URL or page elements
   */
  function initializePageControllers() {
    const path = window.location.pathname;
    
    // Camera page
    if (path === '/' || path.includes('/camera') || document.querySelector('.stream-card')) {
      initializeCameraPage();
    }
    
    // Media browser page
    if (path.includes('/media-browser') || document.querySelector('.gallery')) {
      initializeMediaBrowser();
    }
    
    // Timelapse gallery page
    if (path.includes('/timelapse-gallery') || document.getElementById('timelapse-canvas')) {
      initializeTimelapseGallery();
    }
  }
  
  /**
   * Initialize the camera page functionality
   */
  function initializeCameraPage() {
    console.log('Initializing camera page...');
    
    // Camera video stream
    const videoElement = document.getElementById('camera-stream') || document.getElementById('live-stream');
    if (!videoElement) return;
    
    // Camera controls
    const captureBtn = document.getElementById('capture-btn') || document.querySelector('[data-action="capture"]');
    const recordBtn = document.getElementById('record-btn') || document.getElementById('start-record');
    const stopRecordBtn = document.querySelector('[data-action="stop-record"]');
    const settingsBtn = document.getElementById('settings-btn') || document.getElementById('open-settings');
    const restartBtn = document.getElementById('restart-btn');
    const cameraSelect = document.getElementById('camera-select');
    const audioSelect = document.getElementById('audio-select');
    const audioToggle = document.getElementById('audio-toggle');
    const refreshDevicesBtn = document.getElementById('refresh-devices');
    
    // Camera settings
    const settingSliders = document.querySelectorAll('.setting-slider, [id^="slider_"]');
    const autoExposureToggle = document.getElementById('id_auto_exposure') || document.getElementById('auto-exposure-toggle');
    
    // Modal dialogs
    const settingsModal = document.getElementById('settings-modal');
    const closeSettingsBtn = document.getElementById('close-settings');
    
    // Attach event listeners if elements exist
    
    // Capture photo
    if (captureBtn) {
      captureBtn.addEventListener('click', function() {
        controller.capturePhoto();
      });
    }
    
    // Record video
    if (recordBtn) {
      recordBtn.addEventListener('click', function() {
        if (controller.isRecording) {
          controller.stopRecording().then(() => {
            // Update button appearance when recording stops
            recordBtn.classList.remove('active');
            recordBtn.innerHTML = '<i class="fas fa-dot-circle"></i> Record';
          });
        } else {
          const audioIdx = audioSelect ? parseInt(audioSelect.value, 10) : 0;
          controller.startRecording({
            audioIdx: audioIdx,
            timerElement: document.getElementById('recording-timer') || document.getElementById('recording-duration')
          }).then(() => {
            // Update button appearance when recording starts
            recordBtn.classList.add('active');
            recordBtn.innerHTML = '<i class="fas fa-stop-circle"></i> Stop Recording';
          });
        }
      });
    }
    
    // Stop recording (separate button)
    if (stopRecordBtn && !recordBtn) {
      stopRecordBtn.addEventListener('click', function() {
        controller.stopRecording();
      });
    }
    
    // Settings modal
    if (settingsBtn && settingsModal) {
      settingsBtn.addEventListener('click', function() {
        settingsModal.setAttribute('aria-hidden', 'false');
        settingsModal.classList.add('show');
      });
    }
    
    if (closeSettingsBtn && settingsModal) {
      closeSettingsBtn.addEventListener('click', function() {
        settingsModal.setAttribute('aria-hidden', 'true');
        settingsModal.classList.remove('show');
      });
    }
    
    // Restart camera
    if (restartBtn) {
      restartBtn.addEventListener('click', function() {
        restartBtn.disabled = true;
        controller.restartCamera().finally(() => {
          restartBtn.disabled = false;
        });
      });
    }
    
    // Camera selection
    if (cameraSelect) {
      cameraSelect.addEventListener('change', function() {
        const cameraIdx = parseInt(this.value, 10);
        controller.switchCamera(cameraIdx);
      });
    }
    
    // Audio selection
    if (audioSelect) {
      audioSelect.addEventListener('change', function() {
        const audioIdx = parseInt(this.value, 10);
        controller.switchAudio(audioIdx);
      });
    }
    
    // Audio toggle
    if (audioToggle) {
      audioToggle.addEventListener('click', function() {
        const isMuted = controller.toggleAudio();
        
        if (isMuted) {
          this.innerHTML = '<i class="fas fa-volume-mute"></i>';
          this.setAttribute('title', 'Unmute Audio');
        } else {
          this.innerHTML = '<i class="fas fa-volume-up"></i>';
          this.setAttribute('title', 'Mute Audio');
        }
      });
    }
    
    // Refresh devices
    if (refreshDevicesBtn) {
      refreshDevicesBtn.addEventListener('click', async function() {
        try {
          refreshDevicesBtn.disabled = true;
          refreshDevicesBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Refreshing...';
          
          await controller.refreshDevices();
          
          // Reload the page to update device lists
          window.location.reload();
        } catch (error) {
          console.error('Failed to refresh devices:', error);
          showNotification('Failed to refresh devices: ' + error.message, 'error');
        } finally {
          refreshDevicesBtn.disabled = false;
          refreshDevicesBtn.innerHTML = '<i class="fas fa-sync"></i> Refresh Devices';
        }
      });
    }
    
    // Setting sliders
    settingSliders.forEach(function(slider) {
      const setting = slider.dataset.setting || slider.id.replace('slider_', '');
      if (!setting) return;
      
      // Update value display when slider changes
      slider.addEventListener('input', function() {
        const value = parseInt(this.value, 10);
        const valueEl = document.getElementById(`${setting}-value`);
        if (valueEl) {
          valueEl.textContent = value;
        }
      });
      
      // Apply setting when slider is released
      slider.addEventListener('change', function() {
        const value = parseInt(this.value, 10);
        controller.changeSetting(setting, value);
      });
    });
    
    // Auto exposure toggle
    if (autoExposureToggle) {
      autoExposureToggle.addEventListener('change', function() {
        controller.changeSetting('auto_exposure', this.checked ? 1 : 0);
        
        // Enable/disable manual exposure slider
        const exposureSlider = document.querySelector('[data-setting="exposure"], #slider_exposure');
        if (exposureSlider) {
          exposureSlider.disabled = this.checked;
        }
      });
      
      // Initialize state
      const exposureSlider = document.querySelector('[data-setting="exposure"], #slider_exposure');
      if (exposureSlider && autoExposureToggle.checked) {
        exposureSlider.disabled = true;
      }
    }
  }
  
  /**
   * Initialize the media browser functionality
   */
  function initializeMediaBrowser() {
    console.log('Initializing media browser...');
    
    // Check if we're on a media browser page
    if (!document.querySelector('.gallery')) return;
    
    // Create media browser controller instance
    window.mediaBrowserController = new MediaBrowserController(controller);
  }
  
  /**
   * Initialize the timelapse gallery functionality
   */
  function initializeTimelapseGallery() {
    console.log('Initializing timelapse gallery...');
    
    // Check if we're on a timelapse page
    if (!document.getElementById('timelapse-canvas')) return;
    
    // Create timelapse controller instance
    window.timelapseController = new TimelapseController(controller);
  }
  
  /**
   * Initialize common UI elements used across multiple pages
   */
  function initializeCommonUI() {
    // Modal backdrop click handler
    document.querySelectorAll('.modal-backdrop').forEach(function(backdrop) {
      backdrop.addEventListener('click', function() {
        const modal = this.closest('.modal');
        if (modal) {
          modal.setAttribute('aria-hidden', 'true');
          modal.classList.remove('show');
        }
      });
    });
    
    // ESC key to close modals
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal[aria-hidden="false"], .modal.show').forEach(function(modal) {
          modal.setAttribute('aria-hidden', 'true');
          modal.classList.remove('show');
        });
      }
    });
  }
  
  /**
   * Show a notification message
   * @param {string} message - Notification message
   * @param {string} type - Notification type (info, success, error, warning)
   */
  function showNotification(message, type = 'info') {
    const container = document.getElementById('notification-container') || 
                     document.createElement('div');
    
    if (!container.id) {
      container.id = 'notification-container';
      container.className = 'notification-container';
      document.body.appendChild(container);
    }
    
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = message;
    
    container.appendChild(notification);
    
    setTimeout(() => {
      notification.classList.add('fade-out');
      setTimeout(() => {
        notification.removeAttribute('fade-out');
        container.removeChild(notification);
      }, 300);
    }, 3000);
  }
  
  // Make notification function available globally
  window.showNotification = showNotification;