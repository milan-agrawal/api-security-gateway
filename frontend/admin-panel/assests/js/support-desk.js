var supportDeskSelectedTicketId = null;
var supportDeskSelectedTicketStatus = null;
var supportDeskSearchDebounceTimer = null;
var SUPPORT_DESK_SLA_MINUTES = {
    critical: 30,
    high: 120,
    medium: 480,
    low: 1440
};

function initSupportDesk() {
    _supportDeskBind();
    _supportDeskLoadOverview();
    _supportDeskLoadTickets();
}

function _supportDeskAuthHeaders() {
    return {
        'Authorization': 'Bearer ' + (localStorage.getItem('token') || ''),
        'Content-Type': 'application/json'
    };
}

async function _supportDeskFetch(path, options) {
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
        var detail = _supportDeskNormalizeErrorDetail(data && data.detail);
        throw new Error(detail || (data && data.message) || response.statusText || 'Request failed');
    }

    return data;
}

function _supportDeskBind() {
    var refreshBtn = document.getElementById('supportDeskRefreshBtn');
    var quickRefreshBtn = document.getElementById('supportDeskQuickRefresh');
    var quickEscalatedBtn = document.getElementById('supportDeskQuickEscalated');
    var statusFilter = document.getElementById('supportDeskStatusFilter');
    var categoryFilter = document.getElementById('supportDeskCategoryFilter');
    var priorityFilter = document.getElementById('supportDeskPriorityFilter');
    var replyBtn = document.getElementById('supportDeskReplyBtn');
    var replyInput = document.getElementById('supportDeskReplyInput');
    var searchInput = document.getElementById('supportDeskSearch');
    var searchClearBtn = document.getElementById('supportDeskSearchClear');
    var attachmentUploadBtn = document.getElementById('supportDeskAttachmentUploadBtn');

    if (refreshBtn && !refreshBtn.dataset.bound) {
        refreshBtn.dataset.bound = 'true';
        refreshBtn.addEventListener('click', function () {
            _supportDeskLoadOverview();
            _supportDeskLoadTickets();
        });
    }

    if (quickRefreshBtn && !quickRefreshBtn.dataset.bound) {
        quickRefreshBtn.dataset.bound = 'true';
        quickRefreshBtn.addEventListener('click', function () {
            _supportDeskLoadOverview();
            _supportDeskLoadTickets();
        });
    }

    if (quickEscalatedBtn && !quickEscalatedBtn.dataset.bound) {
        quickEscalatedBtn.dataset.bound = 'true';
        quickEscalatedBtn.addEventListener('click', function () {
            if (statusFilter) statusFilter.value = 'escalated';
            _supportDeskSetActiveTab('escalated');
            _supportDeskLoadTickets();
        });
    }

    [statusFilter, categoryFilter, priorityFilter].forEach(function (el) {
        if (el && !el.dataset.bound) {
            el.dataset.bound = 'true';
            el.addEventListener('change', function () {
                _supportDeskSyncTabsWithStatus();
                _supportDeskLoadTickets();
            });
        }
    });

    document.querySelectorAll('.support-desk-tab').forEach(function (tab) {
        if (tab.dataset.bound) return;
        tab.dataset.bound = 'true';
        tab.addEventListener('click', function () {
            var nextStatus = tab.getAttribute('data-support-tab') || 'all';
            if (statusFilter) statusFilter.value = nextStatus === 'all' ? '' : nextStatus;
            _supportDeskSetActiveTab(nextStatus);
            _supportDeskLoadTickets();
        });
    });

    if (replyBtn && !replyBtn.dataset.bound) {
        replyBtn.dataset.bound = 'true';
        replyBtn.addEventListener('click', function () {
            _supportDeskSendReply();
        });
    }
    if (replyInput && !replyInput.dataset.bound) {
        replyInput.dataset.bound = 'true';
        replyInput.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                _supportDeskSendReply();
            }
        });
    }

    if (searchInput && !searchInput.dataset.bound) {
        searchInput.dataset.bound = 'true';
        searchInput.addEventListener('input', function () {
            window.clearTimeout(supportDeskSearchDebounceTimer);
            supportDeskSearchDebounceTimer = window.setTimeout(function () {
                _supportDeskLoadTickets();
            }, 220);
        });
        searchInput.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                window.clearTimeout(supportDeskSearchDebounceTimer);
                _supportDeskLoadTickets();
            }
        });
    }

    if (searchClearBtn && !searchClearBtn.dataset.bound) {
        searchClearBtn.dataset.bound = 'true';
        searchClearBtn.addEventListener('click', function () {
            if (searchInput) searchInput.value = '';
            _supportDeskLoadTickets();
        });
    }

    if (attachmentUploadBtn && !attachmentUploadBtn.dataset.bound) {
        attachmentUploadBtn.dataset.bound = 'true';
        attachmentUploadBtn.addEventListener('click', function () {
            _supportDeskUploadAttachment();
        });
    }
}

