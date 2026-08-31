/**
 * FinanceFlow — Global Application JavaScript
 */

document.addEventListener('DOMContentLoaded', () => {
    // Sidebar toggle (desktop collapse)
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const mobileToggle = document.getElementById('mobileToggle');

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
        });

        // Restore state
        if (localStorage.getItem('sidebarCollapsed') === 'true') {
            sidebar.classList.add('collapsed');
        }
    }

    // Mobile sidebar toggle
    if (mobileToggle) {
        mobileToggle.addEventListener('click', () => {
            sidebar.classList.toggle('mobile-open');
        });

        // Close on overlay click
        document.addEventListener('click', (e) => {
            if (sidebar.classList.contains('mobile-open') &&
                !sidebar.contains(e.target) &&
                e.target !== mobileToggle) {
                sidebar.classList.remove('mobile-open');
            }
        });
    }

    // Auto-dismiss flash messages after 5 seconds
    document.querySelectorAll('.flash').forEach(flash => {
        setTimeout(() => {
            flash.style.opacity = '0';
            flash.style.transform = 'translateY(-10px)';
            setTimeout(() => flash.remove(), 300);
        }, 5000);
    });

    // Confirm delete actions
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', (e) => {
            if (!confirm(form.dataset.confirm || 'Are you sure?')) {
                e.preventDefault();
            }
        });
    });
});
