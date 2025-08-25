const { makeWASocket, DisconnectReason, useMultiFileAuthState } = require('@whiskeysockets/baileys');
// const { Boom } = require('@hapi/boom'); // não usado em JS puro
const express = require('express');
const cors = require('cors');
const QRCode = require('qrcode');
const fs = require('fs');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json());

// ===== Ambiente / Porta =====
const isRailway = process.env.RAILWAY_ENVIRONMENT_NAME !== undefined;
const isLocal = !isRailway;

// Preferir BAILEYS_PORT (monolito) -> WHATSAPP_PORT -> PORT -> default
const BAILEYS_PORT = parseInt(
  process.env.BAILEYS_PORT ||
  process.env.WHATSAPP_PORT ||
  process.env.PORT ||
  (isRailway ? '8080' : '3001'),
  10
);

console.log(`🌍 Environment: ${isRailway ? 'Railway' : 'Local'}`);
console.log(`📡 Binding port: ${BAILEYS_PORT}`);
if (isRailway) {
  console.log('⚡ Railway environment - optimized for cloud deployment');
} else {
  console.log('💻 Local environment - using standard port 3001');
}

// ===== Sessões =====
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
        this.current++;
        resolve();
      } else {
        this.queue.push(resolve);
      }
    });
  }
  release() {
    this.current--;
    if (this.queue.length > 0) {
      const next = this.queue.shift();
      this.current++;
      next();
    }
  }
}
const connectionSemaphore = new ConnectionSemaphore(2);

