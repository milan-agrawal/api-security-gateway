/* ============================================================
   API SECURITY GATEWAY - USER SUPPORT PAGE
   Support page bootstrap
   ============================================================ */

function initSupportPage() {
    _supportHydrateContext();
    _supportBindQuickActions();
    _supportBindFormActions();
    _supportLoadOverview();
    _supportLoadTickets();
}

function _supportHydrateContext() {
    var email = localStorage.getItem('userEmail') || 'user@example.com';
    var route = (window.location.hash || '#support').replace('#', '') || 'support';
    var emailInput = document.getElementById('supportContactEmail');
    var routeInput = document.getElementById('supportRoute');
    var contextUser = document.getElementById('supportContextUser');
    var contextRoute = document.getElementById('supportContextRoute');

    if (emailInput && !emailInput.value) emailInput.value = email;
    if (routeInput) routeInput.value = route;
    if (contextUser) contextUser.textContent = email;
    if (contextRoute) contextRoute.textContent = route;

    _supportUpdateSuggestedQueue();
}

function _supportBindQuickActions() {
    document.querySelectorAll('[data-support-category]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var category = btn.getAttribute('data-support-category') || 'general_question';
            var categoryEl = document.getElementById('supportCategory');
            if (categoryEl) categoryEl.value = category;
            _supportApplyCategoryDefaults(category);
            _supportScrollToForm();
        });
    });

    var categoryEl = document.getElementById('supportCategory');
    if (categoryEl) {
        categoryEl.addEventListener('change', function () {
            _supportApplyCategoryDefaults(categoryEl.value);
        });
    }
}

function _supportBindFormActions() {
    var form = document.getElementById('supportTicketForm');
    var resetBtn = document.getElementById('supportResetForm');
    var refreshBtn = document.getElementById('supportRefreshTickets');

    if (form) {
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            _supportSubmitTicket(form);
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener('click', function () {
            if (form) form.reset();
            _supportHydrateContext();
        });
    }

    if (refreshBtn) {
        refreshBtn.addEventListener('click', function () {
            _supportLoadOverview();
            _supportLoadTickets();
        });
    }
}

function _supportApplyCategoryDefaults(category) {
    var subjectEl = document.getElementById('supportSubject');
    var priorityEl = document.getElementById('supportPriority');

    var defaults = {
        api_issue: { subject: 'API access issue', priority: 'medium' },
        account_issue: { subject: 'Account or MFA support needed', priority: 'medium' },
        security_issue: { subject: 'Urgent security concern', priority: 'critical' },
        bug_report: { subject: 'Possible product bug report', priority: 'medium' },
        general_question: { subject: 'General support request', priority: 'low' }
    };

    var selected = defaults[category] || defaults.general_question;
    if (subjectEl && !subjectEl.value.trim()) subjectEl.value = selected.subject;
    if (priorityEl) priorityEl.value = selected.priority;
    _supportUpdateSuggestedQueue();
}

function _supportUpdateSuggestedQueue() {
    var category = ((document.getElementById('supportCategory') || {}).value || 'general_question');
    var queueEl = document.getElementById('supportSuggestedQueue');
    if (!queueEl) return;

    var queueMap = {
        api_issue: 'API Operations',
        account_issue: 'Identity Support',
        security_issue: 'Security Response',
        bug_report: 'Product Engineering',
        general_question: 'General Support'
    };

    queueEl.textContent = queueMap[category] || 'General Support';
}

