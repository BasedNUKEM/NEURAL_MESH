// NEURAL_MESH Memory Service — PM2 Ecosystem Config
// Deploy: pm2 start ecosystem.config.js
// Monitor: pm2 monit
// Logs: pm2 logs neural-mesh

module.exports = {
  apps: [{
    name: 'neural-mesh',
    script: './start-mesh.sh',
    cwd: '/opt/data/NEURAL_MESH',
    
    // ─── Process ──────────────────────────────────────────
    instances: 1,              // single instance (SQLite)
    exec_mode: 'fork',
    watch: false,              // manual restart only
    
    // ─── Health ──────────────────────────────────────────
    max_restarts: 10,
    min_uptime: '10s',
    max_memory_restart: '256M',
    restart_delay: 5000,
    
    // ─── Health Check ────────────────────────────────────
    wait_ready: true,
    listen_timeout: 10000,
    kill_timeout: 5000,
    
    // ─── Env ─────────────────────────────────────────────
    env: {
      NODE_ENV: 'production',
      PYTHONUNBUFFERED: '1',
    },
    
    // ─── Logging ─────────────────────────────────────────
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    error_file: '/opt/data/logs/neural-mesh-error.log',
    out_file: '/opt/data/logs/neural-mesh-out.log',
    merge_logs: true,
    max_size: '10M',
    retain: 5,
    
    // ─── Auto-restart on file changes in prod? No. ─────
    autorestart: true,
  }]
};