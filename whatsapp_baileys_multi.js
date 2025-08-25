--- a/whatsapp_baileys_multi.js
+++ b/whatsapp_baileys_multi.js
@@
-const { makeWASocket, DisconnectReason, useMultiFileAuthState } = require('@whiskeysockets/baileys');
-const { Boom } = require('@hapi/boom');
-const express = require('express');
-const cors = require('cors');
-const QRCode = require('qrcode');
-const fs = require('fs');
-const path = require('path');
-
-const app = express();
-app.use(cors());
-app.use(express.json());
-
-// 🌍 Ambiente Railway
-const isRailway = process.env.RAILWAY_ENVIRONMENT_NAME !== undefined;
-console.log(`🌍 Environment: ${isRailway ? 'Railway' : 'Local'}`);
-if (isRailway) console.log('⚡ Railway environment detected - optimizing for cloud deployment');
-
-// 🔧 Base de sessões (permite volume persistente em /data/auth)
-const SESSION_BASE = process.env.SESSION_DIR || path.join(__dirname, 'sessions');
-if (!fs.existsSync(SESSION_BASE)) fs.mkdirSync(SESSION_BASE, { recursive: true });
-
-// 🔧 Porta do Baileys:
-// Monolito: mantenha 3001 (o bot fala com http://127.0.0.1:3001)
-// Serviço separado (Node-only): defina BAILEYS_PORT=$PORT no Railway
-const PORT = parseInt(process.env.BAILEYS_PORT || '3001', 10);
+const { makeWASocket, DisconnectReason, useMultiFileAuthState } = require('@whiskeysockets/baileys');
+const { Boom } = require('@hapi/boom');
+const express = require('express');
+const cors = require('cors');
+const QRCode = require('qrcode');
+const fs = require('fs');
+const path = require('path');
+
+const app = express();
+app.use(cors());
+app.use(express.json());
+
+// 🌍 Ambiente Railway
+const isRailway = process.env.RAILWAY_ENVIRONMENT_NAME !== undefined;
+console.log(`🌍 Environment: ${isRailway ? 'Railway' : 'Local'}`);
+if (isRailway) console.log('⚡ Railway environment detected - optimizing for cloud deployment');
+
+// 🔧 Base de sessões (permite volume persistente em /data/auth)
+const SESSION_BASE = process.env.SESSION_DIR || path.join(__dirname, 'sessions');
+if (!fs.existsSync(SESSION_BASE)) fs.mkdirSync(SESSION_BASE, { recursive: true });
+
+// 🔧 Porta do Baileys:
+// Monolito: defina BAILEYS_PORT=3001 (bot fala com 127.0.0.1:3001)
+// Serviço separado: usa PORT do Railway
+const PORT = parseInt(process.env.BAILEYS_PORT || process.env.WHATSAPP_PORT || process.env.PORT || '3001', 10);
@@
 const userSessions = new Map();
@@
 class ConnectionSemaphore {
@@
 }
 const connectionSemaphore = new ConnectionSemaphore(2);
@@
 class UserWhatsAppSession {
@@
 }
@@
 function getUserSession(userId) {
@@
 }
 
 // ---------- API ----------
 
-// 🔧 Health para Dockerfile: /status simples
+// Home informativa (evita "Cannot GET /")
+app.get('/', (req, res) => {
+  res.type('text/plain').send([
+    'Baileys API is running ✅',
+    'Health:   GET /health',
+    'Status:   GET /status/:userId',
+    'QR:       GET /qr/:userId',
+    'Reconnect:POST /reconnect/:userId',
+    'Force QR: POST /force-qr/:userId',
+    'Pairing:  POST /pairing-code/:userId  { phoneNumber }',
+    'Send:     POST /send/:userId          { number, message }',
+    'Sessions: GET /sessions'
+  ].join('\\n'));
+});
+
+// 🔧 Health para Dockerfile/monitoring
 app.get('/status', (req, res) => {
   const connected = Array.from(userSessions.values()).filter(s => s.isConnected).length;
   res.json({
     ok: true,
     service: 'baileys',
     connectedSessions: connected,
     totalSessions: userSessions.size,
     sessionDir: SESSION_BASE,
     port: PORT,
     uptime: process.uptime(),
     ts: new Date().toISOString()
   });
 });
@@
 app.get('/health', (req, res) => {
   const connectedSessions = Array.from(userSessions.values()).filter(s => s.isConnected).length;
   const totalSessions = userSessions.size;
   res.json({
     success: true,
     status: 'healthy',
     connectedSessions,
     totalSessions,
     uptime: process.uptime(),
     timestamp: new Date().toISOString()
   });
 });
@@
-// 🔧 Bind final
-console.log(`📡 Binding to 0.0.0.0:${PORT}`);
-app.listen(PORT, '0.0.0.0', () => {
-  console.log(`🚀 Servidor Baileys Multi-User rodando na porta ${PORT}`);
-  console.log(`✅ Sistema de recuperação automática ativo`);
-  console.log(`💾 Sessões persistentes em ${SESSION_BASE}`);
-  if (isRailway) {
-    console.log(`⚡ Railway deployment mode ACTIVE`);
-    console.log(`🔗 Health: GET http://127.0.0.1:${PORT}/status`);
-  }
-});
+// 🔧 Bind final
+console.log(`📡 Binding to 0.0.0.0:${PORT}`);
+function graceful() {
+  console.log('🛑 Graceful shutdown initiated...');
+  const promises = Array.from(userSessions.values()).map(session => {
+    if (session.reconnectTimeout) clearTimeout(session.reconnectTimeout);
+    try { return session.sock?.logout?.(); } catch (_) { return Promise.resolve(); }
+  });
+  Promise.all(promises).finally(() => {
+    console.log('✅ All sessions closed'); process.exit(0);
+  });
+}
+process.on('SIGINT', graceful);
+process.on('SIGTERM', graceful);
+
+app.listen(PORT, '0.0.0.0', () => {
+  console.log(`🚀 Servidor Baileys Multi-User rodando na porta ${PORT}`);
+  console.log(`✅ Sistema de recuperação automática ativo`);
+  console.log(`💾 Sessões persistentes em ${SESSION_BASE}`);
+  if (isRailway) {
+    console.log(`⚡ Railway deployment mode ACTIVE`);
+    console.log(`🔗 Health: GET http://127.0.0.1:${PORT}/status`);
+  }
+});
