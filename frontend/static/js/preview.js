/**
 * MyDrive Cinema Lightbox & Professional Media Stage
 * Features:
 * - Immersive full-screen edge-to-edge media viewer
 * - True Full Mode (HTML5 requestFullscreen + cinematic auto-hiding controls)
 * - Interactive Image Zoom (0.5x - 4x), Panning, Mouse Wheel & Double-Tap Zoom
 * - Auto-advancing Slideshow with real-time neon progress bar
 * - Intelligent Next/Previous image preloading for instantaneous switching
 * - Touch gestures: Horizontal swipe, Pull-down to dismiss, and Tap-to-toggle
 * - Keyboard shortcuts: Arrows, Space, F, Esc, +, -, 0
 */

class FilePreviewer {
    constructor() {
        this.modal = null;
        this.stageCard = null;
        this.topBar = null;
        this.container = null;
        this.progressBar = null;

        this.titleEl = null;
        this.counterEl = null;
        this.fileSizeEl = null;

        this.zoomControls = null;
        this.zoomLevelEl = null;

        this.downloadBtn = null;
        this.slideshowBtn = null;
        this.slideshowIcon = null;
        this.slideshowText = null;

        this.fullscreenBtn = null;
        this.fullscreenIcon = null;
        this.fullscreenText = null;

        this.prevBtn = null;
        this.nextBtn = null;

        this.currentFile = null;
        this.playlist = [];
        this.currentIndex = -1;

        // Slideshow
        this.isSlideshow = false;
        this.slideshowTimer = null;
        this.slideshowIntervalMs = 3500;

        // Fullscreen / Full Mode
        this.isFullMode = false;
        this.idleTimer = null;
        this.isControlsHidden = false;

        // Zoom & Pan
        this.zoom = 1.0;
        this.panX = 0;
        this.panY = 0;
        this.isDragging = false;
        this.dragStartX = 0;
        this.dragStartY = 0;
        this.activeImg = null;

        // Touch & Pinch tracking
        this.touchStartX = 0;
        this.touchStartY = 0;
        this.touchStartTime = 0;
        this.isPinching = false;
        this.initialPinchDistance = 0;
        this.initialPinchZoom = 1.0;
        this.lastTapTime = 0;
        this.tapTimeout = null;

        this.keydownBound = false;
        this.boundHandleKeyDown = this.handleKeyDown.bind(this);
    }

    init() {
        this.modal = document.getElementById("previewModal");
        this.stageCard = document.getElementById("previewModalCard");
        this.topBar = document.getElementById("previewTopBar");
        this.container = document.getElementById("previewContainer");
        this.progressBar = document.getElementById("previewProgressBar");

        this.titleEl = document.getElementById("previewTitle");
        this.counterEl = document.getElementById("previewCounter");
        this.fileSizeEl = document.getElementById("previewFileSize");

        this.zoomControls = document.getElementById("previewZoomControls");
        this.zoomLevelEl = document.getElementById("previewZoomLevel");

        this.downloadBtn = document.getElementById("previewDownloadBtn");
        this.slideshowBtn = document.getElementById("previewSlideshowBtn");
        this.slideshowIcon = document.getElementById("previewSlideshowIcon");
        this.slideshowText = document.getElementById("previewSlideshowText");

        this.fullscreenBtn = document.getElementById("previewFullscreenBtn");
        this.fullscreenIcon = document.getElementById("previewFullscreenIcon");
        this.fullscreenText = document.getElementById("previewFullscreenText");

        this.prevBtn = document.getElementById("previewPrevBtn");
        this.nextBtn = document.getElementById("previewNextBtn");

        if (this.slideshowIcon && typeof Icons !== 'undefined') {
            this.slideshowIcon.innerHTML = Icons.get('play', { size: 15 });
        }
        if (this.fullscreenIcon && typeof Icons !== 'undefined') {
            this.fullscreenIcon.innerHTML = Icons.get('fullscreen', { size: 16 });
        }

        // Fullscreen change events
        const onFsChange = () => {
            const isNativeFs = !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement);
            if (!isNativeFs && this.isFullMode) {
                this.exitFullscreen();
            }
        };
        document.addEventListener("fullscreenchange", onFsChange);
        document.addEventListener("webkitfullscreenchange", onFsChange);
        document.addEventListener("mozfullscreenchange", onFsChange);

