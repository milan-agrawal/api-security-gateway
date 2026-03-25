const PRIVACY_API_BASE = 'http://localhost:8001';
const MIN_TRANSLATE_UI_MS = 1200;
const TRANSLATE_RETRY_DELAY_MS = 1800;

const PRIVACY_BASE_CONTENT = {
    meta: {
        eyebrow: 'Privacy & Terms',
        localeLabel: 'Language / Locale',
        downloadPdf: 'Download PDF',
        heroTitle: 'Clear, readable policies for your API workspace.',
        heroDescription: 'This policy covers how we handle account data, security telemetry, and support communications. We collect only what is required to deliver and secure the platform.',
        effective: 'Effective date',
        reviewed: 'Last reviewed',
        applies: 'Applies to',
        appliesValue: 'User panel',
        toc: 'On this page',
        contactPrivacyLabel: 'Privacy inbox',
        contactPrivacyValue: 'privacy@apigateway.local',
        contactSecurityLabel: 'Security desk',
        contactSecurityValue: 'security@apigateway.local'
    },
    toc: {
        collect: 'What we collect',
        avoid: 'What we do not collect',
        use: 'How we use data',
        rights: 'Your rights',
        security: 'Security safeguards',
        cookies: 'Cookies & storage',
        thirdParty: 'Third-party services',
        contact: 'Contact',
        changelog: 'Change log'
    },
    sections: {
        collect: {
            title: 'What we collect',
            description: 'We collect account details and security events that help operate the gateway safely.',
            coreTitle: 'Core account data',
            coreList: [
                'Name, email, role, and profile settings.',
                'Authentication state, MFA status, and session metadata.',
                'API keys, permissions, and key lifecycle events.'
            ],
            opsTitle: 'Operational telemetry',
            opsList: [
                'Security events, audit logs, and system health signals.',
                'Support tickets, conversations, and attachments you submit.',
                'Routing metadata for traffic inspection and rate limiting.'
            ]
        },
        avoid: {
            title: 'What we do not collect',
            description: 'We avoid collecting anything unrelated to product security or reliability.',
            list: [
                'We do not collect or sell advertising profiles.',
                'We do not read payload data beyond what is required for threat analysis.',
                'We do not store payment data in the user panel.'
            ]
        },
        use: {
            title: 'How we use data',
            description: 'Every data point is used to keep your API operations safe and reliable.',
            flow: [
                { title: 'Service delivery', text: 'Account and key data power authentication, API access, and usage controls.' },
                { title: 'Security and compliance', text: 'Security logs and audit trails support investigation, incident response, and compliance.' },
                { title: 'Support', text: 'Support requests and attachments are used to resolve issues you report.' }
            ]
        },
        rights: {
            title: 'Your rights and controls',
            description: 'Manage account data directly from the user panel or contact our team.',
            list: [
                'Export your data from the Data Export page.',
                'Update profile, MFA, and email settings at any time.',
                'Request deletion of your account via the Profile page.'
            ],
            note: 'For high-impact changes like email updates, we require verification before the change is active.'
        },
        security: {
            title: 'Security safeguards',
            description: 'We apply layered controls across infrastructure, storage, and access.',
            list: [
                'Encryption in transit and access-controlled storage.',
                'Audit logging for key security events.',
                'Role-based access controls for operational tooling.'
            ]
        },
        cookies: {
            title: 'Cookies and storage',
            description: 'We use cookies and local storage for authenticated sessions and UI preferences.',
            body: 'We use cookies and local storage for authentication sessions and UI preferences. No advertising cookies are used in the user panel.'
        },
        thirdParty: {
            title: 'Third-party services',
            description: 'Only trusted partners are used for security, delivery, and monitoring.',
            list: [
                'Email delivery providers for verification and alerts.',
                'Infrastructure services required to run the gateway.',
                'Monitoring tools for uptime and incident response.'
            ]
        },
        contact: {
            title: 'Contact',
            description: 'Reach out to our compliance or security team for questions.',
            body: 'Questions about privacy or terms can be sent to our compliance team.'
        },
        changelog: {
            title: 'Change log',
            description: 'We track policy updates for transparency.',
            body: 'Initial privacy and terms publication for the user panel.'
        }
    }
};

