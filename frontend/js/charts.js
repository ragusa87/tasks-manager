// Stats-page doughnut charts (priority + status distribution). Colors come
// from the semantic theme tokens (resolved at init through theme.js, since
// canvas needs concrete values); the charts re-initialize whenever the
// effective theme changes.
import { resolveColor } from './theme.js';
import { formatBytes } from './charts-utils.js';

document.addEventListener('DOMContentLoaded', initializeCharts);
// Manual toggle and OS-level flips both re-render with the new palette.
document.addEventListener('themechange', initializeCharts);
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', initializeCharts);

function initializeCharts() {
    initializePriorityChart();
    initializeStatusChart();
    initializeDiskChart();
}

// status value -> [canvas color token, legend text class]
const STATUS_COLORS = {
    inbox: ['--color-cat-red', 'text-cat-red'],
    next_action: ['--color-accent', 'text-accent'],
    waiting_for: ['--color-cat-orange', 'text-cat-orange'],
    someday_maybe: ['--color-cat-purple', 'text-cat-purple'],
    reference: ['--color-cat-blue', 'text-cat-blue'],
    project: ['--color-body', 'text-body'],
    completed: ['--color-cat-green', 'text-cat-green'],
    cancelled: ['--color-faint', 'text-faint'],
};

// Overall repartition of the user's items by GTD status. Data comes from the
// json_script in charts_section.html: [{value, label, sprite, count}, ...]
// in status declaration order, zero counts included (shown in the legend,
// invisible in the doughnut).
function initializeStatusChart() {
    const canvas = document.getElementById('statusChart');
    const placeholder = document.getElementById('statusChartPlaceholder');
    const dataEl = document.getElementById('status-stats-data');
    if (!canvas || !placeholder || !dataEl) return;

    const stats = JSON.parse(dataEl.textContent);
    const colors = (stat) => STATUS_COLORS[stat.value] || ['--color-muted', 'text-muted'];

    if (window.statusChartInstance) {
        window.statusChartInstance.destroy();
    }

    if (!stats.some((stat) => stat.count > 0)) {
        placeholder.classList.remove('hidden');
        canvas.style.display = 'none';
        return;
    }
    placeholder.classList.add('hidden');
    canvas.style.display = 'block';

    window.statusChartInstance = new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
        data: {
            labels: stats.map((stat) => stat.label),
            datasets: [{
                data: stats.map((stat) => stat.count),
                backgroundColor: stats.map((stat) => resolveColor(colors(stat)[0])),
                borderWidth: 2,
                borderColor: resolveColor('--color-surface'),
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false, // Disable default legend, we'll create custom
                },
            },
        },
    });

    renderLegend('statusLegend', stats.map((stat) => ({
        label: stat.label,
        count: stat.count,
        icon: stat.sprite,
        colorClass: colors(stat)[1],
    })));
}

// document family value -> [canvas color token, legend text class]
const DISK_COLORS = {
    images: ['--color-cat-blue', 'text-cat-blue'],
    audio: ['--color-cat-purple', 'text-cat-purple'],
    other: ['--color-muted', 'text-muted'],
};

// Disk usage of the user's documents by content family. Data comes from the
// json_script in charts_section.html: [{value, label, sprite, size, count}]
// with sizes in bytes, formatted here for the tooltip and legend.
function initializeDiskChart() {
    const canvas = document.getElementById('diskChart');
    const placeholder = document.getElementById('diskChartPlaceholder');
    const dataEl = document.getElementById('disk-stats-data');
    if (!canvas || !placeholder || !dataEl) return;

    const stats = JSON.parse(dataEl.textContent);
    const colors = (stat) => DISK_COLORS[stat.value] || ['--color-muted', 'text-muted'];

    if (window.diskChartInstance) {
        window.diskChartInstance.destroy();
    }

    if (!stats.some((stat) => stat.size > 0)) {
        placeholder.classList.remove('hidden');
        canvas.style.display = 'none';
        return;
    }
    placeholder.classList.add('hidden');
    canvas.style.display = 'block';

    window.diskChartInstance = new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
        data: {
            labels: stats.map((stat) => stat.label),
            datasets: [{
                data: stats.map((stat) => stat.size),
                backgroundColor: stats.map((stat) => resolveColor(colors(stat)[0])),
                borderWidth: 2,
                borderColor: resolveColor('--color-surface'),
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false, // Disable default legend, we'll create custom
                },
                tooltip: {
                    callbacks: {
                        label: (context) => ` ${formatBytes(context.parsed)}`,
                    },
                },
            },
        },
    });

    renderLegend('diskLegend', stats.map((stat) => ({
        label: stat.label,
        count: formatBytes(stat.size),
        icon: stat.sprite,
        colorClass: colors(stat)[1],
    })));
}

