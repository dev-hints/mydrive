/**
 * MyDrive Main Client Application
 */

let currentView = "drive"; // "drive", "recent", "starred", "photos", "videos", "documents", "shares", "trash", "audit", "search"
let currentPath = "";
let viewMode = localStorage.getItem("mydrive_view_mode") || "grid"; // "grid" or "list"
let currentItems = [];
let selectedItem = null;
let currentSort = { field: "name", asc: true };
let selectedPaths = new Set();

// Utility Functions
function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

async function copyTextToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (_) {}
    }
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-9999px";
    textArea.style.top = "-9999px";
    textArea.setAttribute("readonly", "");
    document.body.appendChild(textArea);
    textArea.select();
    textArea.setSelectionRange(0, 99999);
    let success = false;
    try {
        success = document.execCommand("copy");
    } catch (_) {
        success = false;
    }
    document.body.removeChild(textArea);
    if (!success) {
        throw new Error("Copy command not supported");
    }
    return true;
}

function formatBytes(bytes, decimals = 1) {
    if (bytes === 0) return '0 B';
    if (!bytes) return '-';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function formatDate(isoStr) {
    if (!isoStr) return "-";
    try {
        const d = new Date(isoStr);
        return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch (_) {
        return isoStr;
    }
}

function getCsrfToken() {
    const match = document.cookie.match(/(^|;)\s*mydrive_csrf\s*=\s*([^;]+)/);
    return match ? match[2] : "";
}

function showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    const icon = type === "success" 
        ? (typeof Icons !== "undefined" ? Icons.get("check", { size: 16 }) : "") 
        : type === "error" 
        ? (typeof Icons !== "undefined" ? Icons.get("alert", { size: 16 }) : "") 
        : (typeof Icons !== "undefined" ? Icons.get("info", { size: 16 }) : "");
    toast.innerHTML = `<span style="display:inline-flex; align-items:center;">${icon}</span> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transition = "opacity 0.3s ease";
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function getFileIcon(name, isDir) {
    if (typeof Icons !== "undefined") {
        return Icons.file(name, isDir);
    }
    return isDir ? "Folder" : "File";
}

let currentUser = null;
let activeClientVersion = null;

async function checkAppVersion() {
    try {
        const res = await fetch("/api/version");
        if (res.ok) {
            const data = await res.json();
            if (activeClientVersion && activeClientVersion !== data.version) {
                // New deployment/update detected: silently refresh to load latest assets
                window.location.reload();
            }
            activeClientVersion = data.version;
        }
    } catch (_) {}
}

// App Initialization
document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initUI();
    checkCurrentUser();
    checkAppVersion();
    uploadManager.init(() => refreshCurrentView());
    loadStorageStats();
    navigateToPath("");

    // Automatically check for version updates periodically
    setInterval(checkAppVersion, 30000);

    // Real-time automatic data synchronization (every 3.5s)
    setInterval(() => autoSyncData(false), 3500);

    // Instant real-time refresh on window focus and tab visibility change
    window.addEventListener("focus", () => {
        checkAppVersion();
        autoSyncData(true);
    });
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            autoSyncData(true);
        }
    });
});

function initTheme() {
    const savedTheme = localStorage.getItem("mydrive_theme") || "system";
    applyTheme(savedTheme);

    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", e => {
        if (localStorage.getItem("mydrive_theme") === "system") {
            document.documentElement.setAttribute("data-theme", e.matches ? "dark" : "light");
        }
    });
}

function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme") || "light";
    const next = current === "dark" ? "light" : "dark";
    localStorage.setItem("mydrive_theme", next);
    applyTheme(next);
}

function applyTheme(theme) {
    if (theme === "system") {
        const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        document.documentElement.setAttribute("data-theme", prefersDark ? "dark" : "light");
    } else {
        document.documentElement.setAttribute("data-theme", theme);
    }
    const themeBtn = document.getElementById("themeToggleBtn");
    if (themeBtn) {
        const isDark = document.documentElement.getAttribute("data-theme") === "dark";
        if (typeof Icons !== "undefined") {
            themeBtn.innerHTML = isDark ? Icons.get("sun", { size: 18 }) : Icons.get("moon", { size: 18 });
        }
    }
}

function initUI() {
    // View mode setup
    setViewMode(viewMode);

    // Global click listener to close context menu and dropdowns
    document.addEventListener("click", (e) => {
        const ctx = document.getElementById("contextMenu");
        if (ctx && !e.target.closest("#contextMenu") && !e.target.closest(".card-menu-btn")) {
            closeContextMenu();
        }

        const newMenu = document.getElementById("newMenuDropdown");
        if (newMenu && !e.target.closest("#newBtn") && !e.target.closest("#newMenuDropdown")) {
            newMenu.style.display = "none";
        }
        
        const userMenu = document.getElementById("userMenuDropdown");
        if (userMenu && !e.target.closest("#userAvatarBtn") && !e.target.closest("#userMenuDropdown")) {
            userMenu.style.display = "none";
        }
    });

    // Close menus on screen orientation change or resize
    window.addEventListener("resize", () => {
        closeContextMenu();
    });

    // Mobile sidebar toggle and gestures
    const toggleBtn = document.getElementById("mobileSidebarToggle");
    const closeBtn = document.getElementById("sidebarCloseBtn");
    const sidebar = document.getElementById("appSidebar");
    const backdrop = document.getElementById("sidebarBackdrop");

    const closeSidebar = () => {
        if (sidebar) sidebar.classList.remove("open");
        if (backdrop) backdrop.classList.remove("active");
    };

    if (toggleBtn && sidebar && backdrop) {
        toggleBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            sidebar.classList.toggle("open");
            backdrop.classList.toggle("active");
        });
        backdrop.addEventListener("click", closeSidebar);
    }
    if (closeBtn) {
        closeBtn.addEventListener("click", closeSidebar);
    }

    // Touch swipe left on sidebar to close
    if (sidebar) {
        let sbTouchStartX = 0;
        let sbTouchStartY = 0;
        sidebar.addEventListener("touchstart", (e) => {
            if (e.touches && e.touches.length === 1) {
                sbTouchStartX = e.touches[0].clientX;
                sbTouchStartY = e.touches[0].clientY;
            }
        }, { passive: true });

        sidebar.addEventListener("touchend", (e) => {
            if (e.changedTouches && e.changedTouches.length === 1) {
                const dx = e.changedTouches[0].clientX - sbTouchStartX;
                const dy = Math.abs(e.changedTouches[0].clientY - sbTouchStartY);
                if (dx < -45 && dy < 80) {
                    closeSidebar();
                }
            }
        }, { passive: true });
    }

    // Search input handler
    const searchInput = document.getElementById("searchInput");
    let searchDebounce = null;
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            clearTimeout(searchDebounce);
            const query = e.target.value.trim();
            if (currentView === "contacts") {
                searchDebounce = setTimeout(() => loadContacts(query), 250);
                return;
            }
            if (!query) {
                if (currentView === "search") {
                    navigateToPath(currentPath);
                }
                return;
            }
            searchDebounce = setTimeout(() => executeSearch(query), 350);
        });
    }
}

function setViewMode(mode) {
    viewMode = mode;
    localStorage.setItem("mydrive_view_mode", mode);

    const gridBtn = document.getElementById("viewModeGrid");
    const listBtn = document.getElementById("viewModeList");
    if (gridBtn && listBtn) {
        if (mode === "grid") {
            gridBtn.classList.add("active");
            listBtn.classList.remove("active");
        } else {
            listBtn.classList.add("active");
            gridBtn.classList.remove("active");
        }
    }
    if (currentView === "contacts") {
        renderContactsView(currentContacts, currentContacts.length);
        return;
    }
    renderItems(currentItems);
}

function switchNav(viewName) {
    clearSelection();
    currentView = viewName;
    document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
    const navEl = document.getElementById(`nav_${viewName}`);
    if (navEl) navEl.classList.add("active");

    const dlFolderBtn = document.getElementById("downloadCurrentFolderBtn");
    if (dlFolderBtn && viewName !== "drive") {
        dlFolderBtn.style.display = "none";
    }

    // Close mobile sidebar if open
    const sidebar = document.getElementById("appSidebar");
    const backdrop = document.getElementById("sidebarBackdrop");
    if (sidebar) sidebar.classList.remove("open");
    if (backdrop) backdrop.classList.remove("active");

    if (viewName === "drive") {
        navigateToPath(currentPath);
    } else if (viewName === "recent") {
        loadRecentFiles();
    } else if (viewName === "starred") {
        loadStarredFiles();
    } else if (viewName === "photos") {
        loadPhotos();
    } else if (viewName === "videos") {
        loadVideos();
    } else if (viewName === "documents") {
        loadDocuments();
    } else if (viewName === "shares") {
        loadSharedLinks();
    } else if (viewName === "contacts") {
        loadContacts();
    } else if (viewName === "trash") {
        loadTrash();
    }
}

function refreshCurrentView() {
    clearSelection();
    loadStorageStats();
    if (currentView === "drive") {
        navigateToPath(currentPath);
    } else if (currentView === "recent") {
        loadRecentFiles();
    } else if (currentView === "starred") {
        loadStarredFiles();
    } else if (currentView === "photos") {
        loadPhotos();
    } else if (currentView === "videos") {
        loadVideos();
    } else if (currentView === "documents") {
        loadDocuments();
    } else if (currentView === "shares") {
        loadSharedLinks();
    } else if (currentView === "contacts") {
        loadContacts();
    } else if (currentView === "trash") {
        loadTrash();
    }
}

let isAutoSyncing = false;

async function autoSyncData(force = false) {
    if (isAutoSyncing) return;
    if (!force && document.hidden) return;

    // Do not auto-sync if items are selected or a modal is actively open
    if (selectedPaths.size > 0) return;

    const openModals = document.querySelectorAll(".modal-overlay");
    for (const m of openModals) {
        if (m.style.display && m.style.display !== "none") return;
    }

    if (currentView === "search") return;

    isAutoSyncing = true;
    try {
        let endpoint = "";
        if (currentView === "photos") {
            endpoint = "/api/files/photos";
        } else if (currentView === "videos") {
            endpoint = "/api/files/videos";
        } else if (currentView === "documents") {
            endpoint = "/api/files/documents";
        } else if (currentView === "recent") {
            endpoint = "/api/files/recent";
        } else if (currentView === "starred") {
            endpoint = "/api/files/starred";
        } else if (currentView === "drive") {
            endpoint = `/api/files?path=${encodeURIComponent(currentPath)}`;
        } else if (currentView === "trash") {
            endpoint = "/api/files/trash";
        }

        if (!endpoint) return;

        const res = await fetch(endpoint);
        if (!res.ok) return;
        const data = await res.json();
        const newItems = data.items || [];

        // Fingerprint comparison to avoid unnecessary DOM re-renders
        const currentFingerprint = currentItems.map(i => `${i.id || i.relative_path}:${i.name}:${i.size}:${i.modified_at}:${i.is_starred}`).join("|");
        const newFingerprint = newItems.map(i => `${i.id || i.relative_path}:${i.name}:${i.size}:${i.modified_at}:${i.is_starred}`).join("|");

        if (currentFingerprint !== newFingerprint) {
            currentItems = newItems;
            renderItems(currentItems);
            loadStorageStats();
        }
    } catch (_) {
    } finally {
        isAutoSyncing = false;
    }
}

// Navigation and Directory Loading
async function navigateToPath(path) {
    clearSelection();
    currentView = "drive";
    currentPath = path;
    document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
    const driveNav = document.getElementById("nav_drive");
    if (driveNav) driveNav.classList.add("active");

    const dlFolderBtn = document.getElementById("downloadCurrentFolderBtn");
    if (dlFolderBtn) {
        if (path) {
            dlFolderBtn.style.display = "inline-flex";
            const folderName = path.split("/").pop();
            const dlSvg = typeof Icons !== "undefined" ? Icons.get("download", { size: 14 }) : "";
            dlFolderBtn.innerHTML = `${dlSvg} <span>Download "${escapeHtml(folderName)}"</span>`;
        } else {
            dlFolderBtn.style.display = "none";
        }
    }

    renderBreadcrumbs(path);

    try {
        const res = await fetch(`/api/files?path=${encodeURIComponent(path)}`);
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Failed to load directory");
        }
        const data = await res.json();
        currentItems = data.items;
        renderItems(currentItems);
    } catch (err) {
        showToast(err.message, "error");
        renderEmptyState("Failed to load folder", err.message);
    }
}

function downloadCurrentFolder() {
    if (!currentPath) {
        showToast("Select a folder to download", "info");
        return;
    }
    window.location.href = `/api/files/download?path=${encodeURIComponent(currentPath)}`;
}

function renderBreadcrumbs(path) {
    const container = document.getElementById("breadcrumbContainer");
    if (!container) return;

    container.innerHTML = "";

    const rootItem = document.createElement("span");
    rootItem.className = `breadcrumb-item ${!path ? "active" : ""}`;
    const rootBrandIcon = typeof Icons !== "undefined" ? Icons.get("infinity", { size: 14, strokeWidth: 2.2 }) : "";
    rootItem.innerHTML = `<span style="display:inline-flex; align-items:center; gap:6px;">${rootBrandIcon} <span class="breadcrumb-root-label"><span class="breadcrumb-root-full">StrangeInfinity </span>Drive</span></span>`;
    rootItem.onclick = () => navigateToPath("");
    container.appendChild(rootItem);

    if (!path) return;

    const parts = path.split("/").filter(Boolean);
    let accum = "";
    parts.forEach((part, idx) => {
        accum += (accum ? "/" : "") + part;
        const currentAccum = accum;

        const sep = document.createElement("span");
        sep.className = "breadcrumb-separator";
        sep.textContent = "›";
        container.appendChild(sep);

        const item = document.createElement("span");
        item.className = `breadcrumb-item ${idx === parts.length - 1 ? "active" : ""}`;
        item.textContent = part;
        item.onclick = () => navigateToPath(currentAccum);
        container.appendChild(item);
    });
}

function renderItems(items) {
    const container = document.getElementById("fileViewContent");
    if (!container) return;

    if (!items || items.length === 0) {
        let emptyTitle = "No files or folders";
        let emptySub = "Drag files here or click '+ New' to upload.";
        if (currentView === "trash") {
            emptyTitle = "Trash is empty";
            emptySub = "Items moved to trash will appear here.";
        } else if (currentView === "photos") {
            emptyTitle = "No photos found";
            emptySub = "Photos anywhere in your folders will appear here.";
        } else if (currentView === "videos") {
            emptyTitle = "No videos found";
            emptySub = "Videos anywhere in your folders will appear here.";
        } else if (currentView === "documents") {
            emptyTitle = "No documents found";
            emptySub = "Documents anywhere in your folders will appear here.";
        } else if (currentView === "recent") {
            emptyTitle = "No recent files";
            emptySub = "Files you modify or upload will appear here.";
        } else if (currentView === "starred") {
            emptyTitle = "No starred items";
            emptySub = "Star important files or folders to find them quickly.";
        }
        renderEmptyState(emptyTitle, emptySub);
        return;
    }

    // Apply sorting
    const sorted = [...items].sort((a, b) => {
        if (a.is_directory !== b.is_directory) {
            return a.is_directory ? -1 : 1;
        }
        let valA = a[currentSort.field];
        let valB = b[currentSort.field];

        if (typeof valA === "string") {
            return currentSort.asc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        return currentSort.asc ? (valA - valB) : (valB - valA);
    });

    if (viewMode === "grid") {
        renderGridView(container, sorted);
    } else {
        renderListView(container, sorted);
    }
}

// Long-press detection for touch devices
let itemLongPressTimer = null;
let itemLongPressTriggered = false;
let itemTouchStartX = 0;
let itemTouchStartY = 0;

function onItemTouchStart(e, relPath, isDir) {
    if (!e.touches || e.touches.length > 1) {
        if (itemLongPressTimer) clearTimeout(itemLongPressTimer);
        return;
    }
    itemLongPressTriggered = false;
    const t = e.touches[0];
    itemTouchStartX = t.clientX;
    itemTouchStartY = t.clientY;
    itemLongPressTimer = setTimeout(() => {
        itemLongPressTriggered = true;
        if (navigator.vibrate) {
            try { navigator.vibrate(40); } catch (_) {}
        }
        handleContextMenu(e, relPath, isDir);
    }, 500);
}

function onItemTouchMove(e) {
    if (!itemLongPressTimer) return;
    if (!e.touches || e.touches.length === 0) return;
    const t = e.touches[0];
    const dx = Math.abs(t.clientX - itemTouchStartX);
    const dy = Math.abs(t.clientY - itemTouchStartY);
    if (dx > 10 || dy > 10) {
        clearTimeout(itemLongPressTimer);
        itemLongPressTimer = null;
    }
}

function onItemTouchEnd(e) {
    if (itemLongPressTimer) {
        clearTimeout(itemLongPressTimer);
        itemLongPressTimer = null;
    }
    if (itemLongPressTriggered) {
        if (e && e.cancelable) e.preventDefault();
        if (e) e.stopPropagation();
        setTimeout(() => { itemLongPressTriggered = false; }, 200);
    }
}

function renderGridView(container, items) {
    let html = `<div class="file-grid">`;
    items.forEach(item => {
        const icon = getFileIcon(item.name, item.is_directory);
        const meta = item.is_directory ? "Folder" : formatBytes(item.size);
        const ext = (item.name || "").split(".").pop().toLowerCase();
        const isImage = !item.is_directory && ((item.mime_type && item.mime_type.startsWith("image/")) || ["jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "ico", "avif", "heic"].includes(ext));
        const isVideo = !item.is_directory && ((item.mime_type && item.mime_type.startsWith("video/")) || ["mp4", "webm", "mov", "mkv", "avi", "flv", "m4v"].includes(ext));
        const previewSrc = isImage ? `/api/files/preview?path=${encodeURIComponent(item.relative_path)}` : null;
        const videoSrc = isVideo ? `/api/files/preview?path=${encodeURIComponent(item.relative_path)}` : null;
        const isSelected = selectedPaths.has(item.relative_path);
        const folderLocation = item.relative_path.includes('/')
            ? item.relative_path.substring(0, item.relative_path.lastIndexOf('/'))
            : '';

        let previewContent = `<div class="card-icon">${icon}</div>`;
        if (previewSrc) {
            previewContent = `
                <img src="${previewSrc}" class="card-preview-thumb" loading="lazy"
                     onerror="this.style.display='none'; if (this.nextElementSibling) this.nextElementSibling.style.display='flex';" />
                <div class="card-icon" style="display:none;">${icon}</div>
            `;
        } else if (videoSrc && (ext === 'mp4' || ext === 'webm')) {
            previewContent = `
                <video src="${videoSrc}#t=0.5" class="card-preview-thumb" preload="metadata" muted playsinline style="pointer-events:none;"></video>
                <div style="position:absolute; inset:0; display:flex; align-items:center; justify-content:center; pointer-events:none;">
                    <div style="width:30px; height:30px; border-radius:50%; background:rgba(0,0,0,0.6); color:white; display:flex; align-items:center; justify-content:center; box-shadow:0 2px 4px rgba(0,0,0,0.3);">
                        ${Icons.get('play', { size: 14, strokeWidth: 2.5 })}
                    </div>
                </div>
            `;
        }

        html += `
            <div class="file-card ${isSelected ? 'selected' : ''}" data-path="${escapeHtml(item.relative_path)}" data-is-dir="${item.is_directory}"
                 ontouchstart="onItemTouchStart(event, '${escapeHtml(item.relative_path)}', ${item.is_directory})"
                 ontouchmove="onItemTouchMove(event)"
                 ontouchend="onItemTouchEnd(event)"
                 onclick="handleItemClick('${escapeHtml(item.relative_path)}', ${item.is_directory})"
                 oncontextmenu="handleContextMenu(event, '${escapeHtml(item.relative_path)}', ${item.is_directory})">
                <input type="checkbox" class="card-select-checkbox" data-path="${escapeHtml(item.relative_path)}" ${isSelected ? 'checked' : ''}
                       onclick="event.stopPropagation()" onchange="toggleItemSelection(event, '${escapeHtml(item.relative_path)}')">
                <button class="card-menu-btn" onclick="event.stopPropagation(); handleContextMenu(event, '${escapeHtml(item.relative_path)}', ${item.is_directory})" title="More options" aria-label="More options">
                    ${Icons.get('moreVertical', { size: 14 })}
                </button>
                <button class="card-star-btn ${item.is_starred ? 'starred' : ''}" onclick="event.stopPropagation(); toggleStar('${escapeHtml(item.relative_path)}')" title="Star">
                    ${item.is_starred ? Icons.get('starFilled', { size: 14 }) : Icons.get('star', { size: 14 })}
                </button>
                <div class="card-preview-box">
                    ${previewContent}
                </div>
                <div class="card-details">
                    <span class="card-name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</span>
                    <span class="card-meta">${meta} • ${formatDate(item.modified_at)}</span>
                    ${folderLocation && currentView !== 'drive' ? `
                        <span class="card-folder" title="Folder: /${escapeHtml(folderLocation)}" onclick="event.stopPropagation(); navigateToPath('${escapeHtml(folderLocation)}')">
                            <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor" stroke="currentColor" style="color:#f59e0b; margin-right:3px; flex-shrink:0;"><path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2z"/></svg>
                            <span>${escapeHtml(folderLocation)}</span>
                        </span>
                    ` : ''}
                </div>
                <button class="card-dl-btn" onclick="event.stopPropagation(); downloadItem('${escapeHtml(item.relative_path)}')" title="Download ${item.is_directory ? 'Folder (ZIP)' : 'File'}">
                    ${Icons.get('download', { size: 14 })}
                </button>
            </div>
        `;
    });
    html += `</div>`;
    container.innerHTML = html;
    updateSelectionUI();
}

function renderListView(container, items) {
    const allSelected = items.length > 0 && items.every(i => selectedPaths.has(i.relative_path));
    let html = `
        <table class="file-table">
            <thead>
                <tr>
                    <th style="width:42px; text-align:center;">
                        <input type="checkbox" id="selectAllCheckbox" ${allSelected ? 'checked' : ''} onchange="toggleSelectAll(this.checked)" title="Select All">
                    </th>
                    <th onclick="changeSort('name')">Name</th>
                    <th class="col-date" onclick="changeSort('modified_at')">Last Modified</th>
                    <th class="col-size" onclick="changeSort('size')">Size</th>
                    <th class="col-actions" style="text-align:right;">Actions</th>
                </tr>
            </thead>
            <tbody>
    `;

    items.forEach(item => {
        const icon = getFileIcon(item.name, item.is_directory);
        const sizeStr = item.is_directory ? "-" : formatBytes(item.size);
        const isSelected = selectedPaths.has(item.relative_path);
        const folderLocation = item.relative_path.includes('/')
            ? item.relative_path.substring(0, item.relative_path.lastIndexOf('/'))
            : '';

        html += `
            <tr class="${isSelected ? 'selected' : ''}" data-path="${escapeHtml(item.relative_path)}"
                ontouchstart="onItemTouchStart(event, '${escapeHtml(item.relative_path)}', ${item.is_directory})"
                ontouchmove="onItemTouchMove(event)"
                ontouchend="onItemTouchEnd(event)"
                oncontextmenu="handleContextMenu(event, '${escapeHtml(item.relative_path)}', ${item.is_directory})"
                onclick="handleItemClick('${escapeHtml(item.relative_path)}', ${item.is_directory})">
                <td style="text-align:center;" onclick="event.stopPropagation()">
                    <input type="checkbox" class="card-select-checkbox" data-path="${escapeHtml(item.relative_path)}" style="position:static; opacity:1;" ${isSelected ? 'checked' : ''} onchange="toggleItemSelection(event, '${escapeHtml(item.relative_path)}')">
                </td>
                <td>
                    <div class="file-cell-name">
                        <span class="table-file-icon">${icon}</span>
                        <div style="display:flex; flex-direction:column; min-width:0;">
                            <span title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</span>
                            <span class="table-mobile-meta">${sizeStr} • ${formatDate(item.modified_at)}</span>
                            ${folderLocation && currentView !== 'drive' ? `
                                <span class="table-folder-link" onclick="event.stopPropagation(); navigateToPath('${escapeHtml(folderLocation)}')" title="Go to folder: /${escapeHtml(folderLocation)}">
                                    <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor" stroke="currentColor" style="color:#f59e0b; margin-right:3px; flex-shrink:0;"><path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2z"/></svg>
                                    <span>/${escapeHtml(folderLocation)}</span>
                                </span>
                            ` : ''}
                        </div>
                        ${item.is_starred ? `<span style="color:var(--accent-amber); display:inline-flex; align-items:center;">${Icons.get('starFilled', { size: 12 })}</span>` : ''}
                    </div>
                </td>
                <td class="col-date">${formatDate(item.modified_at)}</td>
                <td class="col-size">${sizeStr}</td>
                <td class="col-actions" style="text-align:right;" onclick="event.stopPropagation()">
                    <button class="icon-btn" style="width:30px; height:30px; display:inline-flex; align-items:center; justify-content:center;" title="Download ${item.is_directory ? 'Folder (ZIP)' : 'File'}" onclick="downloadItem('${escapeHtml(item.relative_path)}')">${Icons.get('download', { size: 14 })}</button>
                    <button class="icon-btn" style="width:30px; height:30px; display:inline-flex; align-items:center; justify-content:center;" title="More options" onclick="handleContextMenu(event, '${escapeHtml(item.relative_path)}', ${item.is_directory})">${Icons.get('moreVertical', { size: 14 })}</button>
                </td>
            </tr>
        `;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;
    updateSelectionUI();
}

// Multi-Selection Management
function toggleItemSelection(e, relPath) {
    if (e) e.stopPropagation();
    if (selectedPaths.has(relPath)) {
        selectedPaths.delete(relPath);
    } else {
        selectedPaths.add(relPath);
    }
    updateSelectionUI();
}

function toggleSelectAll(checked) {
    if (checked) {
        currentItems.forEach(item => selectedPaths.add(item.relative_path));
    } else {
        selectedPaths.clear();
    }
    updateSelectionUI();
}

function clearSelection() {
    selectedPaths.clear();
    updateSelectionUI();
}

function updateSelectionUI() {
    const bar = document.getElementById("selectionBar");
    const countText = document.getElementById("selectionCountText");
    const selectAllCheckbox = document.getElementById("selectAllCheckbox");

    if (bar && countText) {
        if (selectedPaths.size > 0) {
            bar.style.display = "flex";
            countText.textContent = `${selectedPaths.size} ${selectedPaths.size === 1 ? 'item' : 'items'} selected`;
        } else {
            bar.style.display = "none";
        }
    }

    if (selectAllCheckbox) {
        selectAllCheckbox.checked = currentItems.length > 0 && selectedPaths.size === currentItems.length;
        selectAllCheckbox.indeterminate = selectedPaths.size > 0 && selectedPaths.size < currentItems.length;
    }

    document.querySelectorAll(".card-select-checkbox").forEach(cb => {
        const path = cb.dataset.path;
        if (path) {
            cb.checked = selectedPaths.has(path);
        }
    });

    document.querySelectorAll(".file-card").forEach(card => {
        const path = card.dataset.path;
        if (path) {
            if (selectedPaths.has(path)) {
                card.classList.add("selected");
            } else {
                card.classList.remove("selected");
            }
        }
    });

    document.querySelectorAll(".file-table tbody tr").forEach(row => {
        const path = row.dataset.path;
        if (path) {
            if (selectedPaths.has(path)) {
                row.classList.add("selected");
            } else {
                row.classList.remove("selected");
            }
        }
    });
}

function downloadSelected() {
    if (selectedPaths.size === 0) {
        showToast("No items selected", "info");
        return;
    }

    const pathsArr = Array.from(selectedPaths);
    if (pathsArr.length === 1) {
        downloadItem(pathsArr[0]);
    } else {
        const encodedPaths = encodeURIComponent(pathsArr.join(","));
        window.location.href = `/api/files/download-batch?paths=${encodedPaths}`;
        showToast(`Preparing download for ${pathsArr.length} items...`, "info");
    }
}

async function deleteSelected() {
    if (selectedPaths.size === 0) return;

    const count = selectedPaths.size;
    if (!confirm(`Move ${count} selected ${count === 1 ? 'item' : 'items'} to Trash?`)) return;

    try {
        const res = await fetch("/api/files/batch-delete", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({ paths: Array.from(selectedPaths) })
        });

        if (res.ok) {
            showToast(`${count} items moved to Trash`, "info");
            clearSelection();
            refreshCurrentView();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to delete items", "error");
        }
    } catch (_) {
        showToast("Network error deleting items", "error");
    }
}

function renderEmptyState(title, subtitle) {
    const container = document.getElementById("fileViewContent");
    if (!container) return;
    const emptyFolderIcon = typeof Icons !== "undefined" ? Icons.get("folderEmpty", { size: 56 }) : "";
    container.innerHTML = `
        <div class="empty-state">
            <div class="empty-icon">${emptyFolderIcon}</div>
            <div class="empty-title">${escapeHtml(title)}</div>
            <div class="empty-subtitle">${escapeHtml(subtitle)}</div>
        </div>
    `;
}

function handleItemClick(relPath, isDir) {
    if (itemLongPressTriggered) {
        return;
    }
    if (isDir) {
        navigateToPath(relPath);
    } else {
        const item = currentItems.find(i => i.relative_path === relPath);
        if (item) {
            filePreviewer.preview(item, currentItems);
        }
    }
}

// Context Menu & Mobile Action Sheet Management
function closeContextMenu() {
    const ctx = document.getElementById("contextMenu");
    const backdrop = document.getElementById("contextMenuBackdrop");
    if (ctx) {
        ctx.style.display = "none";
        ctx.classList.remove("as-bottom-sheet");
        ctx.style.left = "";
        ctx.style.top = "";
        ctx.style.bottom = "";
        ctx.style.right = "";
    }
    if (backdrop) {
        backdrop.style.display = "none";
    }
}
window.closeContextMenu = closeContextMenu;

function openMobileCreateSheet() {
    const ctx = document.getElementById("contextMenu");
    const backdrop = document.getElementById("contextMenuBackdrop");
    if (!ctx) return;

    let itemsHtml = "";
    if (currentView === "contacts") {
        itemsHtml = `
            <div class="sheet-handle"></div>
            <div class="sheet-item-header">
                <div style="flex-shrink:0; display:flex; align-items:center;">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon" style="color:var(--primary);"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                </div>
                <div class="sheet-item-title">Contacts Actions</div>
            </div>
            <div class="menu-item" onclick="closeContextMenu(); openContactModal();">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon" style="color:var(--primary);"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" x2="19" y1="8" y2="14"/><line x1="22" x2="16" y1="11" y2="11"/></svg>
                <span>Add New Contact</span>
            </div>
            <div class="menu-item" onclick="closeContextMenu(); triggerNativePhoneContactPicker();">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon" style="color:#8b5cf6;"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                <span>Import from Phone</span>
            </div>
            <div class="menu-item" onclick="closeContextMenu(); document.getElementById('contactsFileInput').click();">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon" style="color:#10b981;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/></svg>
                <span>Upload vCard / CSV</span>
            </div>
            <div class="menu-item" onclick="closeContextMenu(); openContactExportModal();">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
                <span>Export Contacts</span>
            </div>
        `;
    } else {
        itemsHtml = `
            <div class="sheet-handle"></div>
            <div class="sheet-item-header">
                <div style="flex-shrink:0; display:flex; align-items:center;">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="svg-icon" style="color:var(--primary);"><line x1="12" x2="12" y1="5" y2="19"/><line x1="5" x2="19" y1="12" y2="12"/></svg>
                </div>
                <div class="sheet-item-title">Create or Upload</div>
            </div>
            <div class="menu-item" onclick="closeContextMenu(); openNewFolderModal();">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" stroke="currentColor" style="color:#f59e0b;"><path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2zm0 12H4V8h16v10z"/></svg>
                <span>New Folder</span>
            </div>
            <div class="menu-item" onclick="closeContextMenu(); document.getElementById('fileUploadInput').click();">
                ${Icons.get('upload', { size: 18 })}
                <span>Upload Files</span>
            </div>
            <div class="menu-item" onclick="closeContextMenu(); document.getElementById('folderUploadInput').click();">
                ${Icons.get('uploadFolder', { size: 18 })}
                <span>Upload Folder</span>
            </div>
            <div class="menu-divider"></div>
            <div class="menu-item" onclick="closeContextMenu(); openContactModal();">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon" style="color:var(--primary);"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" x2="19" y1="8" y2="14"/><line x1="22" x2="16" y1="11" y2="11"/></svg>
                <span>Add Contact</span>
            </div>
        `;
    }

    ctx.classList.add("as-bottom-sheet");
    if (backdrop) backdrop.style.display = "block";
    ctx.innerHTML = itemsHtml;
    ctx.style.display = "block";
    ctx.style.left = "0px";
    ctx.style.top = "auto";
    ctx.style.bottom = "0px";
    ctx.style.right = "0px";
}
window.openMobileCreateSheet = openMobileCreateSheet;

function toggleMobileFabMenu(e) {
    if (e) {
        e.stopPropagation();
        e.preventDefault();
    }
    openMobileCreateSheet();
}
window.toggleMobileFabMenu = toggleMobileFabMenu;

function handleContextMenu(e, relPath, isDir) {
    if (e) {
        if (typeof e.preventDefault === "function") e.preventDefault();
        if (typeof e.stopPropagation === "function") e.stopPropagation();
    }

    const item = currentItems.find(i => i.relative_path === relPath) || { relative_path: relPath, is_directory: isDir, name: relPath.split('/').pop() };
    selectedItem = item;

    const ctx = document.getElementById("contextMenu");
    const backdrop = document.getElementById("contextMenuBackdrop");
    if (!ctx) return;

    const folderLocation = relPath.includes('/') ? relPath.substring(0, relPath.lastIndexOf('/')) : '';
    let itemsHtml = "";
    if (currentView === "trash") {
        itemsHtml = `
            <div class="menu-item" onclick="closeContextMenu(); restoreTrashItem(${item.id})">${Icons.get('restore', { size: 15 })} <span>Restore</span></div>
            <div class="menu-item danger" onclick="closeContextMenu(); permanentDeleteItem(${item.id})">${Icons.get('trash', { size: 15 })} <span>Delete Permanently</span></div>
        `;
    } else {
        itemsHtml = `
            ${!isDir ? `<div class="menu-item" onclick="closeContextMenu(); filePreviewer.preview(selectedItem, currentItems)">${Icons.get('eye', { size: 15 })} <span>Preview</span></div>` : ''}
            ${folderLocation && currentView !== 'drive' ? `<div class="menu-item" onclick="closeContextMenu(); navigateToPath('${escapeHtml(folderLocation)}')"><svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" stroke="currentColor" style="color:#f59e0b;"><path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2z"/></svg> <span>Go to containing folder</span></div>` : ''}
            <div class="menu-item" onclick="closeContextMenu(); downloadItem('${escapeHtml(relPath)}')">${Icons.get('download', { size: 15 })} <span>Download${isDir ? ' (ZIP)' : ''}</span></div>
            <div class="menu-item" onclick="closeContextMenu(); openShareModal('${escapeHtml(relPath)}')">${Icons.get('link', { size: 15 })} <span>Get Share Link</span></div>
            <div class="menu-item" onclick="closeContextMenu(); toggleStar('${escapeHtml(relPath)}')">${item.is_starred ? Icons.get('star', { size: 15 }) + ' <span>Remove Star</span>' : Icons.get('starFilled', { size: 15 }) + ' <span>Add Star</span>'}</div>
            <div class="menu-divider"></div>
            <div class="menu-item" onclick="closeContextMenu(); openRenameModal('${escapeHtml(relPath)}')">${Icons.get('edit', { size: 15 })} <span>Rename</span></div>
            <div class="menu-item" onclick="closeContextMenu(); openMoveCopyModal('${escapeHtml(relPath)}', 'move')">${Icons.get('move', { size: 15 })} <span>Move to...</span></div>
            <div class="menu-item" onclick="closeContextMenu(); openMoveCopyModal('${escapeHtml(relPath)}', 'copy')">${Icons.get('copy', { size: 15 })} <span>Copy to...</span></div>
            <div class="menu-divider"></div>
            <div class="menu-item danger" onclick="closeContextMenu(); deleteItem('${escapeHtml(relPath)}')">${Icons.get('trash', { size: 15 })} <span>Move to Trash</span></div>
        `;
    }

    const isMobile = window.innerWidth <= 768;
    if (isMobile) {
        ctx.classList.add("as-bottom-sheet");
        if (backdrop) backdrop.style.display = "block";
        const displayName = item.name || relPath.split('/').pop() || "Item";
        const iconSvg = getFileIcon(displayName, item.is_directory);
        ctx.innerHTML = `
            <div class="sheet-handle"></div>
            <div class="sheet-item-header">
                <div style="flex-shrink:0; display:flex; align-items:center;">${iconSvg}</div>
                <div class="sheet-item-title">${escapeHtml(displayName)}</div>
            </div>
            ${itemsHtml}
        `;
        ctx.style.display = "block";
        ctx.style.left = "0px";
        ctx.style.top = "auto";
        ctx.style.bottom = "0px";
        ctx.style.right = "0px";
    } else {
        ctx.classList.remove("as-bottom-sheet");
        if (backdrop) backdrop.style.display = "none";
        ctx.innerHTML = itemsHtml;
        ctx.style.display = "block";

        // Viewport bound calculation
        let clickX = 100;
        let clickY = 100;
        if (e) {
            if (e.clientX !== undefined) {
                clickX = e.clientX;
                clickY = e.clientY;
            } else if (e.touches && e.touches[0]) {
                clickX = e.touches[0].clientX;
                clickY = e.touches[0].clientY;
            } else if (e.changedTouches && e.changedTouches[0]) {
                clickX = e.changedTouches[0].clientX;
                clickY = e.changedTouches[0].clientY;
            }
        }
        const maxX = window.innerWidth - 220;
        const maxY = window.innerHeight - 340;

        ctx.style.left = `${Math.max(10, Math.min(clickX, maxX))}px`;
        ctx.style.top = `${Math.max(10, Math.min(clickY, maxY))}px`;
        ctx.style.bottom = "auto";
        ctx.style.right = "auto";
    }
}

// File Operations
async function toggleStar(relPath) {
    try {
        const res = await fetch("/api/files/star", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({ path: relPath })
        });
        if (res.ok) {
            refreshCurrentView();
        }
    } catch (err) {
        showToast("Failed to update star", "error");
    }
}

function downloadItem(relPath) {
    window.location.href = `/api/files/download?path=${encodeURIComponent(relPath)}`;
}

async function deleteItem(relPath) {
    if (!confirm(`Move "${relPath.split('/').pop()}" to Trash?`)) return;
    try {
        const res = await fetch(`/api/files?path=${encodeURIComponent(relPath)}`, {
            method: "DELETE",
            headers: { "X-CSRF-Token": getCsrfToken() }
        });
        if (res.ok) {
            showToast("Item moved to Trash", "info");
            refreshCurrentView();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to delete item", "error");
        }
    } catch (err) {
        showToast("Network error deleting item", "error");
    }
}

// Modal actions: New Folder
function openNewFolderModal() {
    document.getElementById("newFolderModal").style.display = "flex";
    const input = document.getElementById("newFolderNameInput");
    input.value = "";
    input.focus();
}

async function submitNewFolder() {
    const input = document.getElementById("newFolderNameInput");
    const name = input.value.trim();
    if (!name) return;

    try {
        const res = await fetch("/api/files/folder", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({
                parent_path: currentPath,
                folder_name: name
            })
        });

        if (res.ok) {
            closeModals();
            showToast(`Created folder "${name}"`, "success");
            refreshCurrentView();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to create folder", "error");
        }
    } catch (err) {
        showToast("Network error creating folder", "error");
    }
}

// Rename
function openRenameModal(relPath) {
    const item = currentItems.find(i => i.relative_path === relPath) || selectedItem;
    document.getElementById("renameModal").style.display = "flex";
    const input = document.getElementById("renameInput");
    input.value = item ? item.name : relPath.split('/').pop();
    input.focus();
    input.select();
    input.dataset.path = relPath;
}

async function submitRename() {
    const input = document.getElementById("renameInput");
    const newName = input.value.trim();
    const oldPath = input.dataset.path;
    if (!newName) return;

    try {
        const res = await fetch("/api/files/rename", {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({
                path: oldPath,
                new_name: newName
            })
        });

        if (res.ok) {
            closeModals();
            showToast(`Renamed to "${newName}"`, "success");
            refreshCurrentView();
        } else {
            const err = await res.json();
            showToast(err.detail || "Rename failed", "error");
        }
    } catch (err) {
        showToast("Network error renaming", "error");
    }
}

// Move / Copy
let moveCopyAction = "move";
let moveCopySource = "";

function openMoveCopyModal(sourcePath, action = "move") {
    moveCopyAction = action;
    moveCopySource = sourcePath;

    document.getElementById("moveCopyTitle").textContent = action === "move" ? "Move Item" : "Copy Item";
    document.getElementById("moveCopySubmitBtn").textContent = action === "move" ? "Move Here" : "Copy Here";
    document.getElementById("moveCopyModal").style.display = "flex";

    loadFolderTreeForMove();
}

async function loadFolderTreeForMove() {
    const select = document.getElementById("moveCopyDestSelect");
    select.innerHTML = `<option value="">/ (Root - StrangeInfinity Drive)</option>`;

    try {
        // Collect all folders in DB or explore root
        const res = await fetch("/api/files?path=");
        if (res.ok) {
            const data = await res.json();
            data.items.filter(i => i.is_directory).forEach(dir => {
                const opt = document.createElement("option");
                opt.value = dir.relative_path;
                opt.textContent = `/${dir.relative_path}`;
                select.appendChild(opt);
            });
        }
    } catch (_) {}
}

async function submitMoveCopy() {
    const destDir = document.getElementById("moveCopyDestSelect").value;
    const url = moveCopyAction === "move" ? "/api/files/move" : "/api/files/copy";

    try {
        const res = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({
                source_path: moveCopySource,
                destination_dir: destDir,
                overwrite: false
            })
        });

        if (res.ok) {
            closeModals();
            showToast(`Item ${moveCopyAction === 'move' ? 'moved' : 'copied'} successfully`, "success");
            refreshCurrentView();
        } else {
            const err = await res.json();
            showToast(err.detail || "Operation failed", "error");
        }
    } catch (err) {
        showToast("Network error", "error");
    }
}

// Sharing System
function openShareModal(relPath) {
    document.getElementById("shareModal").style.display = "flex";
    document.getElementById("shareModalPath").dataset.path = relPath;
    document.getElementById("shareResultBox").style.display = "none";
    document.getElementById("sharePasswordInput").value = "";
    document.getElementById("shareExpiresSelect").value = "0";
    document.getElementById("shareDownloadOnlyCheck").checked = false;
}

async function submitCreateShare() {
    const path = document.getElementById("shareModalPath").dataset.path;
    const password = document.getElementById("sharePasswordInput").value.trim();
    const expiresIn = parseInt(document.getElementById("shareExpiresSelect").value) || null;
    const downloadOnly = document.getElementById("shareDownloadOnlyCheck").checked;

    try {
        const res = await fetch("/api/shares", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({
                path: path,
                password: password || null,
                expires_in_hours: expiresIn,
                download_only: downloadOnly
            })
        });

        if (res.ok) {
            const data = await res.json();
            const fullUrl = `${window.location.origin}${data.share_url}`;
            document.getElementById("shareResultUrl").value = fullUrl;
            document.getElementById("shareResultBox").style.display = "block";
            showToast("Share link created!", "success");
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to create share link", "error");
        }
    } catch (err) {
        showToast("Error creating share link", "error");
    }
}

function copyShareUrl() {
    const urlInput = document.getElementById("shareResultUrl");
    urlInput.select();
    copyTextToClipboard(urlInput.value).then(() => {
        showToast("Share link copied to clipboard!", "success");
    }).catch(() => {
        showToast("Link selected. Press Ctrl+C or Copy on your device.", "info");
    });
}

async function loadSharedLinks() {
    currentView = "shares";
    renderBreadcrumbs("");
    document.getElementById("breadcrumbContainer").innerHTML = `<span class="breadcrumb-item active">Shared Links</span>`;

    try {
        const res = await fetch("/api/shares");
        const data = await res.json();
        const container = document.getElementById("fileViewContent");

        if (!data.shares || data.shares.length === 0) {
            renderEmptyState("No active share links", "Files or folders you share will be listed here.");
            return;
        }

        let html = `
            <table class="file-table">
                <thead>
                    <tr>
                        <th>Path</th>
                        <th>Type</th>
                        <th>Security</th>
                        <th>Expires</th>
                        <th>Clicks</th>
                        <th style="text-align:right;">Actions</th>
                    </tr>
                </thead>
                <tbody>
        `;

        data.shares.forEach(s => {
            const fullUrl = `${window.location.origin}/s/${s.token}`;
            html += `
                <tr>
                    <td><strong>${escapeHtml(s.relative_path)}</strong></td>
                    <td><div style="display:flex; align-items:center; gap:6px;">${s.is_directory ? Icons.get('folder', {size:15}) + ' <span>Folder</span>' : Icons.get('file', {size:15}) + ' <span>File</span>'}</div></td>
                    <td><div style="display:flex; align-items:center; gap:6px;">${s.has_password ? Icons.get('lock', {size:14}) + ' <span>Password</span>' : Icons.get('globe', {size:14}) + ' <span>Public</span>'}</div></td>
                    <td>${s.expires_at ? formatDate(s.expires_at) : "Never"}</td>
                    <td>${s.access_count}</td>
                    <td style="text-align:right;">
                        <button class="action-btn" onclick="copyTextToClipboard('${fullUrl}').then(() => showToast('Link copied', 'success')).catch(() => showToast('Failed to copy', 'error'))" style="display:inline-flex; align-items:center; gap:5px;">${Icons.get('copy', {size:14})} <span>Copy</span></button>
                        <button class="action-btn" style="color:var(--accent-red); display:inline-flex; align-items:center; gap:5px;" onclick="revokeShare('${s.token}')">${Icons.get('trash', {size:14})} <span>Revoke</span></button>
                    </td>
                </tr>
            `;
        });
        html += `</tbody></table>`;
        container.innerHTML = html;
    } catch (err) {
        showToast("Failed to load shared links", "error");
    }
}

async function revokeShare(token) {
    if (!confirm("Revoke this share link?")) return;
    try {
        const res = await fetch(`/api/shares/${token}`, {
            method: "DELETE",
            headers: { "X-CSRF-Token": getCsrfToken() }
        });
        if (res.ok) {
            showToast("Share link revoked", "info");
            loadSharedLinks();
        }
    } catch (_) {
        showToast("Failed to revoke share", "error");
    }
}

// Trash Bin
async function loadTrash() {
    currentView = "trash";
    document.getElementById("breadcrumbContainer").innerHTML = `
        <span class="breadcrumb-item active">Trash Bin</span>
        <button class="action-btn danger-btn" style="margin-left:auto; font-size:0.8rem; padding:4px 10px;" onclick="emptyTrashBin()">Empty Trash</button>
    `;

    try {
        const res = await fetch("/api/files/trash");
        const data = await res.json();
        currentItems = data.items;
        renderItems(currentItems);
    } catch (_) {
        renderEmptyState("Failed to load trash", "");
    }
}

async function restoreTrashItem(id) {
    try {
        const res = await fetch(`/api/files/trash/restore/${id}`, {
            method: "POST",
            headers: { "X-CSRF-Token": getCsrfToken() }
        });
        if (res.ok) {
            showToast("Item restored", "success");
            loadTrash();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to restore", "error");
        }
    } catch (_) {
        showToast("Error restoring item", "error");
    }
}

async function permanentDeleteItem(id) {
    if (!confirm("Permanently delete this item? This action cannot be undone.")) return;
    try {
        const res = await fetch(`/api/files/trash/permanent/${id}`, {
            method: "DELETE",
            headers: { "X-CSRF-Token": getCsrfToken() }
        });
        if (res.ok) {
            showToast("Item permanently deleted", "info");
            loadTrash();
        }
    } catch (_) {
        showToast("Failed to delete", "error");
    }
}

async function emptyTrashBin() {
    if (!confirm("Are you sure you want to permanently delete all items in Trash?")) return;
    try {
        const res = await fetch("/api/files/trash/empty", {
            method: "POST",
            headers: { "X-CSRF-Token": getCsrfToken() }
        });
        if (res.ok) {
            showToast("Trash emptied", "success");
            loadTrash();
        }
    } catch (_) {
        showToast("Failed to empty trash", "error");
    }
}

// Starred & Recent Views
async function loadStarredFiles() {
    currentView = "starred";
    document.getElementById("breadcrumbContainer").innerHTML = `<span class="breadcrumb-item active">Starred Items</span>`;
    try {
        const res = await fetch("/api/files/starred");
        const data = await res.json();
        currentItems = data.items;
        renderItems(currentItems);
    } catch (_) {
        renderEmptyState("Failed to load starred", "");
    }
}

async function loadRecentFiles() {
    currentView = "recent";
    document.getElementById("breadcrumbContainer").innerHTML = `<span class="breadcrumb-item active">Recent Files</span>`;
    try {
        const res = await fetch("/api/files/recent");
        const data = await res.json();
        currentItems = data.items;
        renderItems(currentItems);
    } catch (_) {
        renderEmptyState("Failed to load recent files", "");
    }
}

async function loadPhotos() {
    clearSelection();
    currentView = "photos";
    const dlFolderBtn = document.getElementById("downloadCurrentFolderBtn");
    if (dlFolderBtn) dlFolderBtn.style.display = "none";
    document.getElementById("breadcrumbContainer").innerHTML = `
        <span class="breadcrumb-item active" style="display:inline-flex; align-items:center; gap:6px;">
            ${typeof Icons !== "undefined" ? Icons.get('photo', { size: 15 }) : ''}
            <span>Photos & Images</span>
        </span>
    `;
    try {
        const res = await fetch("/api/files/photos");
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Failed to load photos");
        }
        const data = await res.json();
        currentItems = data.items;
        renderItems(currentItems);
    } catch (err) {
        showToast(err.message, "error");
        renderEmptyState("Failed to load photos", err.message);
    }
}

async function loadVideos() {
    clearSelection();
    currentView = "videos";
    const dlFolderBtn = document.getElementById("downloadCurrentFolderBtn");
    if (dlFolderBtn) dlFolderBtn.style.display = "none";
    document.getElementById("breadcrumbContainer").innerHTML = `
        <span class="breadcrumb-item active" style="display:inline-flex; align-items:center; gap:6px;">
            ${typeof Icons !== "undefined" ? Icons.get('video', { size: 15 }) : ''}
            <span>Videos</span>
        </span>
    `;
    try {
        const res = await fetch("/api/files/videos");
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Failed to load videos");
        }
        const data = await res.json();
        currentItems = data.items;
        renderItems(currentItems);
    } catch (err) {
        showToast(err.message, "error");
        renderEmptyState("Failed to load videos", err.message);
    }
}

async function loadDocuments() {
    clearSelection();
    currentView = "documents";
    const dlFolderBtn = document.getElementById("downloadCurrentFolderBtn");
    if (dlFolderBtn) dlFolderBtn.style.display = "none";
    document.getElementById("breadcrumbContainer").innerHTML = `
        <span class="breadcrumb-item active" style="display:inline-flex; align-items:center; gap:6px;">
            ${typeof Icons !== "undefined" ? Icons.get('document', { size: 15 }) : ''}
            <span>Documents</span>
        </span>
    `;
    try {
        const res = await fetch("/api/files/documents");
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Failed to load documents");
        }
        const data = await res.json();
        currentItems = data.items;
        renderItems(currentItems);
    } catch (err) {
        showToast(err.message, "error");
        renderEmptyState("Failed to load documents", err.message);
    }
}

// Search
async function executeSearch(query) {
    clearSelection();
    currentView = "search";
    const dlFolderBtn = document.getElementById("downloadCurrentFolderBtn");
    if (dlFolderBtn) dlFolderBtn.style.display = "none";
    document.getElementById("breadcrumbContainer").innerHTML = `<span class="breadcrumb-item active">Search: "${escapeHtml(query)}"</span>`;
    try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const data = await res.json();
        currentItems = data.results;
        renderItems(currentItems);
    } catch (_) {
        renderEmptyState("Search failed", "");
    }
}

// Storage Statistics
async function loadStorageStats() {
    try {
        const res = await fetch("/api/storage");
        if (res.ok) {
            const stats = await res.json();
            const fill = document.getElementById("sidebarStorageFill");
            const text = document.getElementById("sidebarStorageText");

            if (fill) fill.style.width = `${Math.min(100, stats.percent_used)}%`;
            if (text) {
                if (stats.quota_bytes && stats.quota_bytes > 0) {
                    text.textContent = `${formatBytes(stats.user_storage_used || stats.managed_size)} of ${formatBytes(stats.quota_bytes)} used`;
                } else {
                    text.textContent = `${formatBytes(stats.used_disk)} of ${formatBytes(stats.total_disk)} used`;
                }
            }
        }
    } catch (_) {}
}

function openStorageDashboard() {
    fetch("/api/storage").then(r => r.json()).then(stats => {
        document.getElementById("dashTotalDisk").textContent = stats.quota_bytes > 0 ? `${formatBytes(stats.quota_bytes)} (Quota)` : formatBytes(stats.total_disk);
        document.getElementById("dashUsedDisk").textContent = formatBytes(stats.user_storage_used !== undefined ? stats.user_storage_used : stats.used_disk);
        document.getElementById("dashFreeDisk").textContent = formatBytes(stats.free_disk);
        document.getElementById("dashPercentUsed").textContent = `${stats.percent_used}%`;
        document.getElementById("dashFileCount").textContent = stats.file_count;
        document.getElementById("dashFolderCount").textContent = stats.folder_count;
        document.getElementById("dashManagedSize").textContent = formatBytes(stats.managed_size);
        document.getElementById("dashStorageRoot").textContent = stats.storage_root;

        document.getElementById("storageDashboardModal").style.display = "flex";
    });
}

// Audit Logs Modal
async function openAuditLogsModal() {
    try {
        const res = await fetch("/api/audit?limit=50");
        const data = await res.json();
        const tbody = document.getElementById("auditLogsTbody");
        tbody.innerHTML = "";

        data.logs.forEach(log => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${escapeHtml(log.event_type)}</strong></td>
                <td>${escapeHtml(log.username || "Anonymous")}</td>
                <td>${escapeHtml(log.ip_address || "-")}</td>
                <td>${escapeHtml(log.details || "-")}</td>
                <td>${formatDate(log.created_at)}</td>
            `;
            tbody.appendChild(tr);
        });

        document.getElementById("auditLogsModal").style.display = "flex";
    } catch (_) {
        showToast("Failed to load audit logs", "error");
    }
}

