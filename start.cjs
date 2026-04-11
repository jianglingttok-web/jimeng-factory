const { spawn } = require('child_process');
const proc = spawn('python', ['-m', 'uvicorn', 'src.web.app:app', '--host', '0.0.0.0', '--port', '8001'], {
  cwd: __dirname,
  stdio: 'inherit',
  windowsHide: true,
});
proc.on('close', (code) => process.exit(code));
