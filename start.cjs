const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const envPath = path.join(__dirname, '.env');
if (fs.existsSync(envPath)) {
  for (const rawLine of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const index = line.indexOf('=');
    if (index === -1) continue;
    const key = line.slice(0, index).trim();
    const value = line.slice(index + 1).trim().replace(/^["']|["']$/g, '');
    if (key && process.env[key] === undefined) process.env[key] = value;
  }
}

const candidates = [
  process.env.PYTHON_EXE,
  path.join(__dirname, '.venv', 'Scripts', 'python.exe'),
  path.join(__dirname, '.venv', 'bin', 'python'),
  'python',
].filter(Boolean);

const python = candidates.find((candidate) => candidate === 'python' || fs.existsSync(candidate));
const proc = spawn(python, ['-m', 'uvicorn', 'src.web.app:app', '--host', '0.0.0.0', '--port', '8001'], {
  cwd: __dirname,
  stdio: 'inherit',
  windowsHide: true,
});
proc.on('close', (code) => process.exit(code));