        // Activity detector to auto-hide controls in Full Mode
        const onActivity = () => {
            if (this.modal && this.modal.style.display === "flex") {
                this.wakeControls();
            }
        };
        window.addEventListener("mousemove", onActivity);
        window.addEventListener("touchstart", onActivity, { passive: true });

        // Wheel Zoom on preview container
        if (this.container) {
            this.container.addEventListener("wheel", (e) => {
                if (!this.activeImg) return;
                e.preventDefault();
                const delta = e.deltaY < 0 ? 0.2 : -0.2;
                this.setZoom(this.zoom + delta);
            }, { passive: false });

            // Mouse drag pan
            this.container.addEventListener("mousedown", (e) => {
                if (this.zoom > 1.0 && this.activeImg) {
                    this.isDragging = true;
                    this.dragStartX = e.clientX - this.panX;
                    this.dragStartY = e.clientY - this.panY;
                    this.container.classList.add("is-dragging");
                }
            });

            window.addEventListener("mousemove", (e) => {
                if (this.isDragging && this.activeImg) {
                    this.panX = e.clientX - this.dragStartX;
                    this.panY = e.clientY - this.dragStartY;
                    this.applyTransform();
                }
            });

            window.addEventListener("mouseup", () => {
                if (this.isDragging) {
                    this.isDragging = false;
                    if (this.container) this.container.classList.remove("is-dragging");
                }
            });

            // Touch gestures
            this.container.addEventListener("touchstart", (e) => {
                if (!e.touches) return;
                if (e.touches.length === 2 && this.activeImg) {
                    this.isPinching = true;
                    this.initialPinchDistance = Math.hypot(
                        e.touches[0].clientX - e.touches[1].clientX,
                        e.touches[0].clientY - e.touches[1].clientY
                    );
                    this.initialPinchZoom = this.zoom;
                    return;
                }
                if (e.touches.length !== 1) return;
                const t = e.touches[0];
                this.touchStartX = t.clientX;
                this.touchStartY = t.clientY;
                this.touchStartTime = Date.now();

                if (this.zoom > 1.0) {
                    this.isDragging = true;
                    this.dragStartX = t.clientX - this.panX;
                    this.dragStartY = t.clientY - this.panY;
                }
            }, { passive: true });

            this.container.addEventListener("touchmove", (e) => {
                if (this.isPinching && e.touches && e.touches.length === 2 && this.activeImg) {
                    const currentDist = Math.hypot(
                        e.touches[0].clientX - e.touches[1].clientX,
                        e.touches[0].clientY - e.touches[1].clientY
                    );
                    if (this.initialPinchDistance > 0) {
                        const scale = currentDist / this.initialPinchDistance;
                        this.setZoom(this.initialPinchZoom * scale);
                    }
                    return;
                }
                if (this.isDragging && this.zoom > 1.0 && e.touches && e.touches.length === 1) {
                    const t = e.touches[0];
                    this.panX = t.clientX - this.dragStartX;
                    this.panY = t.clientY - this.dragStartY;
                    this.applyTransform();
                }
            }, { passive: true });

            this.container.addEventListener("touchend", (e) => {
                if (this.isPinching) {
                    if (!e.touches || e.touches.length < 2) {
                        this.isPinching = false;
                        this.initialPinchDistance = 0;
                    }
                    return;
                }
                if (this.isDragging) {
                    this.isDragging = false;
                }
                if (!e.changedTouches || e.changedTouches.length !== 1) return;
                const t = e.changedTouches[0];
                const deltaX = t.clientX - this.touchStartX;
                const deltaY = t.clientY - this.touchStartY;
                const duration = Date.now() - this.touchStartTime;

                // Double-tap zoom check (< 320ms between taps)
                if (Math.abs(deltaX) < 15 && Math.abs(deltaY) < 15 && duration < 300) {
                    const now = Date.now();
                    if (this.lastTapTime && (now - this.lastTapTime < 320)) {
                        if (this.tapTimeout) {
                            clearTimeout(this.tapTimeout);
                            this.tapTimeout = null;
                        }
                        this.lastTapTime = 0;
                        if (this.activeImg) {
                            if (this.zoom > 1.05) {
                                this.resetZoom();
                            } else {
                                this.setZoom(2.0);
                            }
                        }
                        return;
                    }
                    this.lastTapTime = now;
                    if (this.zoom === 1.0) {
                        this.tapTimeout = setTimeout(() => {
                            this.toggleControls();
                            this.tapTimeout = null;
                        }, 320);
                    }
                    return;
                }

                if (this.zoom === 1.0) {
                    // Pull down to dismiss
                    if (deltaY > 85 && deltaY > Math.abs(deltaX) * 1.5 && duration < 800) {
                        this.close();
                        return;
                    }

                    // Horizontal swipe
                    if (Math.abs(deltaX) >= 42 && Math.abs(deltaX) > Math.abs(deltaY) * 1.25 && duration < 900) {
                        if (deltaX < 0) {
                            this.nextImage();
                        } else {
                            this.prevImage();
                        }
                    }
                }
            }, { passive: true });
        }