// Settings Modal
async function openSettingsModal() {
    try {
        const meRes = await fetch("/api/auth/me");
        const meData = await meRes.json();

        const sessionsList = document.getElementById("settingsSessionsList");
        sessionsList.innerHTML = "";

        meData.sessions.forEach(s => {
            const div = document.createElement("div");
            div.style.cssText = "padding:8px 12px; background:var(--bg-secondary); border-radius:6px; font-size:0.8rem; display:flex; justify-content:space-between; align-items:center;";
            div.innerHTML = `
                <div>
                    <div><strong>IP: ${escapeHtml(s.ip_address)}</strong> ${s.is_current ? '<span style="color:var(--accent-green);">(Current)</span>' : ''}</div>
                    <div style="color:var(--text-muted); font-size:0.7rem;">${escapeHtml(s.user_agent.substring(0, 45))}... • Active: ${formatDate(s.last_active_at)}</div>
                </div>
            `;
            sessionsList.appendChild(div);
        });

        document.getElementById("settingsModal").style.display = "flex";
    } catch (_) {
        showToast("Failed to load settings", "error");
    }
}

async function submitChangePassword() {
    const oldPw = document.getElementById("settingsOldPw").value;
    const newPw = document.getElementById("settingsNewPw").value;

    if (newPw.length < 8) {
        showToast("New password must be at least 8 characters", "error");
        return;
    }

    try {
        const res = await fetch("/api/auth/change-password", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({ old_password: oldPw, new_password: newPw })
        });

        if (res.ok) {
            showToast("Password changed successfully", "success");
            closeModals();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to change password", "error");
        }
    } catch (_) {
        showToast("Network error", "error");
    }
}