// ===== Classe de sessão =====
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
  }

  async start(forceNew = false) {
    await connectionSemaphore.acquire();
    try {
      console.log(`🚀 Starting WhatsApp session for user ${this.userId} (forceNew=${forceNew})`);

      // atrasinho aleatório (1–3s) pra evitar corrida
      const delay = Math.random() * 2000 + 1000;
      await new Promise(r => setTimeout(r, delay));

      if (this.sock && this.isConnected && !forceNew) {
        console.log(`✅ User ${this.userId} already connected`);
        return;
      }

      // encerra socket atual se forçar novo
      if (forceNew && this.sock) {
        try { await this.sock.end(); } catch (e) { console.log(`⚠️ end() warn: ${e.message}`); }
        this.sock = null;
        this.isConnected = false;
      }

      if (this.reconnectTimeout) {
        clearTimeout(this.reconnectTimeout);
        this.reconnectTimeout = null;
      }

      // paths de sessão
      const sessionsDir = path.join(__dirname, 'sessions');
      if (!fs.existsSync(sessionsDir)) fs.mkdirSync(sessionsDir, { recursive: true });
      const authPath = path.join(sessionsDir, this.authFolder);

      const { state, saveCreds } = await useMultiFileAuthState(authPath);

      this.sock = makeWASocket({
        auth: state,
        browser: [`Baileys-${this.userId}`, 'Chrome', '91.0'],
        connectTimeoutMs: 60000,
        defaultQueryTimeoutMs: 60000,
        keepAliveIntervalMs: 30000,
        // logger: pino... (opcional). Se passar objeto inválido pode quebrar; então omitimos.
        shouldIgnoreJid: jid => isJidBroadcast(jid),
        markOnlineOnConnect: false,
        printQRInTerminal: false,
        generateHighQualityLinkPreview: false,
        syncFullHistory: false,
        shouldSyncHistoryMessage: () => false,
        retryRequestDelayMs: 250,
        qrTimeout: 30000
        // version opcional; bailey detecta automaticamente
      });

      this.connectionState = 'connecting';

      // eventos
      this.sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
          try {
            console.log(`📱 QR Code gerado para usuário ${this.userId}`);
            this.qrCodeData = await QRCode.toDataURL(qr);
            this.connectionState = 'qr_ready';
          } catch (err) {
            console.error(`❌ Erro gerando QR para usuário ${this.userId}:`, err);
            this.qrCodeData = null;
          }
        }

        if (connection === 'close') {
          // ⚠️ JS puro: sem "as Boom"
          const statusCode = lastDisconnect?.error?.output?.statusCode;
          const errorMessage = lastDisconnect?.error?.message || 'Unknown error';

          const shouldReconnect = ![
            DisconnectReason.loggedOut,
            DisconnectReason.badSession,
            DisconnectReason.multideviceMismatch
          ].includes(statusCode);

          console.log(`🔌 Conexão fechada (user ${this.userId}) status=${statusCode} err="${errorMessage}" shouldReconnect=${shouldReconnect}`);

          this.isConnected = false;
          this.connectionState = 'disconnected';

          if (shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            this.scheduleReconnect();
          } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log(`❌ Max reconnect attempts reached for user ${this.userId}`);
            this.connectionState = 'failed';
          }

        } else if (connection === 'open') {
          console.log(`✅ WhatsApp conectado para usuário ${this.userId}`);
          this.isConnected = true;
          this.connectionState = 'connected';
          this.reconnectAttempts = 0;
          this.qrCodeData = null;
          this.pairingCode = null;
        }
      });

      this.sock.ev.on('creds.update', saveCreds);
      this.startHeartbeat();

    } catch (error) {
      console.error(`❌ Erro ao iniciar sessão para usuário ${this.userId}:`, error);
      this.connectionState = 'error';
      this.scheduleReconnect();
    } finally {
      connectionSemaphore.release();
    }
  }

  scheduleReconnect() {
    if (this.reconnectTimeout) return;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 60000);
    console.log(`⏰ Reconnect user ${this.userId} in ${Math.round(delay / 1000)}s`);
    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null;
      this.start();
    }, delay);
  }

  startHeartbeat() {
    if (this.heartbeatInterval) clearInterval(this.heartbeatInterval);
    this.heartbeatInterval = setInterval(() => {
      if (this.isConnected && this.sock) {
        // manter conexão viva; erros aqui podem ser ignorados
        this.sock.sendPresenceUpdate('available').catch(() => {});
      }
    }, 30000);
  }

  async sendMessage(number, message) {
    if (!this.isConnected || !this.sock) {
      throw new Error(`WhatsApp não conectado para usuário ${this.userId}`);
    }
    // Normaliza número → E.164 BR simples (prefixa 55 se faltar)
    let digits = String(number || '').replace(/\D/g, '');
    if (digits && !digits.startsWith('55')) digits = '55' + digits;
    const jid = `${digits}@s.whatsapp.net`;

    try {
      const result = await this.sock.sendMessage(jid, { text: message });
      console.log(`📤 Enviado para ${digits} por user ${this.userId}`);
      return result;
    } catch (error) {
      console.error(`❌ Erro ao enviar para ${digits} por user ${this.userId}:`, error);
      throw error;
    }
  }

  getStatus() {
    return {
      userId: this.userId,
      isConnected: this.isConnected,
      connectionState: this.connectionState,
      hasQR: !!this.qrCodeData,
      hasPairingCode: !!this.pairingCode,
      reconnectAttempts: this.reconnectAttempts
    };
  }

  async generatePairingCode(phoneNumber) {
    try {
      // guarda formato simples E.164 BR
      let formatted = String(phoneNumber || '').replace(/\D/g, '');
      if (formatted && !formatted.startsWith('55')) formatted = '55' + formatted;
      this.phoneNumber = formatted;

      if (!this.sock) {
        // sobe sessão “fresh” para permitir pairing
        await this.start(true);
        await new Promise(r => setTimeout(r, 1500));
      }

      const code = await this.sock.requestPairingCode(this.phoneNumber);
      this.pairingCode = code;
      this.connectionState = 'pairing_code_ready';
      console.log(`🔐 Pairing code user ${this.userId}: ${code}`);
      return code;
    } catch (error) {
      console.error(`❌ Error generating pairing code (user ${this.userId}):`, error);
      throw error;
    }
  }

  async disconnect() {
    try {
      if (this.heartbeatInterval) { clearInterval(this.heartbeatInterval); this.heartbeatInterval = null; }
      if (this.reconnectTimeout) { clearTimeout(this.reconnectTimeout); this.reconnectTimeout = null; }
      if (this.sock) { try { await this.sock.end(); } catch (_) {} this.sock = null; }
      this.isConnected = false;
      this.connectionState = 'disconnected';
      this.qrCodeData = null;
      this.pairingCode = null;
      console.log(`🔌 Usuário ${this.userId} desconectado`);
    } catch (error) {
      console.error(`Erro ao desconectar usuário ${this.userId}:`, error);
    }
  }
}

