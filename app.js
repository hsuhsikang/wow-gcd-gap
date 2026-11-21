const DEFAULT_REPORT = 'https://www.warcraftlogs.com/reports/tKGJ2NCQvfxRwMd3?fight=22&type=casts&source=17&view=events';
const $ = id => document.getElementById(id);
let currentReport;
let videoObjectUrl;

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
  const totalIdle = rows.reduce((sum, gap) => sum + gap.idle, 0);
  const totalGcds = rows.reduce((sum, gap) => sum + gap.idle / gap.gcd, 0);
  $('totalGaps').textContent = rows.length.toLocaleString();
  $('totalGcds').textContent = totalGcds.toFixed(2);
  const totalGcdOpportunities = Number(currentReport.gcdActionCount) + totalGcds;
  $('gcdLossPercent').textContent = totalGcdOpportunities > 0
    ? `${(totalGcds / totalGcdOpportunities * 100).toFixed(1)}%`
    : '—';
  $('totalSeconds').textContent = duration(totalIdle);
  $('gapRows').innerHTML = rows.map(gap => `
    <tr class="gap-row" tabindex="0" role="button" aria-label="Review gap beginning at ${formatTime(gap.coverageEnd, currentReport.fightStart)}" data-video-time="${(gap.coverageEnd - currentReport.fightStart) / 1000}">
      <td class="gap-value">${(gap.idle / gap.gcd).toFixed(2)}</td>
      <td class="time">${duration(gap.idle)}</td>
      <td><span class="time">${formatTime(gap.fromTime, currentReport.fightStart)}</span><br><span class="ability">${escapeHtml(gap.fromAbility)}</span></td>
      <td><span class="time">${formatTime(gap.toTime, currentReport.fightStart)}</span><br><span class="ability">${escapeHtml(gap.toAbility)}</span></td>
      <td class="time">${duration(gap.gcd)}</td>
      <td class="time">${duration(gap.interval)}</td>
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
$('videoFile').addEventListener('change', event => {
  const file = event.target.files?.[0];
  if (!file) return;
  if (videoObjectUrl) URL.revokeObjectURL(videoObjectUrl);
  videoObjectUrl = URL.createObjectURL(file);
  const video = $('fightVideo');
  video.src = videoObjectUrl;
  video.hidden = false;
  $('videoHint').textContent = `${file.name} · Set the fight-start offset if the video begins before the fight.`;
});
$('gapRows').addEventListener('click', event => {
  const row = event.target.closest('.gap-row');
  if (row) seekVideoToGap(row);
});
$('gapRows').addEventListener('keydown', event => {
  const row = event.target.closest('.gap-row');
  if (row && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault();
    seekVideoToGap(row);
  }
});

function seekVideoToGap(row) {
  const video = $('fightVideo');
  if (!video.src) {
    $('videoHint').textContent = 'Choose a local video first, then select a gap row.';
    $('videoFile').focus();
    return;
  }
  const offset = Math.max(0, Number($('videoOffset').value) || 0);
  const target = Math.max(0, Number(row.dataset.videoTime) + offset);
  try {
    video.currentTime = Number.isFinite(video.duration) ? Math.min(target, video.duration) : target;
  } catch (error) {
    $('videoHint').textContent = 'The video is still loading. Select the gap again when it is ready.';
    return;
  }
  video.scrollIntoView({behavior: 'smooth', block: 'center'});
  video.focus({preventScroll: true});
  video.play().then(() => {
    $('videoHint').textContent = 'Playing from the start of the uncovered interval. Press pause whenever you want to stop.';
  }).catch(() => {
    $('videoHint').textContent = 'Playback was blocked by the browser. Press play on the video to continue.';
  });
}

try {
  const response = await fetch('./data/gcd-report.json');
  if (!response.ok) throw new Error('Sample report not found');
  render(await response.json());
} catch (error) {
  showStatus('The sample report could not be loaded. Start this project with python3 server.py.', true);
}
