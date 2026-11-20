const DEFAULT_REPORT = 'https://www.warcraftlogs.com/reports/tKGJ2NCQvfxRwMd3?fight=22&type=casts&source=17&view=events';
const $ = id => document.getElementById(id);
let currentReport;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
function formatTime(timestamp, fightStart) {
  const seconds = Math.max(0, (timestamp - fightStart) / 1000);
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2,'0')}:${(seconds - minutes * 60).toFixed(3).padStart(6,'0')}`;
}
function duration(value) { return `${(value / 1000).toFixed(3)}s`; }

function showStatus(message, isError = false) {
  const status = $('status');
  status.hidden = !message;
  status.classList.toggle('error', isError);
  status.textContent = message;
}

function render(report) {
  currentReport = report;
  $('reportContent').hidden = false;
  $('fightName').textContent = report.encounter || 'Encounter';
  const mode = report.difficulty === 5 ? 'Mythic' : `Difficulty ${report.difficulty ?? '—'}`;
  $('fightDetails').textContent = `${mode} · ${report.kill ? 'Kill' : 'Encounter'} · ${(report.fightDuration / 60000).toFixed(2)} min · ${report.playerName}`;
  $('eventCount').textContent = Number(report.eventCount).toLocaleString();
  $('actionCount').textContent = Number(report.gcdActionCount).toLocaleString();
  $('gapCount').textContent = report.gapCount;
  $('gcdRange').textContent = `${(report.gcdRange[0] / 1000).toFixed(2)}–${(report.gcdRange[1] / 1000).toFixed(2)}s`;
  $('hasteRange').textContent = `${(report.hasteRange[0] * 100).toFixed(1)}–${(report.hasteRange[1] * 100).toFixed(1)}%`;
  const link = new URL(`https://www.warcraftlogs.com/reports/${report.reportCode}`);
  link.searchParams.set('fight', report.fightId);
  link.searchParams.set('type', 'casts');
  link.searchParams.set('source', report.playerId);
  link.searchParams.set('view', 'events');
  $('openReport').href = link.toString();
  renderRows();
}

function renderRows() {
  if (!currentReport) return;
  const minGap = Math.max(0, Number($('minimumGap').value) || 0) * 1000;
  const rows = currentReport.gaps.filter(gap => gap.idle >= minGap);
  $('gapRows').innerHTML = rows.map(gap => `
    <tr>
      <td class="gap-value">${duration(gap.idle)}</td>
      <td><span class="time">${formatTime(gap.fromTime, currentReport.fightStart)}</span><br><span class="ability">${escapeHtml(gap.fromAbility)}</span></td>
      <td class="time">${duration(gap.gcd)}</td>
      <td class="time">${duration(gap.interval)}</td>
      <td><span class="time">${formatTime(gap.toTime, currentReport.fightStart)}</span><br><span class="ability">${escapeHtml(gap.toAbility)}</span></td>
    </tr>`).join('');
  $('emptyState').hidden = rows.length > 0;
}

async function analyzeUrl(url, playerName) {
  $('analyzeButton').disabled = true;
  $('reportContent').hidden = true;
  showStatus('Loading fight events, combatant stats, and haste changes from the report…');
  try {
    const query = new URLSearchParams({url, player: playerName || 'Irohaa'});
    const response = await fetch(`/api/analyze?${query}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Report could not be analyzed.');
    showStatus('');
    render(data);
  } catch (error) {
    showStatus(`${error.message} Start this project with python3 server.py.`, true);
  } finally {
    $('analyzeButton').disabled = false;
  }
}

$('reportUrl').value = DEFAULT_REPORT;
$('reportForm').addEventListener('submit', event => {
  event.preventDefault();
  analyzeUrl($('reportUrl').value, $('playerName').value.trim());
});
$('minimumGap').addEventListener('input', renderRows);

try {
  const response = await fetch('./data/gcd-report.json');
  if (!response.ok) throw new Error('Sample report not found');
  render(await response.json());
} catch (error) {
  showStatus('The sample report could not be loaded. Start this project with python3 server.py.', true);
}
