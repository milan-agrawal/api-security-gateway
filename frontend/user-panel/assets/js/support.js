/* ============================================================
   API SECURITY GATEWAY - USER SUPPORT PAGE
   Support page bootstrap
   ============================================================ */

var supportSelectedTicketId = null;
var supportSearchDebounceTimer = null;
var SUPPORT_SLA_MINUTES = {
    critical: 30,
    high: 120,
    medium: 480,
    low: 1440
};

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
    _supportRenderKbSuggestions();
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
    var replyBtn = document.getElementById('supportReplyBtn');
    var replyInput = document.getElementById('supportReplyInput');
    var searchInput = document.getElementById('supportTicketSearch');
    var searchClearBtn = document.getElementById('supportTicketSearchClear');
    var attachmentUploadBtn = document.getElementById('supportAttachmentUploadBtn');
    var categoryInput = document.getElementById('supportCategory');
    var subjectInput = document.getElementById('supportSubject');
    var descriptionInput = document.getElementById('supportDescription');

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

    if (searchInput) {
        searchInput.addEventListener('input', function () {
            window.clearTimeout(supportSearchDebounceTimer);
            supportSearchDebounceTimer = window.setTimeout(function () {
                _supportLoadTickets();
            }, 220);
        });
        searchInput.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                window.clearTimeout(supportSearchDebounceTimer);
                _supportLoadTickets();
            }
        });
    }

    if (searchClearBtn) {
        searchClearBtn.addEventListener('click', function () {
            if (searchInput) searchInput.value = '';
            _supportLoadTickets();
        });
    }

    if (replyBtn) {
        replyBtn.addEventListener('click', function () {
            _supportSendReply();
        });
    }
    if (replyInput) {
        replyInput.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                _supportSendReply();
            }
        });
    }

    if (attachmentUploadBtn) {
        attachmentUploadBtn.addEventListener('click', function () {
            _supportUploadAttachment();
        });
    }

    [categoryInput, subjectInput, descriptionInput].forEach(function (el) {
        if (!el) return;
        el.addEventListener('input', _supportRenderKbSuggestions);
        el.addEventListener('change', _supportRenderKbSuggestions);
    });
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
    _supportRenderKbSuggestions();
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
        var searchQuery = (document.getElementById('supportTicketSearch') || {}).value || '';
        var query = searchQuery.trim() ? ('?q=' + encodeURIComponent(searchQuery.trim())) : '';
        var result = await _supportFetch('/user/support-tickets' + query, {
            headers: _supportAuthHeaders()
        });
        var tickets = (result && result.tickets) || [];

        if (!tickets.length) {
            supportSelectedTicketId = null;
            _supportClearTicketDetail();
            listEl.innerHTML = '<div class="support-ticket-item support-empty-state"><p>' + _supportEscape(searchQuery.trim() ? 'No support tickets matched your search.' : 'Your support tickets will appear here once submitted.') + '</p></div>';
            return;
        }

        if (!supportSelectedTicketId) supportSelectedTicketId = tickets[0].id;
        if (!tickets.some(function (ticket) { return ticket.id === supportSelectedTicketId; })) {
            supportSelectedTicketId = tickets[0].id;
        }

        listEl.innerHTML = tickets.map(function (ticket) {
            var isSelected = ticket.id === supportSelectedTicketId;
            var attachmentLabel = ticket.attachment_count > 0 ? (' · ' + ticket.attachment_count + ' attachment' + (ticket.attachment_count === 1 ? '' : 's')) : '';
            var sla = _supportTicketSla(ticket);
            return '' +
                '<div class="support-ticket-item' + (isSelected ? ' selected' : '') + '" data-support-ticket-card="' + ticket.id + '">' +
                    '<div class="ticket-topline">' +
                        '<strong>SUP-' + ticket.id + '</strong>' +
                        '<div class="ticket-topline-badges">' +
                            '<span class="ticket-status ' + _supportStatusClass(ticket.status) + '">' + _supportStatusLabel(ticket.status) + '</span>' +
                            '<span class="support-sla-badge ' + sla.className + '">' + _supportEscape(sla.shortLabel) + '</span>' +
                        '</div>' +
                    '</div>' +
                    '<p>' + _supportEscape(ticket.subject) + '</p>' +
                    '<div class="ticket-meta">' + _supportCategoryLabel(ticket.category) + ' | Updated ' + _supportTimeAgo(ticket.updated_at) + attachmentLabel + '</div>' +
                '</div>';
        }).join('');
        _supportBindTicketCards(tickets);
        _supportRenderSelectedTicket(tickets);
    } catch (error) {
        _supportClearTicketDetail();
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
            smtp_ready: false,
            workflow_counts: {
                open: 0,
                in_review: 0,
                waiting_for_user: 0,
                escalated: 0,
                resolved: 0,
                closed: 0
            }
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
    var workflowOpenEl = document.getElementById('supportWorkflowOpen');
    var workflowReviewEl = document.getElementById('supportWorkflowReview');
    var workflowWaitingEl = document.getElementById('supportWorkflowWaiting');
    var workflowEscalatedEl = document.getElementById('supportWorkflowEscalated');
    var workflowResolvedEl = document.getElementById('supportWorkflowResolved');
    var workflowClosedEl = document.getElementById('supportWorkflowClosed');
    var workflowNoteEl = document.getElementById('supportWorkflowNote');

    var openCount = Number(overview.open_tickets || 0);
    var criticalCount = Number(overview.critical_open_tickets || 0);
    var totalCount = Number(overview.total_tickets || 0);
    var securityCount = Number(overview.security_tickets || 0);
    var smtpReady = !!overview.smtp_ready;
    var workflow = overview.workflow_counts || {};
    var workflowOpen = Number(workflow.open || 0);
    var workflowReview = Number(workflow.in_review || 0);
    var workflowWaiting = Number(workflow.waiting_for_user || 0);
    var workflowEscalated = Number(workflow.escalated || 0);
    var workflowResolved = Number(workflow.resolved || 0);
    var workflowClosed = Number(workflow.closed || 0);

    if (openEl) openEl.textContent = String(openCount);
    if (criticalEl) criticalEl.textContent = String(criticalCount);
    if (trackedEl) trackedEl.textContent = String(totalCount);
    if (deliveryEl) deliveryEl.textContent = smtpReady ? 'Ready' : 'Check';
    if (workflowOpenEl) workflowOpenEl.textContent = String(workflowOpen);
    if (workflowReviewEl) workflowReviewEl.textContent = String(workflowReview);
    if (workflowWaitingEl) workflowWaitingEl.textContent = String(workflowWaiting);
    if (workflowEscalatedEl) workflowEscalatedEl.textContent = String(workflowEscalated);
    if (workflowResolvedEl) workflowResolvedEl.textContent = String(workflowResolved);
    if (workflowClosedEl) workflowClosedEl.textContent = String(workflowClosed);
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
        formBadgeEl.textContent = workflowEscalated > 0 ? 'Priority Queue Active' : (smtpReady ? 'Live Form' : 'Save Only');
    }

    if (footerEl) {
        if (overview.latest_ticket_updated_at) {
            footerEl.textContent = 'Latest support activity updated ' + _supportTimeAgo(overview.latest_ticket_updated_at) + '. Security requests stay prioritized.';
        } else {
            footerEl.textContent = 'No previous tickets yet. Your first request will appear here immediately after submission.';
        }
    }

    if (workflowNoteEl) {
        if (workflowEscalated > 0) {
            workflowNoteEl.textContent = workflowEscalated + ' ticket' + (workflowEscalated === 1 ? ' is' : 's are') + ' currently in escalation. Security and critical requests are routed there first.';
        } else if (workflowWaiting > 0) {
            workflowNoteEl.textContent = workflowWaiting + ' ticket' + (workflowWaiting === 1 ? ' is' : 's are') + ' waiting for your reply before support can continue.';
        } else if (workflowReview > 0) {
            workflowNoteEl.textContent = workflowReview + ' ticket' + (workflowReview === 1 ? ' is' : 's are') + ' actively under review by the support workflow.';
        } else {
            workflowNoteEl.textContent = 'New tickets open immediately. Security or critical requests are routed into escalation first.';
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
    if (status === 'in_review') return 'review';
    if (status === 'waiting_for_user') return 'waiting';
    if (status === 'escalated') return 'escalated';
    if (status === 'resolved') return 'resolved';
    if (status === 'closed') return 'closed';
    return 'open';
}

function _supportStatusLabel(status) {
    status = (status || 'open').toLowerCase();
    if (status === 'in_review') return 'In Review';
    if (status === 'waiting_for_user') return 'Waiting For User';
    if (status === 'escalated') return 'Escalated';
    if (status === 'resolved') return 'Resolved';
    if (status === 'closed') return 'Closed';
    return 'Open';
}

function _supportTimeAgo(iso) {
    return _supportMumbaiDateTime(iso);
}

function _supportChatTime(iso) {
    if (!iso) return 'Unknown time';
    var hasZone = /Z$|[+-]\d{2}:\d{2}$/.test(iso);
    var ts = new Date(hasZone ? iso : (iso + '+05:30'));
    if (isNaN(ts.getTime())) return 'Unknown time';
    return ts.toLocaleTimeString('en-IN', {
        hour: 'numeric',
        minute: '2-digit',
        timeZone: 'Asia/Kolkata'
    });
}

function _supportMumbaiDateTime(iso) {
    if (!iso) return 'Unknown time';
    var hasZone = /Z$|[+-]\d{2}:\d{2}$/.test(iso);
    var ts = new Date(hasZone ? iso : (iso + '+05:30'));
    if (isNaN(ts.getTime())) return 'Unknown time';
    return ts.toLocaleString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
        timeZone: 'Asia/Kolkata'
    }) + ' IST';
}