async function revokeOtherSessions(callback) {
    try {
        const res = await fetch("/api/auth/revoke-other-sessions", {
            method: "POST",
            headers: { "X-CSRF-Token": getCsrfToken() }
        });
        if (res.ok) {
            showToast("All other sessions terminated", "success");
            if (typeof callback === "function") {
                callback();
            } else {
                openSettingsModal();
            }
        }
    } catch (_) {
        showToast("Error revoking sessions", "error");
    }
}

async function logout() {
    await fetch("/api/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": getCsrfToken() }
    });
    window.location.href = "/login";
}

function closeModals() {
    document.querySelectorAll(".modal-overlay").forEach(m => m.style.display = "none");
    if (filePreviewer) filePreviewer.close();
}

// User UI & Profile Management
function updateUserUI(user) {
    if (!user) return;
    const userAvatarBtn = document.getElementById("userAvatarBtn");
    const avatarUrl = user.profile_pic ? user.profile_pic : `/api/profile/avatar/${user.id}`;

    if (userAvatarBtn) {
        userAvatarBtn.innerHTML = `<img src="${avatarUrl}" alt="${escapeHtml(user.username)}" onerror="this.onerror=null; this.parentElement.textContent='${escapeHtml(user.username.charAt(0).toUpperCase())}'">`;
        userAvatarBtn.title = `${user.display_name ? user.display_name + ' (' + user.username + ')' : user.username} (${user.role})`;
    }

    const dropdownAvatar = document.getElementById("dropdownUserAvatar");
    if (dropdownAvatar) {
        dropdownAvatar.src = avatarUrl;
    }

    const dropdownName = document.getElementById("dropdownUserName");
    if (dropdownName) {
        dropdownName.textContent = user.display_name || user.username;
    }

    const dropdownEmail = document.getElementById("dropdownUserEmail");
    if (dropdownEmail) {
        dropdownEmail.textContent = user.email || (user.role === 'admin' ? 'Administrator' : 'Standard User');
    }

    const adminMenu = document.getElementById("userManagementMenuItem");
    if (adminMenu) {
        adminMenu.style.display = user.role === "admin" ? "block" : "none";
    }
}