function isJidBroadcast(jid) {
  return ['@broadcast', '@newsletter'].some(suffix => jid?.includes?.(suffix));
}

function getUserSession(userId) {
  if (!userSessions.has(userId)) {
    userSessions.set(userId, new UserWhatsAppSession(userId));
  }
  return userSessions.get(userId);
}

// ===== Endpoints =====

// Rota raiz informativa
app.get('/', (req, res) => {
  res.type('text/plain').send([
    'Baileys API is running ✅',
    'Health:   GET /status',
    'User:     GET /status/:userId',
    'QR now:   GET /qr/:userId',
    'Force QR: POST /force-qr/:userId',
    'Connect:  POST /connect/:userId',
    'Send:     POST /send/:userId   { number, message }'
  ].join('\n'));
});

// Health esperado pelo Dockerfile (sem userId)
app.get('/status', (req, res) => {
  const connected = Array.from(userSessions.values()).filter(s => s.isConnected).length;
  res.json({
    ok: true,
    service: 'baileys',
    connectedSessions: connected,
    totalSessions: userSessions.size,
    port: BAILEYS_PORT,
    environment: isRailway ? 'Railway' : 'Local',
    uptime: process.uptime(),
    ts: new Date().toISOString()
  });
});

// Status por usuário
app.get('/status/:userId', (req, res) => {
  const userId = req.params.userId;
  const session = userSessions.get(userId);
  if (!session) {
    return res.json({ success: true, status: 'disconnected', message: 'Sessão não encontrada' });
  }
  res.json({ success: true, ...session.getStatus() });
});

// QR atual
app.get('/qr/:userId', async (req, res) => {
  try {
    const session = getUserSession(req.params.userId);
    if (session.qrCodeData) {
      return res.json({ success: true, qrCode: session.qrCodeData, connectionState: session.connectionState });
    }
    return res.json({ success: false, message: 'QR Code não disponível', connectionState: session.connectionState });
  } catch (e) {
    res.json({ success: false, error: e.message });
  }
});

// Gera QR “fresh”
app.post('/generate-qr/:userId', async (req, res) => {
  try {
    const session = getUserSession(req.params.userId);
    await session.start(true);
    let attempts = 0;
    const maxAttempts = 15;
    while (!session.qrCodeData && attempts < maxAttempts) {
      await new Promise(r => setTimeout(r, 1000));
      attempts++;
    }
    if (session.qrCodeData) {
      return res.json({ success: true, qrCode: session.qrCodeData, message: 'QR Code gerado com sucesso' });
    }
    res.json({ success: false, error: 'Não foi possível gerar o QR Code', connectionState: session.connectionState });
  } catch (e) {
    res.json({ success: false, error: e.message });
  }
});

// Força novo QR (desconecta antes)
app.post('/force-qr/:userId', async (req, res) => {
  try {
    const session = getUserSession(req.params.userId);
    await session.disconnect();
    await new Promise(r => setTimeout(r, 500));
    await session.start(true);

    let attempts = 0;
    const maxAttempts = 15;
    while (!session.qrCodeData && attempts < maxAttempts) {
      await new Promise(r => setTimeout(r, 1000));
      attempts++;
    }
    if (session.qrCodeData) {
      return res.json({ success: true, qrCode: session.qrCodeData, message: 'Novo QR Code gerado com sucesso' });
    }
    res.json({ success: false, error: 'Não foi possível gerar novo QR Code', connectionState: session.connectionState });
  } catch (e) {
    res.json({ success: false, error: e.message });
  }
});

// Connect / Reconnect / Disconnect
app.post('/connect/:userId', async (req, res) => {
  try {
    const session = getUserSession(req.params.userId);
    session.start();
    res.json({ success: true, message: `Iniciando conexão para usuário ${req.params.userId}`, status: session.getStatus() });
  } catch (e) {
    res.json({ success: false, error: e.message });
  }
});

