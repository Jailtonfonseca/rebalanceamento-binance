document.addEventListener('DOMContentLoaded', function() {
    const loadingIndicator = document.getElementById('loading-indicator');
    const opportunitiesTable = document.getElementById('opportunities-table');
    const noOpportunitiesDiv = document.getElementById('no-opportunities');
    const errorMessageDiv = document.getElementById('error-message');
    const tableBody = document.querySelector('#arbitrage-table tbody');
    const rescanButton = document.getElementById('rescan-button');
    const jsStrings = document.getElementById('js-strings').dataset;

    async function fetchOpportunities() {
        // Show loading state
        loadingIndicator.style.display = 'block';
        opportunitiesTable.style.display = 'none';
        noOpportunitiesDiv.style.display = 'none';
        errorMessageDiv.style.display = 'none';
        rescanButton.disabled = true;

        try {
            const response = await fetch('/api/v1/arbitrage/opportunities');
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP error! Status: ${response.status}`);
            }
            const opportunities = await response.json();

            // Clear previous results
            tableBody.innerHTML = '';

            if (opportunities.length > 0) {
                opportunities.forEach(opp => {
                    const row = document.createElement('tr');

                    let ratesHtml = '';
                    for (const [pair, rate] of Object.entries(opp.rates)) {
                        ratesHtml += `<div>${pair}: ${rate}</div>`;
                    }

                    row.innerHTML = `
                        <td>${opp.path}</td>
                        <td>${opp.profit_margin_percent.toFixed(4)}%</td>
                        <td>${ratesHtml}</td>
                    `;
                    tableBody.appendChild(row);
                });
                opportunitiesTable.style.display = 'block';
            } else {
                noOpportunitiesDiv.style.display = 'block';
            }

        } catch (error) {
            console.error('Error fetching arbitrage opportunities:', error);
            errorMessageDiv.textContent = `${jsStrings.fetchFailed} ${error.message}`;
            errorMessageDiv.style.display = 'block';
        } finally {
            // Hide loading state
            loadingIndicator.style.display = 'none';
            rescanButton.disabled = false;
        }
    }

    // Initial fetch
    fetchOpportunities();

    // Rescan button event listener
    rescanButton.addEventListener('click', fetchOpportunities);
});