function _supportEscape(value) {
    var div = document.createElement('div');
    div.textContent = value || '';
    return div.innerHTML;
}

function _supportThreadRoleLabel(authorType) {
    return (authorType || '').toLowerCase() === 'admin' ? 'Admin' : 'User';
}

function _supportBindTicketCards(tickets) {
    document.querySelectorAll('[data-support-ticket-card]').forEach(function (card) {
        if (card.dataset.bound) return;
        card.dataset.bound = 'true';
        card.addEventListener('click', function () {
            var ticketId = Number(card.getAttribute('data-support-ticket-card'));
            supportSelectedTicketId = ticketId;
            document.querySelectorAll('[data-support-ticket-card]').forEach(function (node) {
                node.classList.toggle('selected', Number(node.getAttribute('data-support-ticket-card')) === ticketId);
            });
            _supportRenderSelectedTicket(tickets);
        });
    });
}

function _supportRenderSelectedTicket(tickets) {
    var ticket = (tickets || []).find(function (item) { return item.id === supportSelectedTicketId; });
    var emptyEl = document.getElementById('supportTicketDetailEmpty');
    var panelEl = document.getElementById('supportTicketDetailPanel');

    if (!ticket) {
        _supportClearTicketDetail();
        return;
    }

    if (emptyEl) emptyEl.style.display = 'none';
    if (panelEl) panelEl.style.display = '';

    _supportSetText('supportDetailId', 'SUP-' + ticket.id);
    _supportSetText('supportDetailSubject', ticket.subject);
    _supportSetText('supportDetailCategory', _supportCategoryLabel(ticket.category));
    _supportSetText('supportDetailPriority', _supportLabel(ticket.priority));
    _supportSetText('supportDetailRoute', ticket.related_route || 'support');
    _supportSetText('supportDetailUpdated', _supportTimeAgo(ticket.updated_at));
    _supportSetText('supportDetailDescription', ticket.description);
    var sla = _supportTicketSla(ticket);
    _supportSetText('supportDetailSlaStatus', sla.label);
    _supportSetText('supportDetailSlaTarget', sla.target);

    var statusEl = document.getElementById('supportDetailStatus');
    if (statusEl) {
        statusEl.className = 'ticket-status ' + _supportStatusClass(ticket.status);
        statusEl.textContent = _supportStatusLabel(ticket.status);
    }

    _supportLoadTicketDetail(ticket.id);
}