async function checkCurrentUser() {
    try {
        const res = await fetch("/api/auth/me");
        if (res.ok) {
            const data = await res.json();
            currentUser = data.user || data;
            updateUserUI(currentUser);
        }
    } catch (_) {}
}

function openProfileModal() {
    document.getElementById("profileModal").style.display = "flex";
    switchProfileTab('info');
    loadProfileData();
}

function switchProfileTab(tabName) {
    const tabs = ['info', 'storage', 'security', 'danger'];
    tabs.forEach(t => {
        const btn = document.getElementById(`profileTabBtn_${t}`);
        const panel = document.getElementById(`profileTab_${t}`);
        if (btn) btn.classList.toggle('active', t === tabName);
        if (panel) panel.style.display = (t === tabName) ? 'block' : 'none';
    });
}

async function loadProfileData() {
    try {
        const res = await fetch("/api/profile");
        if (!res.ok) {
            throw new Error("Failed to load profile");
        }
        const data = await res.json();
        const u = data.user;
        const counts = data.counts || {};
        const storage = data.storage || {};

        currentUser = u;
        updateUserUI(u);

        // Tab: Info
        const avatarImg = document.getElementById("profileAvatarImg");
        if (avatarImg) {
            avatarImg.src = u.profile_pic ? u.profile_pic : `/api/profile/avatar/${u.id}?v=${Date.now()}`;
        }
        const removeAvatarBtn = document.getElementById("removeAvatarBtn");
        if (removeAvatarBtn) {
            removeAvatarBtn.style.display = u.profile_pic ? 'flex' : 'none';
        }

        const usernameDisplay = document.getElementById("profileUsernameDisplay");
        if (usernameDisplay) usernameDisplay.textContent = u.username;

        const roleBadge = document.getElementById("profileRoleBadge");
        if (roleBadge) {
            roleBadge.textContent = u.role === 'admin' ? 'Administrator' : 'User';
            roleBadge.className = `badge ${u.role === 'admin' ? 'badge-admin' : 'badge-user'}`;
        }

        const createdDisplay = document.getElementById("profileCreatedAtDisplay");
        if (createdDisplay) createdDisplay.textContent = `Member since ${formatDate(u.created_at)}`;

        const nameInput = document.getElementById("profileDisplayNameInput");
        if (nameInput) nameInput.value = u.display_name || "";

        const emailInput = document.getElementById("profileEmailInput");
        if (emailInput) emailInput.value = u.email || "";

        // Tab: Storage & Takeout
        const fileCount = document.getElementById("profileFileCount");
        if (fileCount) fileCount.textContent = counts.files || 0;

        const folderCount = document.getElementById("profileFolderCount");
        if (folderCount) folderCount.textContent = counts.folders || 0;

        const starredCount = document.getElementById("profileStarredCount");
        if (starredCount) starredCount.textContent = counts.starred || 0;

        const trashCount = document.getElementById("profileTrashCount");
        if (trashCount) trashCount.textContent = counts.trash || 0;

        const usedBytes = storage.managed_size || storage.user_storage_used || 0;
        const quotaBytes = storage.quota_bytes || 0;
        const usedDisplay = formatBytes(usedBytes);
        const quotaDisplay = quotaBytes > 0 ? formatBytes(quotaBytes) : "Unlimited";

        let percent = 0;
        if (quotaBytes > 0) {
            percent = Math.min(100, Math.round((usedBytes / quotaBytes) * 100));
        } else if (storage.percent_used) {
            percent = storage.percent_used;
        }

        const storageUsageText = document.getElementById("profileStorageUsageText");
        if (storageUsageText) storageUsageText.textContent = `${usedDisplay} used`;

        const storageQuotaText = document.getElementById("profileStorageQuotaText");
        if (storageQuotaText) storageQuotaText.textContent = quotaDisplay;

        const storagePercent = document.getElementById("profileStoragePercent");
        if (storagePercent) storagePercent.textContent = `${percent}%`;

        const storageFill = document.getElementById("profileStorageFill");
        if (storageFill) storageFill.style.width = `${percent}%`;

        // Tab: Security (Active Sessions)
        loadProfileSessions();
    } catch (err) {
        showToast("Error loading profile: " + err.message, "error");
    }
}

