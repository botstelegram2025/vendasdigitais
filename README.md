# 🚂 Railway Deployment - Telegram Bot + WhatsApp (UPDATED)

## ✅ Correções Incluídas

Este pacote contém todas as correções necessárias para deploy no Railway:

- **✅ Python3 Fix**: Todos os comandos `python` foram corrigidos para `python3`
- **✅ Node.js 20 Fix**: Atualizado de Node.js 18 para Node.js 20+ (required by @whiskeysockets/baileys)
- **✅ Dockerfile Mínimo**: Usa node:20 (não slim) + dependências essenciais apenas
- **✅ NPM Fix**: Adiciona `--ignore-scripts` para evitar erros de build
- **✅ Python Dependencies**: Instala build tools e dev headers para cryptography, Pillow, psycopg2
- **✅ Sessions Fix**: Criação automática da pasta sessions (não mais erro de "not found")
- **✅ Procfile Fix**: Comando de inicialização corrigido
- **✅ Makefile Fix**: Todos os comandos usando `python3`

## 🚀 Como Fazer Deploy

### 1. Extrair o Pacote
```bash
unzip railway-deploy-updated.zip
cd railway-deploy-updated/
```

### 2. Push para GitHub
```bash
git init
git add .
git commit -m "Railway deployment with fixes - Telegram Bot + WhatsApp"
git remote add origin your-github-repo-url
git push -u origin main
```

### 3. Deploy no Railway
1. **Conectar Repositório**: Vincule seu repo GitHub ao Railway
2. **Configurar Variáveis de Ambiente**:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   MERCADO_PAGO_ACCESS_TOKEN=your_mercado_pago_token
   MERCADO_PAGO_PUBLIC_KEY=your_mercado_pago_public_key
   ```
3. **Deploy**: Railway fará deploy automaticamente

## 📦 Arquivos Incluídos

### Arquivos Corrigidos
- `Dockerfile` - Build multi-stage corrigido
- `Procfile` - Comandos usando python3
- `Makefile` - Todos os comandos corrigidos
- `requirements.txt` - Dependências Python
- `railway.json` - Configurações Railway

### Código da Aplicação
- `main.py` - Bot Telegram principal
- `whatsapp_baileys_multi.js` - Serviço WhatsApp
- `config.py` - Configurações
- `models.py` - Modelos de dados
- Pastas: `services/`, `handlers/`, `core/`, `config/`, `templates/`, `utils/`

### Scripts de Deploy
- `start.py` - Script de inicialização
- `production-config.py` - Configurações de produção

## 🎯 Problemas Resolvidos

1. **"python: command not found"** ❌ → **Usando python3** ✅
2. **"Node.js 20+ required by baileys"** ❌ → **Atualizado para Node.js 20** ✅
3. **"npm ci failed with exit code 1"** ❌ → **Dockerfile simplificado** ✅
4. **"pip3 install failed exit code 1"** ❌ → **Instala build dependencies** ✅
5. **"sessions: not found"** ❌ → **Pasta criada automaticamente** ✅
6. **Multi-stage build errors** ❌ → **Single-stage build** ✅
7. **Conditional logic errors** ❌ → **Comando direto sem condições** ✅

## 💡 Funcionalidades

- 👥 **Gestão de Clientes**: CRUD completo
- 📱 **WhatsApp Integration**: Mensagens automatizadas
- 💰 **Sistema de Pagamento**: PIX via Mercado Pago
- 📊 **Dashboard**: Visão financeira
- ⏰ **Lembretes**: Notificações agendadas
- 📝 **Templates**: Mensagens customizáveis

## 🔧 Suporte

Se houver problemas no deploy:
1. Verifique se todas as variáveis de ambiente estão configuradas
2. Confirme que o repositório GitHub está conectado
3. Monitore os logs: `railway logs --tail`

---

**🎉 DEPLOY PRONTO PARA RAILWAY!**  
Todas as correções aplicadas - sem erros de "python command not found"!