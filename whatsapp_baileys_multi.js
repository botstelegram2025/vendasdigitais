const { makeWASocket, DisconnectReason, useMultiFileAuthState } = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const express = require('express');
const cors = require('cors');
const QRCode = require('qrcode');
const fs = require('fs');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json());

// 🌍 Ambiente Railway
const isRailway = process.env.RAILWAY_ENVIRONMENT_NAME !== undefined;
console.log(`🌍 Environment: ${isRailway ? 'Railway' : 'Local'}`);
if (isRailway) console.log('⚡ Railway environment detected - optimizing for cloud deployment');

// 🔧 Base de sessões (permite volume persistente em /data/auth)
const SESSION_BASE = process.env.SESSION_DIR || path.join(__dirname, 'sessions');
if (!fs.existsSync(SESSION_BASE)) fs.mkdirSync(SESSION_BASE, { recursive: true });

// 🔧 Porta do Baileys:
// Monolito: mantenha 3001 (o bot fala com http://127.0.0.1:3001)
// Serviço separado (Node-only): defina BAILEYS_PORT=$PORT no Railway
const PORT = parseInt(process.env.BAILEYS_PORT || '3001', 10);

const userSessions = new Map();

// Semáforo p/ conexões simultâneas
class ConnectionSemaphore {
  constructor(maxConcurrent = 3) {
    this.maxConcurrent = maxConcurrent;
    this.current = 0;
    this.queue = [];
  }
  async acquire() {
    return new Promise((resolve) => {
      if (this.current < this.maxConcurrent) {
        this.current++; resolve();
      } else { this.queue.push(resolve); }
    });
  }
  release() {
    this.current--;
    if (this.queue.length > 0) {
      const next = this.queue.shift();
      this.current++; next();
    }
  }
}
const connectionSemaphore = new ConnectionSemaphore(2);

// Sessão de usuário
class UserWhatsAppSession {
  constructor(userId) {
    this.userId = userId;
    this.sock = null;
    this.qrCodeData = null;
    this.isConnected = false;
    this.connectionState = 'disconnected';
    this.authFolder = `auth_info_baileys_user_${userId}`;
    this.reconnectTimeout = null;
    this.heartbeatInterval = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.pairingCode = null;
    this.phoneNumber = null;
    this.heartbeatFailures = 0;
  }

  _authPath() { // 🔧 caminho centralizado
    return path.join(SESSION_BASE, this.authFolder);
  }

  async start(forceNew = false) {
    await connectionSemaphore.acquire();
    try {
      console.log(`🔄 Starting connection for user ${this.userId}, forceNew: ${forceNew}`);
      if (this.reconnectTimeout) { clearTimeout(this.reconnectTimeout); }

      if (forceNew) {
        const authPath = this._authPath();
        if (fs.existsSync(authPath)) {
          const backupPath = path.join(SESSION_BASE, `backup_${this.authFolder}_${Date.now()}`);
          try {
            fs.cpSync(authPath, backupPath, { recursive: true });
            console.log(`💾 Backup created for user ${this.userId} at ${backupPath}`);
          } catch (e) {
            console.log(`⚠️ Could not create backup for user ${this.userId}: ${e.message}`);
          }
          fs.rmSync(authPath, { recursive: true, force: true });
          console.log(`🧹 Cleaned auth for user ${this.userId} - will generate new QR`);
        }
        this.qrCodeData = null;
        this.connectionState = 'generating_qr';
      }

      const { state, saveCreds } = await useMultiFileAuthState(this._authPath());

      this.sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        defaultQueryTimeoutMs: 180000,
        connectTimeoutMs: 180000,
        browser: [`User_${this.userId}`, 'Chrome', '22.04.4'],
        syncFullHistory: false,
        markOnlineOnConnect: true,
        generateHighQualityLinkPreview: false,
        retryRequestDelayMs: 5000,
        maxMsgRetryCount: 5,
        shouldSyncHistoryMessage: () => false,
        keepAliveIntervalMs: 30000,
        emitOwnEvents: false,
        msgRetryCounterCache: new Map(),
        shouldIgnoreJid: () => false,
        qrTimeout: 180000,
        connectCooldownMs: 8000,
        userDevicesCache: new Map(),
        transactionOpts: { maxCommitRetries: 5, delayBetweenTriesMs: 2000 },
      });

