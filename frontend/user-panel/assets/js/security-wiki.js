/* ============================================================
   SECURITY WIKI — Interactive Behaviour
   - Live search across cards, glossary items, practice cards
   - Category filter pills (mutually exclusive with search)
   - Glossary accordion (one open at a time)
   ============================================================ */

(function () {

    /* ── Entry point called by router ── */
    function initSecuritywikiPage() {
        initWikiSearch();
        initWikiFilters();
        initWikiGlossary();
    }

    /* ============================================================
       SEARCH
       Searches [data-search] attribute on cards / gloss items /
       practice cards. The log section has a hidden anchor element
       with keywords so the whole section surfaces on relevant terms.
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
                // Hidden anchor divs stay hidden; only real UI elements toggle
                if (el.style.display === 'none' && el.getAttribute('aria-hidden') === 'true') {
                    return; // keep the hidden keyword anchor hidden always
                }
                el.style.display = matches ? '' : 'none';
                if (matches) totalVisible++;
            });

            // Hide sections where no visible items remain (ignore hidden keyword anchors)
            document.querySelectorAll('.wiki-section').forEach(section => {
                const items = Array.from(section.querySelectorAll('[data-search]'))
                    .filter(el => el.getAttribute('aria-hidden') !== 'true');
                const hasVisible = items.some(el => el.style.display !== 'none');
                section.style.display = hasVisible ? '' : 'none';
            });

            // Update count badge
            if (countEl) {
                countEl.textContent = totalVisible + ' result' + (totalVisible !== 1 ? 's' : '');
                countEl.classList.add('visible');
            }

            // No results message
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
                // Reset search input when filter is picked
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
       GLOSSARY ACCORDION
       One item open at a time.
    ============================================================ */
    function initWikiGlossary() {
        document.querySelectorAll('.wiki-gloss-trigger').forEach(trigger => {
            trigger.addEventListener('click', function () {
                const item   = this.closest('.wiki-gloss-item');
                const isOpen = item.classList.contains('open');

                // Close all open items
                document.querySelectorAll('.wiki-gloss-item.open')
                    .forEach(i => i.classList.remove('open'));

                // Open this one if it was closed
                if (!isOpen) item.classList.add('open');
            });
        });
    }

    /* ── Expose to router ── */
    window.initSecuritywikiPage = initSecuritywikiPage;

})();
