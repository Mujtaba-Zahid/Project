/**
 * FinanceFlow — Chart.js Configurations
 */

// Shared chart defaults for dark theme
const chartDefaults = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
        legend: {
            labels: {
                color: '#9ca3af',
                font: { family: 'Inter', size: 12 },
                padding: 16,
            }
        },
        tooltip: {
            backgroundColor: '#1a1f2e',
            titleColor: '#f9fafb',
            bodyColor: '#9ca3af',
            borderColor: 'rgba(255,255,255,0.06)',
            borderWidth: 1,
            padding: 12,
            cornerRadius: 8,
            titleFont: { family: 'Inter', weight: '600' },
            bodyFont: { family: 'Inter' },
        }
    },
    scales: {
        x: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: { color: '#6b7280', font: { family: 'Inter', size: 11 } },
        },
        y: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: { color: '#6b7280', font: { family: 'Inter', size: 11 } },
        }
    }
};

/**
 * Initialize the Income vs Expense trend line chart.
 */
function initIncomeExpenseChart(canvasId, dataUrl) {
    fetch(dataUrl)
        .then(res => res.json())
        .then(data => {
            const ctx = document.getElementById(canvasId);
            if (!ctx) return;

            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [
                        {
                            label: 'Income',
                            data: data.income,
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            fill: true,
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 4,
                            pointHoverRadius: 6,
                            pointBackgroundColor: '#10b981',
                        },
                        {
                            label: 'Expense',
                            data: data.expense,
                            borderColor: '#ef4444',
                            backgroundColor: 'rgba(239, 68, 68, 0.1)',
                            fill: true,
                            tension: 0.4,
                            borderWidth: 2,
                            pointRadius: 4,
                            pointHoverRadius: 6,
                            pointBackgroundColor: '#ef4444',
                        }
                    ]
                },
                options: {
                    ...chartDefaults,
                    plugins: {
                        ...chartDefaults.plugins,
                        legend: { ...chartDefaults.plugins.legend, position: 'top' }
                    }
                }
            });
        });
}

/**
 * Initialize the Spending by Category doughnut chart.
 */
function initSpendingCategoryChart(canvasId, dataUrl) {
    const colors = [
        '#6366f1', '#22d3ee', '#f59e0b', '#ef4444', '#10b981',
        '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#06b6d4'
    ];

    fetch(dataUrl)
        .then(res => res.json())
        .then(data => {
            const ctx = document.getElementById(canvasId);
            if (!ctx) return;

            new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: data.labels,
                    datasets: [{
                        data: data.data,
                        backgroundColor: colors.slice(0, data.labels.length),
                        borderColor: '#0a0e1a',
                        borderWidth: 3,
                        hoverOffset: 8,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    cutout: '65%',
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                color: '#9ca3af',
                                font: { family: 'Inter', size: 11 },
                                padding: 12,
                                usePointStyle: true,
                                pointStyleWidth: 8,
                            }
                        },
                        tooltip: chartDefaults.plugins.tooltip,
                    }
                }
            });
        });
}