async function loadProfileSessions() {
    const list = document.getElementById("profileSessionsList");
    if (!list) return;
    list.innerHTML = `<div style="font-size:0.8rem; color:var(--text-muted);">Loading active sessions...</div>`;

    try {
        const res = await fetch("/api/auth/me");
        if (!res.ok) return;
        const data = await res.json();
        const sessions = data.sessions || [];

        if (sessions.length === 0) {
            list.innerHTML = `<div style="font-size:0.8rem; color:var(--text-muted);">No active sessions found.</div>`;
            return;
        }

        list.innerHTML = "";
        sessions.forEach(s => {
            const row = document.createElement("div");
            row.style.cssText = "display:flex; justify-content:space-between; align-items:center; padding:8px 12px; background:var(--bg-secondary); border-radius:var(--radius-sm); font-size:0.82rem; border:1px solid var(--border-color);";
            
            const uaShort = (s.user_agent || "Unknown Browser").substring(0, 45);
            row.innerHTML = `
                <div>
                    <div style="font-weight:600; display:flex; align-items:center; gap:6px;">
                        <span>${escapeHtml(uaShort)}</span>
                        ${s.is_current ? '<span class="status-badge active" style="font-size:10px;">Current Device</span>' : ''}
                    </div>
                    <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">
                        IP: ${escapeHtml(s.ip_address || "127.0.0.1")} • Active: ${formatDate(s.last_active_at)}
                    </div>
                </div>
            `;
            list.appendChild(row);
        });
    } catch (_) {
        list.innerHTML = `<div style="font-size:0.8rem; color:var(--accent-red);">Failed to load sessions.</div>`;
    }
}