      this.sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr, isNewLogin } = update;

        if (qr) {
          console.log(`✅ QR Code gerado para usuário ${this.userId}`);
          this.qrCodeData = await QRCode.toDataURL(qr);
          this.connectionState = 'qr_generated';
        }

        // Pairing code em novo login (se número estiver setado)
        if (isNewLogin && !this.pairingCode && this.phoneNumber) {
          try {
            const code = await this.sock.requestPairingCode(this.phoneNumber);
            this.pairingCode = code;
            this.connectionState = 'pairing_code_generated';
            console.log(`🔐 Pairing Code gerado para usuário ${this.userId} (${this.phoneNumber}): ${code}`);
          } catch (error) {
            console.log(`⚠️ Could not generate pairing code for user ${this.userId}:`, error.message);
          }
        }

        if (connection === 'close') {
          const statusCode = lastDisconnect?.error?.output?.statusCode;
          const errorMessage = lastDisconnect?.error?.message || 'Unknown error';

          const shouldReconnect = ![
            DisconnectReason.loggedOut,
            DisconnectReason.badSession,
            DisconnectReason.multideviceMismatch
          ].includes(statusCode);

          console.log(`❌ Conexão fechada para usuário ${this.userId}, status: ${statusCode}, erro: "${errorMessage}", reconectando: ${shouldReconnect}`);

          this.isConnected = false;
          this.connectionState = 'disconnected';
          if (statusCode !== 408 && statusCode !== 428) this.qrCodeData = null;

          if (statusCode === 515 || (errorMessage || '').includes('stream errored')) {
            this.reconnectTimeout = setTimeout(() => this.start(false), 8000);
          } else if (statusCode === 408) {
            this.reconnectTimeout = setTimeout(() => this.start(false), 3000);
          } else if (statusCode === 428 || (errorMessage || '').includes('Connection Terminated')) {
            this.reconnectTimeout = setTimeout(() => this.start(false), 10000);
          } else if (statusCode === 401) {
            console.log(`🔐 Auth error 401 for user ${this.userId}, forcing clean QR generation...`);
            try {
              const authPath = this._authPath(); // 🔧
              if (fs.existsSync(authPath)) {
                fs.rmSync(authPath, { recursive: true, force: true });
                console.log(`🗑️ Removed corrupted session for user ${this.userId}`);
              }
            } catch (cleanError) {
              console.log(`⚠️ Error removing session: ${cleanError.message}`);
            }
            this.reconnectTimeout = setTimeout(() => this.start(true), 2000);
          } else if (statusCode === 440) {
            this.reconnectTimeout = setTimeout(() => this.start(false), 15000);
          } else if (shouldReconnect) {
            const delay = Math.min(5000 + (Math.random() * 5000), 20000);
            this.reconnectTimeout = setTimeout(() => this.start(false), delay);
          } else {
            console.log(`❌ User ${this.userId} requires manual reconnection`);
          }
        } else if (connection === 'connecting') {
          console.log(`🔄 WhatsApp conectando para usuário ${this.userId}...`);
          this.connectionState = 'connecting';
        } else if (connection === 'open') {
          console.log(`✅ WhatsApp conectado com sucesso para usuário ${this.userId}!`);
          this.isConnected = true;
          this.connectionState = 'connected';
          this.qrCodeData = null;
          this.pairingCode = null;
          this.reconnectAttempts = 0;

          if (this.reconnectTimeout) { clearTimeout(this.reconnectTimeout); this.reconnectTimeout = null; }
          this.startHeartbeat();
        }
      });

      this.sock.ev.on('creds.update', saveCreds);

    } catch (error) {
      console.error(`❌ Erro ao iniciar WhatsApp para usuário ${this.userId}:`, error);
      this.connectionState = 'error';
    } finally {
      connectionSemaphore.release();
    }
  }

  async sendMessage(number, message) {
    if (!this.sock) throw new Error('WhatsApp não conectado para este usuário');

    if (!this.isConnected) {
      console.log(`⚠️ User ${this.userId} marked as disconnected but attempting to send anyway...`);
    }

    let formattedNumber = number.replace(/\D/g, '');
    // 🔧 formatação robusta: se não começa com 55, prefixa 55
    if (!formattedNumber.startsWith('55')) {
      formattedNumber = '55' + formattedNumber;
    }
    const jid = `${formattedNumber}@s.whatsapp.net`;

    try {
      const result = await this.sock.sendMessage(jid, { text: message });
      console.log(`📤 Mensagem enviada pelo usuário ${this.userId} para ${number}: ${message}`);
      if (!this.isConnected) {
        this.isConnected = true;
        this.connectionState = 'connected';
      }
      return result;
    } catch (error) {
      console.log(`❌ Erro ao enviar mensagem para usuário ${this.userId}:`, error.message);

      if ((error.message || '').toLowerCase().includes('closed') || (error.message || '').includes('ECONNRESET')) {
        this.isConnected = false;
        this.connectionState = 'disconnected';
        if (this.heartbeatInterval) { clearInterval(this.heartbeatInterval); this.heartbeatInterval = null; }
        setTimeout(async () => {
          try { await this.start(false); } catch (e) { console.log(`❌ Auto-reconnection failed: ${e.message}`); }
        }, 3000);
      }
      throw error;
    }
  }

  async disconnect() {
    if (this.reconnectTimeout) { clearTimeout(this.reconnectTimeout); this.reconnectTimeout = null; }
    if (this.heartbeatInterval) { clearInterval(this.heartbeatInterval); this.heartbeatInterval = null; }
    try {
      if (this.sock?.logout) await this.sock.logout();
      if (this.sock?.ws && this.sock.ws.readyState === 1) this.sock.ws.close();
    } catch (_) { /* ignore */ }
    this.isConnected = false;
    this.connectionState = 'disconnected';
    this.qrCodeData = null;
    this.pairingCode = null;
    this.sock = null;
  }

  startHeartbeat() {
    if (this.heartbeatInterval) clearInterval(this.heartbeatInterval);
    this.heartbeatFailures = 0;

    this.heartbeatInterval = setInterval(async () => {
      if (this.isConnected && this.sock) {
        try {
          await Promise.race([
            this.sock.query({ tag: 'iq', attrs: { type: 'get', xmlns: 'w:profile:picture' } }),
            new Promise((_, reject) => setTimeout(() => reject(new Error('Heartbeat timeout')), 15000))
          ]);
          this.heartbeatFailures = 0;
        } catch (error) {
          this.heartbeatFailures++;
          console.log(`💔 Heartbeat failed for user ${this.userId} (${this.heartbeatFailures}/3): ${error.message}`);
          if (this.heartbeatFailures >= 3) {
            this.isConnected = false;
            this.connectionState = 'disconnected';
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;

            if ((error.message || '').toLowerCase().includes('closed')) {
              setTimeout(async () => {
                try { await this.start(false); } catch (e) { console.log(`❌ Auto-reconnect failed: ${e.message}`); }
              }, 10000);
            }
            this.heartbeatFailures = 0;
          }
        }
      }
    }, 90000);
  }

  async reconnect() {
    await this.disconnect();
    await this.start(true); // força novo QR
  }

  async requestPairingCode(phoneNumber) {
    return new Promise(async (resolve) => {
      try {
        console.log(`🔐 Pairing code requested for user ${this.userId} with phone ${phoneNumber}`);

        if (this.heartbeatInterval) { clearInterval(this.heartbeatInterval); this.heartbeatInterval = null; }
        if (this.reconnectTimeout) { clearTimeout(this.reconnectTimeout); this.reconnectTimeout = null; }

        if (this.sock) {
          try {
            if (this.sock.ws && this.sock.ws.readyState === 1) this.sock.ws.close();
          } catch (_) {}
          this.sock = null;
        }

        this.isConnected = false;
        this.connectionState = 'generating_pairing_code';
        this.qrCodeData = null;
        this.pairingCode = null;

        const authPath = this._authPath();
        const backupPath = path.join(SESSION_BASE, `backup_pairing_${this.authFolder}_${Date.now()}`);
        if (fs.existsSync(authPath)) {
          try { fs.cpSync(authPath, backupPath, { recursive: true }); console.log(`💾 Backup created before pairing: ${backupPath}`); }
          catch (e) { console.log(`⚠️ Backup failed: ${e.message}`); }
          fs.rmSync(authPath, { recursive: true, force: true });
          console.log(`🧹 Completely cleaned auth for user ${this.userId} - fresh pairing start`);
        }

        await new Promise(r => setTimeout(r, 500));

        const { state, saveCreds } = await useMultiFileAuthState(this._authPath());
        this.sock = makeWASocket({
          auth: state,
          printQRInTerminal: false,
          browser: [`PairingBot_${this.userId}`, 'Chrome', '22.04.4'],
          connectTimeoutMs: 60000,
          defaultQueryTimeoutMs: 60000,
          emitOwnEvents: true,
          retryRequestDelayMs: 250,
          maxMsgRetryCount: 3,
          shouldSyncHistoryMessage: false
        });

        this.sock.ev.on('connection.update', async (update) => {
          const { connection, lastDisconnect } = update;
          console.log(`🔐 Pairing connection update for user ${this.userId}: ${connection}`);
          if (connection === 'open') {
            console.log(`✅ WhatsApp conectado via pairing code para usuário ${this.userId}!`);
            this.isConnected = true;
            this.connectionState = 'connected';
            this.qrCodeData = null;
            this.pairingCode = null;
            this.startHeartbeat();
          } else if (connection === 'close') {
            this.isConnected = false;
            this.connectionState = 'disconnected';
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            if (statusCode !== 401 && statusCode !== 515) {
              if (!this.pairingCode) resolve({ success: false, error: 'Connection failed before pairing code generation' });
            }
          }
        });

        this.sock.ev.on('creds.update', saveCreds);

        setTimeout(async () => {
          try {
            let formatted = (phoneNumber || '').replace(/\D/g, '');
            // 🔧 regra simples: se não começa com 55, prefixa 55
            if (!formatted.startsWith('55')) formatted = '55' + formatted;
            if (formatted.length < 12 || formatted.length > 13) {
              throw new Error(`Invalid phone number format: ${phoneNumber}. Use E.164, ex: 5561999887766`);
            }
            console.log(`🔐 Requesting pairing code for user ${this.userId} with formatted phone: ${formatted}...`);
            const code = await this.sock.requestPairingCode(formatted);
            this.pairingCode = code;
            this.connectionState = 'pairing_code_generated';
            console.log(`🔐 Pairing code generated for user ${this.userId}: ${code}`);
            resolve({ success: true, pairingCode: code });
          } catch (error) {
            console.error(`❌ Error requesting pairing code for user ${this.userId}:`, error);
            resolve({ success: false, error: error.message });
          }
        }, 1500);

        setTimeout(() => {
          if (!this.pairingCode) resolve({ success: false, error: 'Timeout generating pairing code' });
        }, 30000);

      } catch (error) {
        console.error(`❌ Error in pairing code setup for user ${this.userId}:`, error);
        resolve({ success: false, error: error.message });
      }
    });
  }

  async forceQR() {
    try {
      console.log(`🚀 Force QR requested for user ${this.userId}`);
      if (this.reconnectTimeout) { clearTimeout(this.reconnectTimeout); this.reconnectTimeout = null; }
      if (this.sock) {
        try {
          if (this.sock.ws && this.sock.ws.readyState === 1) this.sock.ws.close();
        } catch (_) {}
        this.sock = null;
      }
      this.isConnected = false;
      this.connectionState = 'generating_qr';
      this.qrCodeData = null;
      this.pairingCode = null;

      await this.start(true);

      return new Promise((resolve, reject) => {
        let attempts = 0;
        const maxAttempts = 20;
        const checkQR = () => {
          attempts++;
          if (this.qrCodeData) resolve({ success: true, qrCode: this.qrCodeData });
          else if (attempts >= maxAttempts) reject(new Error('QR generation timeout'));
          else if (this.connectionState === 'error') reject(new Error('Connection error during QR generation'));
          else setTimeout(checkQR, 500);
        };
        setTimeout(checkQR, 100);
      });

    } catch (error) {
      console.error(`❌ Error in forceQR for user ${this.userId}:`, error);
      return { success: false, error: error.message };
    }
  }

  getStatus() {
    if (this.isConnected && !this.sock) {
      this.isConnected = false;
      this.connectionState = 'disconnected';
    }
    return {
      userId: this.userId,
      connected: this.isConnected,
      state: this.connectionState,
      qrCode: this.qrCodeData,
      qrCodeExists: !!this.qrCodeData,
      pairingCode: this.pairingCode,
      pairingCodeExists: !!this.pairingCode
    };
  }
}