const PRIVACY_LANGUAGE_OPTIONS = [
    'af', 'am', 'ar', 'az', 'be', 'bg', 'bn', 'bs', 'ca', 'cs', 'cy', 'da',
    'de', 'el', 'en', 'es', 'et', 'eu', 'fa', 'fi', 'fil', 'fr', 'ga', 'gl',
    'gu', 'he', 'hi', 'hr', 'hu', 'hy', 'id', 'is', 'it', 'ja', 'ka', 'kk',
    'km', 'kn', 'ko', 'ky', 'lo', 'lt', 'lv', 'mk', 'ml', 'mn', 'mr', 'ms',
    'mt', 'my', 'ne', 'nl', 'no', 'or', 'pa', 'pl', 'ps', 'pt', 'ro', 'ru',
    'si', 'sk', 'sl', 'sq', 'sr', 'sv', 'sw', 'ta', 'te', 'th', 'tr', 'uk',
    'ur', 'uz', 'vi', 'zh', 'zu'
];

const privacyTranslationCache = {};

function initPrivacyPage() {
    const localeSelect = document.getElementById('privacyLocale');
    const downloadBtn = document.getElementById('privacyDownloadPdf');
    const dateNodes = document.querySelectorAll('[data-privacy-date]');
    const tocLinks = document.querySelectorAll('.privacy-toc-link');
    const pageRoot = document.getElementById('privacyPageRoot');
    const progressEl = document.getElementById('privacyTranslateProgress');

    if (!localeSelect || !downloadBtn || dateNodes.length === 0) {
        return;
    }

    populateLocaleSelect(localeSelect);
    const savedLocale = localStorage.getItem('privacyLocale') || 'en';
    localeSelect.value = PRIVACY_LANGUAGE_OPTIONS.includes(savedLocale) ? savedLocale : 'en';

    renderPrivacyContent(PRIVACY_BASE_CONTENT);
    applyPrivacyLocale(localeSelect.value, dateNodes);
    initPrivacyToc(tocLinks);
    translateAndRender(localeSelect.value, dateNodes, pageRoot, progressEl);

    localeSelect.addEventListener('change', async () => {
        const locale = localeSelect.value;
        localStorage.setItem('privacyLocale', locale);
        renderPrivacyContent(PRIVACY_BASE_CONTENT);
        applyPrivacyLocale(locale, dateNodes);
        await translateAndRender(locale, dateNodes, pageRoot, progressEl);
    });

    downloadBtn.addEventListener('click', () => {
        window.print();
    });
}

