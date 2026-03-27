const cloudMailState = {
    presets: null,
    activeWorkflow: null,
    activeTaskId: null,
    taskOffset: 0,
    tasks: [],
};

const workflowListEl = document.getElementById('workflow-list');
const workflowSearchEl = document.getElementById('workflow-search');
const workflowFormEl = document.getElementById('workflow-form');
const flowTitleEl = document.getElementById('flow-title');
const flowDescriptionEl = document.getElementById('flow-description');
const flowScriptEl = document.getElementById('flow-script');
const flowToolkitRootEl = document.getElementById('flow-toolkit-root');
const flowDefaultsEl = document.getElementById('flow-defaults');
const summaryDomainEl = document.getElementById('summary-domain');
const summaryAdminEmailEl = document.getElementById('summary-admin-email');
const summaryAdminPasswordEl = document.getElementById('summary-admin-password');
const summaryApiUrlEl = document.getElementById('summary-api-url');
const commandPreviewEl = document.getElementById('command-preview');
const mainDomainsTableEl = document.getElementById('main-domains-table');
const refreshMainDomainsBtn = document.getElementById('refresh-main-domains');
const taskListEl = document.getElementById('task-list');
const taskLabelEl = document.getElementById('task-label');
const taskStatusEl = document.getElementById('task-status');
const taskLogsEl = document.getElementById('task-logs');
const taskResultEl = document.getElementById('task-result');
const previewButton = document.getElementById('preview-button');
const copyButton = document.getElementById('copy-button');
const runButton = document.getElementById('run-button');
const tabLogs = document.getElementById('tab-logs');
const tabResult = document.getElementById('tab-result');
const panelLogs = document.getElementById('panel-logs');
const panelResult = document.getElementById('panel-result');

const STATUS_TEXT = {
    queued: '排队中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
};

const PRIMARY_FIELDS = new Set([
    'domain',
    'cloudflare_api_token',
    'cloudflare_account_id',
    'jwt_secret',
    'digitalplat_api_key',
    'prefix',
    'suffix',
    'turnstile_token',
    'mail_provider',
    'email',
    'admin_email',
]);

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function splitFields(fields) {
    const primary = [];
    const advanced = [];
    fields.forEach((field, index) => {
        const isPrimary = field.required || PRIMARY_FIELDS.has(field.name) || index < 4;
        if (isPrimary) primary.push(field);
        else advanced.push(field);
    });
    return { primary, advanced };
}

function getWorkflowEntries() {
    const keyword = (workflowSearchEl.value || '').trim().toLowerCase();
    return Object.entries(cloudMailState.presets.workflows).filter(([key, workflow]) => {
        if (!keyword) return true;
        return [key, workflow.label, workflow.description].join(' ').toLowerCase().includes(keyword);
    });
}

function workflowDefaults(workflow) {
    const defaults = {};
    workflow.fields.forEach((field) => {
        if (field.default !== undefined) defaults[field.name] = field.default;
        else if (field.type === 'boolean') defaults[field.name] = false;
        else defaults[field.name] = '';
    });
    return defaults;
}

function renderWorkflowList() {
    workflowListEl.innerHTML = '';
    const entries = getWorkflowEntries();
    if (entries.length === 0) {
        workflowListEl.innerHTML = '<div class="empty-state">没有匹配的流程</div>';
        return;
    }

    entries.forEach(([key, workflow]) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `workflow-item ${cloudMailState.activeWorkflow === key ? 'active' : ''}`;
        button.innerHTML = `<strong>${escapeHtml(workflow.label)}</strong><span>${escapeHtml(workflow.description)}</span>`;
        button.addEventListener('click', () => {
            cloudMailState.activeWorkflow = key;
            cloudMailState.taskOffset = 0;
            renderWorkflowList();
            renderWorkflow();
        });
        workflowListEl.appendChild(button);
    });
}

