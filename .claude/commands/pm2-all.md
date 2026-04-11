Start all services and open PM2 monitor.
```bash
cd "E:/即梦内容工厂" && pm2 start ecosystem.config.cjs && start wt.exe -d "E:/即梦内容工厂" pwsh -NoExit -c "pm2 monit"
```