function getUserSession(userId) {
  if (!userSessions.has(userId)) {
    const session = new UserWhatsAppSession(userId);
    userSessions.set(userId, session);

    const authPath = session._authPath();
    const hasExistingSession = fs.existsSync(authPath) && fs.existsSync(path.join(authPath, 'creds.json'));
    const initDelay = Math.random() * 1000;

    setTimeout(() => {
      if (hasExistingSession) {
        console.log(`🔄 Found existing session for user ${userId}, attempting restore...`);
        session.start(false);
      } else {
        console.log(`🆕 No existing session for user ${userId}, creating new...`);
        session.start(true);
      }
    }, initDelay);
  }
  return userSessions.get(userId);
}

// ---------- API ----------

// 🔧 Health para Dockerfile: /status simples
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

app.get('/status/:userId', async (req, res) => {
  const userId = req.params.userId;
  const session = getUserSession(userId);
  const basicStatus = session.getStatus();

  if (basicStatus.connected && session.sock) {
    try {
      await session.sock.query({ tag: 'iq', attrs: { type: 'get', xmlns: 'w:profile:picture' } });
    } catch (error) {
      console.log(`⚠️ Connection test failed for user ${userId}: ${error.message}`);
      session.isConnected = false;
      session.connectionState = 'disconnected';
      basicStatus.connected = false;
      basicStatus.state = 'disconnected';
    }
  }
  res.json({ success: true, ...basicStatus });
});