function renderField(field, value) {
    const wrapper = document.createElement('div');
    wrapper.className = 'form-group';
    if (field.type === 'textarea') {
        wrapper.style.gridColumn = '1 / -1';
    }

    const label = document.createElement('label');
    label.setAttribute('for', field.name);
    label.textContent = field.required ? `${field.label} *` : field.label;
    wrapper.appendChild(label);

    let input;
    if (field.type === 'boolean') {
        input = document.createElement('input');
        input.type = 'checkbox';
        input.id = field.name;
        input.name = field.name;
        input.checked = Boolean(value);
        input.style.width = 'auto';
        input.addEventListener('change', debouncePreview);
        const checkboxLabel = document.createElement('label');
        checkboxLabel.style.display = 'flex';
        checkboxLabel.style.alignItems = 'center';
        checkboxLabel.style.gap = '8px';
        checkboxLabel.style.cursor = 'pointer';
        checkboxLabel.append(input, document.createTextNode('启用'));
        wrapper.appendChild(checkboxLabel);
    } else {
        if (field.type === 'textarea') {
            input = document.createElement('textarea');
            input.rows = 4;
            input.value = value || '';
        } else if (field.type === 'select') {
            input = document.createElement('select');
            (field.options || []).forEach((option) => {
                const opt = document.createElement('option');
                opt.value = option;
                opt.textContent = option;
                if (option === value) opt.selected = true;
                input.appendChild(opt);
            });
        } else {
            input = document.createElement('input');
            input.type = field.type === 'number' ? 'number' : field.type === 'password' ? 'password' : 'text';
            input.value = value ?? '';
        }
        input.id = field.name;
        input.name = field.name;
        if (field.placeholder) input.placeholder = field.placeholder;
        input.addEventListener('input', debouncePreview);
        wrapper.appendChild(input);
    }

    const hint = document.createElement('small');
    hint.style.color = 'var(--text-muted)';
    hint.style.fontSize = '0.75rem';
    hint.textContent = field.type === 'textarea' ? '每行一个' : (field.required ? '必填' : '可选');
    wrapper.appendChild(hint);
    return wrapper;
}

function getFormValues() {
    const workflow = cloudMailState.presets.workflows[cloudMailState.activeWorkflow];
    const values = {};
    workflow.fields.forEach((field) => {
        const element = workflowFormEl.elements.namedItem(field.name);
        if (!element) return;
        values[field.name] = field.type === 'boolean' ? element.checked : element.value;
    });
    return values;
}

