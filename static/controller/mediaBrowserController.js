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
    this.csrfToken = controller._getCsrfToken();
    this.activeTab = 'photos';
    this.selectedItems = { photos: [], videos: [], tl: [] };
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
   * Initialize tab navigation
   */
  initTabs() {
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        // Deactivate all tabs
        tabs.forEach(t => t.classList.remove('active'));
        tabContents.forEach(c => {
          c.hidden = true;
          c.classList.remove('active');
        });
        
        // Activate clicked tab
        const target = tab.dataset.target;
        tab.classList.add('active');
        
        // Show corresponding content sections
        const contentElement = document.getElementById(target);
        const actionsElement = document.getElementById(target + 'Actions');
        
        if (contentElement) {
          contentElement.hidden = false;
          contentElement.classList.add('active');
        }
        
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
    const sections = ['photos', 'videos', 'tl'];
    
    sections.forEach(section => {
      const gridBtn = document.getElementById(`${section}-grid`);
      const listBtn = document.getElementById(`${section}-list`);
      const gallery = document.getElementById(`${section === 'tl' ? 'tl' : section + 's'}-gallery`);
      
      if (gridBtn && listBtn && gallery) {
        // Save view preference in localStorage
        const savedView = localStorage.getItem(`${section}-view`) || 'grid';
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
          localStorage.setItem(`${section}-view`, 'grid');
        });
        
        listBtn.addEventListener('click', () => {
          gridBtn.classList.remove('active');
          listBtn.classList.add('active');
          gallery.classList.remove('grid-view');
          gallery.classList.add('list-view');
          localStorage.setItem(`${section}-view`, 'list');
        });
      }
    });
  }
  
  /**
   * Initialize item selection controls
   */
  initSelectionControls() {
    const sections = ['photos', 'videos', 'tl'];
    
    sections.forEach(section => {
      const selectAllBtn = document.getElementById(`${section}-select-all`);
      const unselectAllBtn = document.getElementById(`${section}-unselect-all`);
      const gallery = document.getElementById(`${section === 'tl' ? 'tl' : section + 's'}-gallery`);
      
      if (selectAllBtn && unselectAllBtn && gallery) {
        selectAllBtn.addEventListener('click', () => {
          const checkboxes = gallery.querySelectorAll('.select-item');
          checkboxes.forEach(cb => cb.checked = true);
          this.updateSelectionState(section);
          this.showNotification(`Selected all ${section}`, 'info');
        });
        
        unselectAllBtn.addEventListener('click', () => {
          const checkboxes = gallery.querySelectorAll('.select-item');
          checkboxes.forEach(cb => cb.checked = false);
          this.updateSelectionState(section);
          this.showNotification(`Deselected all ${section}`, 'info');
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
              this.updateSelectionState(section);
            }
          });
        });
        
        // Listen for individual checkbox changes
        gallery.addEventListener('change', e => {
          if (e.target.classList.contains('select-item')) {
            this.updateSelectionState(section);
          }
        });
      }
    });
  }
  
  /**
   * Initialize delete controls
   */
  initDeleteControls() {
    const sections = ['photos', 'videos', 'tl'];
    
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
      const deleteSelectedBtn = document.getElementById(`${section}-delete-selected`);
      const gallery = document.getElementById(`${section === 'tl' ? 'tl' : section + 's'}-gallery`);
      
      if (deleteSelectedBtn && gallery) {
        deleteSelectedBtn.addEventListener('click', () => {
          const selectedItems = Array.from(gallery.querySelectorAll('.select-item:checked'))
            .map(cb => cb.closest('.gallery-item'));
          
          if (selectedItems.length === 0) {
            this.showNotification('No items selected', 'warning');
            return;
          }
          
          const type = section === 'tl' ? 'timelapse' : section.slice(0, -1); // Remove 's' from "photos"/"videos"
          const urls = selectedItems.map(item => 
            item.querySelector('.delete-item').dataset.url
          );
          
          this.confirmDelete(
            selectedItems.map(item => item.dataset.filename),
            type,
            () => this.deleteItems(selectedItems, urls)
          );
        });
      }
    });
    
    // Delete all buttons
    sections.forEach(section => {
      const deleteAllBtn = document.getElementById(`${section}-delete-all`);
      const apiEndpoint = section === 'photos' ? 'photosList' : 
                         section === 'videos' ? 'videosList' : 'timelapseList';
      
      if (deleteAllBtn && this.controller.endpoints[apiEndpoint]) {
        deleteAllBtn.addEventListener('click', () => {
          const gallery = document.getElementById(`${section === 'tl' ? 'tl' : section + 's'}-gallery`);
          const items = gallery.querySelectorAll('.gallery-item');
          
          if (items.length === 0) {
            this.showNotification(`No ${section} to delete`, 'warning');
            return;
          }
          
          const type = section === 'tl' ? 'timelapse' : section.slice(0, -1);
          
          this.confirmDelete(
            Array.from(items).map(item => item.dataset.filename),
            type,
            () => this.deleteAll(section, apiEndpoint)
          );
        });
      }
    });
  }
  
  /**
   * Initialize download controls
   */
  initDownloadControls() {
    const sections = ['photos', 'videos', 'tl'];
    
    sections.forEach(section => {
      const downloadSelectedBtn = document.getElementById(`${section}-download-selected`);
      const downloadForm = document.getElementById(`${section}-download-selected-form`);
      const gallery = document.getElementById(`${section === 'tl' ? 'tl' : section + 's'}-gallery`);
      
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
          const isVideo = url.toLowerCase().endsWith('.mp4');
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
        // Find closest video element
        const videoEl = e.target.closest('.gallery-item')?.querySelector('video');
        if (videoEl && !videoEl.hasAttribute('data-playing')) {
          videoEl.setAttribute('data-playing', 'true');
          videoEl.play().catch(() => {});
        }
      });
      
      gallery.addEventListener('mouseout', (e) => {
        // Find closest video element
        const videoEl = e.target.closest('.gallery-item')?.querySelector('video');
        if (videoEl && videoEl.hasAttribute('data-playing')) {
          videoEl.removeAttribute('data-playing');
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
    const gallery = item.closest('.gallery');
    if (!gallery) return 'unknown';
    
    if (gallery.id === 'photos-gallery') return 'photo';
    if (gallery.id === 'videos-gallery') return 'video';
    if (gallery.id === 'tl-gallery') return 'timelapse';
    
    return 'unknown';
  }
  
  /**
   * Update selection state (enable/disable batch buttons)
   * @param {string} section - Section ID (photos, videos, tl)
   */
  updateSelectionState(section) {
    const gallery = document.getElementById(`${section === 'tl' ? 'tl' : section + 's'}-gallery`);
    const deleteSelectedBtn = document.getElementById(`${section}-delete-selected`);
    const downloadSelectedBtn = document.getElementById(`${section}-download-selected`);
    
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
    
    // Remove existing listeners
    const newConfirmBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
    
    // Add new listener
    newConfirmBtn.addEventListener('click', () => {
      this.closeConfirmModal();
      onConfirm();
    });
    
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
    
    // Update selection counts
    this.updateSelectionState(this.activeTab);
    
    // Update empty state if needed
    this.checkEmptyGallery();
  }
  
  /**
   * Delete all items in a section
   * @param {string} section - Section ID (photos, videos, tl)
   * @param {string} apiEndpoint - API endpoint for deletion
   */
  async deleteAll(section, apiEndpoint) {
    this.startOperation();
    
    try {
      const response = await fetch(this.controller.endpoints[apiEndpoint], {
        method: 'DELETE',
        headers: {
          'X-CSRFToken': this.csrfToken
        }
      });
      
      if (!response.ok) {
        throw new Error('Delete request failed');
      }
      
      const data = await response.json();
      
      // Clear the gallery
      const gallery = document.getElementById(`${section === 'tl' ? 'tl' : section + 's'}-gallery`);
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
            message.textContent = `No ${section === 'tl' ? 'timelapse frames' : section} available.`;
            gallery.appendChild(message);
          }
        }, 300);
      }
      
      this.showNotification(`Successfully deleted ${data.deleted} item${data.deleted !== 1 ? 's' : ''}`, 'success');
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
    const sections = ['photos', 'videos', 'tl'];
    
    sections.forEach(section => {
      const gallery = document.getElementById(`${section === 'tl' ? 'tl' : section + 's'}-gallery`);
      if (!gallery) return;
      
      const items = gallery.querySelectorAll('.gallery-item');
      const emptyMessage = gallery.querySelector('.muted');
      
      if (items.length === 0 && !emptyMessage) {
        const message = document.createElement('p');
        message.className = 'muted';
        message.textContent = `No ${section === 'tl' ? 'timelapse frames' : section} available.`;
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
    
    // Fallback to custom implementation
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

// Initialize the media browser if we're on the correct page
document.addEventListener('DOMContentLoaded', function() {
  if (typeof window.controller !== 'undefined' && document.querySelector('.gallery')) {
    // Create media browser controller instance
    window.mediaBrowserController = new MediaBrowserController(window.controller);
  }
});