/* ============================================================
   DOCUMENTATION PAGE — JavaScript Logic
   ============================================================ */

// Store references for cleanup
let _docsScrollCleanup = null;

function initDocumentationPage() {
    // Clean up previous listeners to prevent memory leaks
    if (_docsScrollCleanup) {
        _docsScrollCleanup();
        _docsScrollCleanup = null;
    }
    initScrollSpy();
    initDocsSectionToggle();
}

// ============================================================
// SCROLL-SPY — highlight active TOC link
// ============================================================

function initScrollSpy() {
    const tocLinks = document.querySelectorAll('.docs-toc-list a');
    const sections = [];

    tocLinks.forEach(link => {
        const id = link.getAttribute('href');
        if (id && id.startsWith('#doc-')) {
            const section = document.getElementById(id.slice(1));
            if (section) sections.push({ link, section });
        }
    });

    if (!sections.length) return;

    // Click handler — smooth scroll
    tocLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const id = link.getAttribute('href').slice(1);
            const target = document.getElementById(id);
            if (!target) return;

            // Expand section if collapsed
            const docSection = target.closest('.docs-section');
            if (docSection && docSection.classList.contains('collapsed')) {
                docSection.classList.remove('collapsed');
            }

            target.scrollIntoView({ behavior: 'smooth', block: 'start' });

            // Update active state immediately
            tocLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');
        });
    });

    // Scroll listener — throttled
    const pageContainer = document.getElementById('page-container');
    const scrollTarget = pageContainer || window;

    let ticking = false;
    function onScroll() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
            updateActiveTocLink(sections, tocLinks);
            ticking = false;
        });
    }

    scrollTarget.addEventListener('scroll', onScroll, { passive: true });
    // Also listen on window in case page-container isn't the scroller
    if (scrollTarget !== window) {
        window.addEventListener('scroll', onScroll, { passive: true });
    }

    // Store cleanup function to remove listeners on page change
    _docsScrollCleanup = () => {
        scrollTarget.removeEventListener('scroll', onScroll);
        if (scrollTarget !== window) {
            window.removeEventListener('scroll', onScroll);
        }
    };

    // Initial highlight
    updateActiveTocLink(sections, tocLinks);
}

function updateActiveTocLink(sections, tocLinks) {
    let current = null;
    const offset = 120; // account for sticky header

    for (const { link, section } of sections) {
        const rect = section.getBoundingClientRect();
        if (rect.top <= offset) {
            current = link;
        }
    }

    tocLinks.forEach(l => l.classList.remove('active'));
    if (current) {
        current.classList.add('active');
    } else if (sections.length) {
        // Default to first
        sections[0].link.classList.add('active');
    }
}

// ============================================================
// SECTION COLLAPSE / EXPAND
// ============================================================

function initDocsSectionToggle() {
    document.querySelectorAll('.docs-section-header').forEach(header => {
        header.addEventListener('click', () => {
            const section = header.closest('.docs-section');
            if (section) section.classList.toggle('collapsed');
        });
    });
}

// ============================================================
// COPY CODE BLOCK
// ============================================================

function copyDocCode(btn) {
    const block = btn.closest('.docs-code-block');
    if (!block) return;

    const pre = block.querySelector('pre');
    if (!pre) return;

    const text = pre.textContent;

    navigator.clipboard.writeText(text).then(() => {
        btn.classList.add('copied');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = `
            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
            </svg>
            Copied!`;
        setTimeout(() => {
            btn.classList.remove('copied');
            btn.innerHTML = originalHTML;
        }, 2000);
    }).catch(() => {
        // Fallback
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);

        btn.classList.add('copied');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = `
            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
            </svg>
            Copied!`;
        setTimeout(() => {
            btn.classList.remove('copied');
            btn.innerHTML = originalHTML;
        }, 2000);
    });
}

// ============================================================
// Expose init function for router
// ============================================================
window.initDocumentationPage = initDocumentationPage;