async function _supportLoadTicketDetail(ticketId) {
    var listEl = document.getElementById('supportThreadList');
    var countEl = document.getElementById('supportThreadCount');
    var attachmentListEl = document.getElementById('supportAttachmentList');
    var attachmentCountEl = document.getElementById('supportAttachmentCount');
    if (!ticketId || !listEl) return;

    listEl.innerHTML = '<div class="support-thread-empty">Loading conversation...</div>';
    if (attachmentListEl) attachmentListEl.innerHTML = '<div class="support-thread-empty">Loading attachments...</div>';

    try {
        var result = await _supportFetch('/user/support-tickets/' + ticketId, {
            headers: _supportAuthHeaders()
        });
        var ticket = result.ticket || {};
        var messages = result.messages || [];
        var attachments = result.attachments || [];

        _supportSetText('supportDetailPriority', _supportLabel(ticket.priority || 'medium'));
        if (countEl) countEl.textContent = messages.length + ' message' + (messages.length === 1 ? '' : 's');
        if (attachmentCountEl) attachmentCountEl.textContent = attachments.length + ' file' + (attachments.length === 1 ? '' : 's');

        if (!messages.length) {
            listEl.innerHTML = '<div class="support-thread-empty">No replies yet.</div>';
        } else {
            listEl.innerHTML = messages.map(function (message) {
                var roleLabel = _supportThreadRoleLabel(message.author_type);
                var authorInitial = _supportEscape(roleLabel.charAt(0).toUpperCase());
                return '' +
                    '<div class="support-thread-row ' + (message.author_type === 'user' ? 'user' : 'admin') + '">' +
                        '<div class="support-thread-avatar">' + authorInitial + '</div>' +
                        '<div class="support-thread-message ' + (message.author_type === 'admin' ? 'admin' : 'user') + '">' +
                            '<div class="support-thread-meta">' +
                                '<strong>' + _supportEscape(roleLabel) + '</strong>' +
                                '<span>' + _supportChatTime(message.created_at) + '</span>' +
                            '</div>' +
                            '<p>' + _supportEscape(message.message) + '</p>' +
                        '</div>' +
                '</div>';
            }).join('');
            _supportScrollThreadToBottom(listEl);
        }

        if (!attachmentListEl) return;
        if (!attachments.length) {
            attachmentListEl.innerHTML = '<div class="support-thread-empty">No attachments yet.</div>';
        } else {
            attachmentListEl.innerHTML = attachments.map(function (attachment) {
                var sizeKb = Math.max(1, Math.round((attachment.file_size || 0) / 1024));
                var roleLabel = _supportThreadRoleLabel(attachment.uploader_type);
                return '' +
                    '<div class="support-attachment-item">' +
                        '<div>' +
                            '<strong>' + _supportEscape(attachment.filename) + '</strong>' +
                            '<p>' + _supportEscape(roleLabel) + ' · ' + _supportTimeAgo(attachment.created_at) + ' · ' + sizeKb + ' KB</p>' +
                            '<span>' + _supportEscape(attachment.content_type) + '</span>' +
                        '</div>' +
                        '<button type="button" class="support-attachment-download" data-download-url="' + _supportEscape(attachment.download_url) + '" data-download-filename="' + _supportEscape(attachment.filename) + '">Download</button>' +
                    '</div>';
            }).join('');
            _supportBindAttachmentDownloads(attachmentListEl);
        }
    } catch (error) {
        if (countEl) countEl.textContent = '0 messages';
        listEl.innerHTML = '<div class="support-thread-empty">Unable to load conversation right now.</div>';
        if (attachmentListEl) attachmentListEl.innerHTML = '<div class="support-thread-empty">Unable to load attachments right now.</div>';
    }
}

