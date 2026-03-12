/* ============================================================
   SECURITY WIKI — Interactive Behaviour
   - Live search across cards, glossary items, practice cards
   - Category filter pills (mutually exclusive with search)
   - Glossary accordion (one open at a time)
   - Expand All / Collapse All toggle
   - Keyboard shortcut: / to focus search
   - Section jump nav with active tracking
   - Scroll-to-top button
   - Reading progress bar
   - Section entrance animations (IntersectionObserver)
   ============================================================ */

(function () {

    /* ── Entry point called by router ── */
    function initSecuritywikiPage() {
        initWikiSearch();
        initWikiFilters();
        initWikiGlossary();
        initGlossaryToggle();
        initKeyboardShortcut();
        initJumpNav();
        initScrollToTop();
        initProgressBar();
        initSectionAnimations();
    }

    /* ============================================================
       SEARCH
    ============================================================ */
    function initWikiSearch() {
        const input    = document.getElementById('wiki-search');
        const countEl  = document.getElementById('wiki-search-count');
        const noRes    = document.getElementById('wiki-no-results');
        const termEl   = document.getElementById('wiki-search-term');
        const filterBtns = document.querySelectorAll('.wiki-filter-btn');

        if (!input) return;

        input.addEventListener('input', function () {
            const q = this.value.trim().toLowerCase();

            if (!q) {
                resetAll();
                return;
            }

            // Reset filter pills to "all" when search is active
            filterBtns.forEach(b => b.classList.remove('active'));
            const allBtn = document.querySelector('.wiki-filter-btn[data-filter="all"]');
            if (allBtn) allBtn.classList.add('active');

            // Show all sections first, then hide/show individual items
            document.querySelectorAll('.wiki-section').forEach(s => s.style.display = '');

            let totalVisible = 0;

            // Search searchable items
            document.querySelectorAll('[data-search]').forEach(el => {
                const text = el.getAttribute('data-search').toLowerCase();
                const matches = text.includes(q);
                if (el.style.display === 'none' && el.getAttribute('aria-hidden') === 'true') {
                    return;
                }
                el.style.display = matches ? '' : 'none';
                if (matches) totalVisible++;
            });

            // Hide sections where no visible items remain
            document.querySelectorAll('.wiki-section').forEach(section => {
                const items = Array.from(section.querySelectorAll('[data-search]'))
                    .filter(el => el.getAttribute('aria-hidden') !== 'true');
                const hasVisible = items.some(el => el.style.display !== 'none');
                section.style.display = hasVisible ? '' : 'none';
            });

            if (countEl) {
                countEl.textContent = totalVisible + ' result' + (totalVisible !== 1 ? 's' : '');
                countEl.classList.add('visible');
            }

            if (noRes) {
                noRes.style.display = totalVisible === 0 ? '' : 'none';
                if (termEl) termEl.textContent = this.value;
            }
        });
    }

    /* ── Reset all visibility to default ── */
    function resetAll() {
        document.querySelectorAll('[data-search]').forEach(el => {
            if (el.getAttribute('aria-hidden') !== 'true') {
                el.style.display = '';
            }
        });
        document.querySelectorAll('.wiki-section').forEach(s => s.style.display = '');

        const countEl = document.getElementById('wiki-search-count');
        if (countEl) countEl.classList.remove('visible');

        const noRes = document.getElementById('wiki-no-results');
        if (noRes) noRes.style.display = 'none';
    }

    /* ============================================================
       FILTER PILLS
    ============================================================ */
    function initWikiFilters() {
        const buttons = document.querySelectorAll('.wiki-filter-btn');

        buttons.forEach(btn => {
            btn.addEventListener('click', function () {
                const searchInput = document.getElementById('wiki-search');
                if (searchInput) searchInput.value = '';
                resetAll();

                buttons.forEach(b => b.classList.remove('active'));
                this.classList.add('active');

                const filter = this.dataset.filter;

                document.querySelectorAll('.wiki-section').forEach(section => {
                    section.style.display =
                        (filter === 'all' || section.dataset.section === filter) ? '' : 'none';
                });
            });
        });
    }

    /* ============================================================
       GLOSSARY ACCORDION — One open at a time
    ============================================================ */
    function initWikiGlossary() {
        document.querySelectorAll('.wiki-gloss-trigger').forEach(trigger => {
            trigger.addEventListener('click', function () {
                const item   = this.closest('.wiki-gloss-item');
                const isOpen = item.classList.contains('open');

                document.querySelectorAll('.wiki-gloss-item.open')
                    .forEach(i => i.classList.remove('open'));

                if (!isOpen) item.classList.add('open');

                // Sync toggle button label
                syncToggleLabel();
            });
        });
    }

    /* ============================================================
       EXPAND ALL / COLLAPSE ALL (#4)
    ============================================================ */
    function initGlossaryToggle() {
        const btn = document.getElementById('wiki-gloss-toggle');
        if (!btn) return;

        btn.addEventListener('click', function () {
            const items = document.querySelectorAll('.wiki-gloss-item');
            const allOpen = Array.from(items).every(i => i.classList.contains('open'));

            if (allOpen) {
                items.forEach(i => i.classList.remove('open'));
            } else {
                items.forEach(i => i.classList.add('open'));
            }

            syncToggleLabel();
        });
    }

    function syncToggleLabel() {
        const btn = document.getElementById('wiki-gloss-toggle');
        if (!btn) return;
        const items = document.querySelectorAll('.wiki-gloss-item');
        const allOpen = Array.from(items).every(i => i.classList.contains('open'));
        const labelSpan = btn.querySelector('span');
        if (labelSpan) {
            labelSpan.textContent = allOpen ? 'Collapse All' : 'Expand All';
        }
        btn.classList.toggle('expanded', allOpen);
    }

    /* ============================================================
       KEYBOARD SHORTCUT: / to focus search (#3)
    ============================================================ */
    function initKeyboardShortcut() {
        document.addEventListener('keydown', function (e) {
            // Don't trigger if user is already typing in an input/textarea
            const tag = document.activeElement.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
            if (e.ctrlKey || e.metaKey || e.altKey) return;

            if (e.key === '/') {
                e.preventDefault();
                var searchInput = document.getElementById('wiki-search');
                if (searchInput) {
                    searchInput.focus();
                    searchInput.select();
                }
            }
        });
    }

    /* ============================================================
       SECTION JUMP NAV with active tracking (#1)
    ============================================================ */
    function initJumpNav() {
        var jumpLinks = document.querySelectorAll('.wiki-jump-link');
        if (!jumpLinks.length) return;

        // Smooth scroll on click
        jumpLinks.forEach(function (link) {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                var targetId = this.getAttribute('data-target');
                var target = document.getElementById(targetId);
                if (target) {
                    var top = target.getBoundingClientRect().top + window.scrollY - 80;
                    window.scrollTo({ top: top, behavior: 'smooth' });
                }
            });
        });

        // Active tracking on scroll
        var sectionIds = Array.from(jumpLinks).map(function (l) {
            return l.getAttribute('data-target');
        });

        window.addEventListener('scroll', function () {
            var scrollTop = window.scrollY + 140;
            var activeId = sectionIds[0];

            for (var i = 0; i < sectionIds.length; i++) {
                var section = document.getElementById(sectionIds[i]);
                if (section) {
                    var sectionTop = section.getBoundingClientRect().top + window.scrollY;
                    if (sectionTop <= scrollTop) {
                        activeId = sectionIds[i];
                    }
                }
            }

            jumpLinks.forEach(function (link) {
                link.classList.toggle('active', link.getAttribute('data-target') === activeId);
            });
        });
    }

    /* ============================================================
       SCROLL TO TOP BUTTON (#5)
    ============================================================ */
    function initScrollToTop() {
        var btn = document.getElementById('wiki-scroll-top');
        if (!btn) return;

        window.addEventListener('scroll', function () {
            btn.classList.toggle('visible', window.scrollY > 400);
        });

        btn.addEventListener('click', function () {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    /* ============================================================
       READING PROGRESS BAR (#7)
    ============================================================ */
    function initProgressBar() {
        var bar = document.getElementById('wiki-progress-bar');
        if (!bar) return;

        window.addEventListener('scroll', function () {
            var scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
            if (scrollHeight <= 0) {
                bar.style.width = '0%';
                return;
            }
            var progress = (window.scrollY / scrollHeight) * 100;
            bar.style.width = Math.min(progress, 100) + '%';
        });
    }

    /* ============================================================
       SECTION ENTRANCE ANIMATIONS (#6)
    ============================================================ */
    function initSectionAnimations() {
        var animateEls = document.querySelectorAll('.wiki-animate');
        if (!animateEls.length) return;

        // Use IntersectionObserver if available
        if ('IntersectionObserver' in window) {
            var observer = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('wiki-visible');
                        observer.unobserve(entry.target);
                    }
                });
            }, {
                threshold: 0.08,
                rootMargin: '0px 0px -40px 0px'
            });

            animateEls.forEach(function (el) {
                observer.observe(el);
            });
        } else {
            // Fallback: show everything immediately
            animateEls.forEach(function (el) {
                el.classList.add('wiki-visible');
            });
        }
    }

    /* ── Expose to router ── */
    window.initSecuritywikiPage = initSecuritywikiPage;

})();
