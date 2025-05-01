class CameraController {
    constructor(config) {
      // Configuration from template: CSRF, endpoints, API URLs, settings
      this.config = config ||  window.CameraConfig;
      this.csrfToken = config.csrfToken;
      this.recordStart = null;
      this.recordTimer = null;
        console.log('CameraController', config,  window.CameraConfig);
     
    }
  
    // =========== Camera Controls ===========
    initCameraView() {
      // Settings modal
      const modal = document.getElementById('settings-modal');
      document.getElementById('open-settings')?.addEventListener('click', () => modal.setAttribute('aria-hidden','false'));
      document.getElementById('close-settings')?.addEventListener('click', () => modal.setAttribute('aria-hidden','true'));
      if(modal){
        modal.querySelector('.modal-backdrop')?.addEventListener('click', () => modal.setAttribute('aria-hidden','true'));
      }
  
      // Sync sliders and inputs, auto-submit on change
      (this.config.settings || []).forEach(({ name }) => {
        const input = document.getElementById(`id_${name}`);
        const slider = document.getElementById(`slider_${name}`);
        if (!input || !slider) return;
        input.addEventListener('input', () => slider.value = input.value);
        slider.addEventListener('input', () => input.value = slider.value);
        input.addEventListener('change', () => this.submitSetting(name));
      });
  
      // Snapshot button
      document.getElementById('take-photo')?.addEventListener('click', () =>
        this.postAction('takePhoto', true)
      );
      // Recording start/stop
      document.getElementById('start-record')?.addEventListener('click', () =>
        this.postAction('startRecording', false)
      );
      document.getElementById('stop-record')?.addEventListener('click', () =>
        this.postAction('stopRecording', false)
      );
  
      // Live clock
      this.updateClock();
      this.initAudioControls();
      setInterval(() => this.updateClock(), 1000);
    }
  
    // =========== Media Browser ===========
    initMediaBrowser() {
      // Tab switching
      document.querySelectorAll('.navigation-grid .tab').forEach(tab => {
        tab.addEventListener('click', () => {
          document.querySelectorAll('.navigation-grid .tab').forEach(t => t.classList.remove('active'));
          tab.classList.add('active');
          const target = tab.dataset.target;
          document.querySelectorAll('.tab-content').forEach(sec => {
            const match = sec.id === target || sec.id === `${target}Actions`;
            sec.hidden = !match;
            sec.classList.toggle('active', match);
          });
        });
      });
  
      // Batch operations for each media type
      this._setupBatch('photos',   this.config.api.photosList);
      this._setupBatch('videos',   this.config.api.videosList);
      this._setupBatch('tl',       this.config.api.timelapseList);
  
      // Preview modal
      const modal = document.getElementById('preview-modal');
      const imgEl = document.getElementById('preview-img');
      const videoEl = document.getElementById('preview-video');
      const closeBtn = document.getElementById('preview-close');
  
      document.querySelectorAll('.preview-item').forEach(btn => {
        btn.addEventListener('click', () => {
          const url = btn.dataset.url;
          const isVid = /\.(mp4|webm|ogg)$/i.test(url);
          if (isVid) {
            imgEl.style.display = 'none';
            videoEl.src = url;
            videoEl.style.display = 'block';
          } else {
            videoEl.style.display = 'none';
            imgEl.src = url;
            imgEl.style.display = 'block';
          }
          modal.style.display = 'block';
        });
      });
  
      const closeModal = () => {
        modal.style.display = 'none';
        videoEl.pause();
      };
      closeBtn?.addEventListener('click', closeModal);
      modal?.addEventListener('click', e => e.target === modal && closeModal());
    }
  
    // =========== Batch Helper ===========
    _setupBatch(prefix, apiUrl) {
      const gallery = document.getElementById(`${prefix}-gallery`);
      if (!gallery) return;
      const deleteSelBtn    = document.getElementById(`${prefix}-delete-selected`);
      const downloadForm    = document.getElementById(`${prefix}-download-selected-form`);
      const downloadSelBtn  = document.getElementById(`${prefix}-download-selected`);
      const deleteAllBtn    = document.getElementById(`${prefix}-delete-all`);
      const selectAllBtn    = document.getElementById(`${prefix}-select-all`);
      const unselectAllBtn  = document.getElementById(`${prefix}-unselect-all`);
      const boxes           = Array.from(gallery.querySelectorAll('.select-item'));
  
      // Layout toggles
      document.getElementById(`${prefix}-grid`)?.addEventListener('click', () => {
        gallery.classList.replace('list-view','grid-view');
        document.getElementById(`${prefix}-grid`).classList.add('active');
        document.getElementById(`${prefix}-list`).classList.remove('active');
      });
      document.getElementById(`${prefix}-list`)?.addEventListener('click', () => {
        gallery.classList.replace('grid-view','list-view');
        document.getElementById(`${prefix}-list`).classList.add('active');
        document.getElementById(`${prefix}-grid`).classList.remove('active');
      });
  
      // Select/unselect all
      selectAllBtn?.addEventListener('click', () => { boxes.forEach(b => b.checked=true); toggleBtns(); });
      unselectAllBtn?.addEventListener('click', () => { boxes.forEach(b => b.checked=false); toggleBtns(); });
      boxes.forEach(b => b.addEventListener('change', toggleBtns));
      function toggleBtns() {
        const any = boxes.some(b => b.checked);
        deleteSelBtn.disabled = !any;
        downloadSelBtn.disabled = !any;
        deleteSelBtn.classList.toggle('disabled', !any);
        downloadSelBtn.classList.toggle('disabled', !any);
      }
  
      // Per-item delete
      gallery.querySelectorAll('.delete-item').forEach(btn => {
        btn.addEventListener('click', async () => {
          if (!confirm('Delete this item?')) return;
          const res = await fetch(btn.dataset.url, {
            method:'DELETE', credentials:'same-origin', headers:{ 'X-CSRFToken': this.csrfToken }
          });
          if (res.ok) btn.closest('.gallery-item').remove();
          else alert('Error deleting item');
        });
      });
  
      // Batch delete selected
      deleteSelBtn?.addEventListener('click', async () => {
        if (!confirm('Delete selected?')) return;
        await Promise.all(
          boxes.filter(b=>b.checked).map(async b=>{
            const item = b.closest('.gallery-item');
            const r = await fetch(item.querySelector('.delete-item').dataset.url, {
              method:'DELETE', credentials:'same-origin', headers:{ 'X-CSRFToken': this.csrfToken }
            });
            if (r.ok) item.remove();
          })
        );
        toggleBtns();
      });
  
      // Batch download selected
      downloadSelBtn?.addEventListener('click', () => {
        const names = boxes.filter(b=>b.checked).map(b=>b.closest('.gallery-item').dataset.filename);
        if (!names.length) return;
        const container = downloadForm.querySelector('.selected-inputs');
        container.innerHTML = '';
        names.forEach(n=>{
          const inp = document.createElement('input'); inp.type='hidden'; inp.name='filenames'; inp.value=n;
          container.appendChild(inp);
        });
        downloadForm.submit();
      });
  
      // Batch delete all
      deleteAllBtn?.addEventListener('click', async () => {
        if (!confirm('Delete all?')) return;
        const res = await fetch(apiUrl, {
          method:'DELETE', credentials:'same-origin', headers:{ 'X-CSRFToken': this.csrfToken }
        });
        if (res.ok) gallery.innerHTML='';
        else alert('Failed to delete all');
      });
    }
  
    // =========== Timelapse Gallery ===========
    initTimelapseGallery() {
      const canvas = document.getElementById('timelapse-canvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const thumbs = Array.from(document.querySelectorAll('.thumbnail-container .thumb'));
      const urls = thumbs.map(t=>t.dataset.src);
      const tsEl = document.getElementById('frame-timestamp');
      const playBtn = document.getElementById('play-pause');
      const speedNum = document.getElementById('speed-number');
      const speedSlider = document.getElementById('speed-slider');
      let idx=0, timer=null;
  
      const resizeCanvas = () => { canvas.width=1920; canvas.height=1080; };
      const formatTime = src => {
        const m= src ? src.match(/(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})/) : 0;
        if(!m) return '';
        const [y,mo,d,h,mi,s] = m.slice(1).map(Number);
        return new Date(y,mo-1,d,h,mi,s).toLocaleString();
      };
      const draw = i => {
        const img=new Image();
        img.onload=()=>{ ctx.clearRect(0,0,canvas.width,canvas.height); ctx.drawImage(img,0,0,canvas.width,canvas.height); };
        img.src=urls[i];
        tsEl.textContent=formatTime(urls[i]);
        thumbs.forEach(t=>t.classList.toggle('active',+t.dataset.index===i));
      };
      const scrollTo = ()=>thumbs[idx]?.scrollIntoView({behavior:'smooth',inline:'center'});
      const play = ()=>{ timer=setInterval(()=>{ idx=(idx+1)%urls.length; draw(idx); scrollTo(); },+speedNum.value); playBtn.textContent='Pause'; };
      const pause = ()=>{ clearInterval(timer); timer=null; playBtn.textContent='Play'; };
      playBtn.onclick = ()=> timer? pause(): play();
      speedNum.oninput = ()=>{ speedSlider.value=speedNum.value; if(timer){ pause(); play(); }};
      speedSlider.oninput = ()=>{ speedNum.value=speedSlider.value; if(timer){ pause(); play(); }};
      thumbs.forEach(t=>t.onclick=()=>{ idx=+t.dataset.index; draw(idx); pause(); scrollTo(); });
      window.addEventListener('resize', resizeCanvas);
      resizeCanvas(); draw(0);
  
      // Timelapse settings modal
      const tlModal=document.getElementById('timelapse-settings-modal');
      document.getElementById('open-tl-settings')?.addEventListener('click',()=>tlModal.setAttribute('aria-hidden','false'));
      document.getElementById('close-tl-settings')?.addEventListener('click',()=>tlModal.setAttribute('aria-hidden','true'));
      tlModal.querySelector('.modal-backdrop')?.addEventListener('click',()=>tlModal.setAttribute('aria-hidden','true'));
    }
  
    // =========== Server Interactions ===========
    submitSetting(name, value=null) {
      const val = value!==null ? value : document.getElementById(`id_${name}`).value;
      const url = this.config.urls.setSetting.replace('__dummy__', name);
      fetch(url, {
        method:'POST', credentials:'same-origin',
        headers:{ 'X-CSRFToken': this.csrfToken, 'Content-Type':'application/x-www-form-urlencoded' },
        body:`value=${encodeURIComponent(val)}`
      })
      .then(res=>res.json().then(data=>({ok:res.ok,data})))
      .then(({ok,data})=>{ if(!ok) alert(`Error setting ${name}: ${data.detail||data.error}`); })
      .catch(err=>alert(`Network error: ${err}`));
      console.log('submitSetting',url, name, value);
    }
  
    postAction(actionKey, isPhoto=false) {
      // Allow actionKey to be either a configured key or a direct URL
      const url = this.config.urls[actionKey] || actionKey;
      fetch(url, {
        method:'POST', credentials:'same-origin', headers:{ 'X-CSRFToken': this.csrfToken }
      })
      .then(res=>{
        if(!res.ok) return res.json().then(e=>Promise.reject(e));
        return isPhoto ? res.blob() : res.json();
      })
      .then(data=>{
        if(isPhoto) {
          const blobUrl = URL.createObjectURL(data);
          window.open(blobUrl, '_blank');
        } else {
          const btn = document.getElementById('start-record');
          const status = document.getElementById('recording-status');
          if(actionKey==='startRecording') {
            btn.classList.add('active'); status.innerText='● Recording…'; this.startRecordingTimer();
          } else if(actionKey==='stopRecording') {
            btn.classList.remove('active'); status.innerText=''; this.stopRecordingTimer();
            if(data.last_video) document.getElementById('last-video-block').innerHTML=`<a href="${data.last_video}" target="_blank">Last video</a>`;
          }
        }
      })
      .catch(err=>alert(err.detail||err.error||'Action failed'));
    }
  
    pad(n) { return n<10? '0'+n : ''+n; }
  
    updateClock() {
      const now = new Date();
      const hh=this.pad(now.getHours()), mm=this.pad(now.getMinutes()), ss=this.pad(now.getSeconds());
      const currentTimeElm = document.getElementById('current-time');
      if(currentTimeElm){
        document.getElementById('current-time').innerText = `${hh}:${mm}:${ss}`;
      }
    }
  
    startRecordingTimer() {
      this.recordStart = Date.now();
      this.recordTimer = setInterval(()=>{
        const elapsed = Date.now() - this.recordStart;
        const hrs=Math.floor(elapsed/3600000);
        const mins=Math.floor(elapsed/60000)%60;
        const secs=Math.floor(elapsed/1000)%60;
        document.getElementById('recording-duration').innerText = `${hrs}:${this.pad(mins)}:${this.pad(secs)}`;
      },500);
    }
  
    stopRecordingTimer() {
      clearInterval(this.recordTimer);
      this.recordTimer=null; this.recordStart=null;
      document.getElementById('recording-duration').innerText='';
    }
  
    updateCameraForm(idx) {
      const form = document.getElementById('camera-form');
      form.action = form.action.replace(/switch\/\d+/, `switch/${idx}`);
      form.submit();
    }

    initAudioControls() {
        const sel = document.getElementById('audio-select');
        const btn = document.getElementById('audio-switch-btn');
        const aud = document.getElementById('live-audio');
      
        btn.addEventListener('click', async () => {
          const idx = sel.value;
          const res = await fetch(`/api/switch-audio/${idx}/`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': this.csrfToken }
          });
          if (res.ok) {
            // reload the audio element to pick up the new device
            aud.load();
          } else {
            alert('Failed to switch audio');
          }
        });
      }
  }

  
  // Expose globally
  window.CameraController = CameraController;
  