app.get('/qr/:userId', async (req, res) => {
  try {
    const userId = req.params.userId;
    const session = getUserSession(userId);

    console.log(`📱 QR requested for user ${userId}, state: ${session.connectionState}, hasQR: ${!!session.qrCodeData}`);

    if (session.isConnected) {
      return res.json({ success: false, error: 'Already connected', connected: true });
    }
    if (session.qrCodeData && session.connectionState === 'qr_generated') {
      return res.json({ success: true, qrCode: session.qrCodeData });
    }
    try {
      const result = await session.forceQR();
      res.json(result);
    } catch (error) {
      console.error(`❌ QR generation failed for user ${userId}:`, error);
      res.json({ success: false, message: 'Erro ao gerar QR Code', error: error.message });
    }
  } catch (error) {
    console.error('QR endpoint error:', error);
    res.json({ success: false, error: 'Internal server error' });
  }
});

app.post('/send/:userId', async (req, res) => {
  try {
    const userId = req.params.userId;
    const { number, message } = req.body;
    const session = userSessions.get(userId);
    if (!session) return res.json({ success: false, error: 'Sessão não encontrada para este usuário' });
    if (!session.sock) return res.json({ success: false, error: 'WhatsApp não conectado para este usuário' });

    const result = await session.sendMessage(number, message);
    res.json({ success: true, messageId: result.key.id, response: result });
  } catch (error) {
    console.error('Erro ao enviar mensagem:', error);
    res.json({ success: false, error: error.message });
  }
});