async function submitUpdateProfile() {
    const displayName = document.getElementById("profileDisplayNameInput").value.trim();
    const email = document.getElementById("profileEmailInput").value.trim();

    try {
        const res = await fetch("/api/profile", {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({
                display_name: displayName,
                email: email
            })
        });

        const data = await res.json();
        if (res.ok) {
            showToast("Profile updated successfully", "success");
            currentUser = data.user;
            updateUserUI(currentUser);
        } else {
            showToast(data.detail || "Failed to update profile", "error");
        }
    } catch (err) {
        showToast("Network error updating profile", "error");
    }
}

async function uploadAvatarFile(input) {
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];

    if (file.size > 5 * 1024 * 1024) {
        showToast("Image size exceeds 5MB limit", "error");
        input.value = "";
        return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
        showToast("Uploading profile picture...", "info");
        const res = await fetch("/api/profile/avatar", {
            method: "POST",
            headers: {
                "X-CSRF-Token": getCsrfToken()
            },
            body: formData
        });

        const data = await res.json();
        if (res.ok) {
            showToast("Profile picture updated successfully", "success");
            const avatarUrl = data.avatar_url;
            currentUser.profile_pic = avatarUrl;
            const avatarImg = document.getElementById("profileAvatarImg");
            if (avatarImg) avatarImg.src = avatarUrl;
            const removeBtn = document.getElementById("removeAvatarBtn");
            if (removeBtn) removeBtn.style.display = "flex";
            updateUserUI(currentUser);
        } else {
            showToast(data.detail || "Failed to upload avatar", "error");
        }
    } catch (err) {
        showToast("Network error uploading avatar", "error");
    } finally {
        input.value = "";
    }
}

async function removeAvatarPicture() {
    try {
        const res = await fetch("/api/profile/avatar", {
            method: "DELETE",
            headers: {
                "X-CSRF-Token": getCsrfToken()
            }
        });

        const data = await res.json();
        if (res.ok) {
            showToast("Profile picture removed", "success");
            currentUser.profile_pic = null;
            const avatarImg = document.getElementById("profileAvatarImg");
            if (avatarImg) avatarImg.src = data.avatar_url;
            const removeBtn = document.getElementById("removeAvatarBtn");
            if (removeBtn) removeBtn.style.display = "none";
            updateUserUI(currentUser);
        } else {
            showToast(data.detail || "Failed to remove avatar", "error");
        }
    } catch (err) {
        showToast("Network error removing avatar", "error");
    }
}

async function submitProfileChangePassword() {
    const oldPw = document.getElementById("profileOldPassword").value;
    const newPw = document.getElementById("profileNewPassword").value;
    const confirmPw = document.getElementById("profileConfirmPassword").value;

    if (!oldPw) {
        showToast("Current password is required", "error");
        return;
    }
    if (!newPw || newPw.length < 8) {
        showToast("New password must be at least 8 characters", "error");
        return;
    }
    if (newPw !== confirmPw) {
        showToast("New passwords do not match", "error");
        return;
    }

    try {
        const res = await fetch("/api/auth/change-password", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({
                old_password: oldPw,
                new_password: newPw
            })
        });

        const data = await res.json();
        if (res.ok) {
            showToast("Password updated successfully", "success");
            document.getElementById("profileOldPassword").value = "";
            document.getElementById("profileNewPassword").value = "";
            document.getElementById("profileConfirmPassword").value = "";
        } else {
            showToast(data.detail || "Failed to update password", "error");
        }
    } catch (err) {
        showToast("Network error updating password", "error");
    }
}

function exportPersonalData() {
    showToast("Preparing StrangeInfinity Drive takeout archive...", "info");
    window.location.href = "/api/profile/export";
}

// Danger Zone Actions
let pendingDangerAction = null;

function promptWipeDrive() {
    pendingDangerAction = "wipe_drive";
    document.getElementById("pwdConfirmTitle").textContent = "Confirm Wipe Personal Drive";
    document.getElementById("pwdConfirmMessage").innerHTML = "Are you sure you want to <strong>permanently wipe all files and folders</strong> in your StrangeInfinity Drive? Your account and credentials will be preserved, but all files will be deleted.";
    document.getElementById("pwdConfirmInput").value = "";
    document.getElementById("passwordConfirmModal").style.display = "flex";
    setTimeout(() => document.getElementById("pwdConfirmInput").focus(), 100);
}

function promptDeleteAccount() {
    pendingDangerAction = "delete_account";
    document.getElementById("pwdConfirmTitle").textContent = "Confirm Permanent Account Deletion";
    document.getElementById("pwdConfirmMessage").innerHTML = "Are you sure you want to <strong>permanently delete your user account, custom avatar, and all personal files</strong>? This action is irreversible.";
    document.getElementById("pwdConfirmInput").value = "";
    document.getElementById("passwordConfirmModal").style.display = "flex";
    setTimeout(() => document.getElementById("pwdConfirmInput").focus(), 100);
}

function closePasswordConfirmModal() {
    document.getElementById("passwordConfirmModal").style.display = "none";
    document.getElementById("pwdConfirmInput").value = "";
    pendingDangerAction = null;
}

async function executePasswordConfirmedAction() {
    const password = document.getElementById("pwdConfirmInput").value;
    if (!password) {
        showToast("Password is required to confirm this action", "error");
        return;
    }

    if (pendingDangerAction === "wipe_drive") {
        try {
            const res = await fetch("/api/profile/wipe-drive", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": getCsrfToken()
                },
                body: JSON.stringify({ password })
            });

            const data = await res.json();
            if (res.ok) {
                closePasswordConfirmModal();
                showToast("All personal drive files wiped successfully", "success");
                loadDirectory("");
                loadProfileData();
                updateStorageBar();
            } else {
                showToast(data.detail || "Failed to wipe drive", "error");
            }
        } catch (err) {
            showToast("Network error executing drive wipe", "error");
        }
    } else if (pendingDangerAction === "delete_account") {
        try {
            const res = await fetch("/api/profile/delete-account", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": getCsrfToken()
                },
                body: JSON.stringify({ password })
            });

            const data = await res.json();
            if (res.ok) {
                closePasswordConfirmModal();
                closeModals();
                showToast("Account deleted successfully. Redirecting to login...", "success");
                setTimeout(() => {
                    window.location.href = "/login";
                }, 1500);
            } else {
                showToast(data.detail || "Failed to delete account", "error");
            }
        } catch (err) {
            showToast("Network error deleting account", "error");
        }
    }
}

// User Management (Admin Only)
function openUserManagementModal() {
    document.getElementById("userManagementModal").style.display = "flex";
    toggleAddUserForm(false);
    loadUsersList();
}

function toggleAddUserForm(forceState) {
    const card = document.getElementById("addUserCard");
    const btn = document.getElementById("toggleAddUserBtn");
    if (!card || !btn) return;

    const show = forceState !== undefined ? forceState : (card.style.display === "none");
    card.style.display = show ? "block" : "none";
    btn.innerHTML = show ? `${Icons.get("x", {size:14})} <span>Cancel</span>` : `${Icons.get("plus", {size:14})} <span>Add New User</span>`;

    if (show) {
        document.getElementById("newUsername").value = "";
        document.getElementById("newUserPassword").value = "";
        document.getElementById("newUserRole").value = "user";
        document.getElementById("newUserQuotaGb").value = "0";
        document.getElementById("newUsername").focus();
    }
}

async function loadUsersList() {
    const tbody = document.getElementById("usersTableTbody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--text-muted);">Loading users...</td></tr>`;

    try {
        const res = await fetch("/api/users");
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Failed to load users");
        }
        const data = await res.json();
        const users = Array.isArray(data) ? data : (data.users || []);
        tbody.innerHTML = "";

        if (users.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--text-muted);">No users found.</td></tr>`;
            return;
        }

        users.forEach(u => {
            const tr = document.createElement("tr");
            const isSelf = currentUser && currentUser.id === u.id;
            const quotaDisplay = u.quota_bytes > 0 ? formatBytes(u.quota_bytes) : "Unlimited";
            const usedDisplay = formatBytes(u.used_bytes);

            const avatarUrl = u.profile_pic ? u.profile_pic : `/api/profile/avatar/${u.id}`;

            tr.innerHTML = `
                <td>
                    <div style="display:flex; align-items:center; gap:10px;">
                        <img src="${avatarUrl}" alt="${escapeHtml(u.username)}" style="width:30px; height:30px; border-radius:50%; object-fit:cover; border:1px solid var(--border-color); flex-shrink:0;">
                        <div style="display:flex; flex-direction:column; min-width:0;">
                            <div style="display:flex; align-items:center; gap:6px;">
                                <span style="font-weight:600;">${escapeHtml(u.display_name || u.username)}</span>
                                ${isSelf ? '<span class="status-badge active" style="font-size:10px;">You</span>' : ''}
                            </div>
                            ${u.display_name ? `<span style="font-size:0.75rem; color:var(--text-muted);">@${escapeHtml(u.username)}</span>` : ''}
                        </div>
                    </div>
                </td>
                <td>
                    <span class="status-badge ${u.role === 'admin' ? 'active' : ''}" style="text-transform:capitalize;">
                        ${escapeHtml(u.role)}
                    </span>
                </td>
                <td>
                    <span class="status-badge ${u.is_active ? 'active' : 'revoked'}">
                        ${u.is_active ? 'Active' : 'Disabled'}
                    </span>
                </td>
                <td>
                    <div style="font-size:0.85rem;">${usedDisplay} / ${quotaDisplay}</div>
                </td>
                <td style="font-size:0.85rem; color:var(--text-muted);">${formatDate(u.created_at)}</td>
                <td style="text-align:right;">
                    <div style="display:inline-flex; gap:6px;">
                        <button class="action-btn" title="Reset Password" onclick="promptResetUserPassword(${u.id}, '${escapeHtml(u.username)}')" style="display:inline-flex; align-items:center; justify-content:center;">${Icons.get('key', {size:14})}</button>
                        <button class="action-btn" title="Set Quota" onclick="promptChangeUserQuota(${u.id}, '${escapeHtml(u.username)}', ${u.quota_bytes || 0})" style="display:inline-flex; align-items:center; justify-content:center;">${Icons.get('save', {size:14})}</button>
                        ${!isSelf ? `
                            <button class="action-btn" title="${u.is_active ? 'Disable account' : 'Enable account'}" onclick="toggleUserStatus(${u.id}, ${u.is_active})" style="display:inline-flex; align-items:center; justify-content:center;">
                                ${u.is_active ? Icons.get('pause', {size:14}) : Icons.get('play', {size:14})}
                            </button>
                            <button class="action-btn danger-btn" title="Permanently Delete User" onclick="deleteUser(${u.id}, '${escapeHtml(u.username)}')" style="display:inline-flex; align-items:center; justify-content:center;">
                                ${Icons.get('trash', {size:14})}
                            </button>
                        ` : ''}
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--accent-red);">${escapeHtml(err.message)}</td></tr>`;
    }
}

async function submitCreateUser() {
    const username = document.getElementById("newUsername").value.trim();
    const password = document.getElementById("newUserPassword").value;
    const role = document.getElementById("newUserRole").value;
    const quotaGb = parseFloat(document.getElementById("newUserQuotaGb").value) || 0;

    if (!username || username.length < 3) {
        showToast("Username must be at least 3 characters", "error");
        return;
    }
    if (!password || password.length < 8) {
        showToast("Password must be at least 8 characters", "error");
        return;
    }

    const quotaBytes = quotaGb > 0 ? Math.round(quotaGb * 1024 * 1024 * 1024) : 0;

    try {
        const res = await fetch("/api/users", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({
                username: username,
                password: password,
                role: role,
                quota_bytes: quotaBytes
            })
        });

        if (res.ok) {
            showToast(`User "${username}" created with separate storage`, "success");
            toggleAddUserForm(false);
            loadUsersList();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to create user", "error");
        }
    } catch (err) {
        showToast("Network error creating user", "error");
    }
}