function computeSummary(workflowKey, values) {
    const result = {
        domain: '-',
        adminEmail: '-',
        adminPassword: '-',
        apiUrl: '-',
    };

    if (workflowKey === 'bootstrap_existing') {
        const domain = (values.domain || '').trim();
        const adminLocalpart = (values.admin_localpart || 'admin').trim() || 'admin';
        result.domain = domain || '-';
        result.adminEmail = domain ? `${adminLocalpart}@${domain}` : '-';
        result.adminPassword = 'Admin123456';
        result.apiUrl = domain ? `https://${domain}/api/init/<jwt_secret>` : '-';
        return result;
    }

    if (workflowKey === 'bootstrap_new') {
        const suffix = (values.suffix || '').trim();
        const prefix = (values.prefix || '').trim();
        const displayPrefix = !prefix || prefix === '自动生成' ? '<随机前缀>' : prefix;
        result.domain = suffix ? `${displayPrefix}.${suffix}` : displayPrefix;
        result.adminEmail = result.domain && result.domain !== '<随机前缀>' ? `admin@${result.domain}` : `admin@${result.domain}`;
        result.adminPassword = 'Admin123456';
        result.apiUrl = result.domain !== '-' ? `https://${result.domain}/api/init/<jwt_secret>` : '-';
        return result;
    }

    if (workflowKey === 'register_pipeline') {
        const suffix = (values.suffix || '').trim();
        const prefix = (values.prefix || '').trim();
        const displayPrefix = !prefix || prefix === '自动生成' ? '<随机前缀>' : prefix;
        result.domain = suffix ? `${displayPrefix}.${suffix}` : displayPrefix;
        return result;
    }

    if (workflowKey === 'deploy_worker') {
        const domain = (values.domain || '').trim();
        result.domain = domain || '-';
        result.adminEmail = (values.admin_email || '-').trim() || '-';
        result.adminPassword = (values.admin_password || 'Admin123456').trim() || 'Admin123456';
        result.apiUrl = domain ? `https://${domain}/api/init/<jwt_secret>` : '-';
        return result;
    }

    if (workflowKey === 'dashboard_register') {
        const baseUrl = (values.base_url || 'https://dash.domain.digitalplat.org').trim();
        result.domain = baseUrl.replace(/^https?:\/\//, '');
        result.adminEmail = (values.email || '<自动生成邮箱>').trim() || '<自动生成邮箱>';
        result.adminPassword = (values.password || '<自动生成密码>').trim() || '<自动生成密码>';
        result.apiUrl = baseUrl;
        return result;
    }

    return result;
}

function renderSummary(workflowKey, values) {
    const summary = computeSummary(workflowKey, values);
    summaryDomainEl.textContent = summary.domain;
    summaryAdminEmailEl.textContent = summary.adminEmail;
    summaryAdminPasswordEl.textContent = summary.adminPassword;
    summaryApiUrlEl.textContent = summary.apiUrl;
}

function renderDefaults(workflow, values) {
    const chips = workflow.fields
        .filter((field) => values[field.name] !== '' && values[field.name] !== false && values[field.name] !== undefined)
        .slice(0, 6)
        .map((field) => `<span class="default-chip"><strong>${escapeHtml(field.label)}</strong>${escapeHtml(field.type === 'boolean' ? '开' : String(values[field.name]))}</span>`);

    flowDefaultsEl.innerHTML = chips.length ? chips.join('') : '<span class="default-chip">暂无默认配置</span>';
}

function getMainDomainStatusCell(item) {
    const domainStatus = item.disabled
        ? '<span class="status-badge disabled">已禁用</span>'
        : '<span class="status-badge completed">可用</span>';
    const providerStatus = item.status
        ? `<span class="status-badge">${escapeHtml(item.status)}</span>`
        : '';
    return [domainStatus, providerStatus].filter(Boolean).join(' ');
}

async function toggleMainDomain(domain, disabled) {
    const actionText = disabled ? '禁用' : '启用';
    const confirmed = await confirm(`确定要${actionText}域名 "${domain}" 吗？`);
    if (!confirmed) return;

    try {
        const endpoint = disabled ? '/email-services/cloudmail/disable' : '/email-services/cloudmail/enable';
        const result = await api.post(endpoint, { domain });
        toast.success(result.message || `域名已${actionText}`);
        await loadMainDomains();
    } catch (error) {
        toast.error(`${actionText}失败: ${error.message}`);
    }
}

async function loadMainDomains() {
    if (!mainDomainsTableEl) return;
    mainDomainsTableEl.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:20px;">加载中...</td></tr>';
    try {
        const payload = await api.get('/cloud-mail/main-domains');
        const items = payload.items || [];
        if (items.length === 0) {
            mainDomainsTableEl.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:20px;">暂无域名</td></tr>';
            return;
        }
        mainDomainsTableEl.innerHTML = items.map((item) => `
            <tr>
                <td>${escapeHtml(item.domain)}</td>
                <td style="display:flex;gap:6px;flex-wrap:wrap;">${getMainDomainStatusCell(item)}</td>
                <td>
                    <code>${escapeHtml(item.api_url)}</code>
                    <button class="btn btn-ghost btn-sm" style="margin-left:6px;" onclick="copyToClipboard('${escapeHtml(item.api_url)}')">📋</button>
                </td>
                <td>
                    <code>${escapeHtml(item.admin_email)}</code>
                    <button class="btn btn-ghost btn-sm" style="margin-left:6px;" onclick="copyToClipboard('${escapeHtml(item.admin_email)}')">📋</button>
                </td>
                <td>
                    <code>${escapeHtml(item.admin_password)}</code>
                    <button class="btn btn-ghost btn-sm" style="margin-left:6px;" onclick="copyToClipboard('${escapeHtml(item.admin_password)}')">📋</button>
                </td>
                <td>${escapeHtml(item.expires_at || '-')}</td>
                <td>
                    <button class="btn btn-secondary btn-sm" onclick="toggleMainDomain('${escapeHtml(item.domain)}', ${!item.disabled})">${item.disabled ? '启用域名' : '禁用域名'}</button>
                </td>
            </tr>
        `).join('');
    } catch (error) {
        mainDomainsTableEl.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--danger-color);padding:20px;">${escapeHtml(error.message || '加载失败')}</td></tr>`;
    }
}

