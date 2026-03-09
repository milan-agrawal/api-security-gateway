/* ============================================================
   FEATURES & SPECIFICATIONS PAGE — JavaScript Logic
   Horizontal nav scroll-spy + smooth scroll
   ============================================================ */

let _featScrollCleanup = null;

function initFeaturesPage() {
    if (_featScrollCleanup) {
        _featScrollCleanup();
        _featScrollCleanup = null;
    }
    initFeatNavScrollSpy();
    initFeatBlockToggle();
    initFeatToggleAll();
    initFeatFaq();
    initFeatCtaLinks();
}

// ============================================================
// SCROLL-SPY — highlight active horizontal nav item
// ============================================================

function initFeatNavScrollSpy() {
    const navItems = document.querySelectorAll('.feat-nav-item');
    const sections = [];

    navItems.forEach(item => {
        const id = item.getAttribute('href');
        if (id && id.startsWith('#feat-')) {
            const section = document.getElementById(id.slice(1));
            if (section) sections.push({ link: item, section });
        }
    });

    if (!sections.length) return;

    // Click handler — smooth scroll
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const id = item.getAttribute('href').slice(1);
            const target = document.getElementById(id);
            if (!target) return;

            // Expand if collapsed
            const block = target.closest('.feat-block') || target;
            if (block && block.classList.contains('collapsed')) {
                block.classList.remove('collapsed');
            }

            target.scrollIntoView({ behavior: 'smooth', block: 'start' });

            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');
        });
    });

    // Scroll listener — throttled via rAF
    const pageContainer = document.getElementById('page-container');
    const scrollTarget = pageContainer || window;

    let ticking = false;
    function onScroll() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
            updateFeatActiveNav(sections, navItems);
            ticking = false;
        });
    }

    scrollTarget.addEventListener('scroll', onScroll, { passive: true });
    if (scrollTarget !== window) {
        window.addEventListener('scroll', onScroll, { passive: true });
    }

    _featScrollCleanup = () => {
        scrollTarget.removeEventListener('scroll', onScroll);
        if (scrollTarget !== window) {
            window.removeEventListener('scroll', onScroll);
        }
    };

    updateFeatActiveNav(sections, navItems);
}

function updateFeatActiveNav(sections, navItems) {
    let current = null;
    const offset = 140;

    for (const { link, section } of sections) {
        const rect = section.getBoundingClientRect();
        if (rect.top <= offset) {
            current = link;
        }
    }

    navItems.forEach(n => n.classList.remove('active'));
    if (current) {
        current.classList.add('active');
        // Scroll active nav item into view horizontally
        current.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    } else if (sections.length) {
        sections[0].link.classList.add('active');
    }
}

// ============================================================
// BLOCK COLLAPSE / EXPAND
// ============================================================

function initFeatBlockToggle() {
    document.querySelectorAll('.feat-block-header').forEach(header => {
        header.addEventListener('click', () => {
            const block = header.closest('.feat-block');
            if (block) {
                block.classList.toggle('collapsed');
                syncToggleAllBtn();
            }
        });
    });
}

// ============================================================
// EXPAND ALL / COLLAPSE ALL
// ============================================================

function initFeatToggleAll() {
    const btn = document.getElementById('feat-toggle-all');
    if (!btn) return;

    btn.addEventListener('click', () => {
        const blocks = document.querySelectorAll('.feat-block');
        const allCollapsed = Array.from(blocks).every(b => b.classList.contains('collapsed'));

        blocks.forEach(b => {
            if (allCollapsed) {
                b.classList.remove('collapsed');
            } else {
                b.classList.add('collapsed');
            }
        });

        syncToggleAllBtn();
    });
}

function syncToggleAllBtn() {
    const btn = document.getElementById('feat-toggle-all');
    if (!btn) return;

    const blocks = document.querySelectorAll('.feat-block');
    const allCollapsed = Array.from(blocks).every(b => b.classList.contains('collapsed'));

    const collapseIcon = btn.querySelector('.collapse-icon');
    const expandIcon = btn.querySelector('.expand-icon');
    const label = btn.querySelector('.feat-toolbar-label');

    if (allCollapsed) {
        if (collapseIcon) collapseIcon.style.display = 'none';
        if (expandIcon) expandIcon.style.display = '';
        if (label) label.textContent = 'Expand All';
    } else {
        if (collapseIcon) collapseIcon.style.display = '';
        if (expandIcon) expandIcon.style.display = 'none';
        if (label) label.textContent = 'Collapse All';
    }
}

// ============================================================
// FAQ ACCORDION
// ============================================================

function initFeatFaq() {
    document.querySelectorAll('.feat-faq-q').forEach(btn => {
        btn.addEventListener('click', () => {
            const item = btn.closest('.feat-faq-item');
            if (!item) return;

            // Close other open items
            document.querySelectorAll('.feat-faq-item.open').forEach(other => {
                if (other !== item) other.classList.remove('open');
            });

            item.classList.toggle('open');
        });
    });
}

// ============================================================
// CTA LINK NAVIGATION (hash-based SPA routing)
// ============================================================

function initFeatCtaLinks() {
    document.querySelectorAll('.feat-cta-btn').forEach(link => {
        link.addEventListener('click', (e) => {
            const href = link.getAttribute('href');
            if (href && href.startsWith('#')) {
                e.preventDefault();
                window.location.hash = href;
            }
        });
    });
}

// Expose to router
window.initFeaturesPage = initFeaturesPage;
