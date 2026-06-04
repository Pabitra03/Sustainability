// In local dev, always call Flask directly at port 5001.
// On Vercel (production), use relative /api since both are on the same domain.
const IS_LOCAL = location.hostname === 'localhost' || location.hostname === '127.0.0.1' || location.protocol === 'file:';
const API_BASE_URL = IS_LOCAL ? 'http://127.0.0.1:5001/api' : '/api';

function initTheme() {
    if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
    } else {
        document.documentElement.classList.remove('dark');
    }
}

function toggleTheme() {
    if (document.documentElement.classList.contains('dark')) {
        document.documentElement.classList.remove('dark');
        localStorage.theme = 'light';
    } else {
        document.documentElement.classList.add('dark');
        localStorage.theme = 'dark';
    }
}

function getUserId() { return localStorage.getItem('user_id'); }
function getUserName() { return localStorage.getItem('user_name'); }
function setSession(userId, name) {
    localStorage.setItem('user_id', userId);
    localStorage.setItem('user_name', name);
}
function logout() {
    // Clear session
    localStorage.removeItem('user_id');
    localStorage.removeItem('user_name');

    // Clear AI Coach chat data (frontend-only cache)
    localStorage.removeItem('ai_coach_messages');
    localStorage.removeItem('ai_coach_last_user_id');

    try {
        const coachMessagesEl = document.getElementById('coach-messages');
        if (coachMessagesEl) coachMessagesEl.innerHTML = '';
    } catch (e) {
        // ignore
    }

    window.location.href = 'index.html';
}

function showAppLoading(message = 'Loading your workspace...') {
    const overlay = document.getElementById('app-loading-overlay');
    if (!overlay) return;
    const text = overlay.querySelector('[data-loading-text]');
    if (text) text.textContent = message;
    overlay.classList.remove('hidden');
}

function hideAppLoading() {
    const overlay = document.getElementById('app-loading-overlay');
    if (overlay) overlay.classList.add('hidden');
}

async function updateHostelModeVisibility(activePath) {
    const userId = getUserId();
    if (!userId) return;

    const applyVisibility = (usesHostel) => {
        document.querySelectorAll('[data-hostel-nav="true"]').forEach(link => {
            link.classList.toggle('hidden', !usesHostel);
        });
        if (!usesHostel && activePath === 'hostel.html') {
            window.location.href = 'dashboard.html';
        }
    };

    const cachedHostel = localStorage.getItem('uses_hostel');
    if (cachedHostel !== null) {
        applyVisibility(cachedHostel === 'true');
        if (!['hostel.html', 'profile.html'].includes(activePath)) return;
    }

    try {
        const res = await fetch(`${API_BASE_URL}/user/profile?user_id=${userId}`);
        if (!res.ok) return;
        const profile = await res.json();
        const usesHostel = Boolean(profile.uses_hostel);
        localStorage.setItem('uses_hostel', usesHostel ? 'true' : 'false');
        applyVisibility(usesHostel);
    } catch (e) {
        // Keep navigation usable if the profile fetch is unavailable.
    }
}