function initializePriorityChart() {
    const canvas = document.getElementById('priorityChart');
    const placeholder = document.getElementById('priorityChartPlaceholder');
    if (!canvas || !placeholder) return;

    // Get priority stats from data attribute
    const priorityStatsRaw = canvas.dataset.priorityStats;
    const priorityData = [];

    if (priorityStatsRaw && priorityStatsRaw.trim()) {
        const pairs = priorityStatsRaw.split(',');
        pairs.forEach(pair => {
            const [priority, count] = pair.split(':').map(Number);
            if (!isNaN(priority) && !isNaN(count)) {
                priorityData.push({ priority, count });
            }
        });
    }

    const priorityLabels = ['Low', 'Normal', 'High', 'Urgent'];
    // Same mapping as GTDConfig.PRIORITY_COLORS (constants.py)
    const priorityColors = [
        resolveColor('--color-cat-blue'),
        resolveColor('--color-muted'),
        resolveColor('--color-cat-orange'),
        resolveColor('--color-cat-red'),
    ];

    // Process data for chart
    const chartData = [0, 0, 0, 0]; // Initialize for priorities 1-4
    priorityData.forEach(item => {
        if (item.priority >= 1 && item.priority <= 4) {
            chartData[item.priority - 1] = item.count;
        }
    });

    // Check if there's any data
    const hasData = chartData.some(count => count > 0);

    // Destroy existing chart if it exists
    if (window.priorityChartInstance) {
        window.priorityChartInstance.destroy();
    }

    if (!hasData) {
        // Show placeholder, hide canvas
        placeholder.classList.remove('hidden');
        canvas.style.display = 'none';
        return;
    }

    // Hide placeholder, show canvas
    placeholder.classList.add('hidden');
    canvas.style.display = 'block';

    const ctx = canvas.getContext('2d');

    window.priorityChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: priorityLabels,
            datasets: [{
                data: chartData,
                backgroundColor: priorityColors,
                borderWidth: 2,
                borderColor: resolveColor('--color-surface')
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false // Disable default legend, we'll create custom
                }
            }
        }
    });

    // Same mapping as GTDConfig.PRIORITY_ICONS / PRIORITY_COLORS (constants.py)
    const priorityIcons = ['lucide-arrow-down', 'lucide-minus', 'lucide-arrow-up', 'lucide-circle-alert'];
    const priorityColorClasses = ['text-cat-blue', 'text-muted', 'text-cat-orange', 'text-cat-red'];
    renderLegend('priorityLegend', priorityLabels.map((label, index) => ({
        label,
        count: chartData[index],
        icon: priorityIcons[index],
        colorClass: priorityColorClasses[index],
    })));
}

// Custom legend with sprite icons, shared by both charts.
// entries: [{label, count, icon, colorClass}]
function renderLegend(containerId, entries) {
    const legendContainer = document.getElementById(containerId);
    if (!legendContainer) return;

    legendContainer.innerHTML = '';

    entries.forEach(({ label, count, icon, colorClass }) => {
        const legendItem = document.createElement('div');
        legendItem.className = 'flex items-center space-x-2 p-2 rounded hover:bg-ground';

        legendItem.innerHTML = `
            <svg class="h-3 w-3 ${colorClass}" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <use href="#${icon}"></use>
            </svg>
            <span class="text-muted">${label}</span>
            <span class="font-medium text-body">${count}</span>
        `;

        legendContainer.appendChild(legendItem);
    });
}