        // Global key listener
        if (!this.keydownBound) {
            window.addEventListener("keydown", this.boundHandleKeyDown);
            this.keydownBound = true;
        }
    }

    isImageFile(file) {
        if (!file || file.is_directory) return false;
        const ext = (file.name || "").split('.').pop().toLowerCase();
        const mime = file.mime_type || "";
        return mime.startsWith("image/") || ["jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "ico", "avif", "heic"].includes(ext);
    }

    setupPlaylist(file, itemsList) {
        let pool = itemsList;
        if (!pool && typeof currentItems !== 'undefined' && Array.isArray(currentItems)) {
            pool = currentItems;
        }
        if (!Array.isArray(pool)) {
            pool = [];
        }

        this.playlist = pool.filter(item => this.isImageFile(item));

        const foundIdx = this.playlist.findIndex(item => item.relative_path === file.relative_path || (item.id && file.id && item.id === file.id));
        if (foundIdx >= 0) {
            this.currentIndex = foundIdx;
        } else {
            this.playlist = [file, ...this.playlist];
            this.currentIndex = 0;
        }
    }

    updateControlsUI() {
        const hasGallery = this.playlist && this.playlist.length > 1;

        if (this.prevBtn) {
            this.prevBtn.style.display = hasGallery ? "flex" : "none";
        }
        if (this.nextBtn) {
            this.nextBtn.style.display = hasGallery ? "flex" : "none";
        }
        if (this.slideshowBtn) {
            this.slideshowBtn.style.display = hasGallery ? "inline-flex" : "none";
        }
        if (this.counterEl) {
            if (hasGallery && this.currentIndex >= 0) {
                this.counterEl.textContent = `${this.currentIndex + 1} / ${this.playlist.length}`;
                this.counterEl.style.display = "inline-flex";
            } else {
                this.counterEl.style.display = "none";
            }
        }
    }

    wakeControls() {
        if (this.topBar) this.topBar.classList.remove("is-idle");
        if (this.prevBtn) this.prevBtn.classList.remove("is-idle");
        if (this.nextBtn) this.nextBtn.classList.remove("is-idle");
        this.isControlsHidden = false;

        if (this.idleTimer) {
            clearTimeout(this.idleTimer);
            this.idleTimer = null;
        }

        // In Full Mode, auto-hide controls after 2.5s of inactivity
        if (this.isFullMode) {
            this.idleTimer = setTimeout(() => {
                if (this.isFullMode && this.modal && this.modal.style.display === "flex") {
                    if (this.topBar) this.topBar.classList.add("is-idle");
                    if (this.prevBtn) this.prevBtn.classList.add("is-idle");
                    if (this.nextBtn) this.nextBtn.classList.add("is-idle");
                    this.isControlsHidden = true;
                }
            }, 2500);
        }
    }

    toggleControls() {
        if (this.isControlsHidden) {
            this.wakeControls();
        } else {
            if (this.topBar) this.topBar.classList.add("is-idle");
            if (this.prevBtn) this.prevBtn.classList.add("is-idle");
            if (this.nextBtn) this.nextBtn.classList.add("is-idle");
            this.isControlsHidden = true;
        }
    }

    preview(file, itemsList = null) {
        if (!this.modal) this.init();

        this.currentFile = file;
        this.stopSlideshow();
        this.resetZoom();

        const ext = (file.name || "").split('.').pop().toLowerCase();
        const mime = file.mime_type || "";
        const isImg = this.isImageFile(file);

        if (isImg) {
            this.setupPlaylist(file, itemsList);
            if (this.zoomControls) this.zoomControls.style.display = "inline-flex";
        } else {
            this.playlist = [];
            this.currentIndex = -1;
            if (this.zoomControls) this.zoomControls.style.display = "none";
        }

        this.updateControlsUI();
        this.modal.style.display = "flex";
        this.wakeControls();

        if (isImg) {
            this.renderCurrentImage();
            return;
        }

        // Non-image previews (Audio, Video, PDF, Text)
        this.activeImg = null;
        const previewUrl = `/api/files/preview?path=${encodeURIComponent(file.relative_path)}`;
        const downloadUrl = `/api/files/download?path=${encodeURIComponent(file.relative_path)}`;

        this.titleEl.textContent = file.name;
        this.titleEl.title = file.name;
        if (this.fileSizeEl) {
            this.fileSizeEl.textContent = typeof formatBytes === 'function' ? formatBytes(file.size) : '';
        }
        this.downloadBtn.onclick = () => window.open(downloadUrl, "_blank");

        // Audio
        if (mime.startsWith("audio/") || ["mp3", "wav", "ogg", "m4a", "flac", "aac"].includes(ext)) {
            this.container.innerHTML = `
                <div style="display:flex; flex-direction:column; align-items:center; gap:20px; width:100%; max-width:500px; padding:32px; background:rgba(15,23,42,0.85); border:1px solid rgba(255,255,255,0.12); border-radius:16px; box-shadow:0 16px 48px rgba(0,0,0,0.6); backdrop-filter:blur(16px);">
                    <div style="display:flex; justify-content:center; color:var(--primary);">${typeof Icons !== 'undefined' ? Icons.get('fileAudio', { size: 64 }) : ''}</div>
                    <div style="font-size:1.15rem; font-weight:600; text-align:center; color:#ffffff; word-break:break-word;">${escapeHtml(file.name)}</div>
                    <audio controls autoplay style="width:100%;">
                        <source src="${previewUrl}" type="${mime}">
                        Your browser does not support audio playback.
                    </audio>
                </div>
            `;
            return;
        }

        // Video
        if (mime.startsWith("video/") || ["mp4", "webm", "ogv", "mov", "mkv", "avi"].includes(ext)) {
            this.container.innerHTML = `
                <video controls autoplay style="max-width:90vw; max-height:85vh; border-radius:12px; box-shadow:0 16px 48px rgba(0,0,0,0.7); outline:none;">
                    <source src="${previewUrl}" type="${mime}">
                    Your browser does not support video playback.
                </video>
            `;
            return;
        }

        // PDF
        if (mime === "application/pdf" || ext === "pdf") {
            this.container.innerHTML = `
                <iframe src="${previewUrl}" style="width:90vw; height:88vh; border:none; border-radius:12px; background:#ffffff; box-shadow:0 16px 48px rgba(0,0,0,0.7);"></iframe>
            `;
            return;
        }

        // Text / Code
        const textExts = ["txt", "md", "json", "py", "js", "ts", "html", "css", "yaml", "yml", "sh", "log", "csv", "xml", "ini", "env", "sql"];
        if (mime.startsWith("text/") || textExts.includes(ext)) {
            this.container.innerHTML = `<div style="color:var(--text-muted); display:flex; align-items:center; gap:8px;"><span>Loading text content...</span></div>`;
            fetch(previewUrl)
                .then(res => res.text())
                .then(text => {
                    this.container.innerHTML = "";
                    const pre = document.createElement("pre");
                    pre.className = "text-preview-box";
                    pre.textContent = text;
                    this.container.appendChild(pre);
                })
                .catch(() => this.renderFallback(file, downloadUrl));
            return;
        }

        // Fallback
        this.renderFallback(file, downloadUrl);
    }

    renderCurrentImage() {
        if (!this.currentFile) return;
        const file = this.currentFile;
        const previewUrl = `/api/files/preview?path=${encodeURIComponent(file.relative_path)}`;
        const downloadUrl = `/api/files/download?path=${encodeURIComponent(file.relative_path)}`;

        this.titleEl.textContent = file.name;
        this.titleEl.title = file.name;
        if (this.fileSizeEl) {
            this.fileSizeEl.textContent = typeof formatBytes === 'function' ? formatBytes(file.size) : '';
        }
        this.downloadBtn.onclick = () => window.open(downloadUrl, "_blank");
        this.updateControlsUI();
        this.resetZoom();

        const img = document.createElement("img");
        img.alt = file.name;
        img.src = previewUrl;

        // Double click to zoom in/out
        img.ondblclick = (e) => {
            e.stopPropagation();
            if (this.zoom === 1.0) {
                this.setZoom(2.0);
            } else {
                this.resetZoom();
            }
        };

        img.onload = () => {
            if (this.currentFile && this.currentFile.relative_path === file.relative_path) {
                this.container.innerHTML = "";
                this.container.appendChild(img);
                this.activeImg = img;
                this.applyTransform();

                // Smart background preloading of adjacent images
                this.preloadNeighbors();
            }
        };

        img.onerror = () => {
            if (this.currentFile && this.currentFile.relative_path === file.relative_path) {
                this.renderFallback(file, downloadUrl);
            }
        };
    }

    preloadNeighbors() {
        if (!this.playlist || this.playlist.length <= 1) return;
        const nextIdx = (this.currentIndex + 1) % this.playlist.length;
        const prevIdx = (this.currentIndex - 1 + this.playlist.length) % this.playlist.length;

        [this.playlist[nextIdx], this.playlist[prevIdx]].forEach(f => {
            if (f && f.relative_path) {
                const preload = new Image();
                preload.src = `/api/files/preview?path=${encodeURIComponent(f.relative_path)}`;
            }
        });
    }

    nextImage(isAuto = false) {
        if (!this.playlist || this.playlist.length <= 1) return;

        if (!isAuto && this.isSlideshow) {
            this.resetSlideshowTimer();
        }

        let nextIdx = (this.currentIndex + 1) % this.playlist.length;
        this.currentIndex = nextIdx;
        this.currentFile = this.playlist[nextIdx];
        this.renderCurrentImage();

        if (this.isSlideshow) {
            this.animateProgressBar();
        }
    }

    prevImage() {
        if (!this.playlist || this.playlist.length <= 1) return;

        if (this.isSlideshow) {
            this.resetSlideshowTimer();
        }

        let prevIdx = (this.currentIndex - 1 + this.playlist.length) % this.playlist.length;
        this.currentIndex = prevIdx;
        this.currentFile = this.playlist[prevIdx];
        this.renderCurrentImage();

        if (this.isSlideshow) {
            this.animateProgressBar();
        }
    }

    // Zoom Controls
    zoomIn() {
        this.setZoom(this.zoom + 0.25);
    }

    zoomOut() {
        this.setZoom(this.zoom - 0.25);
    }

    resetZoom() {
        this.zoom = 1.0;
        this.panX = 0;
        this.panY = 0;
        this.applyTransform();
    }

    setZoom(level) {
        const clamped = Math.max(0.5, Math.min(4.0, Math.round(level * 100) / 100));
        this.zoom = clamped;
        if (this.zoom === 1.0) {
            this.panX = 0;
            this.panY = 0;
        }
        this.applyTransform();
    }

    applyTransform() {
        if (this.zoomLevelEl) {
            this.zoomLevelEl.textContent = `${Math.round(this.zoom * 100)}%`;
        }

        if (this.container) {
            if (this.zoom > 1.0) {
                this.container.classList.add("is-zoomed");
            } else {
                this.container.classList.remove("is-zoomed");
            }
        }

        if (this.activeImg) {
            this.activeImg.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
        }
    }

    // Slideshow
    toggleSlideshow() {
        if (this.isSlideshow) {
            this.stopSlideshow();
        } else {
            this.startSlideshow();
        }
    }

    startSlideshow() {
        if (!this.playlist || this.playlist.length <= 1) return;
        this.isSlideshow = true;

        if (this.slideshowBtn) {
            this.slideshowBtn.classList.add("is-playing");
            this.slideshowBtn.title = "Pause Slideshow (Space)";
        }
        if (this.slideshowText) {
            this.slideshowText.textContent = "Pause";
        }
        if (this.slideshowIcon && typeof Icons !== 'undefined') {
            this.slideshowIcon.innerHTML = Icons.get('pause', { size: 15 });
        }

        this.animateProgressBar();
        this.resetSlideshowTimer();
    }

    stopSlideshow() {
        this.isSlideshow = false;
        if (this.slideshowTimer) {
            clearInterval(this.slideshowTimer);
            this.slideshowTimer = null;
        }

        if (this.progressBar) {
            this.progressBar.classList.remove("animating");
            this.progressBar.style.width = "0%";
        }

        if (this.slideshowBtn) {
            this.slideshowBtn.classList.remove("is-playing");
            this.slideshowBtn.title = "Slideshow (Space)";
        }
        if (this.slideshowText) {
            this.slideshowText.textContent = "Slideshow";
        }
        if (this.slideshowIcon && typeof Icons !== 'undefined') {
            this.slideshowIcon.innerHTML = Icons.get('play', { size: 15 });
        }
    }

    animateProgressBar() {
        if (!this.progressBar) return;
        this.progressBar.classList.remove("animating");
        this.progressBar.style.width = "0%";

        // Trigger reflow to restart transition
        void this.progressBar.offsetWidth;

        this.progressBar.classList.add("animating");
        this.progressBar.style.width = "100%";
    }

    resetSlideshowTimer() {
        if (this.slideshowTimer) {
            clearInterval(this.slideshowTimer);
            this.slideshowTimer = null;
        }
        if (this.isSlideshow) {
            this.slideshowTimer = setInterval(() => {
                this.nextImage(true);
            }, this.slideshowIntervalMs);
        }
    }

    // Full Mode / Fullscreen
    toggleFullscreen() {
        if (this.isFullMode) {
            this.exitFullscreen();
        } else {
            this.enterFullscreen();
        }
    }

    enterFullscreen() {
        this.isFullMode = true;
        if (this.modal) {
            this.modal.classList.add("is-full-mode");
        }

        // Request native fullscreen on document.documentElement for edge-to-edge cinema
        const de = document.documentElement;
        const req = de.requestFullscreen || de.webkitRequestFullscreen || de.mozRequestFullScreen || de.msRequestFullscreen;
        if (req && !document.fullscreenElement) {
            req.call(de).catch(() => {
                // Fallback to CSS full mode which is already active
            });
        }

        this.updateFullscreenUI();
        this.wakeControls();
    }

    exitFullscreen() {
        this.isFullMode = false;
        if (this.modal) {
            this.modal.classList.remove("is-full-mode");
            this.wakeControls();
        }

        if (this.idleTimer) {
            clearTimeout(this.idleTimer);
            this.idleTimer = null;
        }

        if (document.fullscreenElement) {
            const exit = document.exitFullscreen || document.webkitExitFullscreen || document.mozCancelFullScreen || document.msExitFullscreen;
            if (exit) exit.call(document).catch(() => {});
        }

        this.updateFullscreenUI();
    }

    updateFullscreenUI() {
        if (!this.fullscreenBtn) return;
        if (this.fullscreenText) {
            this.fullscreenText.textContent = this.isFullMode ? "Exit Full" : "Full Mode";
        }
        this.fullscreenBtn.title = this.isFullMode ? "Exit Fullscreen (F / Esc)" : "Full Mode (F)";

        if (this.isFullMode) {
            this.fullscreenBtn.classList.add("is-active");
        } else {
            this.fullscreenBtn.classList.remove("is-active");
        }

        if (this.fullscreenIcon && typeof Icons !== 'undefined') {
            this.fullscreenIcon.innerHTML = Icons.get(this.isFullMode ? 'fullscreenExit' : 'fullscreen', { size: 16 });
        }
    }

    handleKeyDown(e) {
        if (!this.modal || this.modal.style.display !== "flex") return;
        if (e.target && ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;

        this.wakeControls();
        const hasGallery = this.playlist && this.playlist.length > 1;

        if (e.key === "ArrowRight") {
            if (hasGallery) {
                e.preventDefault();
                this.nextImage();
            }
        } else if (e.key === "ArrowLeft") {
            if (hasGallery) {
                e.preventDefault();
                this.prevImage();
            }
        } else if (e.key === " " || e.code === "Space") {
            if (hasGallery) {
                e.preventDefault();
                this.toggleSlideshow();
            }
        } else if (e.key === "f" || e.key === "F") {
            e.preventDefault();
            this.toggleFullscreen();
        } else if (e.key === "+" || e.key === "=") {
            if (this.activeImg) {
                e.preventDefault();
                this.zoomIn();
            }
        } else if (e.key === "-" || e.key === "_") {
            if (this.activeImg) {
                e.preventDefault();
                this.zoomOut();
            }
        } else if (e.key === "0") {
            if (this.activeImg) {
                e.preventDefault();
                this.resetZoom();
            }
        } else if (e.key === "Escape") {
            e.preventDefault();
            if (this.isFullMode) {
                this.exitFullscreen();
            } else {
                this.close();
            }
        }
    }

    renderFallback(file, downloadUrl) {
        this.activeImg = null;
        const boxIcon = typeof Icons !== 'undefined' ? Icons.get('box', { size: 64, strokeWidth: 1.5 }) : '';
        const dlIcon = typeof Icons !== 'undefined' ? Icons.get('download', { size: 16 }) : '';
        this.container.innerHTML = `
            <div style="display:flex; flex-direction:column; align-items:center; gap:18px; padding:48px; text-align:center; background:rgba(15,23,42,0.85); border:1px solid rgba(255,255,255,0.12); border-radius:16px; box-shadow:0 16px 48px rgba(0,0,0,0.6); backdrop-filter:blur(16px); max-width:480px;">
                <div style="display:flex; justify-content:center; color:var(--text-muted); opacity:0.8;">${boxIcon}</div>
                <div style="font-size:1.25rem; font-weight:600; color:#ffffff; word-break:break-word;">${escapeHtml(file.name)}</div>
                <div style="color:var(--text-muted); font-size:0.92rem;">Preview is not available for this file type (${escapeHtml(file.mime_type || "binary")}).</div>
                <a href="${downloadUrl}" download class="primary-btn" style="text-decoration:none; margin-top:8px; display:inline-flex; align-items:center; gap:8px;">
                    ${dlIcon} <span>Download File (${typeof formatBytes === 'function' ? formatBytes(file.size) : ''})</span>
                </a>
            </div>
        `;
    }

    close() {
        this.stopSlideshow();
        if (this.isFullMode) {
            this.exitFullscreen();
        }
        if (this.tapTimeout) {
            clearTimeout(this.tapTimeout);
            this.tapTimeout = null;
        }
        this.isPinching = false;
        this.initialPinchDistance = 0;
        this.lastTapTime = 0;
        if (this.modal) {
            this.modal.style.display = "none";
            this.container.innerHTML = "";
        }
        this.activeImg = null;
        this.currentFile = null;
        this.playlist = [];
        this.currentIndex = -1;
        this.resetZoom();
    }
}

const filePreviewer = new FilePreviewer();