// Inject App Shell (Sidebar & Mobile Bottom Nav) into authenticated pages
function renderAppShell(activePath) {
    const shellContainer = document.getElementById('app-shell');
    if (!shellContainer) return;

    const navItems = [
        { path: 'dashboard.html', icon: 'grid', label: 'Dashboard' },
        { path: 'diet.html', icon: 'coffee', label: 'Diet Plan' },
        { path: 'workout.html', icon: 'activity', label: 'Workout Plan' },
        { path: 'progress.html', icon: 'trending-up', label: 'Progress' },
        { path: 'hostel.html', icon: 'home', label: 'Hostel Mode', requiresHostel: true },
        { path: 'ai-coach.html', icon: 'message-circle', label: 'AI Coach' },
        { path: 'reports.html', icon: 'file-text', label: 'Reports' },
        { path: 'profile.html', icon: 'user', label: 'Profile' }
    ];

    let sidebarLinks = '';
    let bottomNavLinks = '';

    navItems.forEach(item => {
        const isActive = activePath === item.path;
        const activeClassSidebar = isActive ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800';
        const activeClassBottom = isActive ? 'text-primary-600 dark:text-primary-400' : 'text-gray-500 dark:text-gray-400';

        sidebarLinks += `
            <a href="${item.path}" data-hostel-nav="${item.requiresHostel ? 'true' : 'false'}" class="flex items-center px-4 py-3 mb-2 rounded-lg transition-colors ${activeClassSidebar}">
                <i data-feather="${item.icon}" class="w-5 h-5 mr-3"></i>
                <span class="font-medium">${item.label}</span>
            </a>
        `;

        bottomNavLinks += `
            <a href="${item.path}" data-hostel-nav="${item.requiresHostel ? 'true' : 'false'}" class="flex flex-col items-center justify-center w-full py-1 ${activeClassBottom}">
                <i data-feather="${item.icon}" class="w-5 h-5 mb-0.5"></i>
                <span class="text-[8px] sm:text-[10px] uppercase font-black tracking-tighter sm:tracking-wider text-center px-1 leading-none">${item.label}</span>
            </a>
        `;
    });

    const shellHTML = `
        <div class="flex h-screen bg-background dark:bg-gray-900">
            <!-- Desktop Sidebar -->
            <aside class="hidden md:flex flex-col w-64 border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
                <div class="p-6 flex items-center gap-2">
                    <i data-feather="activity" class="text-primary-500"></i>
                    <span class="text-xl font-bold tracking-tight text-gray-900 dark:text-white">Sustainability</span>
                </div>
                <nav class="flex-1 px-4 py-4 space-y-1">
                    ${sidebarLinks}
                </nav>
                <div class="p-4 border-t border-gray-200 dark:border-gray-800">
                    <div class="flex items-center justify-between px-4 py-2 mb-2">
                        <span class="text-sm font-medium text-gray-500">Theme</span>
                        <button onclick="toggleTheme()" class="p-2 bg-gray-100 dark:bg-gray-800 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
                            <i data-feather="moon" class="w-4 h-4 text-gray-600 hidden dark:block"></i>
                            <i data-feather="sun" class="w-4 h-4 text-gray-400 block dark:hidden"></i>
                        </button>
                    </div>
                    <button onclick="logout()" class="w-full flex items-center px-4 py-3 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/10 rounded-lg transition-colors">
                        <i data-feather="log-out" class="w-5 h-5 mr-3"></i>
                        <span class="font-medium">Logout</span>
                    </button>
                </div>
            </aside>

            <!-- Main Content Container -->
            <div class="flex-1 flex flex-col min-w-0 overflow-y-auto pb-16 md:pb-0">
                
                <!-- Mobile Topbar -->
                <header class="md:hidden flex items-center justify-between px-4 py-4 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 sticky top-0 z-20">
                    <div class="flex items-center gap-2">
                        <i data-feather="activity" class="text-primary-500 h-5 w-5"></i>
                        <span class="text-lg font-bold text-gray-900 dark:text-white">Sustainability</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <button onclick="toggleTheme()" class="p-2 text-gray-500">
                            <i data-feather="moon" class="w-5 h-5 hidden dark:block"></i>
                            <i data-feather="sun" class="w-5 h-5 block dark:hidden"></i>
                        </button>
                        <button onclick="logout()" class="p-2 text-red-500">
                            <i data-feather="log-out" class="w-5 h-5"></i>
                        </button>
                    </div>
                </header>

                <main class="flex-1 p-4 sm:p-6 lg:p-8" id="main-view">
                    <!-- Page content injected below -->
                </main>
                <div id="app-loading-overlay" class="hidden fixed inset-0 z-[120] bg-white/90 dark:bg-gray-950/90 backdrop-blur-sm flex items-center justify-center p-6">
                    <div class="w-full max-w-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6 shadow-xl text-center">
                        <div class="w-12 h-12 rounded-full bg-primary-500/15 text-primary-500 grid place-items-center mx-auto mb-4">
                            <i data-feather="loader" class="w-6 h-6 animate-spin"></i>
                        </div>
                        <p data-loading-text class="text-sm font-black text-gray-900 dark:text-white">Loading your workspace...</p>
                        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">Pulling fresh data from your account.</p>
                    </div>
                </div>
            </div>

            <!-- Mobile Bottom Nav -->
            <nav class="md:hidden fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 z-50 flex justify-around items-center h-16 safe-area-pb">
                ${bottomNavLinks}
            </nav>
        </div>
    `;

    // Wrap the existing body content inside the main-view area
    const existingContent = shellContainer.innerHTML;
    shellContainer.innerHTML = shellHTML;
    document.getElementById('main-view').innerHTML = existingContent;
    const cachedHostel = localStorage.getItem('uses_hostel');
    if (cachedHostel === 'false') {
        document.querySelectorAll('[data-hostel-nav="true"]').forEach(link => link.classList.add('hidden'));
    }
    updateHostelModeVisibility(activePath);
}

document.addEventListener('DOMContentLoaded', () => {
    initTheme();

    // Auto-render shell if container exists
    const shellContainer = document.getElementById('app-shell');
    if (shellContainer) {
        const path = window.location.pathname.split('/').pop() || 'index.html';
        renderAppShell(path);
    }

    if (typeof feather !== 'undefined') feather.replace();

    // ── Page Transition: Standard Nav ──────────────────
    // We removed the fade-out to ensure 100% reliability.
    // The background-color lock in the head still prevents the white blink.
});