function renderWorkflow() {
    const workflow = cloudMailState.presets.workflows[cloudMailState.activeWorkflow];
    const values = workflowDefaults(workflow);
    const { primary, advanced } = splitFields(workflow.fields);

    flowTitleEl.textContent = workflow.label;
    flowDescriptionEl.textContent = workflow.description;
    flowScriptEl.textContent = workflow.script;
    flowToolkitRootEl.textContent = cloudMailState.presets.toolkit_root;
    renderDefaults(workflow, values);
    renderSummary(cloudMailState.activeWorkflow, values);

    workflowFormEl.innerHTML = '';

    const primarySection = document.createElement('section');
    primarySection.className = 'form-section';
    primarySection.innerHTML = '<div class="section-title">基础参数</div>';
    const primaryGrid = document.createElement('div');
    primaryGrid.className = 'fields-grid';
    primary.forEach((field) => primaryGrid.appendChild(renderField(field, values[field.name])));
    primarySection.appendChild(primaryGrid);
    workflowFormEl.appendChild(primarySection);

    if (advanced.length > 0) {
        const advancedDetails = document.createElement('details');
        advancedDetails.className = 'advanced-details';
        advancedDetails.innerHTML = '<summary>高级参数</summary>';
        const advancedGrid = document.createElement('div');
        advancedGrid.className = 'fields-grid';
        advancedGrid.style.marginTop = '12px';
        advanced.forEach((field) => advancedGrid.appendChild(renderField(field, values[field.name])));
        advancedDetails.appendChild(advancedGrid);
        workflowFormEl.appendChild(advancedDetails);
    }

    requestPreview();
}

let previewTimer = null;
function debouncePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(() => {
        renderSummary(cloudMailState.activeWorkflow, getFormValues());
        requestPreview();
    }, 180);
}

async function requestPreview() {
    try {
        const payload = await api.post('/cloud-mail/preview', {
            workflow: cloudMailState.activeWorkflow,
            params: getFormValues(),
        });
        commandPreviewEl.textContent = payload.pretty_command;
    } catch (error) {
        commandPreviewEl.textContent = error.message || String(error);
    }
}

function renderTaskList() {
    taskListEl.innerHTML = '';
    if (cloudMailState.tasks.length === 0) {
        taskListEl.innerHTML = '<div class="task-item"><strong>暂无任务</strong><span>执行流程后会显示在这里</span></div>';
        return;
    }

    cloudMailState.tasks.forEach((task) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `task-item ${cloudMailState.activeTaskId === task.id ? 'active' : ''}`;
        button.innerHTML = `
            <strong>${escapeHtml(task.label)}</strong>
            <span>${escapeHtml(task.workflow)}</span>
            <span>${escapeHtml(STATUS_TEXT[task.status] || task.status)}</span>
        `;
        button.addEventListener('click', async () => {
            cloudMailState.activeTaskId = task.id;
            cloudMailState.taskOffset = 0;
            renderTaskList();
            await refreshTaskDetail(true);
        });
        taskListEl.appendChild(button);
    });
}

async function refreshTaskList() {
    const data = await api.get('/cloud-mail/tasks');
    cloudMailState.tasks = data.tasks || [];
    if (!cloudMailState.activeTaskId && cloudMailState.tasks[0]) {
        cloudMailState.activeTaskId = cloudMailState.tasks[0].id;
    }
    renderTaskList();
}