async function toggleUserStatus(userId, currentIsActive) {
    try {
        const res = await fetch(`/api/users/${userId}`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({ is_active: !currentIsActive })
        });
        if (res.ok) {
            showToast(`User account ${!currentIsActive ? 'activated' : 'disabled'}`, "info");
            loadUsersList();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to update user", "error");
        }
    } catch (err) {
        showToast("Network error updating user", "error");
    }
}

async function promptResetUserPassword(userId, username) {
    const newPassword = prompt(`Enter new password for user "${username}" (min 8 characters):`);
    if (newPassword === null) return;
    if (newPassword.length < 8) {
        showToast("Password must be at least 8 characters", "error");
        return;
    }

    try {
        const res = await fetch(`/api/users/${userId}`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({ password: newPassword })
        });
        if (res.ok) {
            showToast(`Password updated for "${username}"`, "success");
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to reset password", "error");
        }
    } catch (err) {
        showToast("Network error", "error");
    }
}

async function promptChangeUserQuota(userId, username, currentQuotaBytes) {
    const currentGb = (currentQuotaBytes / (1024 * 1024 * 1024)).toFixed(1);
    const newGbStr = prompt(`Set storage quota in GB for "${username}" (Enter 0 for Unlimited):`, currentGb == 0 ? "0" : currentGb);
    if (newGbStr === null) return;

    const newGb = parseFloat(newGbStr);
    if (isNaN(newGb) || newGb < 0) {
        showToast("Please enter a valid non-negative number", "error");
        return;
    }

    const quotaBytes = newGb > 0 ? Math.round(newGb * 1024 * 1024 * 1024) : 0;

    try {
        const res = await fetch(`/api/users/${userId}`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({ quota_bytes: quotaBytes })
        });
        if (res.ok) {
            showToast(`Storage quota updated for "${username}"`, "success");
            loadUsersList();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to update quota", "error");
        }
    } catch (err) {
        showToast("Network error", "error");
    }
}

async function deleteUser(userId, username) {
    if (!confirm(`Are you sure you want to permanently delete user "${username}" and all their private storage and files? This cannot be undone!`)) {
        return;
    }

    try {
        const res = await fetch(`/api/users/${userId}`, {
            method: "DELETE",
            headers: { "X-CSRF-Token": getCsrfToken() }
        });
        if (res.ok) {
            showToast(`User "${username}" and storage deleted`, "success");
            loadUsersList();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to delete user", "error");
        }
    } catch (err) {
        showToast("Network error deleting user", "error");
    }
}

/* ==========================================
   Contacts Management & Phone Import Engine
   ========================================== */
let currentContacts = [];
let contactsSearchQuery = "";
let contactsStarredOnly = false;
let selectedContactIds = new Set();

const AVATAR_GRADIENTS = [
    "linear-gradient(135deg, #3b82f6, #1d4ed8)",
    "linear-gradient(135deg, #10b981, #047857)",
    "linear-gradient(135deg, #8b5cf6, #6d28d9)",
    "linear-gradient(135deg, #f59e0b, #d97706)",
    "linear-gradient(135deg, #ec4899, #be185d)",
    "linear-gradient(135deg, #06b6d4, #0e7490)",
    "linear-gradient(135deg, #6366f1, #4338ca)"
];