app.post('/disconnect/:userId', async (req, res) => {
  try {
    const userId = req.params.userId;
    const session = userSessions.get(userId);
    if (session) {
      await session.disconnect();
      userSessions.delete(userId);
    }
    res.json({ success: true, message: 'WhatsApp desconectado para o usuário' });
  } catch (error) {
    res.json({ success: false, error: error.message });
  }
});

app.post('/reconnect/:userId', async (req, res) => {
  try {
    const userId = req.params.userId;
    const session = getUserSession(userId);
    await session.reconnect();
    res.json({ success: true, message: 'Gerando novo QR Code...' });
  } catch (error) {
    res.json({ success: false, error: error.message });
  }
});

app.post('/force-qr/:userId', async (req, res) => {
  try {
    const userId = req.params.userId;
    const session = getUserSession(userId);
    const result = await session.forceQR();
    res.json(result);
  } catch (error) {
    res.json({ success: false, error: error.message });
  }
});

app.post('/pairing-code/:userId', async (req, res) => {
  try {
    const userId = req.params.userId;
    const { phoneNumber } = req.body;
    if (!phoneNumber) return res.json({ success: false, error: 'Número de telefone é obrigatório' });

    const session = getUserSession(userId);
    // 🔧 guarda já no formato E.164 simples (prefixa 55 se faltar)
    let formatted = phoneNumber.replace(/\D/g, '');
    if (!formatted.startsWith('55')) formatted = '55' + formatted;
    session.phoneNumber = formatted;

    const result = await session.requestPairingCode(formatted);
    res.json(result);
  } catch (error) {
    console.error('Pairing code endpoint error:', error);
    res.json({ success: false, error: 'Internal server error' });
  }
});

