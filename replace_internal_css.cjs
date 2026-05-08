const fs = require('fs');
const file = '/Users/a0000/projects/pharmaide/src/styles.css';
const content = fs.readFileSync(file, 'utf8');
const lines = content.split('\n');

const newCSS = `
/* --- APP SHELL / DASHBOARD LAYOUT --- */
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: #f8f9ff;
  color: #000000;
  font-family: 'Public Sans', sans-serif;
}

/* Sidebar */
.sidebar {
  width: 256px;
  background: #131b2e;
  color: #7c839b;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e2e8f0;
  z-index: 40;
}

.sidebar__header {
  padding: 24px 16px;
}

.sidebar__header h1 {
  font-size: 24px;
  line-height: 32px;
  font-weight: 700;
  color: #ffffff;
  margin: 0 0 4px 0;
  letter-spacing: -0.02em;
}

.sidebar__header p {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #bec6e0;
  margin: 0;
}

.sidebar-action-btn {
  margin: 0 16px 24px 16px;
  background: #ffffff;
  color: #131b2e;
  border: 1px solid #e2e8f0;
  padding: 8px 16px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 150ms ease;
}

.sidebar-action-btn:hover {
  background: #f1f5f9;
}

.sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  padding: 0 16px;
}

.sidebar__link {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  color: #818486;
  font-size: 14px;
  text-decoration: none;
  transition: all 150ms ease;
}

.sidebar__link:hover {
  background: #1e293b;
  color: #ffffff;
}

.sidebar__link--active {
  background: #d5e3fd;
  color: #131b2e;
  font-weight: 500;
  transform: translateX(4px);
}

.sidebar__link--active:hover {
  background: #d5e3fd;
  color: #131b2e;
}

.sidebar__footer {
  padding: 24px 16px;
  border-top: 1px solid #1e293b;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: auto;
}

.pharmacist-avatar {
  width: 40px;
  height: 40px;
  border-radius: 9999px;
  background: #1e293b;
  border: 1px solid #334155;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
}

.sidebar__footer-text p:first-child {
  font-size: 13px;
  color: #ffffff;
  margin: 0;
}

.sidebar__footer-text p:last-child {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #7c839b;
  margin: 0;
}

/* Main Workspace */
.workspace {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: #f8f9ff;
}

/* Topbar */
.topbar {
  height: 64px;
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  z-index: 30;
}

.topbar-search {
  position: relative;
  width: 320px;
}

.topbar-search svg {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: #64748b;
}

.topbar-search input {
  width: 100%;
  padding: 8px 16px 8px 36px;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  background: #f8f9ff;
  font-size: 14px;
  outline: none;
  transition: border-color 150ms ease;
}

.topbar-search input:focus {
  border-color: #000000;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 24px;
}

.topbar-actions-icons {
  display: flex;
  align-items: center;
  gap: 12px;
}

.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 9999px;
  border: 0;
  background: transparent;
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 150ms ease;
  position: relative;
}

.icon-btn:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.notification-dot {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 8px;
  height: 8px;
  background: #b91c1c;
  border-radius: 9999px;
}

.topbar-profile {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-left: 24px;
  border-left: 1px solid #e2e8f0;
}

.profile-circle {
  width: 32px;
  height: 32px;
  background: #e5eeff;
  color: #000000;
  border-radius: 9999px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}

/* Page Content Container */
.page-content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Page Headers */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.page-header h2 {
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.02em;
  margin: 0 0 4px 0;
  color: #000000;
}

.page-header p {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}

.page-actions {
  display: flex;
  gap: 12px;
}

.secondary-btn {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 14px;
  color: #000000;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 150ms ease;
}

.secondary-btn:hover {
  background: #f8f9ff;
}

.primary-btn {
  background: #000000;
  border: 1px solid #000000;
  color: #ffffff;
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: opacity 150ms ease;
}

.primary-btn:hover {
  opacity: 0.9;
}

/* Modules / Cards */
.module {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
}

.module__header {
  padding: 20px 24px;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.module__header h3 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: #000000;
}

.module__header p {
  font-size: 13px;
  color: #64748b;
  margin: 4px 0 0 0;
}

/* Tables (Surveillance & Interventions) */
.table-wrap {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

.data-table th {
  padding: 12px 16px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #64748b;
  background: #f8f9ff;
  border-bottom: 1px solid #e2e8f0;
  position: sticky;
  top: 0;
  z-index: 10;
}

.data-table td {
  padding: 16px;
  border-bottom: 1px solid #e2e8f0;
  vertical-align: top;
}

.data-table tbody tr {
  transition: background 150ms ease;
}

.data-table tbody tr:hover {
  background: #f8f9ff;
}

/* Patient Row Specifics */
.patient-cell {
  display: flex;
  flex-direction: column;
}

.patient-id {
  font-weight: 500;
  color: #000000;
  font-variant-numeric: tabular-nums;
}

.patient-name-blur {
  font-size: 12px;
  color: #64748b;
  filter: blur(4px);
  transition: filter 300ms ease;
}

tr:hover .patient-name-blur {
  filter: blur(0);
}

.adherence-bars {
  display: flex;
  align-items: center;
  gap: 4px;
}

.adherence-bar {
  width: 8px;
  height: 24px;
  border-radius: 2px;
}

.bar-error { background: #b91c1c; }
.bar-warning { background: #515f74; }
.bar-stable { background: #131b2e; }
.bar-empty { background: #e2e8f0; }

/* Clinical Chips */
.clinical-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.chip-high-risk {
  background: #b91c1c;
  color: #ffffff;
}

.chip-elevated {
  background: #dce9ff;
  color: #000000;
  border: 1px solid #c6c6cd;
}

.chip-stable {
  background: #eff4ff;
  color: #45464d;
  border: 1px solid #c6c6cd;
}

/* Triage Queue Specifics */
.dashboard-grid-layout {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 24px;
}

.alert-banner {
  background: #ba1a1a;
  color: #ffffff;
  padding: 12px 16px;
  border-radius: 4px;
  border: 1px solid #ffdad6;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
  grid-column: 1 / -1;
  margin-bottom: 24px;
}

.escalation-list {
  display: flex;
  flex-direction: column;
  padding: 16px;
  gap: 12px;
}

.escalation-card {
  padding: 16px;
  border-radius: 4px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.escalation-card--critical {
  background: #fff5f5;
  border: 1px solid rgba(185, 28, 28, 0.2);
}

.escalation-card--warning {
  background: #ffffff;
  border: 1px solid #e2e8f0;
}

.system-health-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding: 16px;
}

.health-metric {
  background: #f8f9ff;
  border: 1px solid #e2e8f0;
  padding: 12px;
  border-radius: 4px;
}

.health-metric p {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #64748b;
  margin: 0 0 4px 0;
}

.health-metric strong {
  font-size: 24px;
  color: #000000;
}

/* Heatmaps Specifics */
.heatmap-layout {
  display: flex;
  gap: 24px;
}

.heatmap-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.heatmap-controls {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.heatmap-filter-group {
  display: flex;
  gap: 16px;
}

.heatmap-filter {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.heatmap-filter label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #64748b;
}

.heatmap-filter select {
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  background: #f8f9ff;
  font-size: 13px;
  outline: none;
}

.heatmap-legend {
  display: flex;
  gap: 16px;
  background: #f8f9ff;
  border: 1px solid #e2e8f0;
  padding: 6px 16px;
  border-radius: 4px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.legend-box {
  width: 12px;
  height: 12px;
  border-radius: 2px;
}
.box-taken { background: #000000; }
.box-missed { background: #b91c1c; }
.box-nodata { background: #d3e4fe; }

.heatmap-matrix {
  overflow-x: auto;
  padding: 16px;
}

.heatmap-row {
  display: flex;
  align-items: center;
  padding: 4px 0;
}

.heatmap-row:hover {
  background: #f8f9ff;
}

.heatmap-pt-id {
  width: 120px;
  flex-shrink: 0;
  font-family: 'Public Sans', monospace;
  font-size: 13px;
  color: #000000;
}

.heatmap-pt-id.critical {
  color: #b91c1c;
  font-weight: 700;
}

.heatmap-cells {
  display: flex;
  gap: 4px;
}

.h-cell {
  width: 12px;
  height: 12px;
  border-radius: 2px;
}

.h-taken { background: #000000; }
.h-missed { background: #b91c1c; }
.h-nodata { background: #d3e4fe; }

.critical-alerts-sidebar {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.alert-card-side {
  background: #eff4ff;
  border-left: 4px solid #b91c1c;
  padding: 12px;
  border-radius: 0 4px 4px 0;
}

.alert-card-side--nodata {
  border-left-color: #76777d;
}

.alert-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 4px;
}

.alert-pt {
  font-family: 'Public Sans', monospace;
  font-size: 13px;
  font-weight: 700;
}

.alert-badge {
  background: #ffdad6;
  color: #ba1a1a;
  padding: 2px 4px;
  border-radius: 2px;
  font-size: 10px;
  font-weight: 700;
}
\n`;

const startIndex = lines.findIndex(l => l.startsWith('.app-shell {'));

if (startIndex !== -1) {
  // Replace from startIndex to the end of the file with the new dashboard CSS
  const result = lines.slice(0, startIndex).join('\n') + '\n' + newCSS;
  fs.writeFileSync(file, result, 'utf8');
  console.log('Successfully replaced old dashboard CSS starting at line', startIndex);
} else {
  console.log('Failed to find .app-shell { in styles.css');
}
