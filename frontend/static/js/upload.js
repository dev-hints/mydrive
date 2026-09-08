/**
 * MyDrive Resumable Chunked Upload Manager
 * Engineered for Android Termux + Debian PRoot userspace resilience
 */

class UploadManager {
    constructor() {
        this.queue = [];
        this.activeUploads = 0;
        this.maxConcurrent = 2; // Keep low for mobile RAM and CPU friendliness
        this.chunkSize = 4 * 1024 * 1024; // 4MB chunks
        this.onUploadComplete = null;
        this.drawer = null;
        this.drawerList = null;
    }

    init(onUploadComplete) {
        this.onUploadComplete = onUploadComplete;
        this.drawer = document.getElementById("uploadDrawer");
        this.drawerList = document.getElementById("uploadDrawerList");
        this.setupDragAndDrop();
    }

    getCsrfToken() {
        const match = document.cookie.match(/(^|;)\s*mydrive_csrf\s*=\s*([^;]+)/);
        return match ? match[2] : "";
    }

    setupDragAndDrop() {
        const dropZone = document.getElementById("dropZoneContainer");
        const dropOverlay = document.getElementById("dropOverlay");

        if (!dropZone || !dropOverlay) return;

        ['dragenter', 'dragover'].forEach(eventName => {
            window.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropOverlay.classList.add("active");
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            window.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (e.type === 'drop' || (e.clientX <= 0 || e.clientY <= 0)) {
                    dropOverlay.classList.remove("active");
                }
            }, false);
        });

        window.addEventListener('drop', (e) => {
            e.preventDefault();
            dropOverlay.classList.remove("active");
            const files = e.dataTransfer.files;
            if (files && files.length > 0) {
                this.addFiles(Array.from(files), window.currentPath || "");
            }
        });
    }

    addFiles(files, targetDir) {
        if (!files || files.length === 0) return;

        this.drawer.style.display = "flex";
        this.drawer.classList.remove("minimized");

        files.forEach(file => {
            const task = {
                id: "up_" + Math.random().toString(36).substring(2, 9),
                file: file,
                targetDir: targetDir,
                status: "queued", // queued, uploading, completed, error, cancelled
                totalChunks: Math.ceil(file.size / this.chunkSize) || 1,
                currentChunk: 0,
                uploadedBytes: 0,
                speed: 0,
                startTime: 0,
                serverUploadId: null,
                xhr: null,
                retryCount: 0
            };

            this.queue.push(task);
            this.renderTaskItem(task);
        });

        this.processQueue();
    }

    renderTaskItem(task) {
        const el = document.createElement("div");
        el.className = "upload-item";
        el.id = `task_${task.id}`;
        el.innerHTML = `
            <div class="upload-item-header">
                <span class="upload-item-name" title="${escapeHtml(task.file.name)}">${escapeHtml(task.file.name)}</span>
                <span class="upload-item-status" id="status_${task.id}">Waiting...</span>
                <button class="drawer-ctrl-btn" onclick="uploadManager.cancelTask('${task.id}')" title="Cancel" style="display:inline-flex; align-items:center; justify-content:center;">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                </button>
            </div>
            <div class="upload-progress-bar">
                <div class="upload-progress-fill" id="bar_${task.id}"></div>
            </div>
            <div class="upload-item-meta">
                <span id="speed_${task.id}">${formatBytes(task.file.size)}</span>
                <span id="percent_${task.id}">0%</span>
            </div>
        `;
        this.drawerList.prepend(el);
    }

    processQueue() {
        if (this.activeUploads >= this.maxConcurrent) return;

        const nextTask = this.queue.find(t => t.status === "queued");
        if (!nextTask) return;

        this.activeUploads++;
        nextTask.status = "uploading";
        nextTask.startTime = Date.now();
        this.startUpload(nextTask);
    }

    async startUpload(task) {
        const statusEl = document.getElementById(`status_${task.id}`);
        if (statusEl) statusEl.textContent = "Initializing...";

        try {
            // Step 1: Init chunked upload
            const initRes = await fetch("/api/upload/init", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": this.getCsrfToken()
                },
                body: JSON.stringify({
                    filename: task.file.name,
                    target_dir: task.targetDir,
                    total_size: task.file.size,
                    total_chunks: task.totalChunks,
                    mime_type: task.file.type || null,
                    overwrite: false
                })
            });

            if (!initRes.ok) {
                const err = await initRes.json().catch(() => ({ detail: "Init failed" }));
                throw new Error(err.detail || "Server rejected upload init");
            }

            const initData = await initRes.json();
            task.serverUploadId = initData.upload_id;

            // Step 2: Upload chunks sequentially
            await this.uploadNextChunk(task);

        } catch (err) {
            console.error("Upload error:", err);
            this.handleUploadError(task, err.message);
        }
    }

    async uploadNextChunk(task) {
        if (task.status === "cancelled") return;

        if (task.currentChunk >= task.totalChunks) {
            // All chunks sent, finish
            await this.finishUpload(task);
            return;
        }

        const start = task.currentChunk * this.chunkSize;
        const end = Math.min(start + this.chunkSize, task.file.size);
        const chunkBlob = task.file.slice(start, end);

        const formData = new FormData();
        formData.append("upload_id", task.serverUploadId);
        formData.append("chunk_index", task.currentChunk);
        formData.append("chunk_file", chunkBlob, task.file.name);

        const xhr = new XMLHttpRequest();
        task.xhr = xhr;

        xhr.open("POST", "/api/upload/chunk");
        xhr.setRequestHeader("X-CSRF-Token", this.getCsrfToken());

        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const totalUploaded = start + e.loaded;
                const percent = Math.min(99, Math.round((totalUploaded / task.file.size) * 100));

                const elapsed = (Date.now() - task.startTime) / 1000;
                const speed = elapsed > 0 ? (totalUploaded / elapsed) : 0;

                this.updateProgress(task.id, percent, totalUploaded, task.file.size, speed);
            }
        };

        xhr.onload = async () => {
            task.xhr = null;
            if (xhr.status >= 200 && xhr.status < 300) {
                task.currentChunk++;
                task.retryCount = 0;
                await this.uploadNextChunk(task);
            } else {
                let errMsg = "Chunk upload failed";
                try {
                    const res = JSON.parse(xhr.responseText);
                    errMsg = res.detail || errMsg;
                } catch (_) {}

                if (task.retryCount < 3) {
                    task.retryCount++;
                    console.warn(`Retrying chunk ${task.currentChunk} for ${task.file.name} (attempt ${task.retryCount})...`);
                    setTimeout(() => this.uploadNextChunk(task), 1000 * task.retryCount);
                } else {
                    this.handleUploadError(task, errMsg);
                }
            }
        };

        xhr.onerror = () => {
            task.xhr = null;
            if (task.retryCount < 3) {
                task.retryCount++;
                setTimeout(() => this.uploadNextChunk(task), 1500 * task.retryCount);
            } else {
                this.handleUploadError(task, "Network disconnect during upload");
            }
        };

        xhr.send(formData);
    }

    async finishUpload(task) {
        const statusEl = document.getElementById(`status_${task.id}`);
        if (statusEl) statusEl.textContent = "Assembling...";

        try {
            const finishRes = await fetch("/api/upload/finish", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": this.getCsrfToken()
                },
                body: JSON.stringify({
                    upload_id: task.serverUploadId
                })
            });

            if (!finishRes.ok) {
                const err = await finishRes.json().catch(() => ({ detail: "Finish failed" }));
                throw new Error(err.detail || "Server assembly error");
            }

            task.status = "completed";
            this.updateProgress(task.id, 100, task.file.size, task.file.size, 0);

            if (statusEl) {
                statusEl.textContent = "Completed";
                statusEl.style.color = "var(--accent-green)";
            }

            showToast(`Uploaded "${task.file.name}"`, "success");

            if (this.onUploadComplete) {
                this.onUploadComplete();
            }

        } catch (err) {
            this.handleUploadError(task, err.message);
        } finally {
            this.activeUploads--;
            this.processQueue();
        }
    }

    handleUploadError(task, message) {
        task.status = "error";
        this.activeUploads--;
        const statusEl = document.getElementById(`status_${task.id}`);
        if (statusEl) {
            statusEl.textContent = "Failed";
            statusEl.style.color = "var(--accent-red)";
        }
        showToast(`Failed to upload ${task.file.name}: ${message}`, "error");
        this.processQueue();
    }

    cancelTask(taskId) {
        const task = this.queue.find(t => t.id === taskId);
        if (!task) return;

        task.status = "cancelled";
        if (task.xhr) {
            task.xhr.abort();
        }

        if (task.serverUploadId) {
            fetch(`/api/upload/cancel/${task.serverUploadId}`, {
                method: "POST",
                headers: { "X-CSRF-Token": this.getCsrfToken() }
            }).catch(() => {});
        }

        const taskEl = document.getElementById(`task_${taskId}`);
        if (taskEl) taskEl.remove();

        this.queue = this.queue.filter(t => t.id !== taskId);
        this.activeUploads = Math.max(0, this.activeUploads - 1);
        this.processQueue();

        if (this.queue.length === 0) {
            this.drawer.style.display = "none";
        }
    }

    updateProgress(taskId, percent, uploaded, total, speed) {
        const bar = document.getElementById(`bar_${taskId}`);
        const percentEl = document.getElementById(`percent_${taskId}`);
        const speedEl = document.getElementById(`speed_${taskId}`);

        if (bar) bar.style.width = `${percent}%`;
        if (percentEl) percentEl.textContent = `${percent}%`;
        if (speedEl) {
            const speedFormatted = speed > 0 ? `${formatBytes(speed)}/s` : "";
            speedEl.textContent = `${formatBytes(uploaded)} / ${formatBytes(total)} ${speedFormatted ? "• " + speedFormatted : ""}`;
        }
    }
}

const uploadManager = new UploadManager();
