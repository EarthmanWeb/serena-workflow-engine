const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const os = require('os');

let outputChannel;
let fileWatcher;
let dirWatcher;
let currentFile;
let currentOffset = 0;

function getSerenaHome() {
  return process.env.SERENA_HOME || path.join(os.homedir(), '.serena');
}

function getTodayLogDir() {
  const now = new Date();
  const dateStr = now.toISOString().slice(0, 10);
  return path.join(getSerenaHome(), 'logs', dateStr);
}

function findLatestLogFile(logDir) {
  let files;
  try {
    files = fs.readdirSync(logDir).filter(f => f.startsWith('mcp_') && f.endsWith('.txt'));
  } catch {
    return null;
  }
  if (files.length === 0) return null;

  let latest = null;
  let latestMtime = 0;
  for (const file of files) {
    const fullPath = path.join(logDir, file);
    const stat = fs.statSync(fullPath);
    if (stat.mtimeMs > latestMtime) {
      latestMtime = stat.mtimeMs;
      latest = fullPath;
    }
  }
  return latest;
}

function readNewContent(filePath) {
  let stat;
  try {
    stat = fs.statSync(filePath);
  } catch {
    return;
  }
  if (stat.size <= currentOffset) return;

  const stream = fs.createReadStream(filePath, {
    start: currentOffset,
    encoding: 'utf8',
  });
  stream.on('data', (chunk) => {
    outputChannel.append(chunk);
  });
  currentOffset = stat.size;
}

function startTailing(filePath) {
  if (fileWatcher) {
    fileWatcher.close();
    fileWatcher = null;
  }

  currentFile = filePath;
  currentOffset = 0;

  outputChannel.appendLine(`--- Tailing: ${filePath} ---`);
  readNewContent(filePath);

  fileWatcher = fs.watch(filePath, (eventType) => {
    if (eventType === 'change') {
      readNewContent(filePath);
    }
  });
}

function watchLogDir(logDir) {
  if (dirWatcher) {
    dirWatcher.close();
    dirWatcher = null;
  }

  try {
    fs.mkdirSync(logDir, { recursive: true });
  } catch {
    // ignore
  }

  dirWatcher = fs.watch(logDir, (eventType, filename) => {
    if (!filename || !filename.startsWith('mcp_') || !filename.endsWith('.txt')) return;

    const newFile = path.join(logDir, filename);
    if (newFile !== currentFile && fs.existsSync(newFile)) {
      outputChannel.appendLine('');
      outputChannel.appendLine(`--- New log file detected ---`);
      startTailing(newFile);
    }
  });
}

function activate(context) {
  outputChannel = vscode.window.createOutputChannel('SWE: Serena Logs');
  context.subscriptions.push(outputChannel);

  const showCmd = vscode.commands.registerCommand('serena-log-viewer.show', () => {
    outputChannel.show(true);
  });
  context.subscriptions.push(showCmd);

  const logDir = getTodayLogDir();
  const latestFile = findLatestLogFile(logDir);

  if (latestFile) {
    startTailing(latestFile);
  } else {
    outputChannel.appendLine(`Waiting for Serena logs in ${logDir} ...`);
  }

  watchLogDir(logDir);

  const scheduleNewDay = () => {
    const now = new Date();
    const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    const msUntilMidnight = tomorrow.getTime() - now.getTime();

    const timer = setTimeout(() => {
      const newLogDir = getTodayLogDir();
      outputChannel.appendLine(`--- New day: watching ${newLogDir} ---`);
      watchLogDir(newLogDir);
      scheduleNewDay();
    }, msUntilMidnight);

    context.subscriptions.push({ dispose: () => clearTimeout(timer) });
  };
  scheduleNewDay();
}

function deactivate() {
  if (fileWatcher) {
    fileWatcher.close();
    fileWatcher = null;
  }
  if (dirWatcher) {
    dirWatcher.close();
    dirWatcher = null;
  }
}

module.exports = { activate, deactivate };