app.post('/reconnect/:userId', async (req, res) => {
  try {
    const session = getUserSession(req.params.userId);
    await session.start(true);
    res.json({ success: true, message: `Reconexão iniciada para usuário ${req.params.userId}`, status: session.getStatus() });
  } catch (e) {
    res.json({ success: false, error: e.message });
  }
});

app.post('/disconnect/:userId', async (req, res) => {
  try {
    const session = userSessions.get(req.params.userId);
    if (session) {
      await session.disconnect();
      userSessions.delete(req.params.userId);
    }
    res.json({ success: true, message: `Usuário ${req.params.userId} desconectado` });
  } catch (e) {
    res.json({ success: false, error: e.message });
  }
});

// Enviar mensagem
app.post('/send/:userId', async (req, res) => {
  try {
    const { number, message } = req.body || {};
    if (!number || !message) return res.json({ success: false, error: 'Number e message são obrigatórios' });
    const session = getUserSession(req.params.userId);
    if (!session.isConnected) return res.json({ success: false, error: `WhatsApp não conectado para usuário ${req.params.userId}` });
    const result = await session.sendMessage(number, message);
    res.json({ success: true, messageId: result.key.id, result });
  } catch (e) {
    res.json({ success: false, error: e.message });
  }
});

// Pairing code
app.post('/generate-pairing-code/:userId', async (req, res) => {
  try {
    const { phoneNumber } = req.body || {};
    if (!phoneNumber) return res.json({ success: false, error: 'Número de telefone é obrigatório' });
    const session = getUserSession(req.params.userId);
    const code = await session.generatePairingCode(phoneNumber);
    res.json({ success: true, pairingCode: code, message: 'Código de pareamento gerado com sucesso', phoneNumber });
  } catch (e) {
    res.json({ success: false, error: e.message });
  }
});

app.get('/pairing-code/:userId', (req, res) => {
  const session = userSessions.get(req.params.userId);
  if (!session) return res.json({ success: false, error: 'Sessão não encontrada' });
  if (session.pairingCode) return res.json({ success: true, pairingCode: session.pairingCode, state: session.connectionState });
  res.json({ success: false, message: 'Código de pareamento não disponível' });
});

// Listagem de sessões
app.get('/sessions', (req, res) => {
  const sessions = Array.from(userSessions.entries()).map(([userId, session]) => ({
    userId, ...session.getStatus()
  }));
  res.json({ success: true, sessions, totalSessions: sessions.length });
});

// Health alternativo
app.get('/health', (req, res) => {
  const connected = Array.from(userSessions.values()).filter(s => s.isConnected).length;
  res.json({
    success: true,
    status: 'healthy',
    connectedSessions: connected,
    totalSessions: userSessions.size,
    uptime: process.uptime(),
    timestamp: new Date().toISOString(),
    port: BAILEYS_PORT,
    environment: isRailway ? 'Railway' : 'Local'
  });
});

// Auto-recovery a cada 5 min
setInterval(() => {
  console.log(`🔍 Health check: ${userSessions.size} active sessions`);
  userSessions.forEach((session, userId) => {
    if (!session.isConnected && session.connectionState === 'disconnected') {
      const authPath = path.join(__dirname, 'sessions', session.authFolder);
      const hasValid = fs.existsSync(authPath) && fs.existsSync(path.join(authPath, 'creds.json'));
      if (hasValid && !session.reconnectTimeout) {
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
    try { return session.sock?.end?.(); } catch { return Promise.resolve(); }
  });
  Promise.all(promises).finally(() => {
    console.log('✅ All sessions closed');
    process.exit(0);
  });
});

// ==== Start do servidor HTTP ====
app.listen(BAILEYS_PORT, '0.0.0.0', () => {
  console.log(`🚀 Servidor Baileys Multi-User rodando na porta ${BAILEYS_PORT}`);
  console.log(`✅ Sistema de recuperação automática ativo`);
  console.log(`💾 Sessões persistentes em ./sessions/`);
  console.log(`🌍 Listening on 0.0.0.0:${BAILEYS_PORT}`);
});
