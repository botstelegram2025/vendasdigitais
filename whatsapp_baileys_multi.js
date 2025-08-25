
const { makeWASocket, DisconnectReason, useMultiFileAuthState } = require('@whiskeysockets/baileys');
const express = require('express'); const cors = require('cors'); const QRCode = require('qrcode');
const fs = require('fs'); const path = require('path');
const app = express(); app.use(cors()); app.use(express.json());
const isRailway = process.env.RAILWAY_ENVIRONMENT_NAME !== undefined;
const SESSION_BASE = process.env.SESSION_DIR || path.join(__dirname, 'sessions');
if (!fs.existsSync(SESSION_BASE)) fs.mkdirSync(SESSION_BASE, { recursive: true });
const PORT = parseInt(process.env.BAILEYS_PORT || process.env.WHATSAPP_PORT || process.env.PORT || '3001', 10);
const userSessions = new Map();
class ConnectionSemaphore{constructor(m=3){this.maxConcurrent=m;this.current=0;this.queue=[];}async acquire(){return new Promise(r=>{if(this.current<this.maxConcurrent){this.current++;r();}else this.queue.push(r);});}release(){this.current--;if(this.queue.length>0){const n=this.queue.shift();this.current++;n();}}}
const connectionSemaphore=new ConnectionSemaphore(2);
class UserWhatsAppSession{
  constructor(userId){this.userId=userId;this.sock=null;this.qrCodeData=null;this.isConnected=false;this.connectionState='disconnected';this.authFolder=`auth_info_baileys_user_${userId}`;this.reconnectTimeout=null;this.heartbeatInterval=null;this.reconnectAttempts=0;this.maxReconnectAttempts=5;this.pairingCode=null;this.phoneNumber=null;this.heartbeatFailures=0;}
  _authPath(){return path.join(SESSION_BASE,this.authFolder);}
  async start(forceNew=false){
    await connectionSemaphore.acquire();
    try{
      if(forceNew){const p=this._authPath(); if(fs.existsSync(p)){const b=path.join(SESSION_BASE,`backup_${this.authFolder}_${Date.now()}`);try{fs.cpSync(p,b,{recursive:true});}catch{} fs.rmSync(p,{recursive:true,force:true});} this.qrCodeData=null; this.connectionState='generating_qr';}
      const {state,saveCreds}=await useMultiFileAuthState(this._authPath());
      const sock = require('@whiskeysockets/baileys').makeWASocket;
      this.sock=sock({auth:state,printQRInTerminal:false,defaultQueryTimeoutMs:180000,connectTimeoutMs:180000,browser:[`User_${this.userId}`,'Chrome','22.04.4'],syncFullHistory:false,markOnlineOnConnect:true,generateHighQualityLinkPreview:false,retryRequestDelayMs:5000,maxMsgRetryCount:5,shouldSyncHistoryMessage:()=>false,keepAliveIntervalMs:30000,emitOwnEvents:false,msgRetryCounterCache:new Map(),shouldIgnoreJid:()=>false,qrTimeout:180000,connectCooldownMs:8000,userDevicesCache:new Map(),transactionOpts:{maxCommitRetries:5,delayBetweenTriesMs:2000}});
      this.sock.ev.on('connection.update', async (u)=>{
        const {connection, lastDisconnect, qr, isNewLogin}=u;
        if(qr){this.qrCodeData=await QRCode.toDataURL(qr); this.connectionState='qr_generated';}
        if(connection==='close'){this.isConnected=false; this.connectionState='disconnected'; this.qrCodeData=null; const status=lastDisconnect?.error?.output?.statusCode; const msg=lastDisconnect?.error?.message||''; const shouldReconn = ![401,440].includes(status); const delay = status===515?8000:status===408?3000:status===428||msg.includes('Connection Terminated')?10000:5000; if(shouldReconn){this.reconnectTimeout=setTimeout(()=>this.start(false),delay);} }
        else if(connection==='connecting'){this.connectionState='connecting';}
        else if(connection==='open'){this.isConnected=true; this.connectionState='connected'; this.qrCodeData=null; this.pairingCode=null; this.reconnectAttempts=0; this.startHeartbeat();}
      });
      this.sock.ev.on('creds.update', saveCreds);
    }catch(e){this.connectionState='error';}finally{connectionSemaphore.release();}
  }
  async sendMessage(number,message){
    if(!this.sock) throw new Error('WhatsApp não conectado para este usuário');
    let n=(number||'').replace(/\D/g,''); if(!n.startsWith('55')) n='55'+n; const jid=`${n}@s.whatsapp.net`;
    const r = await this.sock.sendMessage(jid,{text:message}); if(!this.isConnected){this.isConnected=true; this.connectionState='connected';} return r;
  }
  async reconnect(){ if(this.sock?.logout) await this.sock.logout(); this.sock=null; this.isConnected=false; this.connectionState='disconnected'; await this.start(true); }
  async forceQR(){ if(this.sock?.logout) try{await this.sock.logout();}catch{} this.sock=null; this.isConnected=false; this.connectionState='generating_qr'; this.qrCodeData=null; await this.start(true); return new Promise((res,rej)=>{let t=0;const m=20;const ck=()=>{t++; if(this.qrCodeData) res({success:true,qrCode:this.qrCodeData}); else if(t>=m) rej(new Error('QR generation timeout')); else if(this.connectionState==='error') rej(new Error('Connection error during QR generation')); else setTimeout(ck,500);}; setTimeout(ck,100);});}
  getStatus(){ if(this.isConnected && !this.sock){this.isConnected=false; this.connectionState='disconnected';} return { userId:this.userId, connected:this.isConnected, state:this.connectionState, qrCode:this.qrCodeData, qrCodeExists:!!this.qrCodeData, pairingCode:this.pairingCode, pairingCodeExists:!!this.pairingCode };}
}
function getUserSession(userId){ if(!userSessions.has(userId)){ const s=new UserWhatsAppSession(userId); userSessions.set(userId,s); const p=s._authPath(); const has=fs.existsSync(p)&&fs.existsSync(path.join(p,'creds.json')); setTimeout(()=>{ if(has) s.start(false); else s.start(true); }, Math.random()*1000); } return userSessions.get(userId); }
app.get('/', (req,res)=>{ res.type('text/plain').send(['Baileys API is running ✅','Health:   GET /health','Status:   GET /status/:userId','QR:       GET /qr/:userId','Reconnect:POST /reconnect/:userId','Force QR: POST /force-qr/:userId','Pairing:  POST /pairing-code/:userId  { phoneNumber }','Send:     POST /send/:userId          { number, message }','Sessions: GET /sessions'].join('\n'));});
app.get('/status', (req,res)=>{ const connected=[...userSessions.values()].filter(s=>s.isConnected).length; res.json({ok:true,service:'baileys',connectedSessions:connected,totalSessions:userSessions.size,sessionDir:SESSION_BASE,port:PORT,uptime:process.uptime(),ts:new Date().toISOString()}); });
app.get('/status/:userId', async (req,res)=>{ const s=getUserSession(req.params.userId); res.json({success:true, ...s.getStatus()}); });
app.get('/qr/:userId', async (req,res)=>{ const s=getUserSession(req.params.userId); if(s.isConnected) return res.json({success:false,error:'Already connected',connected:true}); try{ const r=await s.forceQR(); res.json(r);}catch(e){res.json({success:false,error:e.message});}});
app.post('/send/:userId', async (req,res)=>{ const s=userSessions.get(req.params.userId); if(!s||!s.sock) return res.json({success:false,error:'WhatsApp não conectado para este usuário'}); try{ const r=await s.sendMessage((req.body||{}).number,(req.body||{}).message); res.json({success:true,messageId:r.key.id,response:r}); }catch(e){ res.json({success:false,error:e.message}); }});
app.post('/reconnect/:userId', async (req,res)=>{ const s=getUserSession(req.params.userId); await s.reconnect(); res.json({success:true,message:'Gerando novo QR Code...'}); });
app.get('/sessions', (req,res)=>{ const sessions=[...userSessions.entries()].map(([userId,s])=>({userId,...s.getStatus()})); res.json({success:true,sessions,totalSessions:sessions.length}); });
app.get('/health', (req,res)=>{ const connected=[...userSessions.values()].filter(s=>s.isConnected).length; res.json({success:true,status:'healthy',connectedSessions:connected,totalSessions:userSessions.size,uptime:process.uptime(),timestamp:new Date().toISOString()}); });
function graceful(){ const ps=[...userSessions.values()].map(s=>{ try{return s.sock?.logout?.();}catch{return Promise.resolve();}}); Promise.all(ps).finally(()=>process.exit(0)); }
process.on('SIGINT', graceful); process.on('SIGTERM', graceful);
console.log(`📡 Binding to 0.0.0.0:${PORT}`);
app.listen(PORT,'0.0.0.0',()=>{ console.log(`🚀 Servidor Baileys Multi-User rodando na porta ${PORT}`); console.log(`✅ Sistema de recuperação automática ativo`); console.log(`💾 Sessões persistentes em ${SESSION_BASE}`); if(isRailway){ console.log(`⚡ Railway deployment mode ACTIVE`); console.log(`🔗 Health: GET http://127.0.0.1:${PORT}/status`);} });