app.get('/pairing-code/:userId', (req, res) => {
  try {
    const userId = req.params.userId;
    const session = userSessions.get(userId);
    if (!session) return res.json({ success: false, error: 'Sessão não encontrada' });

    if (session.pairingCode) {
      res.json({ success: true, pairingCode: session.pairingCode, state: session.connectionState });
    } else {
      res.json({ success: false, message: 'Código de pareamento não disponível' });
    }
  } catch (error) {
    console.error('Get pairing code error:', error);
    res.json({ success: false, error: 'Internal server error' });
  }
});

app.get('/sessions', (req, res) => {
  const sessions = Array.from(userSessions.entries()).map(([userId, session]) => ({
    userId, ...session.getStatus()
  }));
  res.json({ success: true, sessions, totalSessions: sessions.length });
});

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

app.post('/restore/:userId', async (req, res) => {
  try {
    const userId = req.params.userId;
    const session = getUserSession(userId);
    const authPath = session._authPath();
    const hasValidSession = fs.existsSync(authPath) && fs.existsSync(path.join(authPath, 'creds.json'));
    if (!hasValidSession) return res.json({ success: false, error: 'No valid session found for this user' });
    await session.start(false);
    res.json({ success: true, message: 'Session restore initiated', hasSession: hasValidSession });
  } catch (error) {
    res.json({ success: false, error: error.message });
  }
});

// Auto-recovery a cada 5 min
setInterval(() => {
  console.log(`🔍 Health check: ${userSessions.size} active sessions`);
  userSessions.forEach((session, userId) => {
    if (!session.isConnected && session.connectionState === 'disconnected') {
      const authPath = session._authPath();
      const hasValidSession = fs.existsSync(authPath) && fs.existsSync(path.join(authPath, 'creds.json'));
      if (hasValidSession && !session.reconnectTimeout) {
        console.log(`🔄 Auto-recovering session for user ${userId}...`);
        session.start(false);
      }
    }
  });
}, 300000);

// Encerramento gracioso
process.on('SIGINT', () => {
  console.log('🛑 Graceful shutdown initiated...');
  const promises = Array.from(userSessions.values()).map(session => {
    if (session.reconnectTimeout) clearTimeout(session.reconnectTimeout);
    try { return session.sock?.logout?.(); } catch (_) { return Promise.resolve(); }
  });
  Promise.all(promises).finally(() => {
    console.log('✅ All sessions closed');
    process.exit(0);
  });
});

// 🔧 Bind final
console.log(`📡 Binding to 0.0.0.0:${PORT}`);
app.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 Servidor Baileys Multi-User rodando na porta ${PORT}`);
  console.log(`✅ Sistema de recuperação automática ativo`);
  console.log(`💾 Sessões persistentes em ${SESSION_BASE}`);
  if (isRailway) {
    console.log(`⚡ Railway deployment mode ACTIVE`);
    console.log(`🔗 Health: GET http://127.0.0.1:${PORT}/status`);
  }
});