function _supportScrollToForm() {
    var formCard = document.querySelector('.support-form-card');
    if (formCard) formCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function _supportShowToast(message, type) {
    if (typeof showToast === 'function') {
        showToast(message, type || 'info');
        return;
    }
    window.alert(message);
}

function _supportAuthHeaders() {
    return {
        'Authorization': 'Bearer ' + (localStorage.getItem('token') || ''),
        'Content-Type': 'application/json'
    };
}

async function _supportFetch(path, options) {
    var response = await fetch('http://localhost:8001' + path, options || {});
    if (response.status === 401) {
        localStorage.clear();
        window.location.replace('http://localhost:3000/login.html');
        throw new Error('Session expired');
    }

    var data = {};
    try {
        data = await response.json();
    } catch (e) {}

    if (!response.ok) {
        var detail = _supportNormalizeErrorDetail(data.detail);
        throw new Error(detail || response.statusText || 'Request failed');
    }

    return data;
}

async function _supportSubmitTicket(form) {
    var submitBtn = document.getElementById('supportSubmitBtn');
    if (!form) return;

    var payload = {
        category: (document.getElementById('supportCategory') || {}).value || 'general_question',
        priority: (document.getElementById('supportPriority') || {}).value || 'medium',
        subject: ((document.getElementById('supportSubject') || {}).value || '').trim(),
        description: ((document.getElementById('supportDescription') || {}).value || '').trim(),
        contact_email: ((document.getElementById('supportContactEmail') || {}).value || '').trim(),
        related_route: ((document.getElementById('supportRoute') || {}).value || '').trim() || 'support'
    };

    if (!payload.subject || !payload.description || !payload.contact_email) {
        _supportShowToast('Subject, description, and contact email are required.', 'error');
        return;
    }
    if (payload.subject.length < 5) {
        _supportShowToast('Subject must be at least 5 characters.', 'error');
        return;
    }
    if (payload.description.length < 20) {
        _supportShowToast('Description must be at least 20 characters.', 'error');
        return;
    }

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Submitting...';
    }

    try {
        var result = await _supportFetch('/user/support-tickets', {
            method: 'POST',
            headers: _supportAuthHeaders(),
            body: JSON.stringify(payload)
        });
        _supportShowToast(result.message || 'Support ticket submitted successfully.', 'success');
        form.reset();
        _supportHydrateContext();
        _supportLoadOverview();
        _supportLoadTickets();
    } catch (error) {
        _supportShowToast(error.message || 'Failed to submit support ticket.', 'error');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit Ticket';
        }
    }
}

async function _supportLoadTickets() {
    var listEl = document.getElementById('supportTicketList');
    if (!listEl) return;

    listEl.innerHTML = '<div class="support-ticket-item support-empty-state"><p>Loading your support tickets...</p></div>';

    try {
        var result = await _supportFetch('/user/support-tickets', {
            headers: _supportAuthHeaders()
        });
        var tickets = (result && result.tickets) || [];

        if (!tickets.length) {
            listEl.innerHTML = '<div class="support-ticket-item support-empty-state"><p>Your support tickets will appear here once submitted.</p></div>';
            return;
        }

        listEl.innerHTML = tickets.map(function (ticket) {
            return '' +
                '<div class="support-ticket-item">' +
                    '<div class="ticket-topline">' +
                        '<strong>SUP-' + ticket.id + '</strong>' +
                        '<span class="ticket-status ' + _supportStatusClass(ticket.status) + '">' + _supportStatusLabel(ticket.status) + '</span>' +
                    '</div>' +
                    '<p>' + _supportEscape(ticket.subject) + '</p>' +
                    '<div class="ticket-meta">' + _supportCategoryLabel(ticket.category) + ' | Updated ' + _supportTimeAgo(ticket.updated_at) + '</div>' +
                '</div>';
        }).join('');
    } catch (error) {
        listEl.innerHTML = '<div class="support-ticket-item support-empty-state"><p>Unable to load support tickets right now.</p></div>';
    }
}

async function _supportLoadOverview() {
    try {
        var overview = await _supportFetch('/user/support-tickets/overview', {
            headers: _supportAuthHeaders()
        });
        _supportRenderOverview(overview || {});
    } catch (error) {
        _supportRenderOverview({
            total_tickets: 0,
            open_tickets: 0,
            critical_open_tickets: 0,
            security_tickets: 0,
            latest_ticket_updated_at: null,
            smtp_ready: false
        });
    }
}

