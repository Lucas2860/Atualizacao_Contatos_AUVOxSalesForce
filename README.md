# Atualização de Contatos AUVO

Este projeto em Python é usado para sincronizar os contatos de síndicos entre o **Salesforce** e o **AUVO**.
Ele pega os síndicos cadastrados no Salesforce e atualiza nos contatos dos clientes no AUVO.

## Como funciona

1. Coleta os contatos do Salesforce e os clientes do AUVO.
2. Compara os dois e monta um plano do que precisa mudar.
3. Aplica as alterações de contatos no AUVO.

## Arquivos

- `SALES_GET.py` – busca os contatos no Salesforce.
- `AUVO_GET.py` – busca os clientes no AUVO.
- `montar_alteracoes_auvo.py` – monta o plano de alterações.
- `aplicar_alteracoes_auvo.py` – roda tudo e aplica as mudanças no AUVO.

## Requisitos

```bash
pip install requests python-dotenv
```

## Configuração

Crie um arquivo `.env` na pasta do projeto com as credenciais, o arquivo .env.exemple é uma base já montada:

```env
SALESFORCE_URL=
SALESFORCE_CLIENT_ID=
SALESFORCE_CLIENT_SECRET=

AUVO_URL=https://api.auvo.com.br/v2
AUVO_API_KEY=
AUVO_API_TOKEN=
```

## Como usar

Simular (mostra o que seria feito, sem alterar nada):

```bash
python aplicar_alteracoes_auvo.py --simular
```

Execução real:

```bash
python aplicar_alteracoes_auvo.py
```
