/**
 * Timelapse Controller 
 * 
 * This script enhances the timelapse_gallery.html template to use the CameraController
 * for managing and displaying timelapse frames.
 */


class TimelapseController {
    /**
     * Initialize the timelapse controller
     * @param {CameraController|Object} controller - The main camera controller instance or configuration
     */
    constructor(controller) {
      // If controller is the main CameraController instance
      if (controller && typeof controller._getCsrfToken === 'function') {
        this.controller = controller;
        this.csrfToken = controller._getCsrfToken();
      } else {
        // If controller is a configuration object
        this.controller = null;
        this.csrfToken = this._getCsrfTokenFromCookies();
      }
      
      // Timelapse state
      this.frames = [];
      this.currentFrameIndex = 0;
      this.isPlaying = false;
      this.playInterval = null;
      this.playbackSpeed = 100; // ms between frames
      
      // Canvas elements
      this.canvas = document.getElementById('timelapse-canvas');
      this.ctx = this.canvas ? this.canvas.getContext('2d') : null;
      
      // Timelapse modal
      this.settingsModal = document.getElementById('timelapse-settings-modal');
      
      // Load frames from thumbnails
      this.loadFramesFromThumbnails();
      
      // Initialize event listeners
      this.initControls();
      this.initSettingsModal();
      
      // Draw the first frame if available
      if (this.frames.length > 0) {
        this.drawFrame(0);
      }
    }
    
    /**
     * Get CSRF token from cookies as fallback
     * @private
     * @returns {string} - CSRF token
     */
    _getCsrfTokenFromCookies() {
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
    
    // Load frames from thumbnail elements
    loadFramesFromThumbnails() {
      const thumbnails = document.querySelectorAll('.thumb');
      this.frames = Array.from(thumbnails).map(thumb => ({
        src: thumb.dataset.src,
        index: parseInt(thumb.dataset.index, 10),
        timestamp: thumb.alt || `Frame ${thumb.dataset.index}`
      }));
      
      // Add click handlers to thumbnails
      thumbnails.forEach(thumb => {
        thumb.addEventListener('click', () => {
          const index = parseInt(thumb.dataset.index, 10);
          this.stopPlayback();
          this.drawFrame(index);
        });
      });
    }
    
    // Initialize timelapse controls
    initControls() {
      // Play/Pause button
      const playPauseBtn = document.getElementById('play-pause');
      const playIcon = playPauseBtn ? playPauseBtn.querySelector('.fa-play') : null;
      const pauseIcon = playPauseBtn ? playPauseBtn.querySelector('.fa-pause') : null;
      
      if (playPauseBtn && playIcon && pauseIcon) {
        playPauseBtn.addEventListener('click', () => {
          if (this.isPlaying) {
            this.stopPlayback();
            playIcon.style.display = '';
            pauseIcon.style.display = 'none';
          } else {
            this.startPlayback();
            playIcon.style.display = 'none';
            pauseIcon.style.display = '';
          }
        });
      }
      
      // Speed controls
      const speedSlider = document.getElementById('speed-slider');
      const speedNumber = document.getElementById('speed-number');
      const downloadSpeed = document.getElementById('download-speed');
      
      if (speedSlider && speedNumber) {
        // Update number input when slider changes
        speedSlider.addEventListener('input', () => {
          const value = speedSlider.value;
          speedNumber.value = value;
          this.playbackSpeed = parseInt(value, 10);
          
          // Update hidden download speed input
          if (downloadSpeed) {
            downloadSpeed.value = value;
          }
          
          // Restart playback if active to apply new speed
          if (this.isPlaying) {
            this.stopPlayback();
            this.startPlayback();
          }
        });
        
        // Update slider when number input changes
        speedNumber.addEventListener('input', () => {
          const value = Math.max(25, Math.min(2000, speedNumber.value));
          speedSlider.value = value;
          this.playbackSpeed = value;
          
          // Update hidden download speed input
          if (downloadSpeed) {
            downloadSpeed.value = value;
          }
          
          // Restart playback if active to apply new speed
          if (this.isPlaying) {
            this.stopPlayback();
            this.startPlayback();
          }
        });
      }
    }
    
    // Initialize settings modal
    initSettingsModal() {
      const openSettingsBtn = document.getElementById('open-tl-settings');
      const closeSettingsBtn = document.getElementById('close-tl-settings');
      
      if (openSettingsBtn && closeSettingsBtn && this.settingsModal) {
        openSettingsBtn.addEventListener('click', () => {
          this.settingsModal.setAttribute('aria-hidden', 'false');
        });
        
        closeSettingsBtn.addEventListener('click', () => {
          this.settingsModal.setAttribute('aria-hidden', 'true');
        });
      }
    }
    
    // Start timelapse playback
    startPlayback() {
      if (this.frames.length === 0) return;
      
      this.isPlaying = true;
      
      // Clear existing interval if any
      if (this.playInterval) {
        clearInterval(this.playInterval);
      }
      
      // Set up interval for frame playback
      this.playInterval = setInterval(() => {
        this.currentFrameIndex = (this.currentFrameIndex + 1) % this.frames.length;
        this.drawFrame(this.currentFrameIndex);
      }, this.playbackSpeed);
    }
    
    // Stop timelapse playback
    stopPlayback() {
      this.isPlaying = false;
      
      if (this.playInterval) {
        clearInterval(this.playInterval);
        this.playInterval = null;
      }
    }
    
    // Draw a frame on the canvas
    drawFrame(index) {
      if (!this.canvas || !this.ctx || index < 0 || index >= this.frames.length) return;
      
      const frame = this.frames[index];
      this.currentFrameIndex = index;
      
      // Highlight the active thumbnail
      document.querySelectorAll('.thumb').forEach(thumb => {
        if (parseInt(thumb.dataset.index, 10) === index) {
          thumb.classList.add('active');
          
          // Scroll the thumbnail into view if not visible
          const thumbContainer = thumb.parentElement;
          if (thumbContainer && 
              (thumbContainer.scrollLeft > thumb.offsetLeft || 
               thumbContainer.scrollLeft + thumbContainer.clientWidth < thumb.offsetLeft + thumb.clientWidth)) {
            thumb.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
          }
        } else {
          thumb.classList.remove('active');
        }
      });
      
      // Update timestamp display
      const timestampEl = document.getElementById('frame-timestamp');
      if (timestampEl) {
        timestampEl.textContent = frame.timestamp;
      }
      
      // Load and draw the image
      const img = new Image();
      img.onload = () => {
        // Resize canvas to match image dimensions (if needed)
        if (this.canvas.width !== img.width || this.canvas.height !== img.height) {
          this.canvas.width = img.width;
          this.canvas.height = img.height;
        }
        
        // Clear canvas and draw image
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.ctx.drawImage(img, 0, 0, this.canvas.width, this.canvas.height);
      };
      
      // Add cache-busting parameter to avoid browser caching
      img.src = frame.src + '?t=' + new Date().getTime();
    }
  }
  
document.addEventListener('DOMContentLoaded', function() {
  

    
    // Initialize the timelapse controller if we're on the timelapse page
    if (document.getElementById('timelapse-canvas')) {
      // Use window.controller if available, otherwise just create a standalone instance
      const mainController = window.controller || window.CameraConfig || {};
      window.timelapseController = new TimelapseController(mainController);
    }
  });