async function _supportSendReply() {
    var replyInput = document.getElementById('supportReplyInput');
    var replyBtn = document.getElementById('supportReplyBtn');
    if (!supportSelectedTicketId || !replyInput || !replyBtn) return;

    var message = (replyInput.value || '').trim();
    if (message.length < 2) {
        _supportShowToast('Reply must be at least 2 characters.', 'error');
        return;
    }

    replyBtn.disabled = true;
    replyBtn.textContent = 'Sending...';

    try {
        var result = await _supportFetch('/user/support-tickets/' + supportSelectedTicketId + '/messages', {
            method: 'POST',
            headers: _supportAuthHeaders(),
            body: JSON.stringify({ message: message })
        });
        replyInput.value = '';
        _supportShowToast(result.message || 'Reply sent successfully.', 'success');
        _supportLoadOverview();
        _supportLoadTickets();
    } catch (error) {
        _supportShowToast(error.message || 'Failed to send reply.', 'error');
    } finally {
        replyBtn.disabled = false;
        replyBtn.textContent = 'Send';
    }
}

function _supportScrollThreadToBottom(listEl) {
    if (!listEl) return;
    window.requestAnimationFrame(function () {
        listEl.scrollTop = listEl.scrollHeight;
    });
}

async function _supportUploadAttachment() {
    var fileInput = document.getElementById('supportAttachmentInput');
    var uploadBtn = document.getElementById('supportAttachmentUploadBtn');
    if (!supportSelectedTicketId || !fileInput || !uploadBtn) return;

    if (!fileInput.files || !fileInput.files.length) {
        _supportShowToast('Choose a file to upload first.', 'error');
        return;
    }

    var file = fileInput.files[0];
    if (file.size > 2 * 1024 * 1024) {
        _supportShowToast('Attachment must be 2 MB or smaller.', 'error');
        return;
    }

    uploadBtn.disabled = true;
    uploadBtn.textContent = 'Uploading...';

    try {
        var formData = new FormData();
        formData.append('file', file);
        var response = await fetch('http://localhost:8001/user/support-tickets/' + supportSelectedTicketId + '/attachments', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + (localStorage.getItem('token') || '')
            },
            body: formData
        });

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
            throw new Error(_supportNormalizeErrorDetail(data.detail) || data.message || response.statusText || 'Upload failed');
        }

        fileInput.value = '';
        _supportShowToast(data.message || 'Attachment uploaded successfully.', 'success');
        _supportLoadTickets();
    } catch (error) {
        _supportShowToast(error.message || 'Failed to upload attachment.', 'error');
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Upload';
    }
}