async function _supportDeskLoadOverview() {
    var statusLabelEl = document.getElementById('supportDeskStatusLabel');
    try {
        var overview = await _supportDeskFetch('/admin/support-tickets/overview', {
            headers: _supportDeskAuthHeaders()
        });
        _supportDeskRenderOverview(overview || {});
    } catch (error) {
        if (statusLabelEl) statusLabelEl.textContent = 'Unable to load support queue overview';
    }
}

async function _supportDeskLoadTickets() {
    var listEl = document.getElementById('supportDeskTicketList');
    var badgeEl = document.getElementById('supportDeskQueueBadge');
    if (!listEl) return;

    listEl.innerHTML = '<div class="support-desk-placeholder-item"><div><strong>Loading support tickets...</strong><p>Please wait while the queue is refreshed.</p></div><span class="support-desk-pill neutral">Loading</span></div>';

    var query = new URLSearchParams();
    var searchQuery = (document.getElementById('supportDeskSearch') || {}).value || '';
    var statusFilter = (document.getElementById('supportDeskStatusFilter') || {}).value || '';
    var categoryFilter = (document.getElementById('supportDeskCategoryFilter') || {}).value || '';
    var priorityFilter = (document.getElementById('supportDeskPriorityFilter') || {}).value || '';
    if (searchQuery.trim()) query.set('q', searchQuery.trim());
    if (statusFilter) query.set('status_filter', statusFilter);
    if (categoryFilter) query.set('category', categoryFilter);
    if (priorityFilter) query.set('priority', priorityFilter);

    try {
        var result = await _supportDeskFetch('/admin/support-tickets' + (query.toString() ? ('?' + query.toString()) : ''), {
            headers: _supportDeskAuthHeaders()
        });
        var tickets = (result && result.tickets) || [];
        if (badgeEl) badgeEl.textContent = tickets.length + ' in view';

        if (!tickets.length) {
            listEl.innerHTML = '<div class="support-desk-placeholder-item"><div><strong>No tickets match the current filters.</strong><p>Try changing the workflow, category, or priority filters.</p></div><span class="support-desk-pill neutral">Empty</span></div>';
            return;
        }

        if (!supportDeskSelectedTicketId && tickets.length) {
            supportDeskSelectedTicketId = tickets[0].id;
        }
        if (supportDeskSelectedTicketId && !tickets.some(function (ticket) { return ticket.id === supportDeskSelectedTicketId; })) {
            supportDeskSelectedTicketId = tickets.length ? tickets[0].id : null;
        }

        listEl.innerHTML = tickets.map(function (ticket) {
            var isSelected = ticket.id === supportDeskSelectedTicketId;
            var isClosed = String(ticket.status || '').toLowerCase() === 'closed';
            var attachmentLabel = ticket.attachment_count > 0 ? (' · ' + ticket.attachment_count + ' attachment' + (ticket.attachment_count === 1 ? '' : 's')) : '';
            var sla = _supportDeskTicketSla(ticket);
            return '' +
                '<div class="support-desk-ticket' + (isSelected ? ' selected' : '') + '" data-ticket-card="' + ticket.id + '">' +
                    '<div class="support-desk-ticket-head">' +
                        '<div>' +
                            '<strong>SUP-' + ticket.id + ' · ' + _supportDeskEscape(ticket.subject) + '</strong>' +
                            '<p>' + _supportDeskEscape(ticket.user_full_name) + ' · ' + _supportDeskEscape(ticket.user_email) + '</p>' +
                        '</div>' +
                        '<div class="support-desk-ticket-badges">' +
                            '<span class="support-desk-pill ' + _supportDeskPriorityClass(ticket.priority) + '">' + _supportDeskLabel(ticket.priority) + '</span>' +
                            '<span class="support-desk-pill ' + _supportDeskStatusClass(ticket.status) + '">' + _supportDeskLabel(ticket.status) + '</span>' +
                            '<span class="support-desk-sla-badge ' + sla.className + '">' + _supportDeskEscape(sla.shortLabel) + '</span>' +
                        '</div>' +
                    '</div>' +
                    '<div class="support-desk-ticket-meta">' +
                        '<span>' + _supportDeskCategoryLabel(ticket.category) + '</span>' +
                        '<span>Route: ' + _supportDeskEscape(ticket.related_route || 'support') + '</span>' +
                        '<span>Updated ' + _supportDeskTimeAgo(ticket.updated_at) + attachmentLabel + '</span>' +
                    '</div>' +
                    '<p class="support-desk-ticket-description">' + _supportDeskEscape(ticket.description) + '</p>' +
                    '<div class="support-desk-ticket-actions">' +
                        '<select class="support-desk-status-select" data-ticket-id="' + ticket.id + '"' + (isClosed ? ' disabled' : '') + '>' +
                            _supportDeskStatusOptions(ticket.status) +
                        '</select>' +
                        '<button type="button" class="support-desk-update-btn" data-ticket-id="' + ticket.id + '"' + (isClosed ? ' disabled' : '') + '>Update Status</button>' +
                    '</div>' +
                '</div>';
        }).join('');
        _supportDeskBindAttachmentDownloads(listEl);

        _supportDeskBindTicketCards(tickets);
        _supportDeskBindUpdateButtons();
        _supportDeskRenderSelectedTicket(tickets);
    } catch (error) {
        if (badgeEl) badgeEl.textContent = 'Load failed';
        listEl.innerHTML = '<div class="support-desk-placeholder-item"><div><strong>Unable to load support tickets.</strong><p>' + _supportDeskEscape(error.message || 'Try refreshing again.') + '</p></div><span class="support-desk-pill neutral">Error</span></div>';
        _supportDeskClearSelectedTicket();
    }
}