function _supportRenderOverview(overview) {
    var openEl = document.getElementById('supportMetricOpen');
    var criticalEl = document.getElementById('supportMetricCritical');
    var trackedEl = document.getElementById('supportMetricTracked');
    var deliveryEl = document.getElementById('supportMetricDelivery');
    var footerEl = document.getElementById('supportSignalFooter');
    var headLabelEl = document.getElementById('supportSignalHeadLabel');
    var badgePrimaryEl = document.getElementById('supportHeroBadgePrimary');
    var badgeSecondaryEl = document.getElementById('supportHeroBadgeSecondary');
    var badgeTertiaryEl = document.getElementById('supportHeroBadgeTertiary');
    var formBadgeEl = document.getElementById('supportFormStatusBadge');

    var openCount = Number(overview.open_tickets || 0);
    var criticalCount = Number(overview.critical_open_tickets || 0);
    var totalCount = Number(overview.total_tickets || 0);
    var securityCount = Number(overview.security_tickets || 0);
    var smtpReady = !!overview.smtp_ready;

    if (openEl) openEl.textContent = String(openCount);
    if (criticalEl) criticalEl.textContent = String(criticalCount);
    if (trackedEl) trackedEl.textContent = String(totalCount);
    if (deliveryEl) deliveryEl.textContent = smtpReady ? 'Ready' : 'Check';
    if (headLabelEl) headLabelEl.textContent = securityCount > 0 ? 'Support Overview | Security Watch Active' : 'Support Overview';

    if (badgePrimaryEl) {
        badgePrimaryEl.className = 'support-pill ' + (openCount > 0 ? 'online' : 'neutral');
        badgePrimaryEl.textContent = openCount > 0 ? (openCount + ' active support request' + (openCount === 1 ? '' : 's')) : 'No open tickets right now';
    }
    if (badgeSecondaryEl) {
        badgeSecondaryEl.className = 'support-pill ' + (securityCount > 0 ? 'danger' : 'neutral');
        badgeSecondaryEl.textContent = securityCount > 0 ? (securityCount + ' security-related ticket' + (securityCount === 1 ? '' : 's') + ' tracked') : 'No security escalation on file';
    }
    if (badgeTertiaryEl) {
        badgeTertiaryEl.className = 'support-pill ' + (smtpReady ? 'online' : 'danger');
        badgeTertiaryEl.textContent = smtpReady ? 'Delivery channel connected' : 'Delivery channel needs attention';
    }
    if (formBadgeEl) {
        formBadgeEl.textContent = smtpReady ? 'Live Form' : 'Save Only';
    }

    if (footerEl) {
        if (overview.latest_ticket_updated_at) {
            footerEl.textContent = 'Latest support activity updated ' + _supportTimeAgo(overview.latest_ticket_updated_at) + '. Security requests stay prioritized.';
        } else {
            footerEl.textContent = 'No previous tickets yet. Your first request will appear here immediately after submission.';
        }
    }
}

function _supportCategoryLabel(category) {
    var map = {
        api_issue: 'API Access Issue',
        account_issue: 'Account & MFA Help',
        security_issue: 'Security Emergency',
        bug_report: 'Bug Report',
        general_question: 'General Question'
    };
    return map[category] || 'Support';
}

function _supportStatusClass(status) {
    status = (status || 'open').toLowerCase();
    if (status === 'waiting_for_user') return 'waiting';
    if (status === 'resolved') return 'resolved';
    return 'open';
}

function _supportStatusLabel(status) {
    status = (status || 'open').toLowerCase();
    if (status === 'waiting_for_user') return 'Waiting For User';
    if (status === 'resolved') return 'Resolved';
    return 'Open';
}

function _supportTimeAgo(iso) {
    if (!iso) return 'just now';
    var ts = new Date(/Z$|[+-]\d{2}:\d{2}$/.test(iso) ? iso : (iso + 'Z'));
    if (isNaN(ts.getTime())) return 'just now';
    var diff = Math.floor((Date.now() - ts.getTime()) / 1000);
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + ' min ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
}

function _supportEscape(value) {
    var div = document.createElement('div');
    div.textContent = value || '';
    return div.innerHTML;
}

function _supportNormalizeErrorDetail(detail) {
    if (!detail) return '';

    if (typeof detail === 'string') return detail;

    if (Array.isArray(detail)) {
        return detail.map(function (item) {
            return _supportNormalizeErrorDetail(item);
        }).filter(Boolean).join(', ');
    }

    if (typeof detail === 'object') {
        if (detail.msg) return detail.msg;
        if (detail.detail) return _supportNormalizeErrorDetail(detail.detail);
        if (detail.message) return detail.message;
        return JSON.stringify(detail);
    }

    return String(detail);
}

window.initSupportPage = initSupportPage;
