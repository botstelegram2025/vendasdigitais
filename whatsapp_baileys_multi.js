const { makeWASocket, DisconnectReason, useMultiFileAuthState } = require('@whiskeysockets/baileys');
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

const BAILEYS_PORT = parseInt(
  process.env.BAILEYS_PORT ||
  process.env.WHATSAPP_PORT ||
  process.env.PORT ||
  (isRailway ? '8080' : '3001'),
  10
);

console.log(`🌍 Environment: ${isRailway ? 'Railway' : 'Local'}`);
console.log(`📡 Binding port: ${BAILEYS_PORT}`);

// ===== Sessões =====
const userSessions = new Map();

// Controle de conexões
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
      console.log(`🚀 Starting session for user ${this.userId} (forceNew=${forceNew})`);

      if (this.sock && this.isConnected && !forceNew) {
        console.log(`✅ User ${this.userId} already connected`);
        return;
      }

      if (forceNew && this.sock) {
        try { await this.sock.end(); } catch {}
        this.sock = null;
        this.isConnected = false;
      }

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
        markOnlineOnConnect: false,
        printQRInTerminal: false,
      });

      this.connectionState = 'connecting';

      this.sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
          try {
            this.qrCodeData = await QRCode.toDataURL(qr);
            this.connectionState = 'qr_ready';
            console.log(`📱 QR code pronto p/ user ${this.userId}`);
          } catch (err) {
            this.qrCodeData = null;
          }
        }

        if (connection === 'close') {
          const statusCode = lastDisconnect?.error?.output?.statusCode;
          const shouldReconnect = ![
            DisconnectReason.loggedOut,
            DisconnectReason.badSession
          ].includes(statusCode);

          this.isConnected = false;
          this.connectionState = 'disconnected';

          if (shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            this.scheduleReconnect();
          }
        } else if (connection === 'open') {
          this.isConnected = true;
          this.connectionState = 'connected';
          this.qrCodeData = null;
          this.pairingCode = null;
          this.reconnectAttempts = 0;
          console.log(`✅ WhatsApp conectado user ${this.userId}`);
        }
      });

      this.sock.ev.on('creds.update', saveCreds);
      this.startHeartbeat();

    } catch (err) {
      console.error(`❌ Erro start user ${this.userId}:`, err);
      this.connectionState = 'error';
      this.scheduleReconnect();
    } finally {
      connectionSemaphore.release();
    }
  }

  scheduleReconnect() {
    if (this.reconnectTimeout) return;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 60000);
    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null;
      this.start();
    }, delay);
  }

  startHeartbeat() {
    if (this.heartbeatInterval) clearInterval(this.heartbeatInterval);
    this.heartbeatInterval = setInterval(() => {
      if (this.isConnected && this.sock) {
        this.sock.sendPresenceUpdate('available').catch(() => {});
      }
    }, 30000);
  }

  async sendMessage(number, message) {
    if (!this.isConnected || !this.sock) {
      throw new Error(`WhatsApp não conectado para user ${this.userId}`);
    }
    const jid = `${number.replace(/\D/g, '')}@s.whatsapp.net`;
    return await this.sock.sendMessage(jid, { text: message });
  }

  getStatus() {
    return {
      userId: this.userId,
      isConnected: this.isConnected,
      connectionState: this.connectionState,
      hasQR: !!this.qrCodeData,
      hasPairingCode: !!this.pairingCode,
    };
  }

  async disconnect() {
    if (this.sock) { try { await this.sock.end(); } catch {} this.sock = null; }
    this.isConnected = false;
    this.connectionState = 'disconnected';
    this.qrCodeData = null;
    this.pairingCode = null;
  }
}

// Utils
function getUserSession(userId) {
  if (!userSessions.has(userId)) {
    userSessions.set(userId, new UserWhatsAppSession(userId));
  }
  return userSessions.get(userId);
}

// ===== Endpoints =====
app.get('/status/:userId', (req, res) => {
  const session = userSessions.get(req.params.userId);
  res.json(session ? session.getStatus() : { success: false, status: 'disconnected' });
});

app.post('/connect/:userId', async (req, res) => {
  const session = getUserSession(req.params.userId);
  session.start();
  res.json({ success: true, message: 'Conexão iniciada' });
});

app.get('/qr/:userId', (req, res) => {
  const session = getUserSession(req.params.userId);
  if (session.qrCodeData) {
    res.json({ success: true, qrCode: session.qrCodeData });
  } else {
    res.json({ success: false, message: 'QR não disponível' });
  }
});

// ===== Start Server =====
app.listen(BAILEYS_PORT, '0.0.0.0', () => {
  console.log(`🚀 Servidor Baileys rodando na porta ${BAILEYS_PORT}`);
});
