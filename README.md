# Bot Telegram com Teste Grátis e Cobrança por PIX

Este bot Telegram oferece 7 dias de teste grátis, após os quais solicita pagamento via Mercado Pago PIX.

## Rodando no Railway

1. **Clone este repositório** e faça deploy no Railway.
2. **Adicione as variáveis de ambiente**:
   - `TELEGRAM_BOT_TOKEN` — Token do bot do Telegram
   - `CHAVE_PIX` — Sua chave PIX do Mercado Pago

3. **Deploy automático:** Railway instala as dependências do `requirements.txt` e executa o comando definido no `Procfile`.

## Comandos principais

- `/start` — Inicia o teste grátis e pede o número de telefone.
- `/acesso` — Mostra status do teste ou cobra o pagamento após 7 dias.
- `/liberar` — (Admin) Libera o acesso manualmente após o pagamento.

## Personalização

- Ajuste a lógica do arquivo `bot.py` conforme sua necessidade.
- Para integração automática do pagamento via Mercado Pago, implemente webhook/check no código.

---