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
            if (block) block.classList.toggle('collapsed');
        });
    });
}

// Expose to router
window.initFeaturesPage = initFeaturesPage;