function getContactAvatarStyle(name) {
    let hash = 0;
    for (let i = 0; i < (name || "").length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    const idx = Math.abs(hash) % AVATAR_GRADIENTS.length;
    return `background: ${AVATAR_GRADIENTS[idx]};`;
}

function getContactInitials(name) {
    if (!name) return "?";
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

async function loadContacts(query = null) {
    currentView = "contacts";
    if (query !== null) {
        contactsSearchQuery = query;
    }

    const container = document.getElementById("fileViewContent");
    const breadcrumb = document.getElementById("breadcrumbContainer");
    if (breadcrumb) {
        breadcrumb.innerHTML = `
            <span class="breadcrumb-item active" style="display:inline-flex; align-items:center; gap:6px;">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                Contacts
            </span>
        `;
    }

    const dlFolderBtn = document.getElementById("downloadCurrentFolderBtn");
    if (dlFolderBtn) dlFolderBtn.style.display = "none";

    try {
        let url = `/api/contacts?limit=1000`;
        if (contactsSearchQuery) url += `&search=${encodeURIComponent(contactsSearchQuery)}`;
        if (contactsStarredOnly) url += `&starred_only=true`;

        const res = await fetch(url);
        if (!res.ok) throw new Error("Failed to fetch contacts");
        const data = await res.json();
        currentContacts = data.contacts || [];

        renderContactsView(currentContacts, data.total || 0);
    } catch (err) {
        showToast("Error loading contacts", "error");
    }
}
window.loadContacts = loadContacts;

function renderContactsView(contacts, totalCount) {
    const container = document.getElementById("fileViewContent");
    if (!container) return;

    let toolbarHtml = `
        <div class="contacts-toolbar-wrapper">
            <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <button class="primary-btn" onclick="openContactModal()" style="display:inline-flex; align-items:center; gap:6px; font-size:0.85rem; padding:7px 14px;">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="svg-icon"><line x1="12" x2="12" y1="5" y2="19"/><line x1="5" x2="19" y1="12" y2="12"/></svg>
                    <span>Add Contact</span>
                </button>
                <button class="action-btn" onclick="triggerNativePhoneContactPicker()" style="display:inline-flex; align-items:center; gap:6px; font-size:0.85rem; padding:6px 12px; border:1px solid var(--border-color); background:var(--bg-surface); color:var(--primary);" title="Upload contacts directly from your smartphone">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                    <span>Import from Phone</span>
                </button>
                <button class="action-btn" onclick="document.getElementById('contactsFileInput').click()" style="display:inline-flex; align-items:center; gap:6px; font-size:0.85rem; padding:6px 12px; border:1px solid var(--border-color); background:var(--bg-surface);" title="Upload .vcf or .csv contact file">
                    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>
                    <span>Import File</span>
                </button>
                <button class="action-btn" onclick="openContactExportModal()" style="display:inline-flex; align-items:center; gap:6px; font-size:0.85rem; padding:6px 12px; border:1px solid var(--border-color); background:var(--bg-surface);" title="Export contacts to VCF or CSV">
                    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
                    <span>Export</span>
                </button>
            </div>

            <div style="display:flex; align-items:center; gap:10px; flex:1; justify-content:flex-end; min-width:240px;">
                <div class="contacts-search-bar">
                    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon" style="color:var(--text-muted); margin-right:8px;"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                    <input type="text" class="contacts-search-input" id="contactsLocalSearch" placeholder="Search contacts..." value="${escapeHtml(contactsSearchQuery)}" oninput="debounceContactsSearch(this.value)">
                    ${contactsSearchQuery ? `<button onclick="clearContactsSearch()" style="background:none; border:none; color:var(--text-muted); cursor:pointer; padding:0 4px;">✕</button>` : ''}
                </div>
                <button class="action-btn ${contactsStarredOnly ? 'active' : ''}" onclick="toggleContactsStarredFilter()" style="display:inline-flex; align-items:center; gap:6px; padding:6px 10px; font-size:0.85rem;" title="Show Starred Only">
                    ${contactsStarredOnly ? Icons.get('starFilled', { size: 15 }) : Icons.get('star', { size: 15 })}
                    <span>Starred</span>
                </button>
            </div>
        </div>
    `;

    let selectionHtml = "";
    if (selectedContactIds.size > 0) {
        selectionHtml = `
            <div style="display:flex; align-items:center; justify-content:space-between; background:var(--primary); color:white; padding:8px 16px; border-radius:var(--radius-md); margin-bottom:14px; box-shadow:var(--shadow-sm);">
                <div style="display:flex; align-items:center; gap:12px;">
                    <button class="icon-btn" onclick="clearContactSelection()" style="color:white; width:28px; height:28px; background:rgba(255,255,255,0.15); border:none; display:inline-flex; align-items:center; justify-content:center;" title="Deselect All">✕</button>
                    <span style="font-weight:600; font-size:0.92rem;">${selectedContactIds.size} contact${selectedContactIds.size > 1 ? 's' : ''} selected</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <button class="action-btn" onclick="deleteSelectedContacts()" style="background:rgba(239,68,68,0.4); color:white; border:none; font-weight:600; display:inline-flex; align-items:center; gap:6px; padding:5px 12px;">
                        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                        <span>Delete Selected</span>
                    </button>
                </div>
            </div>
        `;
    }

    if (contacts.length === 0) {
        container.innerHTML = toolbarHtml + selectionHtml + `
            <div class="empty-state" style="padding:48px 16px; text-align:center;">
                <div style="display:flex; justify-content:center; margin-bottom:16px;">
                    <div style="width:72px; height:72px; border-radius:50%; background:var(--bg-secondary); display:flex; align-items:center; justify-content:center; color:var(--text-muted);">
                        <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" class="svg-icon"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                    </div>
                </div>
                <h3 style="font-size:1.15rem; font-weight:600; margin-bottom:6px;">No contacts found</h3>
                <p style="font-size:0.88rem; color:var(--text-muted); max-width:380px; margin:0 auto 16px auto;">
                    ${contactsSearchQuery ? 'No contacts match your search query.' : 'Upload contacts directly from your phone address book, import a .vcf/.csv backup, or add contacts manually.'}
                </p>
                <div style="display:flex; justify-content:center; gap:10px; flex-wrap:wrap;">
                    <button class="primary-btn" onclick="openContactModal()" style="font-size:0.88rem; padding:8px 16px;">+ Add Contact</button>
                    <button class="secondary-btn" onclick="triggerNativePhoneContactPicker()" style="font-size:0.88rem; padding:8px 16px;">Import from Phone</button>
                </div>
            </div>
        `;
        return;
    }

    let cardsHtml = "";
    if (viewMode === "list") {
        cardsHtml = `
            <div style="overflow-x:auto; -webkit-overflow-scrolling:touch;">
                <table class="file-table" style="table-layout:fixed; width:100%;">
                    <thead>
                        <tr>
                            <th style="width:40px; text-align:center;">
                                <input type="checkbox" onchange="toggleSelectAllContacts(this.checked)" ${selectedContactIds.size === contacts.length && contacts.length > 0 ? 'checked' : ''}>
                            </th>
                            <th style="width:36px;"></th>
                            <th>Name</th>
                            <th>Phone</th>
                            <th>Email</th>
                            <th>Organization</th>
                            <th style="width:110px; text-align:right;">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        contacts.forEach(c => {
            const isSelected = selectedContactIds.has(c.id);
            cardsHtml += `
                <tr class="${isSelected ? 'selected' : ''}">
                    <td style="text-align:center;">
                        <input type="checkbox" onchange="toggleContactSelect(${c.id}, this.checked)" ${isSelected ? 'checked' : ''}>
                    </td>
                    <td>
                        <button class="icon-btn" onclick="toggleContactStar(${c.id}, event)" style="width:28px; height:28px; padding:0; color:${c.is_starred ? 'var(--accent-amber)' : 'var(--text-muted)'};" title="${c.is_starred ? 'Unstar' : 'Star'}">
                            ${c.is_starred ? Icons.get('starFilled', { size: 16 }) : Icons.get('star', { size: 16 })}
                        </button>
                    </td>
                    <td>
                        <div style="display:flex; align-items:center; gap:10px;">
                            <div class="contact-avatar-bubble" style="width:32px; height:32px; font-size:0.82rem; ${getContactAvatarStyle(c.name)}">${getContactInitials(c.name)}</div>
                            <strong style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(c.name)}</strong>
                        </div>
                    </td>
                    <td>
                        ${c.phone ? `<a href="tel:${escapeHtml(c.phone)}" class="contact-link-row" title="Call ${escapeHtml(c.phone)}"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon" style="color:var(--accent-green);"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg> <span>${escapeHtml(c.phone)}</span></a>` : '<span style="color:var(--text-muted);">&mdash;</span>'}
                    </td>
                    <td>
                        ${c.email ? `<a href="mailto:${escapeHtml(c.email)}" class="contact-link-row" title="Email ${escapeHtml(c.email)}"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon" style="color:var(--primary);"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg> <span>${escapeHtml(c.email)}</span></a>` : '<span style="color:var(--text-muted);">&mdash;</span>'}
                    </td>
                    <td>
                        <span style="font-size:0.82rem; color:var(--text-muted);">${escapeHtml(c.organization || '—')}</span>
                    </td>
                    <td style="text-align:right; white-space:nowrap;">
                        <button class="icon-btn" onclick="openContactModal(${c.id})" style="width:30px; height:30px; display:inline-flex; align-items:center; justify-content:center;" title="Edit Contact">
                            ${Icons.get('edit', { size: 14 })}
                        </button>
                        <button class="icon-btn" onclick="deleteContactItem(${c.id}, '${escapeHtml(c.name).replace(/'/g, "\\'")}')" style="width:30px; height:30px; display:inline-flex; align-items:center; justify-content:center; color:var(--accent-red);" title="Delete Contact">
                            ${Icons.get('trash', { size: 14 })}
                        </button>
                    </td>
                </tr>
            `;
        });
        cardsHtml += `</tbody></table></div>`;
    } else {
        cardsHtml = `<div class="contacts-grid ${selectedContactIds.size > 0 ? 'has-selected-contacts' : ''}">`;
        contacts.forEach(c => {
            const isSelected = selectedContactIds.has(c.id);
            cardsHtml += `
                <div class="contact-card ${isSelected ? 'selected' : ''}" id="contactCard_${c.id}">
                    <input type="checkbox" class="contact-checkbox" onchange="toggleContactSelect(${c.id}, this.checked)" ${isSelected ? 'checked' : ''}>
                    
                    <div class="contact-header">
                        <div class="contact-avatar-bubble" style="${getContactAvatarStyle(c.name)}">${getContactInitials(c.name)}</div>
                        <div class="contact-info">
                            <div class="contact-name" title="${escapeHtml(c.name)}">${escapeHtml(c.name)}</div>
                            <div class="contact-org" title="${escapeHtml(c.organization || '')}">${escapeHtml(c.organization || 'No organization')}</div>
                        </div>
                        <button class="icon-btn" onclick="toggleContactStar(${c.id}, event)" style="width:32px; height:32px; padding:0; flex-shrink:0; color:${c.is_starred ? 'var(--accent-amber)' : 'var(--text-muted)'};" title="${c.is_starred ? 'Unstar' : 'Star'}">
                            ${c.is_starred ? Icons.get('starFilled', { size: 17 }) : Icons.get('star', { size: 17 })}
                        </button>
                    </div>

                    <div class="contact-details-list">
                        ${c.phone ? `
                            <a href="tel:${escapeHtml(c.phone)}" class="contact-link-row" title="Call ${escapeHtml(c.phone)}">
                                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon" style="color:var(--accent-green);"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                                <span>${escapeHtml(c.phone)}</span>
                            </a>
                        ` : ''}
                        ${c.email ? `
                            <a href="mailto:${escapeHtml(c.email)}" class="contact-link-row" title="Email ${escapeHtml(c.email)}">
                                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="svg-icon" style="color:var(--primary);"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
                                <span>${escapeHtml(c.email)}</span>
                            </a>
                        ` : ''}
                    </div>

                    ${c.notes ? `<div class="contact-notes-box">${escapeHtml(c.notes)}</div>` : ''}

                    <div class="contact-footer-actions">
                        <span style="font-size:0.75rem; color:var(--text-muted);">${formatDate(c.created_at)}</span>
                        <div style="display:flex; align-items:center; gap:4px;">
                            <button class="icon-btn" onclick="openContactModal(${c.id})" style="width:30px; height:30px;" title="Edit Contact">
                                ${Icons.get('edit', { size: 14 })}
                            </button>
                            <button class="icon-btn" onclick="deleteContactItem(${c.id}, '${escapeHtml(c.name).replace(/'/g, "\\'")}')" style="width:30px; height:30px; color:var(--accent-red);" title="Delete Contact">
                                ${Icons.get('trash', { size: 14 })}
                            </button>
                        </div>
                    </div>
                </div>
            `;
        });
        cardsHtml += `</div>`;
    }

    container.innerHTML = toolbarHtml + selectionHtml + cardsHtml;
}

let contactsSearchDebounceTimer = null;
function debounceContactsSearch(val) {
    clearTimeout(contactsSearchDebounceTimer);
    contactsSearchDebounceTimer = setTimeout(() => {
        contactsSearchQuery = val.trim();
        loadContacts();
    }, 280);
}
window.debounceContactsSearch = debounceContactsSearch;

function clearContactsSearch() {
    contactsSearchQuery = "";
    loadContacts();
}
window.clearContactsSearch = clearContactsSearch;

function toggleContactsStarredFilter() {
    contactsStarredOnly = !contactsStarredOnly;
    loadContacts();
}
window.toggleContactsStarredFilter = toggleContactsStarredFilter;

function toggleContactSelect(id, isChecked) {
    if (isChecked) {
        selectedContactIds.add(id);
    } else {
        selectedContactIds.delete(id);
    }
    renderContactsView(currentContacts, currentContacts.length);
}
window.toggleContactSelect = toggleContactSelect;

function toggleSelectAllContacts(isChecked) {
    if (isChecked) {
        currentContacts.forEach(c => selectedContactIds.add(c.id));
    } else {
        selectedContactIds.clear();
    }
    renderContactsView(currentContacts, currentContacts.length);
}
window.toggleSelectAllContacts = toggleSelectAllContacts;

function clearContactSelection() {
    selectedContactIds.clear();
    renderContactsView(currentContacts, currentContacts.length);
}
window.clearContactSelection = clearContactSelection;

async function deleteSelectedContacts() {
    if (selectedContactIds.size === 0) return;
    const count = selectedContactIds.size;
    if (!confirm(`Permanently delete ${count} selected contact${count > 1 ? 's' : ''}?`)) return;

    try {
        const res = await fetch("/api/contacts/delete-batch", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": getCsrfToken()
            },
            body: JSON.stringify({ contact_ids: Array.from(selectedContactIds) })
        });
        if (res.ok) {
            showToast(`Deleted ${count} contacts`, "success");
            selectedContactIds.clear();
            loadContacts();
        } else {
            showToast("Failed to delete contacts", "error");
        }
    } catch (_) {
        showToast("Network error deleting contacts", "error");
    }
}
window.deleteSelectedContacts = deleteSelectedContacts;

async function toggleContactStar(id, e) {
    if (e) e.stopPropagation();
    try {
        const res = await fetch(`/api/contacts/${id}/star`, {
            method: "POST",
            headers: { "X-CSRF-Token": getCsrfToken() }
        });
        if (res.ok) {
            const data = await res.json();
            const contact = currentContacts.find(c => c.id === id);
            if (contact) contact.is_starred = data.is_starred;
            renderContactsView(currentContacts, currentContacts.length);
        }
    } catch (_) {
        showToast("Failed to update star", "error");
    }
}
window.toggleContactStar = toggleContactStar;

async function deleteContactItem(id, name) {
    if (!confirm(`Delete contact "${name}"?`)) return;
    try {
        const res = await fetch(`/api/contacts/${id}`, {
            method: "DELETE",
            headers: { "X-CSRF-Token": getCsrfToken() }
        });
        if (res.ok) {
            showToast(`Deleted "${name}"`, "success");
            selectedContactIds.delete(id);
            loadContacts();
        } else {
            showToast("Failed to delete contact", "error");
        }
    } catch (_) {
        showToast("Network error deleting contact", "error");
    }
}
window.deleteContactItem = deleteContactItem;

function openContactModal(contactId = null) {
    const modal = document.getElementById("contactModal");
    const title = document.getElementById("contactModalTitle");
    const idInput = document.getElementById("contactId");
    const nameInput = document.getElementById("contactName");
    const phoneInput = document.getElementById("contactPhone");
    const emailInput = document.getElementById("contactEmail");
    const orgInput = document.getElementById("contactOrg");
    const notesInput = document.getElementById("contactNotes");
    const starredInput = document.getElementById("contactStarred");
    const saveBtn = document.getElementById("contactSaveBtn");

    if (contactId) {
        const contact = currentContacts.find(c => c.id === contactId);
        if (!contact) return;
        title.textContent = "Edit Contact";
        idInput.value = contact.id;
        nameInput.value = contact.name || "";
        phoneInput.value = contact.phone || "";
        emailInput.value = contact.email || "";
        orgInput.value = contact.organization || "";
        notesInput.value = contact.notes || "";
        starredInput.checked = !!contact.is_starred;
        saveBtn.textContent = "Update Contact";
    } else {
        title.textContent = "Add Contact";
        idInput.value = "";
        nameInput.value = "";
        phoneInput.value = "";
        emailInput.value = "";
        orgInput.value = "";
        notesInput.value = "";
        starredInput.checked = false;
        saveBtn.textContent = "Save Contact";
    }

    modal.style.display = "flex";
    setTimeout(() => nameInput.focus(), 50);
}
window.openContactModal = openContactModal;

async function handleContactSubmit(e) {
    e.preventDefault();
    const contactId = document.getElementById("contactId").value;
    const name = document.getElementById("contactName").value.trim();
    const phone = document.getElementById("contactPhone").value.trim();
    const email = document.getElementById("contactEmail").value.trim();
    const org = document.getElementById("contactOrg").value.trim();
    const notes = document.getElementById("contactNotes").value.trim();
    const isStarred = document.getElementById("contactStarred").checked;

    if (!name) {
        showToast("Contact name is required", "warning");
        return;
    }

    const payload = {
        name,
        phone,
        email,
        organization: org,
        notes,
        is_starred: isStarred
    };

    try {
        let res;
        if (contactId) {
            res = await fetch(`/api/contacts/${contactId}`, {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": getCsrfToken()
                },
                body: JSON.stringify(payload)
            });
        } else {
            res = await fetch("/api/contacts", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": getCsrfToken()
                },
                body: JSON.stringify(payload)
            });
        }

        if (res.ok) {
            showToast(contactId ? "Contact updated" : "Contact created", "success");
            closeModals();
            loadContacts();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to save contact", "error");
        }
    } catch (_) {
        showToast("Network error saving contact", "error");
    }
}
window.handleContactSubmit = handleContactSubmit;

async function triggerNativePhoneContactPicker() {
    if ('contacts' in navigator && 'ContactsManager' in window) {
        try {
            const props = ['name', 'tel', 'email'];
            let supported = [];
            try {
                supported = await navigator.contacts.getProperties();
            } catch (_) {}

            const queryProps = props.filter(p => supported.length === 0 || supported.includes(p));
            const selected = await navigator.contacts.select(
                queryProps.length > 0 ? queryProps : ['name', 'tel'],
                { multiple: true }
            );

            if (!selected || selected.length === 0) return;

            const contactsToUpload = selected.map(c => {
                const name = (c.name && c.name.length > 0) ? c.name[0] : (c.tel && c.tel.length > 0 ? `Phone ${c.tel[0]}` : 'Unnamed Contact');
                const phone = (c.tel && c.tel.length > 0) ? c.tel[0] : '';
                const email = (c.email && c.email.length > 0) ? c.email[0] : '';
                const notes = (c.tel && c.tel.length > 1) ? `Other phones: ${c.tel.slice(1).join(', ')}` : '';
                return { name, phone, email, notes, organization: '' };
            });

            showToast(`Uploading ${contactsToUpload.length} contacts from phone...`, "info");
            const res = await fetch("/api/contacts/batch", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": getCsrfToken()
                },
                body: JSON.stringify({ contacts: contactsToUpload })
            });

            if (res.ok) {
                const result = await res.json();
                showToast(`Successfully uploaded ${result.imported} contacts!`, "success");
                loadContacts();
            } else {
                showToast("Failed to save imported contacts", "error");
            }
        } catch (err) {
            if (err.name !== "AbortError") {
                openPhoneContactImportModal();
            }
        }
    } else {
        openPhoneContactImportModal();
    }
}
window.triggerNativePhoneContactPicker = triggerNativePhoneContactPicker;

function openPhoneContactImportModal() {
    closeModals();
    const modal = document.getElementById("phoneContactImportModal");
    if (modal) modal.style.display = "flex";
}
window.openPhoneContactImportModal = openPhoneContactImportModal;

function openContactExportModal() {
    closeModals();
    const modal = document.getElementById("contactExportModal");
    if (modal) modal.style.display = "flex";
}
window.openContactExportModal = openContactExportModal;

async function handleContactsFileChosen(input) {
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];
    input.value = "";

    const formData = new FormData();
    formData.append("file", file);

    showToast(`Importing contacts from "${file.name}"...`, "info");
    try {
        const res = await fetch("/api/contacts/import-file", {
            method: "POST",
            headers: {
                "X-CSRF-Token": getCsrfToken()
            },
            body: formData
        });

        if (res.ok) {
            const data = await res.json();
            showToast(`Successfully imported ${data.imported} contacts!`, "success");
            loadContacts();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to import contacts file", "error");
        }
    } catch (_) {
        showToast("Network error uploading contacts file", "error");
    }
}
window.handleContactsFileChosen = handleContactsFileChosen;
