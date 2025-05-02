/**
 * MediaBrowser.js
 * 
 * Enhanced JavaScript controller for the media browser functionality
 * that integrates with the CameraController.
 */

class MediaBrowserController {
  /**
   * Initialize the media browser controller
   * @param {CameraController} controller - The main camera controller instance
   */
  constructor(controller) {
    this.controller = controller;
    this.csrfToken = this._getCsrfToken(); // Fixed to not rely on controller method
    this.activeTab = 'photos'; // Default active tab
    this.selectedItems = { photos: [], videos: [], timelapse: [] }; // Fixed key name for timelapse
    this.pendingOperations = 0;
    
    // Initialize components
    this.initTabs();
    this.initViewToggles();
    this.initSelectionControls();
    this.initDeleteControls();
    this.initDownloadControls();
    this.initPreviewModal();
    this.initConfirmModal();
    
    // Initialize hover effects for videos
    this.initVideoHover();
  }
  
  /**
   * Get CSRF token from cookies
   * @returns {string} CSRF token
   */
  _getCsrfToken() {
    // Add fallback method to get CSRF token if controller doesn't provide it
    if (this.controller && typeof this.controller._getCsrfToken === 'function') {
      return this.controller._getCsrfToken();
    }
    
    // Extract from cookie directly as fallback
    const name = 'csrftoken';
    const cookieValue = document.cookie
      .split('; ')
      .find(row => row.startsWith(name + '='))
      ?.split('=')[1];
      
    return cookieValue || '';
  }
  