function _supportDeskBindTicketCards(tickets) {
    document.querySelectorAll('[data-ticket-card]').forEach(function (card) {
        if (card.dataset.bound) return;
        card.dataset.bound = 'true';
        card.addEventListener('click', function (event) {
            if (event.target.closest('.support-desk-ticket-actions')) return;
            var ticketId = Number(card.getAttribute('data-ticket-card'));
            supportDeskSelectedTicketId = ticketId;
            document.querySelectorAll('[data-ticket-card]').forEach(function (node) {
                node.classList.toggle('selected', Number(node.getAttribute('data-ticket-card')) === ticketId);
            });
            _supportDeskRenderSelectedTicket(tickets);
        });
    });
}

function _supportDeskBindUpdateButtons() {
    document.querySelectorAll('.support-desk-update-btn').forEach(function (btn) {
        if (btn.dataset.bound) return;
        btn.dataset.bound = 'true';
        btn.addEventListener('click', async function () {
            var ticketId = btn.getAttribute('data-ticket-id');
            var select = document.querySelector('.support-desk-status-select[data-ticket-id="' + ticketId + '"]');
            if (!ticketId || !select) return;
            if (btn.disabled || select.disabled) return;

            var originalLabel = btn.textContent;
            btn.disabled = true;
            btn.textContent = 'Updating...';

            try {
                var result = await _supportDeskFetch('/admin/support-tickets/' + ticketId, {
                    method: 'PATCH',
                    headers: _supportDeskAuthHeaders(),
                    body: JSON.stringify({ status: select.value })
                });
                if (typeof showToast === 'function') {
                    showToast(result.message || 'Ticket updated successfully.', 'success');
                }
                _supportDeskLoadOverview();
                _supportDeskLoadTickets();
            } catch (error) {
                if (typeof showToast === 'function') {
                    showToast(error.message || 'Failed to update ticket.', 'error');
                }
            } finally {
                btn.disabled = false;
                btn.textContent = originalLabel;
            }
        });
    });
}