function _supportClearTicketDetail() {
    var emptyEl = document.getElementById('supportTicketDetailEmpty');
    var panelEl = document.getElementById('supportTicketDetailPanel');
    if (emptyEl) emptyEl.style.display = '';
    if (panelEl) panelEl.style.display = 'none';
}

function _supportSetText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value || '';
}

function _supportLabel(value) {
    return String(value || '')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, function (char) { return char.toUpperCase(); });
}

function _supportParseTs(iso) {
    if (!iso) return null;
    var ts = new Date(/Z$|[+-]\d{2}:\d{2}$/.test(iso) ? iso : (iso + 'Z'));
    return isNaN(ts.getTime()) ? null : ts;
}

function _supportTicketSla(ticket) {
    var priority = (ticket && ticket.priority ? String(ticket.priority) : 'medium').toLowerCase();
    var targetMinutes = SUPPORT_SLA_MINUTES[priority] || SUPPORT_SLA_MINUTES.medium;
    var createdAt = _supportParseTs(ticket && ticket.created_at);
    if (!createdAt) {
        return {
            className: 'ok',
            shortLabel: 'SLA',
            label: 'SLA unavailable',
            target: 'Created time missing'
        };
    }

    var status = (ticket && ticket.status ? String(ticket.status) : 'open').toLowerCase();
    var closedLike = status === 'resolved' || status === 'closed';
    var updatedAt = _supportParseTs(ticket && ticket.updated_at);
    var endTs = closedLike && updatedAt ? updatedAt : new Date();
    var elapsedMinutes = Math.max(0, Math.floor((endTs.getTime() - createdAt.getTime()) / 60000));
    var remainingMinutes = targetMinutes - elapsedMinutes;
    var targetText = _supportFormatDuration(targetMinutes);

    if (closedLike) {
        if (elapsedMinutes <= targetMinutes) {
            return {
                className: 'ok',
                shortLabel: 'SLA met',
                label: 'Resolved within SLA',
                target: 'Resolved in ' + _supportFormatDuration(elapsedMinutes) + ' (target ' + targetText + ')'
            };
        }
        return {
            className: 'breached',
            shortLabel: 'Breached',
            label: 'Resolved after SLA breach',
            target: 'Resolved in ' + _supportFormatDuration(elapsedMinutes) + ' (target ' + targetText + ')'
        };
    }

    if (remainingMinutes <= 0) {
        return {
            className: 'breached',
            shortLabel: 'Breached',
            label: 'SLA breached',
            target: 'Target was ' + targetText
        };
    }

    if (remainingMinutes <= Math.ceil(targetMinutes * 0.25)) {
        return {
            className: 'risk',
            shortLabel: 'At risk',
            label: 'SLA at risk',
            target: 'Due in ' + _supportFormatDuration(remainingMinutes)
        };
    }

    return {
        className: 'ok',
        shortLabel: 'On track',
        label: 'SLA on track',
        target: 'Due in ' + _supportFormatDuration(remainingMinutes)
    };
}

function _supportFormatDuration(minutes) {
    minutes = Math.max(0, Math.round(Number(minutes) || 0));
    if (minutes < 60) return minutes + 'm';
    var hours = Math.floor(minutes / 60);
    var mins = minutes % 60;
    if (hours < 24) return mins ? (hours + 'h ' + mins + 'm') : (hours + 'h');
    var days = Math.floor(hours / 24);
    var remHours = hours % 24;
    return remHours ? (days + 'd ' + remHours + 'h') : (days + 'd');
}