  /**
   * Initialize tab navigation
   */
  initTabs() {
    const tabs = document.querySelectorAll('.tab');
    
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        // Deactivate all tabs
        tabs.forEach(t => t.classList.remove('active'));
        
        // Hide all tab content sections
        document.querySelectorAll('.tab-content').forEach(content => {
          content.hidden = true;
          content.classList.remove('active');
        });
        
        // Activate clicked tab
        const target = tab.dataset.target;
        tab.classList.add('active');
        
        // Show corresponding content section
        const contentElement = document.getElementById(target);
        if (contentElement) {
          contentElement.hidden = false;
          contentElement.classList.add('active');
        }
        
        // Show corresponding actions section
        const actionsElement = document.getElementById(target + 'Actions');
        if (actionsElement) {
          actionsElement.hidden = false;
          actionsElement.classList.add('active');
        }
        
        this.activeTab = target;
        
        // Update the URL hash for better navigation
        window.location.hash = target;
      });
    });
    
    // Set initial tab based on URL hash if present
    if (window.location.hash) {
      const tabId = window.location.hash.substring(1);
      const targetTab = document.querySelector(`.tab[data-target="${tabId}"]`);
      if (targetTab) {
        targetTab.click();
      }
    }
  }
  
  /**
   * Initialize grid/list view toggles
   */
  initViewToggles() {
    // Define sections properly to match the actual DOM structure
    const sections = [
      {id: 'photos', gallery: 'photos-gallery'},
      {id: 'videos', gallery: 'videos-gallery'},
      {id: 'timelapse', gallery: 'tl-gallery'} // Fixed mapping for timelapse
    ];
    
    sections.forEach(section => {
      const gridBtn = document.getElementById(`${section.id === 'timelapse' ? 'tl' : section.id}-grid`);
      const listBtn = document.getElementById(`${section.id === 'timelapse' ? 'tl' : section.id}-list`);
      const gallery = document.getElementById(section.gallery);
      
      if (gridBtn && listBtn && gallery) {
        // Save view preference in localStorage
        const savedView = localStorage.getItem(`${section.id}-view`) || 'grid';
        if (savedView === 'list') {
          listBtn.classList.add('active');
          gridBtn.classList.remove('active');
          gallery.classList.remove('grid-view');
          gallery.classList.add('list-view');
        } else {
          gridBtn.classList.add('active');
          listBtn.classList.remove('active');
          gallery.classList.add('grid-view');
          gallery.classList.remove('list-view');
        }
        
        gridBtn.addEventListener('click', () => {
          listBtn.classList.remove('active');
          gridBtn.classList.add('active');
          gallery.classList.remove('list-view');
          gallery.classList.add('grid-view');
          localStorage.setItem(`${section.id}-view`, 'grid');
        });
        
        listBtn.addEventListener('click', () => {
          gridBtn.classList.remove('active');
          listBtn.classList.add('active');
          gallery.classList.remove('grid-view');
          gallery.classList.add('list-view');
          localStorage.setItem(`${section.id}-view`, 'list');
        });
      }
    });
  }
  
  /**
   * Initialize item selection controls
   */
  initSelectionControls() {
    // Define sections properly to match the actual DOM structure
    const sections = [
      {id: 'photos', gallery: 'photos-gallery', selectPrefix: 'photos'},
      {id: 'videos', gallery: 'videos-gallery', selectPrefix: 'videos'},
      {id: 'timelapse', gallery: 'tl-gallery', selectPrefix: 'tl'} // Fixed mapping for timelapse
    ];
    
    sections.forEach(section => {
      const selectAllBtn = document.getElementById(`${section.selectPrefix}-select-all`);
      const unselectAllBtn = document.getElementById(`${section.selectPrefix}-unselect-all`);
      const gallery = document.getElementById(section.gallery);
      
      if (selectAllBtn && unselectAllBtn && gallery) {
        selectAllBtn.addEventListener('click', () => {
          const checkboxes = gallery.querySelectorAll('.select-item');
          checkboxes.forEach(cb => cb.checked = true);
          this.updateSelectionState(section.id);
          this.showNotification(`Selected all ${section.id}`, 'info');
        });
        
        unselectAllBtn.addEventListener('click', () => {
          const checkboxes = gallery.querySelectorAll('.select-item');
          checkboxes.forEach(cb => cb.checked = false);
          this.updateSelectionState(section.id);
          this.showNotification(`Deselected all ${section.id}`, 'info');
        });
        
        // Make whole gallery item clickable to toggle selection
        gallery.querySelectorAll('.gallery-item').forEach(item => {
          item.addEventListener('click', e => {
            // Don't toggle if clicked on controls, checkbox, or media
            if (e.target.closest('.item-controls') || 
                e.target.closest('a') || 
                e.target.tagName === 'INPUT' ||
                e.target.tagName === 'IMG' ||
                e.target.tagName === 'VIDEO') {
              return;
            }
            
            const checkbox = item.querySelector('.select-item');
            if (checkbox) {
              checkbox.checked = !checkbox.checked;
              this.updateSelectionState(section.id);
            }
          });
        });
        
        // Listen for individual checkbox changes
        gallery.addEventListener('change', e => {
          if (e.target.classList.contains('select-item')) {
            this.updateSelectionState(section.id);
          }
        });
      }
    });
  }
  
  /**
   * Initialize delete controls
   */
  initDeleteControls() {
    // Define sections properly to match the actual DOM structure
    const sections = [
      {id: 'photos', gallery: 'photos-gallery', deletePrefix: 'photos', apiType: 'photo'},
      {id: 'videos', gallery: 'videos-gallery', deletePrefix: 'videos', apiType: 'video'},
      {id: 'timelapse', gallery: 'tl-gallery', deletePrefix: 'tl', apiType: 'timelapse'} 
    ];
    
    // Individual item delete buttons
    document.querySelectorAll('.delete-item').forEach(btn => {
      btn.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        
        const item = btn.closest('.gallery-item');
        if (!item) return;
        
        const filename = item.dataset.filename;
        const type = item.dataset.type || this.getTypeFromItem(item);
        
        this.confirmDelete([filename], type, () => {
          this.deleteItems([item], [btn.dataset.url]);
        });
      });
    });
    
    // Delete selected buttons
    sections.forEach(section => {
      const deleteSelectedBtn = document.getElementById(`${section.deletePrefix}-delete-selected`);
      const gallery = document.getElementById(section.gallery);
      
      if (deleteSelectedBtn && gallery) {
        deleteSelectedBtn.addEventListener('click', () => {
          const selectedItems = Array.from(gallery.querySelectorAll('.select-item:checked'))
            .map(cb => cb.closest('.gallery-item'));
          
          if (selectedItems.length === 0) {
            this.showNotification('No items selected', 'warning');
            return;
          }
          
          const urls = selectedItems.map(item => 
            item.querySelector('.delete-item').dataset.url
          );
          
          this.confirmDelete(
            selectedItems.map(item => item.dataset.filename),
            section.apiType,
            () => this.deleteItems(selectedItems, urls)
          );
        });
      }
    });
    
    // Delete all buttons
    sections.forEach(section => {
      const deleteAllBtn = document.getElementById(`${section.deletePrefix}-delete-all`);
      const gallery = document.getElementById(section.gallery);
      
      if (deleteAllBtn && gallery) {
        deleteAllBtn.addEventListener('click', () => {
          const items = gallery.querySelectorAll('.gallery-item');
          
          if (items.length === 0) {
            this.showNotification(`No ${section.id} to delete`, 'warning');
            return;
          }
          
          // Determine API endpoint URL from a sample item if possible
          let apiEndpoint = '';
          const sampleDeleteBtn = gallery.querySelector('.delete-item');
          if (sampleDeleteBtn && sampleDeleteBtn.dataset.url) {
            // Extract the base API path from the sample delete URL
            const urlParts = sampleDeleteBtn.dataset.url.split('/');
            // Remove the filename part and keep the base path
            urlParts.pop();
            apiEndpoint = urlParts.join('/') + '/delete-all/';
          }
          
          if (!apiEndpoint) {
            // Fallback to constructing URLs based on section type
            apiEndpoint = `/api/delete-all-${section.apiType}s/`;
          }
          
          this.confirmDelete(
            Array.from(items).map(item => item.dataset.filename),
            section.apiType,
            () => this.deleteAll(section.id, apiEndpoint)
          );
        });
      }
    });
  }
  
  /**
   * Initialize download controls
   */
  initDownloadControls() {
    // Define sections properly to match the actual DOM structure
    const sections = [
      {id: 'photos', gallery: 'photos-gallery', downloadPrefix: 'photos'},
      {id: 'videos', gallery: 'videos-gallery', downloadPrefix: 'videos'},
      {id: 'timelapse', gallery: 'tl-gallery', downloadPrefix: 'tl'} 
    ];
    
    sections.forEach(section => {
      const downloadSelectedBtn = document.getElementById(`${section.downloadPrefix}-download-selected`);
      const downloadForm = document.getElementById(`${section.downloadPrefix}-download-selected-form`);
      const gallery = document.getElementById(section.gallery);
      
      if (downloadSelectedBtn && downloadForm && gallery) {
        downloadSelectedBtn.addEventListener('click', () => {
          const selectedItems = gallery.querySelectorAll('.select-item:checked');
          
          if (selectedItems.length === 0) {
            this.showNotification('No items selected', 'warning');
            return;
          }
          
          // Clear existing inputs
          const inputsContainer = downloadForm.querySelector('.selected-inputs');
          inputsContainer.innerHTML = '';
          
          // Add CSRF token if not present in the form
          if (!downloadForm.querySelector('input[name="csrfmiddlewaretoken"]')) {
            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrfmiddlewaretoken';
            csrfInput.value = this.csrfToken;
            inputsContainer.appendChild(csrfInput);
          }
          
          // Add selected filenames as hidden inputs
          selectedItems.forEach(checkbox => {
            const item = checkbox.closest('.gallery-item');
            if (item && item.dataset.filename) {
              const input = document.createElement('input');
              input.type = 'hidden';
              input.name = 'filenames';
              input.value = item.dataset.filename;
              inputsContainer.appendChild(input);
            }
          });
          
          // Show notification
          this.showNotification(`Downloading ${selectedItems.length} items...`, 'info');
          
          // Submit the form
          downloadForm.submit();
        });
      }
    });
  }
  
  /**
   * Initialize preview modal
   */
  initPreviewModal() {
    const modal = document.getElementById('preview-modal');
    const previewImage = document.getElementById('preview-img');
    const previewVideo = document.getElementById('preview-video');
    const previewTitle = document.getElementById('preview-title');
    const previewDownload = document.getElementById('preview-download');
    const closeBtn = document.getElementById('preview-close');
    
    if (modal && previewImage && previewVideo && closeBtn) {
      // Preview buttons
      document.querySelectorAll('.preview-item').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          
          const url = btn.dataset.url;
          const isVideo = btn.closest('.gallery-item').dataset.type === 'video' || 
                         url.toLowerCase().endsWith('.mp4');
          const item = btn.closest('.gallery-item');
          const filename = item ? item.dataset.filename : 'Media';
          
          // Reset modal content
          previewImage.style.display = 'none';
          previewVideo.style.display = 'none';
          
          // Set title and download link
          previewTitle.textContent = filename;
          previewDownload.href = url;
          previewDownload.download = filename;
          
          if (isVideo) {
            previewVideo.src = url;
            previewVideo.style.display = 'block';
            
            // Auto-play videos when previewed
            previewVideo.play().catch(error => {
              console.warn('Could not autoplay video:', error);
            });
          } else {
            previewImage.src = url;
            previewImage.style.display = 'block';
          }
          
          // Show modal
          modal.setAttribute('aria-hidden', 'false');
          modal.classList.add('show');
        });
      });
      
      // Close button
      closeBtn.addEventListener('click', () => {
        modal.setAttribute('aria-hidden', 'true');
        modal.classList.remove('show');
        
        // Stop video playback if active
        if (previewVideo.style.display === 'block') {
          previewVideo.pause();
        }
      });
      
      // Close on backdrop click
      modal.querySelector('.modal-backdrop').addEventListener('click', () => {
        closeBtn.click();
      });
      
      // Keyboard navigation
      modal.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          closeBtn.click();
        }
      });
    }
  }
  
  /**
   * Initialize confirmation modal
   */
  initConfirmModal() {
    this.confirmModal = document.getElementById('confirm-modal');
    this.confirmTitle = document.getElementById('confirm-title');
    this.confirmMessage = document.getElementById('confirm-message');
    
    if (this.confirmModal) {
      // Setup confirm button
      const confirmBtn = this.confirmModal.querySelector('[data-action="confirm"]');
      if (confirmBtn) {
        // Store the original button for cloning
        this.originalConfirmBtn = confirmBtn.cloneNode(true);
      }
      
      // Setup close buttons
      this.confirmModal.querySelectorAll('[data-action="cancel"]').forEach(btn => {
        btn.addEventListener('click', () => {
          this.closeConfirmModal();
        });
      });
      
      // Backdrop click
      this.confirmModal.querySelector('.modal-backdrop').addEventListener('click', () => {
        this.closeConfirmModal();
      });
      
      // Keyboard escape
      this.confirmModal.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          this.closeConfirmModal();
        }
      });
    }
  }
  
  /**
   * Initialize video hover preview
   */
  initVideoHover() {
    // Auto-play videos on hover in galleries
    document.querySelectorAll('.gallery').forEach(gallery => {
      gallery.addEventListener('mouseover', (e) => {
        // Find closest video element within the hovered item
        const item = e.target.closest('.gallery-item');
        if (!item) return;
        
        const videoEl = item.querySelector('video');
        if (videoEl && videoEl.tagName === 'VIDEO') {
          videoEl.play().catch(() => {
            // Ignore autoplay errors
          });
        }
      });
      
      gallery.addEventListener('mouseout', (e) => {
        // Find closest video element within the previously hovered item
        const item = e.target.closest('.gallery-item');
        if (!item) return;
        
        const videoEl = item.querySelector('video');
        if (videoEl && videoEl.tagName === 'VIDEO') {
          videoEl.pause();
          videoEl.currentTime = 0;
        }
      });
    });
  }
  
  /**
   * Get the item type from a gallery item element
   * @param {HTMLElement} item - The gallery item element
   * @returns {string} - The item type (photo, video, timelapse)
   */
  getTypeFromItem(item) {
    // First check if the type is explicitly set on the item
    if (item.dataset.type) {
      return item.dataset.type;
    }
    
    // Otherwise determine from which gallery it belongs to
    const gallery = item.closest('.gallery');
    if (!gallery) return 'unknown';
    
    if (gallery.id === 'photos-gallery') return 'photo';
    if (gallery.id === 'videos-gallery') return 'video';
    if (gallery.id === 'tl-gallery') return 'timelapse';
    
    return 'unknown';
  }
  
  /**
   * Update selection state (enable/disable batch buttons)
   * @param {string} section - Section ID (photos, videos, timelapse)
   */
  updateSelectionState(section) {
    // Map section ID to DOM element IDs
    const prefixMap = {
      'photos': 'photos',
      'videos': 'videos',
      'timelapse': 'tl'
    };
    
    const prefix = prefixMap[section] || section;
    const galleryId = section === 'timelapse' ? 'tl-gallery' : `${section}-gallery`;
    
    const gallery = document.getElementById(galleryId);
    const deleteSelectedBtn = document.getElementById(`${prefix}-delete-selected`);
    const downloadSelectedBtn = document.getElementById(`${prefix}-download-selected`);
    
    if (gallery && deleteSelectedBtn && downloadSelectedBtn) {
      const selectedItems = gallery.querySelectorAll('.select-item:checked');
      const selectedCount = selectedItems.length;
      
      // Update button states
      if (selectedCount > 0) {
        deleteSelectedBtn.classList.remove('disabled');
        downloadSelectedBtn.classList.remove('disabled');
      } else {
        deleteSelectedBtn.classList.add('disabled');
        downloadSelectedBtn.classList.add('disabled');
      }
      
      // Update selection counts
      const deleteCountEl = deleteSelectedBtn.querySelector('.selection-count');
      const downloadCountEl = downloadSelectedBtn.querySelector('.selection-count');
      
      if (deleteCountEl) {
        deleteCountEl.textContent = selectedCount;
        deleteCountEl.style.display = selectedCount > 0 ? 'inline-block' : 'none';
      }
      
      if (downloadCountEl) {
        downloadCountEl.textContent = selectedCount;
        downloadCountEl.style.display = selectedCount > 0 ? 'inline-block' : 'none';
      }
      
      // Update internal state
      this.selectedItems[section] = Array.from(selectedItems).map(
        cb => cb.closest('.gallery-item').dataset.filename
      );
    }
  }
  
  /**
   * Show confirmation dialog for delete operations
   * @param {Array<string>} filenames - Array of filenames to delete
   * @param {string} type - Type of items (photo, video, timelapse)
   * @param {Function} onConfirm - Callback function on confirmation
   */
  confirmDelete(filenames, type, onConfirm) {
    if (!this.confirmModal || !this.confirmTitle || !this.confirmMessage) {
      // Fall back to simple confirm if modal not available
      if (confirm(`Are you sure you want to delete ${filenames.length} ${type}${filenames.length > 1 ? 's' : ''}?`)) {
        onConfirm();
      }
      return;
    }
    
    // Set modal content
    this.confirmTitle.textContent = 'Confirm Deletion';
    this.confirmMessage.textContent = 
      `Are you sure you want to delete ${filenames.length} ${type}${filenames.length > 1 ? 's' : ''}?`;
    
    // Set confirm button action
    const confirmBtn = this.confirmModal.querySelector('[data-action="confirm"]');
    const footer = confirmBtn.parentNode;
    
    // Remove existing button
    confirmBtn.remove();
    
    // Create new button based on the original
    const newConfirmBtn = this.originalConfirmBtn ? 
      this.originalConfirmBtn.cloneNode(true) : 
      document.createElement('button');
    
    if (!this.originalConfirmBtn) {
      newConfirmBtn.className = 'btn-action';
      newConfirmBtn.setAttribute('data-action', 'confirm');
      newConfirmBtn.textContent = 'Confirm';
    }
    
    // Add event listener
    newConfirmBtn.addEventListener('click', () => {
      this.closeConfirmModal();
      onConfirm();
    });
    
    // Add to DOM
    footer.appendChild(newConfirmBtn);
    
    // Show modal
    this.confirmModal.setAttribute('aria-hidden', 'false');
    this.confirmModal.classList.add('show');
  }
  
  /**
   * Close confirmation modal
   */
  closeConfirmModal() {
    if (this.confirmModal) {
      this.confirmModal.setAttribute('aria-hidden', 'true');
      this.confirmModal.classList.remove('show');
    }
  }
  
  /**
   * Delete multiple items
   * @param {Array<HTMLElement>} items - Array of gallery item elements
   * @param {Array<string>} urls - Array of API URLs for deletion
   */
  async deleteItems(items, urls) {
    if (items.length === 0 || urls.length === 0) return;
    
    this.startOperation();
    
    let successCount = 0;
    let errorCount = 0;
    
    // Process each deletion sequentially
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      const url = urls[i];
      
      try {
        const response = await fetch(url, {
          method: 'DELETE',
          headers: {
            'X-CSRFToken': this.csrfToken
          }
        });
        
        if (response.ok) {
          // Remove the item from the DOM with fade-out effect
          item.style.opacity = '0';
          item.style.transition = 'opacity 0.3s';
          
          setTimeout(() => {
            item.remove();
          }, 300);
          
          successCount++;
        } else {
          console.error('Delete error:', response.status, response.statusText);
          errorCount++;
        }
      } catch (error) {
        console.error('Delete error:', error);
        errorCount++;
      }
    }
    
    this.finishOperation();
    
    // Show notification
    if (successCount > 0) {
      this.showNotification(`Successfully deleted ${successCount} item${successCount !== 1 ? 's' : ''}`, 'success');
    }
    
    if (errorCount > 0) {
      this.showNotification(`Failed to delete ${errorCount} item${errorCount !== 1 ? 's' : ''}`, 'error');
    }
    
    // Update selection counts for the active tab
    this.updateSelectionState(this.activeTab === 'tl' ? 'timelapse' : this.activeTab);
    
    // Update empty state if needed
    this.checkEmptyGallery();
  }
  
  /**
   * Delete all items in a section
   * @param {string} section - Section ID (photos, videos, timelapse)
   * @param {string} apiEndpoint - API endpoint for deletion
   */
  async deleteAll(section, apiEndpoint) {
    this.startOperation();
    
    try {
      const response = await fetch(apiEndpoint, {
        method: 'DELETE',
        headers: {
          'X-CSRFToken': this.csrfToken,
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) {
        throw new Error(`Delete request failed: ${response.status} ${response.statusText}`);
      }
      
      // Try to parse response as JSON, but handle case where it might not be
      let deletedCount = 0;
      try {
        const data = await response.json();
        deletedCount = data.deleted || 0;
      } catch (e) {
        // If not JSON, assume success but unknown count
        deletedCount = 'all';
      }
      
      // Clear the gallery
      const galleryId = section === 'timelapse' ? 'tl-gallery' : `${section}-gallery`;
      const gallery = document.getElementById(galleryId);
      
      if (gallery) {
        // Fade out all items
        const items = gallery.querySelectorAll('.gallery-item');
        items.forEach(item => {
          item.style.opacity = '0';
          item.style.transition = 'opacity 0.3s';
        });
        
        // Remove after animation
        setTimeout(() => {
          items.forEach(item => item.remove());
          
          // Add "no items" message
          if (gallery.querySelector('.muted') === null) {
            const message = document.createElement('p');
            message.className = 'muted';
            message.textContent = `No ${section === 'timelapse' ? 'timelapse frames' : section} available.`;
            gallery.appendChild(message);
          }
        }, 300);
      }
      
      this.showNotification(
        `Successfully deleted ${deletedCount === 'all' ? 'all' : deletedCount} ${section} items`, 
        'success'
      );
      
      // Update UI selection state
      this.updateSelectionState(section);
    } catch (error) {
      console.error('Delete all error:', error);
      this.showNotification('Error: ' + error.message, 'error');
    } finally {
      this.finishOperation();
    }
  }
  
  /**
   * Check if gallery is empty and show placeholder message
   */
  checkEmptyGallery() {
    // Map section IDs to gallery elements
    const galleries = [
      {section: 'photos', id: 'photos-gallery'},
      {section: 'videos', id: 'videos-gallery'},
      {section: 'timelapse', id: 'tl-gallery'}
    ];
    
    galleries.forEach(({section, id}) => {
      const gallery = document.getElementById(id);
      if (!gallery) return;
      
      const items = gallery.querySelectorAll('.gallery-item');
      const emptyMessage = gallery.querySelector('.muted');
      
      if (items.length === 0 && !emptyMessage) {
        const message = document.createElement('p');
        message.className = 'muted';
        message.textContent = `No ${section === 'timelapse' ? 'timelapse frames' : section} available.`;
        gallery.appendChild(message);
      } else if (items.length > 0 && emptyMessage) {
        emptyMessage.remove();
      }
    });
  }
  
  /**
   * Mark the start of an asynchronous operation
   */
  startOperation() {
    this.pendingOperations++;
    document.body.classList.add('loading');
    
    const statusBar = document.querySelector('.gallery-status-bar');
    if (statusBar) {
      statusBar.style.display = 'flex';
    }
  }
  
  /**
   * Mark the completion of an asynchronous operation
   */
  finishOperation() {
    this.pendingOperations--;
    
    if (this.pendingOperations <= 0) {
      this.pendingOperations = 0;
      document.body.classList.remove('loading');
      
      const statusBar = document.querySelector('.gallery-status-bar');
      if (statusBar) {
        statusBar.style.display = 'none';
      }
    }
  }
  
  /**
   * Show a notification message
   * @param {string} message - Notification message
   * @param {string} type - Notification type (info, success, error, warning)
   */
  showNotification(message, type = 'info') {
    // Use global showNotification if available
    if (typeof window.showNotification === 'function') {
      window.showNotification(message, type);
      return;
    }
    
    // Fallback implementation when global function is not available
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
        container.removeChild(notification);
      }, 300);
    }, 3000);
  }
}

// Initialize the media browser on page load
document.addEventListener('DOMContentLoaded', function() {
  if (document.querySelector('.gallery')) {
    // Create media browser controller instance
    window.mediaBrowserController = new MediaBrowserController(window.controller || {});
  }
});