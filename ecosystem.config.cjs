module.exports = {
  apps: [
    {
      name: 'jimeng-backend-8001',
      cwd: __dirname,
      script: 'start.cjs',
      interpreter: 'C:/Program Files/nodejs/node.exe',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
      },
    },
    {
      name: 'jimeng-frontend-5173',
      cwd: __dirname + '/frontend',
      script: 'node_modules/vite/bin/vite.js',
      args: '--port 5173',
      interpreter: 'C:/Program Files/nodejs/node.exe',
      env: {
        NODE_ENV: 'development',
      },
    },
  ],
};