function setTaskStatus(status) {
    taskStatusEl.textContent = STATUS_TEXT[status] || status || '空闲';
    taskStatusEl.className = `status-badge ${status || ''}`.trim();
}

async function refreshTaskDetail(resetLogs = false) {
    if (!cloudMailState.activeTaskId) {
        taskLabelEl.textContent = '未选择';
        setTaskStatus('');
        taskLogsEl.textContent = '未选择任务。';
        taskResultEl.textContent = '暂无结果。';
        return;
    }

    if (resetLogs) {
        cloudMailState.taskOffset = 0;
        taskLogsEl.textContent = '';
    }

    const payload = await api.get(`/cloud-mail/tasks/${cloudMailState.activeTaskId}?offset=${cloudMailState.taskOffset}`);
    taskLabelEl.textContent = payload.label;
    setTaskStatus(payload.status);

    if (cloudMailState.taskOffset === 0 && payload.logs.length === 0) {
        taskLogsEl.textContent = '等待输出…';
    } else if (payload.logs.length > 0) {
        const prefix = taskLogsEl.textContent === '等待输出…' ? '' : taskLogsEl.textContent;
        taskLogsEl.textContent = [prefix, ...payload.logs].filter(Boolean).join('\n');
    }

    cloudMailState.taskOffset = payload.next_offset || cloudMailState.taskOffset;

    if (payload.result_json) {
        taskResultEl.textContent = JSON.stringify(payload.result_json, null, 2);
    } else if (payload.result_text) {
        taskResultEl.textContent = payload.result_text;
    } else {
        taskResultEl.textContent = '暂无结果。';
    }

    taskLogsEl.scrollTop = taskLogsEl.scrollHeight;
}

function switchDetailTab(mode) {
    const logsActive = mode === 'logs';
    tabLogs.classList.toggle('active', logsActive);
    tabResult.classList.toggle('active', !logsActive);
    panelLogs.classList.toggle('active', logsActive);
    panelResult.classList.toggle('active', !logsActive);
}

async function runWorkflow() {
    try {
        const payload = await api.post('/cloud-mail/tasks', {
            workflow: cloudMailState.activeWorkflow,
            params: getFormValues(),
        });
        cloudMailState.activeTaskId = payload.id;
        cloudMailState.taskOffset = 0;
        await refreshTaskList();
        await refreshTaskDetail(true);
        toast.success('任务已启动');
    } catch (error) {
        toast.error(error.message || '启动失败');
        taskLogsEl.textContent = error.message || String(error);
    }
}

async function bootCloudMailConsole() {
    try {
        cloudMailState.presets = await api.get('/cloud-mail/workflows');
        cloudMailState.activeWorkflow = Object.keys(cloudMailState.presets.workflows)[0];
        renderWorkflowList();
        renderWorkflow();
        await loadMainDomains();
        await refreshTaskList();
        await refreshTaskDetail();
        setInterval(() => refreshTaskList().catch(() => {}), 2000);
        setInterval(() => refreshTaskDetail().catch(() => {}), 1200);
    } catch (error) {
        toast.error(error.message || 'Cloud Mail 工具台初始化失败');
        commandPreviewEl.textContent = error.message || String(error);
    }
}

workflowSearchEl?.addEventListener('input', renderWorkflowList);
previewButton?.addEventListener('click', requestPreview);
copyButton?.addEventListener('click', async () => {
    try {
        await navigator.clipboard.writeText(commandPreviewEl.innerText);
        toast.success('命令已复制');
    } catch (error) {
        toast.error('复制失败');
    }
});
refreshMainDomainsBtn?.addEventListener('click', loadMainDomains);
runButton?.addEventListener('click', runWorkflow);
tabLogs?.addEventListener('click', () => switchDetailTab('logs'));
tabResult?.addEventListener('click', () => switchDetailTab('result'));

document.addEventListener('DOMContentLoaded', () => {
    switchDetailTab('logs');
    bootCloudMailConsole();
});