async function translateAndRender(locale, dateNodes, pageRoot, progressEl) {
    if (locale === 'en') {
        applyPrivacyLocale(locale, dateNodes);
        setTranslateProgress(progressEl, '');
        return;
    }

    if (privacyTranslationCache[locale]) {
        renderPrivacyContent(privacyTranslationCache[locale]);
        applyPrivacyLocale(locale, dateNodes);
        setTranslateProgress(progressEl, '');
        return;
    }

    const strings = collectStrings(PRIVACY_BASE_CONTENT);
    const token = localStorage.getItem('token') || localStorage.getItem('authToken');
    if (!token) {
        setTranslateProgress(progressEl, '');
        if (typeof showToast === 'function') {
            showToast('Session token missing. Please login again.', 'error');
        }
        return;
    }

    const startedAt = Date.now();
    try {
        setTranslateProgress(progressEl, 'Translating...');
        setTranslatingState(pageRoot, true);
        while (true) {
            if (!pageRoot || !pageRoot.isConnected || !window.location.hash.includes('privacy')) {
                return;
            }

            try {
                const response = await fetch(`${PRIVACY_API_BASE}/user/privacy/translate`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${token}`
                    },
                    body: JSON.stringify({ target_locale: locale, texts: strings })
                });

                if (!response.ok) {
                    await waitMs(TRANSLATE_RETRY_DELAY_MS);
                    continue;
                }

                const payload = await response.json();
                if (!payload || !Array.isArray(payload.texts) || payload.texts.length !== strings.length) {
                    await waitMs(TRANSLATE_RETRY_DELAY_MS);
                    continue;
                }

                if (!payload.provider_available) {
                    await waitMs(TRANSLATE_RETRY_DELAY_MS);
                    continue;
                }

                const translatedTree = applyTranslatedStrings(PRIVACY_BASE_CONTENT, payload.texts);
                privacyTranslationCache[locale] = translatedTree;
                renderPrivacyContent(translatedTree);
                applyPrivacyLocale(locale, dateNodes);
                break;
            } catch (_) {
                await waitMs(TRANSLATE_RETRY_DELAY_MS);
            }
        }
    } catch (_) {
        renderPrivacyContent(PRIVACY_BASE_CONTENT);
        applyPrivacyLocale(locale, dateNodes);
        if (typeof showToast === 'function') {
            showToast('Translation failed. Please try another language.', 'error');
        }
    } finally {
        const elapsed = Date.now() - startedAt;
        if (elapsed < MIN_TRANSLATE_UI_MS) {
            await waitMs(MIN_TRANSLATE_UI_MS - elapsed);
        }
        setTranslatingState(pageRoot, false);
        setTranslateProgress(progressEl, '');
    }
}

function renderPrivacyContent(content) {
    setText('privacyEyebrow', content.meta.eyebrow);
    setText('privacyLocaleLabel', content.meta.localeLabel);
    setText('privacyDownloadPdf', content.meta.downloadPdf);
    setText('privacyHeroTitle', content.meta.heroTitle);
    setText('privacyHeroDescription', content.meta.heroDescription);
    setText('privacyEffectiveLabel', content.meta.effective);
    setText('privacyReviewedLabel', content.meta.reviewed);
    setText('privacyAppliesLabel', content.meta.applies);
    setText('privacyAppliesValue', content.meta.appliesValue);
    setText('privacyTocTitle', content.meta.toc);
    setText('contactPrivacyLabel', content.meta.contactPrivacyLabel);
    setText('contactPrivacyValue', content.meta.contactPrivacyValue);
    setText('contactSecurityLabel', content.meta.contactSecurityLabel);
    setText('contactSecurityValue', content.meta.contactSecurityValue);

    setText('tocCollect', content.toc.collect);
    setText('tocAvoid', content.toc.avoid);
    setText('tocUse', content.toc.use);
    setText('tocRights', content.toc.rights);
    setText('tocSecurity', content.toc.security);
    setText('tocCookies', content.toc.cookies);
    setText('tocThirdParty', content.toc.thirdParty);
    setText('tocContact', content.toc.contact);
    setText('tocChangelog', content.toc.changelog);

    setText('sectionCollectTitle', content.sections.collect.title);
    setText('sectionCollectDesc', content.sections.collect.description);
    setText('collectCoreTitle', content.sections.collect.coreTitle);
    fillList('collectCoreList', content.sections.collect.coreList);
    setText('collectOpsTitle', content.sections.collect.opsTitle);
    fillList('collectOpsList', content.sections.collect.opsList);

    setText('sectionAvoidTitle', content.sections.avoid.title);
    setText('sectionAvoidDesc', content.sections.avoid.description);
    fillList('avoidList', content.sections.avoid.list);

    setText('sectionUseTitle', content.sections.use.title);
    setText('sectionUseDesc', content.sections.use.description);
    fillFlow('useFlow', content.sections.use.flow);

    setText('sectionRightsTitle', content.sections.rights.title);
    setText('sectionRightsDesc', content.sections.rights.description);
    fillList('rightsList', content.sections.rights.list);
    setText('rightsNote', content.sections.rights.note);

    setText('sectionSecurityTitle', content.sections.security.title);
    setText('sectionSecurityDesc', content.sections.security.description);
    fillList('securityList', content.sections.security.list);

    setText('sectionCookiesTitle', content.sections.cookies.title);
    setText('sectionCookiesDesc', content.sections.cookies.description);
    setText('cookiesBody', content.sections.cookies.body);

    setText('sectionThirdPartyTitle', content.sections.thirdParty.title);
    setText('sectionThirdPartyDesc', content.sections.thirdParty.description);
    fillList('thirdPartyList', content.sections.thirdParty.list);

    setText('sectionContactTitle', content.sections.contact.title);
    setText('sectionContactDesc', content.sections.contact.description);
    setText('contactBody', content.sections.contact.body);

    setText('sectionChangelogTitle', content.sections.changelog.title);
    setText('sectionChangelogDesc', content.sections.changelog.description);
    setText('changeLogText', content.sections.changelog.body);
}

function collectStrings(node) {
    const out = [];
    walkCollect(node, out);
    return out;
}

function walkCollect(node, out) {
    if (typeof node === 'string') {
        out.push(node);
        return;
    }
    if (Array.isArray(node)) {
        node.forEach((item) => walkCollect(item, out));
        return;
    }
    if (node && typeof node === 'object') {
        Object.keys(node).forEach((key) => walkCollect(node[key], out));
    }
}

function applyTranslatedStrings(template, translatedStrings) {
    const cursor = { index: 0 };
    return walkApply(template, translatedStrings, cursor);
}

function walkApply(template, translatedStrings, cursor) {
    if (typeof template === 'string') {
        const translated = translatedStrings[cursor.index];
        cursor.index += 1;
        return typeof translated === 'string' ? translated : template;
    }
    if (Array.isArray(template)) {
        return template.map((item) => walkApply(item, translatedStrings, cursor));
    }
    if (template && typeof template === 'object') {
        const cloned = {};
        Object.keys(template).forEach((key) => {
            cloned[key] = walkApply(template[key], translatedStrings, cursor);
        });
        return cloned;
    }
    return template;
}

function applyPrivacyLocale(locale, nodes) {
    const formatter = new Intl.DateTimeFormat(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });

    nodes.forEach((node) => {
        const rawDate = node.getAttribute('data-privacy-date');
        if (!rawDate) {
            return;
        }
        const parsed = new Date(rawDate);
        if (Number.isNaN(parsed.getTime())) {
            return;
        }
        node.textContent = formatter.format(parsed);
    });

    document.documentElement.lang = locale;
}

function populateLocaleSelect(selectEl) {
    const display = typeof Intl.DisplayNames === 'function'
        ? new Intl.DisplayNames(['en'], { type: 'language' })
        : null;

    const fragment = document.createDocumentFragment();
    PRIVACY_LANGUAGE_OPTIONS.forEach((locale) => {
        const option = document.createElement('option');
        option.value = locale;
        option.textContent = display ? `${display.of(locale) || locale} (${locale})` : locale;
        fragment.appendChild(option);
    });

    selectEl.innerHTML = '';
    selectEl.appendChild(fragment);
}

function initPrivacyToc(tocLinks) {
    if (!tocLinks.length) {
        return;
    }

    const sections = Array.from(tocLinks)
        .map((link) => document.getElementById(link.dataset.target))
        .filter(Boolean);

    tocLinks.forEach((link) => {
        link.addEventListener('click', () => {
            const targetId = link.dataset.target;
            const target = document.getElementById(targetId);
            if (!target) {
                return;
            }
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            setActivePrivacyTocLink(tocLinks, targetId);
        });
    });

    setActivePrivacyTocLink(tocLinks, tocLinks[0].dataset.target);

    const observer = new IntersectionObserver((entries) => {
        const visible = entries
            .filter((entry) => entry.isIntersecting)
            .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible?.target?.id) {
            setActivePrivacyTocLink(tocLinks, visible.target.id);
        }
    }, {
        rootMargin: '-20% 0px -55% 0px',
        threshold: [0.2, 0.4, 0.6]
    });

    sections.forEach((section) => observer.observe(section));
}

function setActivePrivacyTocLink(tocLinks, targetId) {
    tocLinks.forEach((link) => {
        link.classList.toggle('is-active', link.dataset.target === targetId);
    });
}

function setText(id, text) {
    const node = document.getElementById(id);
    if (!node) {
        return;
    }
    node.textContent = text;
}

function fillList(id, items) {
    const root = document.getElementById(id);
    if (!root) {
        return;
    }
    root.innerHTML = '';
    items.forEach((item) => {
        const li = document.createElement('li');
        li.textContent = item;
        root.appendChild(li);
    });
}

function fillFlow(id, items) {
    const root = document.getElementById(id);
    if (!root) {
        return;
    }
    root.innerHTML = '';
    items.forEach((item) => {
        const node = document.createElement('div');
        node.className = 'privacy-flow-item';
        const strong = document.createElement('strong');
        strong.textContent = item.title;
        const text = document.createElement('span');
        text.textContent = item.text;
        node.appendChild(strong);
        node.appendChild(text);
        root.appendChild(node);
    });
}

function setTranslatingState(root, isLoading) {
    if (!root) return;
    root.classList.toggle('is-translating', Boolean(isLoading));
}

function setTranslateProgress(node, text) {
    if (!node) return;
    node.textContent = text || '';
}

function waitMs(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

window.initPrivacyPage = initPrivacyPage;