function _supportDeskRenderOverview(overview) {
    var openEl = document.getElementById('supportDeskMetricOpen');
    var escalatedEl = document.getElementById('supportDeskMetricEscalated');
    var resolvedEl = document.getElementById('supportDeskMetricResolved');
    var waitingEl = document.getElementById('supportDeskMetricWaiting');
    var reviewEl = document.getElementById('supportDeskMetricReview');
    var closedEl = document.getElementById('supportDeskMetricClosed');
    var badgeEl = document.getElementById('supportDeskQueueBadge');
    var statusLabelEl = document.getElementById('supportDeskStatusLabel');
    var totalChipEl = document.getElementById('supportDeskHeroChipTotal');
    var escalatedChipEl = document.getElementById('supportDeskHeroChipEscalated');
    var waitingChipEl = document.getElementById('supportDeskHeroChipWaiting');
    var deliveryChipEl = document.getElementById('supportDeskHeroChipDelivery');
    var summaryLineEl = document.getElementById('supportDeskSummaryLine');

    var total = Number(overview.total_tickets || 0);
    var open = Number(overview.open || 0);
    var escalated = Number(overview.escalated || 0);
    var resolved = Number(overview.resolved || 0);
    var waiting = Number(overview.waiting_for_user || 0);
    var review = Number(overview.in_review || 0);
    var closed = Number(overview.closed || 0);

    if (openEl) openEl.textContent = String(open);
    if (escalatedEl) escalatedEl.textContent = String(escalated);
    if (resolvedEl) resolvedEl.textContent = String(resolved);
    if (waitingEl) waitingEl.textContent = String(waiting);
    if (reviewEl) reviewEl.textContent = String(review);
    if (closedEl) closedEl.textContent = String(closed);
    if (badgeEl) badgeEl.textContent = total + ' total tickets';
    if (totalChipEl) totalChipEl.textContent = total + ' total ticket' + (total === 1 ? '' : 's');
    if (escalatedChipEl) escalatedChipEl.textContent = escalated + ' escalated';
    if (waitingChipEl) waitingChipEl.textContent = waiting + ' waiting on user';
    if (deliveryChipEl) deliveryChipEl.textContent = 'Status emails active';

    if (statusLabelEl) {
        if (escalated > 0) {
            statusLabelEl.textContent = escalated + ' escalated support ticket' + (escalated === 1 ? ' requires' : 's require') + ' attention';
        } else {
            statusLabelEl.textContent = 'Support queue is live and synced';
        }
    }

    if (summaryLineEl) {
        if (escalated > 0) {
            summaryLineEl.textContent = escalated + ' escalated ticket' + (escalated === 1 ? ' is' : 's are') + ' at the front of the queue. Review those before routine requests.';
        } else if (waiting > 0) {
            summaryLineEl.textContent = waiting + ' ticket' + (waiting === 1 ? ' is' : 's are') + ' waiting on the user. Follow up there before opening new work.';
        } else if (review > 0) {
            summaryLineEl.textContent = review + ' ticket' + (review === 1 ? ' is' : 's are') + ' currently in review and moving through the workflow.';
        } else {
            summaryLineEl.textContent = 'Queue is stable right now. New user requests will appear here and can be triaged immediately.';
        }
    }

}

function _supportDeskCategoryLabel(category) {
    var map = {
        api_issue: 'API Access Issue',
        account_issue: 'Account & MFA Help',
        security_issue: 'Security Emergency',
        bug_report: 'Bug Report',
        general_question: 'General Question'
    };
    return map[category] || 'Support';
}

function _supportDeskLabel(value) {
    return String(value || '')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, function (char) { return char.toUpperCase(); });
}

function _supportDeskStatusClass(status) {
    status = (status || 'open').toLowerCase();
    if (status === 'in_review') return 'info';
    if (status === 'waiting_for_user') return 'warning';
    if (status === 'reopen_requested') return 'warning';
    if (status === 'escalated') return 'danger';
    if (status === 'resolved') return 'success';
    if (status === 'closed') return 'neutral';
    return 'info';
}

function _supportDeskPriorityClass(priority) {
    priority = (priority || 'medium').toLowerCase();
    if (priority === 'critical') return 'danger';
    if (priority === 'high') return 'warning';
    if (priority === 'low') return 'neutral';
    return 'info';
}

function _supportDeskStatusOptions(currentStatus) {
    var statuses = ['open', 'in_review', 'waiting_for_user', 'escalated', 'resolved', 'closed'];
    currentStatus = (currentStatus || 'open').toLowerCase();
    return statuses.map(function (status) {
        var selected = status === currentStatus ? ' selected' : '';
        return '<option value="' + status + '"' + selected + '>' + _supportDeskLabel(status) + '</option>';
    }).join('');
}

