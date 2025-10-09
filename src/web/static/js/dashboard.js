document.addEventListener('DOMContentLoaded', function () {
    const runBtn = document.getElementById('run-rebalance-btn');
    const dryRunBtn = document.getElementById('run-dry-run-btn');
    const alertPlaceholder = document.getElementById('alert-placeholder');

    function createAlert(message, type = 'danger') {
        const wrapper = document.createElement('div');
        wrapper.innerHTML = `<div class="alert alert-${type}" role="alert">${message}</div>`;
        alertPlaceholder.innerHTML = ''; // Clear previous alerts
        alertPlaceholder.append(wrapper);
        window.scrollTo(0, 0);
    }

    async function runRebalance(isDryRun) {
        const btn = isDryRun ? dryRunBtn : runBtn;
        btn.textContent = 'Executando...';
        btn.disabled = true;
        if (isDryRun) runBtn.disabled = true; else dryRunBtn.disabled = true;

        try {
            const response = await fetch(`/api/v1/rebalance/run?dry=${isDryRun}`, {
                method: 'POST'
            });
            const result = await response.json();

            if (response.ok) {
                createAlert(`Execução ${result.status}: ${result.message}`, 'success');
                setTimeout(() => window.location.reload(), 2000);
            } else {
                createAlert(`Falha ao iniciar a execução: ${result.detail || 'Erro desconhecido'}`);
            }
        } catch (error) {
            createAlert(`Ocorreu um erro: ${error.message}`);
        } finally {
            runBtn.textContent = 'Executar Rebalanceamento';
            dryRunBtn.textContent = 'Executar Simulação';
            runBtn.disabled = false;
            dryRunBtn.disabled = false;
        }
    }

    runBtn.addEventListener('click', () => runRebalance(false));
    dryRunBtn.addEventListener('click', () => runRebalance(true));

    // Fetch and display balances
    async function fetchBalances() {
        const loadingDiv = document.getElementById('balances-loading');
        const contentDiv = document.getElementById('balances-content');
        const errorDiv = document.getElementById('balances-error');
        const tableBody = document.getElementById('balances-table-body');
        const totalBalanceBaseEl = document.getElementById('total-balance-base');
        const totalBalanceUsdEl = document.getElementById('total-balance-usd');
        const baseConversionEl = document.getElementById('base-conversion-note');
        const valueHeaderBase = document.getElementById('value-header-base');

        try {
            const response = await fetch('/api/v1/status/balances');
            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            const basePair = data.base_pair || 'USDT';
            const baseFormatter = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

            valueHeaderBase.textContent = `Valor (${basePair})`;

            const totalBase = Number(data.total_value_in_base ?? 0);
            totalBalanceBaseEl.textContent = `${baseFormatter.format(totalBase)} ${basePair}`;

            if (typeof data.total_value_usd === 'number' && !Number.isNaN(data.total_value_usd)) {
                totalBalanceUsdEl.textContent = `≈ ${currencyFormatter.format(data.total_value_usd)}`;
                totalBalanceUsdEl.style.display = '';
            } else {
                totalBalanceUsdEl.textContent = '';
                totalBalanceUsdEl.style.display = 'none';
            }

            if (data.base_to_usd_rate) {
                baseConversionEl.textContent = `1 ${basePair} ≈ ${currencyFormatter.format(data.base_to_usd_rate)}`;
            } else {
                baseConversionEl.textContent = '';
            }

            tableBody.innerHTML = '';

            const sortedAssets = Object.keys(data.balances).sort((a, b) => {
                const assetA = data.balances[a] || {};
                const assetB = data.balances[b] || {};
                const valueA = assetA.value_usd ?? assetA.value_in_base ?? 0;
                const valueB = assetB.value_usd ?? assetB.value_in_base ?? 0;
                return valueB - valueA;
            });

            for (const asset of sortedAssets) {
                const balance = data.balances[asset];
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${asset}</td>
                    <td>${quantityFormatter.format(Number(balance.quantity))}</td>
                    <td>${baseFormatter.format(Number(balance.value_in_base ?? 0))} ${basePair}</td>
                    <td>${balance.value_usd !== undefined ? currencyFormatter.format(Number(balance.value_usd)) : '—'}</td>
                `;
                tableBody.appendChild(row);
            }

            loadingDiv.style.display = 'none';
            contentDiv.style.display = 'block';

        } catch (error) {
            loadingDiv.style.display = 'none';
            errorDiv.textContent = `Não foi possível carregar os saldos: ${error.message}`;
            errorDiv.style.display = 'block';
        }
    }

    const currencyFormatter = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
    const quantityFormatter = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 8 });
    const chartPalette = [
        { border: '#0d6efd', background: 'rgba(13, 110, 253, 0.12)' },
        { border: '#20c997', background: 'rgba(32, 201, 151, 0.12)' },
        { border: '#d63384', background: 'rgba(214, 51, 132, 0.12)' },
        { border: '#fd7e14', background: 'rgba(253, 126, 20, 0.12)' },
        { border: '#6610f2', background: 'rgba(102, 16, 242, 0.12)' },
        { border: '#198754', background: 'rgba(25, 135, 84, 0.12)' },
        { border: '#6c757d', background: 'rgba(108, 117, 125, 0.12)' },
        { border: '#0dcaf0', background: 'rgba(13, 202, 240, 0.12)' },
    ];

    async function fetchPortfolioHistory() {
        const portfolioWrapper = document.getElementById('portfolio-history-wrapper');
        const portfolioCanvas = document.getElementById('portfolio-history-chart');
        const portfolioEmpty = document.getElementById('portfolio-history-empty');
        const assetContainer = document.getElementById('asset-charts-container');
        const assetEmpty = document.getElementById('asset-charts-empty');

        if (!portfolioWrapper || !portfolioCanvas || !assetContainer || typeof Chart === 'undefined') {
            return;
        }

        try {
            const response = await fetch('/api/v1/history/portfolio-stats');
            if (!response.ok) {
                throw new Error('Resposta inválida do servidor');
            }
            const data = await response.json();

            const portfolioData = Array.isArray(data.portfolio) ? data.portfolio : [];
            if (portfolioData.length === 0) {
                portfolioWrapper.style.display = 'none';
                portfolioEmpty.style.display = 'block';
            } else {
                portfolioEmpty.style.display = 'none';
                portfolioWrapper.style.display = 'block';
                const labels = portfolioData.map(point => new Date(point.timestamp).toLocaleString('pt-BR'));
                const values = portfolioData.map(point => Number(point.total_value_usd ?? 0));

                const existingPortfolioChart = Chart.getChart(portfolioCanvas);
                if (existingPortfolioChart) {
                    existingPortfolioChart.destroy();
                }

                new Chart(portfolioCanvas.getContext('2d'), {
                    type: 'line',
                    data: {
                        labels,
                        datasets: [{
                            label: 'Valor da carteira (USD)',
                            data: values,
                            borderColor: '#0d6efd',
                            backgroundColor: 'rgba(13, 110, 253, 0.12)',
                            tension: 0.25,
                            fill: true,
                            pointRadius: 3,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                ticks: {
                                    callback: (value) => currencyFormatter.format(value ?? 0),
                                }
                            }
                        },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: (context) => `Valor: ${currencyFormatter.format(context.parsed.y ?? 0)}`,
                                }
                            }
                        }
                    }
                });
            }

            const assetEntries = Object.entries(data.assets || {}).filter(([, points]) => Array.isArray(points) && points.length > 0);
            assetContainer.innerHTML = '';

            if (assetEntries.length === 0) {
                assetEmpty.style.display = 'block';
            } else {
                assetEmpty.style.display = 'none';
                let colorIndex = 0;

                for (const [asset, points] of assetEntries) {
                    const wrapper = document.createElement('div');
                    wrapper.className = 'asset-chart';

                    const title = document.createElement('h4');
                    title.textContent = asset;
                    wrapper.appendChild(title);

                    const chartWrapper = document.createElement('div');
                    chartWrapper.className = 'chart-wrapper';

                    const canvas = document.createElement('canvas');
                    canvas.height = 220;
                    chartWrapper.appendChild(canvas);

                    wrapper.appendChild(chartWrapper);

                    assetContainer.appendChild(wrapper);

                    const labels = points.map(point => new Date(point.timestamp).toLocaleString('pt-BR'));
                    const values = points.map(point => Number(point.value_usd ?? 0));
                    const quantities = points.map(point => point.quantity !== undefined && point.quantity !== null ? Number(point.quantity) : null);

                    const paletteEntry = chartPalette[colorIndex % chartPalette.length];
                    colorIndex += 1;

                    new Chart(canvas.getContext('2d'), {
                        type: 'line',
                        data: {
                            labels,
                            datasets: [{
                                label: `Valor de ${asset} (USD)`,
                                data: values,
                                borderColor: paletteEntry.border,
                                backgroundColor: paletteEntry.background,
                                tension: 0.25,
                                fill: true,
                                pointRadius: 2.5,
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: {
                                y: {
                                    ticks: {
                                        callback: (value) => currencyFormatter.format(value ?? 0),
                                    }
                                }
                            },
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    callbacks: {
                                        label: (context) => {
                                            const idx = context.dataIndex;
                                            const parts = [`Valor: ${currencyFormatter.format(context.parsed.y ?? 0)}`];
                                            const quantity = quantities[idx];
                                            if (quantity !== null) {
                                                parts.push(`Quantidade: ${quantityFormatter.format(quantity)}`);
                                            }
                                            return parts;
                                        }
                                    }
                                }
                            }
                        }
                    });
                }
            }
        } catch (error) {
            console.error('Erro ao carregar histórico da carteira', error);
            if (portfolioWrapper) {
                portfolioWrapper.style.display = 'none';
            }
            if (portfolioEmpty) {
                portfolioEmpty.textContent = `Não foi possível carregar o histórico da carteira: ${error.message}`;
                portfolioEmpty.style.display = 'block';
            }
            if (assetContainer) {
                assetContainer.innerHTML = '';
            }
            if (assetEmpty) {
                assetEmpty.textContent = `Não foi possível carregar os gráficos dos ativos: ${error.message}`;
                assetEmpty.style.display = 'block';
            }
        }
    }

    fetchBalances();
    fetchPortfolioHistory();
});