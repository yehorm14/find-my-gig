document.addEventListener('DOMContentLoaded', function () {
    const filterBtn = document.getElementById('filter-btn');

    if (filterBtn) {
        filterBtn.addEventListener('click', function () {
            const instrumentFilter = document.getElementById('filter-instrument')?.value || '';
            const params = new URLSearchParams();
            if (instrumentFilter) params.append('instrument', instrumentFilter);
            if (document.getElementById('show-past-toggle')?.checked) params.append('show_past', '1');
            window.location.href = window.location.pathname + '?' + params.toString();
        });
    }
});

document.addEventListener('DOMContentLoaded', function () {
    const showPastToggle = document.getElementById('show-past-toggle');

    if (showPastToggle) {
        showPastToggle.addEventListener('change', function () {
            const params = new URLSearchParams(window.location.search);
            params.delete('page');
            if (this.checked) {
                params.set('show_past', '1');
            } else {
                params.delete('show_past');
            }
            window.location.href = window.location.pathname + '?' + params.toString();
        });
    }
});