function _supportBindAttachmentDownloads(rootEl) {
    if (!rootEl) return;
    rootEl.querySelectorAll('.support-attachment-download').forEach(function (btn) {
        if (btn.dataset.bound) return;
        btn.dataset.bound = 'true';
        btn.addEventListener('click', function () {
            var url = btn.getAttribute('data-download-url') || '';
            var filename = btn.getAttribute('data-download-filename') || 'attachment';
            _supportDownloadWithAuth(url, filename);
        });
    });
}

async function _supportDownloadWithAuth(url, filename) {
    if (!url) return;
    var fullUrl = url.indexOf('http') === 0 ? url : ('http://localhost:8001' + url);
    try {
        var response = await fetch(fullUrl, {
            method: 'GET',
            headers: {
                'Authorization': 'Bearer ' + (localStorage.getItem('token') || '')
            }
        });
        if (response.status === 401) {
            localStorage.clear();
            window.location.replace('http://localhost:3000/login.html');
            return;
        }
        if (!response.ok) throw new Error('Download failed');

        var blob = await response.blob();
        var objectUrl = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = objectUrl;
        link.download = filename || 'attachment';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(objectUrl);
    } catch (error) {
        _supportShowToast('Failed to download attachment.', 'error');
    }
}

function _supportKbCatalog() {
    return [
        { category: 'api_issue', title: 'Fix 401/403 API access errors', hint: 'Validate token scope, key status, and route permission mapping.', href: '#documentation', keys: ['401', '403', 'permission', 'token', 'auth', 'denied'] },
        { category: 'api_issue', title: 'Handle rate-limit and quota blocks', hint: 'Review burst windows, retry strategy, and quota reset timing.', href: '#documentation', keys: ['429', 'rate', 'quota', 'limit', 'throttle'] },
        { category: 'account_issue', title: 'Recover account and MFA access', hint: 'Use secure recovery flow for OTP, backup code, and session reset.', href: '#troubleshooting', keys: ['mfa', 'otp', 'backup', 'login', 'session'] },
        { category: 'security_issue', title: 'Immediate security incident checklist', hint: 'Rotate keys, revoke sessions, and capture route/IP/time evidence.', href: '#security-logs', keys: ['leak', 'attack', 'breach', 'compromise', 'suspicious'] },
        { category: 'bug_report', title: 'Write a reproducible bug report', hint: 'Share expected vs actual behavior with exact reproduction steps.', href: '#troubleshooting', keys: ['bug', 'crash', 'error', 'fail', 'broken'] },
        { category: 'general_question', title: 'General support playbook', hint: 'Try fast checks before raising a deeper escalation.', href: '#documentation', keys: ['help', 'question', 'how', 'guide'] }
    ];
}

function _supportRenderKbSuggestions() {
    var listEl = document.getElementById('supportKbList');
    var hintEl = document.getElementById('supportKbHint');
    if (!listEl) return;

    var category = ((document.getElementById('supportCategory') || {}).value || 'general_question').toLowerCase();
    var subject = ((document.getElementById('supportSubject') || {}).value || '').toLowerCase();
    var description = ((document.getElementById('supportDescription') || {}).value || '').toLowerCase();
    var text = (subject + ' ' + description).trim();

    var suggestions = _supportKbCatalog().map(function (item) {
        var score = item.category === category ? 6 : 0;
        item.keys.forEach(function (key) {
            if (text.indexOf(key) !== -1) score += 2;
        });
        return { item: item, score: score };
    }).sort(function (a, b) { return b.score - a.score; }).slice(0, 3).map(function (entry) {
        return entry.item;
    });

    if (!suggestions.length) {
        listEl.innerHTML = '<div class="support-kb-empty">Start describing the issue to get contextual suggestions.</div>';
        if (hintEl) hintEl.textContent = 'Based on your ticket draft';
        return;
    }

    listEl.innerHTML = suggestions.map(function (entry) {
        return '' +
            '<a class="support-kb-item" href="' + entry.href + '">' +
                '<strong>' + _supportEscape(entry.title) + '</strong>' +
                '<span>' + _supportEscape(entry.hint) + '</span>' +
            '</a>';
    }).join('');
    if (hintEl) hintEl.textContent = 'Real-time suggestions from your draft';
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

