# Bot Telegram para Gestão de Clientes

Este bot Telegram permite adicionar e gerenciar clientes com informações completas, armazenando os dados em banco PostgreSQL.

## Funcionalidades

- ➕ Adicionar clientes com fluxo completo de coleta de dados
- 📝 Coleta de 7 campos: nome, telefone, pacote, valor, data de vencimento, servidor e outras informações
- 🗃️ Persistência de dados em banco PostgreSQL
- ⌨️ Interface com teclados personalizados para facilitar a entrada de dados

## Rodando no Railway

1. **Clone este repositório** e faça deploy no Railway.
2. **Adicione as variáveis de ambiente**:
   - `TELEGRAM_BOT_TOKEN` — Token do bot do Telegram
   - `POSTGRES_URL` — URL de conexão do PostgreSQL

### Exemplos de POSTGRES_URL:
```
# Railway PostgreSQL
POSTGRES_URL=postgresql://username:password@hostname:port/database

# Local PostgreSQL
POSTGRES_URL=postgresql://user:password@localhost:5432/vendasdigitais

# Heroku PostgreSQL
POSTGRES_URL=postgres://user:password@hostname:port/database
```

3. **Deploy automático:** Railway instala as dependências do `requirements.txt` e executa o comando definido no `Procfile`.

## Comandos principais

- `/start` — Inicia o bot e mostra o menu principal com botão "➕ ADICIONAR CLIENTE"

## Fluxo de Adição de Cliente

1. **Nome do cliente** (texto livre)
2. **Telefone** (texto livre)
3. **Pacote**: 📅 MENSAL, 📆 TRIMESTRAL, 📅 SEMESTRAL, 📅 ANUAL, 🛠️ PACOTE PERSONALIZADO
4. **Valor**: 25, 30, 35, 40, 45, 50, 60, 70, 90, 💸 OUTRO VALOR
5. **Data de vencimento**: Sugestões automáticas baseadas no pacote ou 📅 OUTRA DATA
6. **Servidor**: ⚡ FAST PLAY, 🏅 GOLD PLAY, 📺 EITV, 🖥️ X SERVER, 🛰️ UNITV, 🆙 UPPER PLAY, 🪶 SLIM TV, 🛠️ CRAFT TV, 🖊️ OUTRO SERVIDOR
7. **Outras informações** (opcional, pode pular)

## Estrutura do Banco de Dados

A tabela `clientes` é criada automaticamente com os seguintes campos:
- `id` (SERIAL PRIMARY KEY)
- `user_id` (BIGINT) - ID do usuário do Telegram
- `nome` (TEXT) - Nome do cliente
- `telefone` (TEXT) - Telefone do cliente
- `pacote` (TEXT) - Tipo de pacote selecionado
- `valor` (TEXT) - Valor do pacote
- `data_vencimento` (TEXT) - Data de vencimento
- `servidor` (TEXT) - Servidor selecionado
- `outras_informacoes` (TEXT) - Informações adicionais

## Personalização

- Ajuste a lógica do arquivo `bot.py` conforme sua necessidade.
- Modifique as opções de pacotes, valores e servidores diretamente no código.
- Adicione novos campos ou validações conforme necessário.

---