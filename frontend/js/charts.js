// Priority Distribution Chart
document.addEventListener('DOMContentLoaded', function() {
    initializePriorityChart();
});

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
    const priorityColors = ['#3B82F6', '#6B7280', '#F97316', '#EF4444']; // Updated to match our color system

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
                borderColor: '#fff'
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

    // Create custom legend with icons
    createCustomLegend(chartData, priorityLabels, priorityColors);
}

function createCustomLegend(chartData, labels, colors) {
    const legendContainer = document.getElementById('priorityLegend');
    if (!legendContainer) return;

    const priorityIcons = ['lucide-arrow-down', 'lucide-minus', 'lucide-arrow-up', 'lucide-circle-alert'];
    const priorityColorClasses = ['text-blue-500', 'text-gray-500', 'text-orange-500', 'text-red-500'];

    legendContainer.innerHTML = '';

    labels.forEach((label, index) => {
        const count = chartData[index];
        const icon = priorityIcons[index];
        const colorClass = priorityColorClasses[index];

        const legendItem = document.createElement('div');
        legendItem.className = 'flex items-center space-x-2 p-2 rounded hover:bg-gray-50';

        legendItem.innerHTML = `
            <svg class="h-3 w-3 ${colorClass}" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <use href="#${icon}"></use>
            </svg>
            <span class="text-gray-700">${label}</span>
            <span class="font-medium text-gray-900">${count}</span>
        `;

        legendContainer.appendChild(legendItem);
    });
}