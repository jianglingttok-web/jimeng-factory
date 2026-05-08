const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

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