function _supportDeskTimeAgo(iso) {
    return _supportDeskMumbaiDateTime(iso);
}

function _supportDeskChatTime(iso) {
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

function _supportDeskMumbaiDateTime(iso) {
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

function _supportDeskEscape(value) {
    var div = document.createElement('div');
    div.textContent = value || '';
    return div.innerHTML;
}

function _supportDeskThreadRoleLabel(authorType) {
    return (authorType || '').toLowerCase() === 'admin' ? 'Admin' : 'User';
}

function _supportDeskRenderSelectedTicket(tickets) {
    var emptyEl = document.getElementById('supportDeskDetailEmpty');
    var panelEl = document.getElementById('supportDeskDetailPanel');
    var attachmentCountEl = document.getElementById('supportDeskAttachmentCount');
    var ticket = (tickets || []).find(function (item) {
        return item.id === supportDeskSelectedTicketId;
    });

    if (!ticket) {
        _supportDeskClearSelectedTicket();
        return;
    }

    if (emptyEl) emptyEl.style.display = 'none';
    if (panelEl) panelEl.style.display = '';
    supportDeskSelectedTicketStatus = (ticket.status || 'open').toLowerCase();

    _supportDeskSetText('supportDeskDetailId', 'SUP-' + ticket.id);
    _supportDeskSetText('supportDeskDetailSubject', ticket.subject);
    _supportDeskSetText('supportDeskDetailPriority', _supportDeskLabel(ticket.priority));
    _supportDeskSetText('supportDeskDetailStatus', _supportDeskLabel(ticket.status));
    _supportDeskSetText('supportDeskDetailUser', ticket.user_full_name);
    _supportDeskSetText('supportDeskDetailUserEmail', ticket.user_email);
    _supportDeskSetText('supportDeskDetailContactEmail', ticket.contact_email);
    _supportDeskSetText('supportDeskDetailCategory', _supportDeskCategoryLabel(ticket.category));
    _supportDeskSetText('supportDeskDetailRoute', ticket.related_route || 'support');
    _supportDeskSetText('supportDeskDetailUpdated', _supportDeskTimeAgo(ticket.updated_at));
    _supportDeskSetText('supportDeskDetailCreated', _supportDeskTimeAgo(ticket.created_at));
    _supportDeskSetText('supportDeskDetailDescription', ticket.description);
    var sla = _supportDeskTicketSla(ticket);
    _supportDeskSetText('supportDeskDetailSlaStatus', sla.label);
    _supportDeskSetText('supportDeskDetailSlaTarget', sla.target);
    _supportDeskLoadTicketThread(ticket.id);

    var priorityEl = document.getElementById('supportDeskDetailPriority');
    var statusEl = document.getElementById('supportDeskDetailStatus');
    if (priorityEl) priorityEl.className = 'support-desk-pill ' + _supportDeskPriorityClass(ticket.priority);
    if (statusEl) statusEl.className = 'support-desk-pill ' + _supportDeskStatusClass(ticket.status);
    _supportDeskApplyTicketEditState(ticket);

    if (attachmentCountEl) {
        var attachmentCount = Number(ticket.attachment_count || 0);
        attachmentCountEl.textContent = attachmentCount + ' file' + (attachmentCount === 1 ? '' : 's');
    }

    _supportDeskLoadTicketAttachments(ticket.id);
}

function _supportDeskClearSelectedTicket() {
    var emptyEl = document.getElementById('supportDeskDetailEmpty');
    var panelEl = document.getElementById('supportDeskDetailPanel');
    supportDeskSelectedTicketStatus = null;
    if (emptyEl) emptyEl.style.display = '';
    if (panelEl) panelEl.style.display = 'none';
    _supportDeskApplyTicketEditState(null);
}

function _supportDeskSetText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value || '';
}

async function _supportDeskLoadTicketThread(ticketId) {
    var listEl = document.getElementById('supportDeskThreadList');
    var countEl = document.getElementById('supportDeskThreadCount');
    if (!ticketId || !listEl) return;

    listEl.innerHTML = '<div class="support-desk-thread-empty">Loading conversation...</div>';

    try {
        var result = await _supportDeskFetch('/admin/support-tickets/' + ticketId, {
            headers: _supportDeskAuthHeaders()
        });
        var ticket = result.ticket || {};
        supportDeskSelectedTicketStatus = (ticket.status || supportDeskSelectedTicketStatus || 'open').toLowerCase();
        _supportDeskApplyTicketEditState(ticket);
        var messages = (result && result.messages) || [];
        if (countEl) countEl.textContent = messages.length + ' message' + (messages.length === 1 ? '' : 's');

        if (!messages.length) {
            listEl.innerHTML = '<div class="support-desk-thread-empty">No replies yet.</div>';
            return;
        }

        listEl.innerHTML = messages.map(function (message) {
            var roleLabel = _supportDeskThreadRoleLabel(message.author_type);
            var authorInitial = _supportDeskEscape(roleLabel.charAt(0).toUpperCase());
            var reopenReason = _supportDeskExtractReopenReason(message.message);
            var messageBody = reopenReason
                ? (
                    '<div class="support-desk-thread-event-label">Reopen Request</div>' +
                    '<p class="support-desk-thread-event-text">' + _supportDeskEscape(reopenReason) + '</p>'
                )
                : ('<p>' + _supportDeskEscape(message.message) + '</p>');
            return '' +
                '<div class="support-desk-thread-row ' + (message.author_type === 'admin' ? 'admin' : 'user') + (reopenReason ? ' reopen-request' : '') + '">' +
                    '<div class="support-desk-thread-avatar">' + authorInitial + '</div>' +
                    '<div class="support-desk-thread-message ' + (message.author_type === 'admin' ? 'admin' : 'user') + (reopenReason ? ' reopen-request' : '') + '">' +
                        '<div class="support-desk-thread-meta">' +
                            '<strong>' + _supportDeskEscape(roleLabel) + '</strong>' +
                            '<span>' + _supportDeskChatTime(message.created_at) + '</span>' +
                        '</div>' +
                        messageBody +
                    '</div>' +
                '</div>';
        }).join('');
        _supportDeskScrollThreadToBottom(listEl);
    } catch (error) {
        if (countEl) countEl.textContent = '0 messages';
        listEl.innerHTML = '<div class="support-desk-thread-empty">Unable to load conversation right now.</div>';
    }
}

function _supportDeskScrollThreadToBottom(listEl) {
    if (!listEl) return;
    window.requestAnimationFrame(function () {
        listEl.scrollTop = listEl.scrollHeight;
    });
}

async function _supportDeskLoadTicketAttachments(ticketId) {
    var listEl = document.getElementById('supportDeskAttachmentList');
    var countEl = document.getElementById('supportDeskAttachmentCount');
    if (!ticketId || !listEl) return;

    listEl.innerHTML = '<div class="support-desk-thread-empty">Loading attachments...</div>';

    try {
        var result = await _supportDeskFetch('/admin/support-tickets/' + ticketId, {
            headers: _supportDeskAuthHeaders()
        });
        var attachments = (result && result.attachments) || [];

        if (countEl) countEl.textContent = attachments.length + ' file' + (attachments.length === 1 ? '' : 's');

        if (!attachments.length) {
            listEl.innerHTML = '<div class="support-desk-thread-empty">No attachments yet.</div>';
            return;
        }

        listEl.innerHTML = attachments.map(function (attachment) {
            var sizeKb = Math.max(1, Math.round((attachment.file_size || 0) / 1024));
            var roleLabel = _supportDeskThreadRoleLabel(attachment.uploader_type);
            return '' +
                '<div class="support-desk-attachment-item">' +
                    '<div>' +
                        '<strong>' + _supportDeskEscape(attachment.filename) + '</strong>' +
                        '<p>' + _supportDeskEscape(roleLabel) + ' · ' + _supportDeskTimeAgo(attachment.created_at) + ' · ' + sizeKb + ' KB</p>' +
                        '<span>' + _supportDeskEscape(attachment.content_type) + '</span>' +
                    '</div>' +
                    '<button type="button" class="support-desk-attachment-download" data-download-url="' + _supportDeskEscape(attachment.download_url) + '" data-download-filename="' + _supportDeskEscape(attachment.filename) + '">Download</button>' +
                '</div>';
        }).join('');
    } catch (error) {
        if (countEl) countEl.textContent = '0 files';
        listEl.innerHTML = '<div class="support-desk-thread-empty">Unable to load attachments right now.</div>';
    }
}

async function _supportDeskSendReply() {
    var replyInput = document.getElementById('supportDeskReplyInput');
    var replyBtn = document.getElementById('supportDeskReplyBtn');
    if (!supportDeskSelectedTicketId || !replyInput || !replyBtn) return;
    if (['closed', 'reopen_requested'].indexOf((supportDeskSelectedTicketStatus || '').toLowerCase()) !== -1) {
        if (typeof showToast === 'function') showToast('This ticket is locked until admin reopens it.', 'error');
        return;
    }

    var message = (replyInput.value || '').trim();
    if (message.length < 2) {
        if (typeof showToast === 'function') showToast('Reply must be at least 2 characters.', 'error');
        return;
    }

    replyBtn.disabled = true;
    replyBtn.textContent = 'Sending...';

    try {
        var result = await _supportDeskFetch('/admin/support-tickets/' + supportDeskSelectedTicketId + '/messages', {
            method: 'POST',
            headers: _supportDeskAuthHeaders(),
            body: JSON.stringify({ message: message })
        });
        replyInput.value = '';
        if (typeof showToast === 'function') showToast(result.message || 'Reply sent successfully.', 'success');
        _supportDeskLoadOverview();
        _supportDeskLoadTickets();
    } catch (error) {
        if (typeof showToast === 'function') showToast(error.message || 'Failed to send reply.', 'error');
    } finally {
        replyBtn.disabled = false;
        replyBtn.textContent = 'Send';
    }
}

async function _supportDeskUploadAttachment() {
    var fileInput = document.getElementById('supportDeskAttachmentInput');
    var uploadBtn = document.getElementById('supportDeskAttachmentUploadBtn');
    if (!supportDeskSelectedTicketId || !fileInput || !uploadBtn) return;
    if (['closed', 'reopen_requested'].indexOf((supportDeskSelectedTicketStatus || '').toLowerCase()) !== -1) {
        if (typeof showToast === 'function') showToast('This ticket is locked until admin reopens it.', 'error');
        return;
    }

    if (!fileInput.files || !fileInput.files.length) {
        if (typeof showToast === 'function') showToast('Choose a file to upload first.', 'error');
        return;
    }

    var file = fileInput.files[0];
    if (file.size > 2 * 1024 * 1024) {
        if (typeof showToast === 'function') showToast('Attachment must be 2 MB or smaller.', 'error');
        return;
    }

    uploadBtn.disabled = true;
    uploadBtn.textContent = 'Uploading...';

    try {
        var formData = new FormData();
        formData.append('file', file);
        var response = await fetch('http://localhost:8001/admin/support-tickets/' + supportDeskSelectedTicketId + '/attachments', {
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
            throw new Error((data && (data.detail || data.message)) || response.statusText || 'Upload failed');
        }

        fileInput.value = '';
        if (typeof showToast === 'function') showToast(data.message || 'Attachment uploaded successfully.', 'success');
        _supportDeskLoadOverview();
        _supportDeskLoadTickets();
    } catch (error) {
        if (typeof showToast === 'function') showToast(error.message || 'Failed to upload attachment.', 'error');
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Upload';
    }
}

function _supportDeskSetActiveTab(status) {
    document.querySelectorAll('.support-desk-tab').forEach(function (tab) {
        var tabStatus = tab.getAttribute('data-support-tab') || 'all';
        tab.classList.toggle('active', tabStatus === status);
    });
}

function _supportDeskSyncTabsWithStatus() {
    var statusFilter = (document.getElementById('supportDeskStatusFilter') || {}).value || '';
    _supportDeskSetActiveTab(statusFilter || 'all');
}

function _supportDeskParseTs(ts) {
    if (!ts) return null;
    var parsed = new Date(/Z$|[+-]\d{2}:\d{2}$/.test(ts) ? ts : (ts + 'Z'));
    return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function _supportDeskFormatDuration(minutes) {
    minutes = Math.max(0, Math.round(Number(minutes) || 0));
    if (minutes < 60) return minutes + 'm';
    var hours = Math.floor(minutes / 60);
    var mins = minutes % 60;
    if (hours < 24) return mins ? (hours + 'h ' + mins + 'm') : (hours + 'h');
    var days = Math.floor(hours / 24);
    var remHours = hours % 24;
    return remHours ? (days + 'd ' + remHours + 'h') : (days + 'd');
}

function _supportDeskTicketSla(ticket) {
    var priority = (ticket && ticket.priority ? String(ticket.priority) : 'medium').toLowerCase();
    var targetMinutes = SUPPORT_DESK_SLA_MINUTES[priority] || SUPPORT_DESK_SLA_MINUTES.medium;
    var createdAt = _supportDeskParseTs(ticket && ticket.created_at);
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
    var updatedAt = _supportDeskParseTs(ticket && ticket.updated_at);
    var endTs = closedLike && updatedAt ? updatedAt : new Date();
    var elapsedMinutes = Math.max(0, Math.floor((endTs.getTime() - createdAt.getTime()) / 60000));
    var remainingMinutes = targetMinutes - elapsedMinutes;
    var targetText = _supportDeskFormatDuration(targetMinutes);

    if (closedLike) {
        if (elapsedMinutes <= targetMinutes) {
            return {
                className: 'ok',
                shortLabel: 'SLA met',
                label: 'Resolved within SLA',
                target: 'Resolved in ' + _supportDeskFormatDuration(elapsedMinutes) + ' (target ' + targetText + ')'
            };
        }
        return {
            className: 'breached',
            shortLabel: 'Breached',
            label: 'Resolved after SLA breach',
            target: 'Resolved in ' + _supportDeskFormatDuration(elapsedMinutes) + ' (target ' + targetText + ')'
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
            target: 'Due in ' + _supportDeskFormatDuration(remainingMinutes)
        };
    }

    return {
        className: 'ok',
        shortLabel: 'On track',
        label: 'SLA on track',
        target: 'Due in ' + _supportDeskFormatDuration(remainingMinutes)
    };
}

function _supportDeskBindAttachmentDownloads(rootEl) {
    if (!rootEl) return;
    rootEl.querySelectorAll('.support-desk-attachment-download').forEach(function (btn) {
        if (btn.dataset.bound) return;
        btn.dataset.bound = 'true';
        btn.addEventListener('click', function () {
            var url = btn.getAttribute('data-download-url') || '';
            var filename = btn.getAttribute('data-download-filename') || 'attachment';
            _supportDeskDownloadWithAuth(url, filename);
        });
    });
}

async function _supportDeskDownloadWithAuth(url, filename) {
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
        if (typeof showToast === 'function') showToast('Failed to download attachment.', 'error');
    }
}

function _supportDeskNormalizeErrorDetail(detail) {
    if (!detail) return '';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail.map(function (item) {
            return _supportDeskNormalizeErrorDetail(item);
        }).filter(Boolean).join(', ');
    }
    if (typeof detail === 'object') {
        if (detail.msg) return detail.msg;
        if (detail.detail) return _supportDeskNormalizeErrorDetail(detail.detail);
        if (detail.message) return detail.message;
        return JSON.stringify(detail);
    }
    return String(detail);
}

function _supportDeskExtractReopenReason(message) {
    var text = String(message || '');
    var prefix = 'Reopen request reason:';
    if (text.indexOf(prefix) !== 0) return '';
    return text.slice(prefix.length).trim();
}

function _supportDeskApplyTicketEditState(ticket) {
    var status = (ticket && ticket.status ? String(ticket.status) : (supportDeskSelectedTicketStatus || 'open')).toLowerCase();
    var isClosed = status === 'closed' || status === 'reopen_requested';
    var closedNote = document.getElementById('supportDeskClosedNote');
    var replyInput = document.getElementById('supportDeskReplyInput');
    var replyBtn = document.getElementById('supportDeskReplyBtn');
    var fileInput = document.getElementById('supportDeskAttachmentInput');
    var uploadBtn = document.getElementById('supportDeskAttachmentUploadBtn');

    if (closedNote) closedNote.style.display = isClosed ? '' : 'none';
    if (replyInput) {
        replyInput.disabled = isClosed;
        replyInput.placeholder = status === 'reopen_requested'
            ? 'User requested reopen. Set status to Open or In Review to unlock.'
            : (isClosed ? 'Closed ticket: waiting for user reopen request.' : 'Type as a admin...');
    }
    if (replyBtn) replyBtn.disabled = isClosed;
    if (fileInput) fileInput.disabled = isClosed;
    if (uploadBtn) uploadBtn.disabled = isClosed;
    if (closedNote) {
        closedNote.textContent = status === 'reopen_requested'
            ? 'Reopen request pending. Change status to Open or In Review to unlock this ticket.'
            : 'This ticket is closed and locked. Wait for a user reopen request.';
    }
}

window.initSupportDesk = initSupportDesk;
