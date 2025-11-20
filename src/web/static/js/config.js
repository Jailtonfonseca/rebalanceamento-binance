document.addEventListener('DOMContentLoaded', function () {
    const allocationsContainer = document.getElementById('allocations-container');
    const addAllocBtn = document.getElementById('add-alloc-btn');
    const totalPctSpan = document.getElementById('total-alloc-pct');
    const form = document.getElementById('config-form');
    const saveBtn = document.getElementById('save-btn');
    const testKeysBtn = document.getElementById('test-keys-btn');
    const alertPlaceholder = document.getElementById('alert-placeholder');
    const jsStrings = document.getElementById('js-strings').dataset;

    function createAlert(message, type = 'danger') {
        const wrapper = document.createElement('div');
        wrapper.innerHTML = `<div class="alert alert-${type}" role="alert">${message}</div>`;
        alertPlaceholder.innerHTML = ''; // Clear previous alerts
        alertPlaceholder.append(wrapper);
    }

    function calculateTotalAllocation() {
        let total = 0;
        document.querySelectorAll('.alloc-pct').forEach(input => {
            total += parseFloat(input.value) || 0;
        });
        totalPctSpan.textContent = total.toFixed(1);
        totalPctSpan.style.color = Math.round(total) === 100 ? 'var(--success-color)' : 'var(--danger-color)';
    }

    function addAllocationRow(symbol = '', pct = '') {
        const div = document.createElement('div');
        div.className = 'allocation-item';
        div.innerHTML = `
            <input type="text" placeholder="${jsStrings.assetPlaceholder}" value="${symbol.toUpperCase()}" class="alloc-symbol">
            <input type="number" placeholder="%" value="${pct}" min="0" max="100" step="0.1" class="alloc-pct">
            <button type="button" class="remove-alloc-btn">&times;</button>
        `;
        allocationsContainer.appendChild(div);
        div.querySelector('.remove-alloc-btn').addEventListener('click', () => div.remove());
        div.querySelector('.alloc-pct').addEventListener('input', calculateTotalAllocation);
    }

    addAllocBtn.addEventListener('click', () => addAllocationRow());

    allocationsContainer.addEventListener('click', function(e) {
        if (e.target.classList.contains('remove-alloc-btn')) {
            e.target.closest('.allocation-item').remove();
            calculateTotalAllocation();
        }
    });

    allocationsContainer.addEventListener('input', function(e) {
        if (e.target.classList.contains('alloc-pct')) {
            calculateTotalAllocation();
        }
    });

    // Handle form submission
    form.addEventListener('submit', async function (e) {
        e.preventDefault();
        saveBtn.textContent = jsStrings.saving;
        saveBtn.disabled = true;

        const formData = new FormData();
        // Collect all form data
        new FormData(form).forEach((value, key) => {
            // We handle allocations separately
            if (!key.startsWith('allocations[')) {
                formData.append(key, value);
            }
        });

        // Collect allocations correctly
        document.querySelectorAll('.allocation-item').forEach(item => {
            const symbol = item.querySelector('.alloc-symbol').value.toUpperCase();
            const pct = item.querySelector('.alloc-pct').value;
            if (symbol && pct) {
                formData.append(`allocations[${symbol}]`, pct);
            }
        });

        try {
            const response = await fetch('/api/v1/config', {
                method: 'POST',
                body: new URLSearchParams(formData) // FastAPI Form depends on this format
            });

            if (response.ok) {
                createAlert(jsStrings.configSaved, 'success');
                // Optionally reload or update UI
                setTimeout(() => window.location.reload(), 1000);
            } else {
                const errorData = await response.json();
                createAlert(`${jsStrings.saveFailed} ${errorData.detail || jsStrings.unknownError}`);
            }
        } catch (error) {
            createAlert(`${jsStrings.genericError} ${error.message}`);
        } finally {
            saveBtn.textContent = jsStrings.saveConfiguration;
            saveBtn.disabled = false;
        }
    });

    // Handle Test API Keys
    testKeysBtn.addEventListener('click', async function () {
        testKeysBtn.textContent = jsStrings.testing;
        testKeysBtn.disabled = true;

        // First, save the current keys in the form if any are entered
        await fetch('/api/v1/config', {
            method: 'POST',
            body: new URLSearchParams(new FormData(form))
        });

        try {
            const response = await fetch('/api/v1/config/test-keys', { method: 'POST' });
            const result = await response.json();

            if (response.ok) {
                let report = `<strong>${jsStrings.apiTestResults}</strong><br>`;
                report += `Binance: <span style="color:var(--success-color)">${result.binance.message}</span><br>`;
                report += `CoinMarketCap: <span style="color:var(--success-color)">${result.cmc.message}</span>`;
                createAlert(report, 'success');
            } else {
                 let report = `<strong>${jsStrings.apiTestResults}</strong><br>`;
                 const details = result.detail;
                 report += `Binance: <span style="color:${details.binance.status === 'success' ? 'var(--success-color)' : 'var(--danger-color)'}">${details.binance.message}</span><br>`;
                 report += `CoinMarketCap: <span style="color:${details.cmc.status === 'success' ? 'var(--success-color)' : 'var(--danger-color)'}">${details.cmc.message}</span>`;
                 createAlert(report, 'danger');
            }
        } catch (error) {
            createAlert(`${jsStrings.genericError} ${error.message}`);
        } finally {
            testKeysBtn.textContent = jsStrings.testApiKeys;
            testKeysBtn.disabled = false;
        }
    });

    // Initial calculation
    calculateTotalAllocation();
});
