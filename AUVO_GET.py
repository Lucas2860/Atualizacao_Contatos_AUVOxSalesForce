import os
import requests
from dotenv import load_dotenv
import json 
from pathlib import Path
import logging

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent

# CONFIGURAÇÕES AUVO

AUVO_URL = os.getenv("AUVO_URL")
AUVO_API_KEY = os.getenv("AUVO_API_KEY")
AUVO_API_TOKEN = os.getenv("AUVO_API_TOKEN")

# AUTENTICAR NO AUVO

def autenticar_auvo():

    url = f"{AUVO_URL}/login"

    payload = {
        "apiKey": AUVO_API_KEY,
        "apiToken": AUVO_API_TOKEN
    }

    response = requests.post(
        url,
        json=payload,
        #timeout=30,
    )

    response.raise_for_status()

    dados = response.json()

    access_token = dados["result"]["accessToken"]

    print("✅ Autenticado no Auvo com sucesso.")

    return access_token

# LISTAR TODOS OS CLIENTES

def listar_clientes_auvo(access_token):

    url = f"{AUVO_URL}/customers"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    pagina = 1
    tamanho_pagina = 100

    todos_clientes = []

    while True:

        params = {
            "page": pagina,
            "pageSize": tamanho_pagina
        }

        response = requests.get(
            url,
            headers=headers,
            params=params,
            #timeout=30,
        )

        if response.status_code != 200:

            print("❌ Erro ao buscar clientes")
            print(f"Status: {response.status_code}")
            print(response.text)

            break

        dados = response.json()

        resultado = dados.get("result", {})

        clientes = resultado.get("entityList", [])

        informacoes_pagina = resultado.get(
            "pagedSearchReturnData",
            {}
        )

        todos_clientes.extend(clientes)

        total_itens = informacoes_pagina.get(
            "totalItems",
            len(todos_clientes)
        )

        print(
            f"   Página {pagina}"
            f" | Encontrados: {len(clientes)}"
            f" | Total acumulado: {len(todos_clientes)}"
            f" | Total Auvo: {total_itens}"
        )

        if not clientes or len(todos_clientes) >= total_itens:

            break

        pagina += 1
        

    return todos_clientes

# SALVAR DADOS NO JSON

def salvar_clientes_json(
    clientes,
    diretorio=rf"{BASE_DIR}\Dados_API",
    nome_arquivo="clientes_auvo.json"
):

    os.makedirs(diretorio, exist_ok=True)

    caminho_arquivo = os.path.join(diretorio, nome_arquivo)

    with open(caminho_arquivo, "w", encoding="utf-8") as arquivo:
        json.dump(
            clientes,
            arquivo,
            ensure_ascii=False,
            indent=4
        )

    print(f"✅ Arquivo JSON salvo: {caminho_arquivo}")

def filtrar_clientes(clientes):

    clientes_filtrados = []

    for cliente in clientes:

        cliente_filtrado = {
            "id": cliente.get("id"),
            "description": cliente.get("description"),
            "legalName": cliente.get("legalName"),
            "contacts": cliente.get("contacts"),
        }

        clientes_filtrados.append(cliente_filtrado)

    return clientes_filtrados

# EXECUÇÃO

if __name__ == "__main__":

    try:

        token = autenticar_auvo()

        clientes = listar_clientes_auvo(token)

        clientes_filtrados = filtrar_clientes(clientes)

        salvar_clientes_json(clientes_filtrados)

        print(f"✅ Total de clientes salvos: {len(clientes)}")
        

    except requests.exceptions.HTTPError as erro:

        print("❌ Erro HTTP:")
        print(erro)

        if erro.response is not None:
            print(erro.response.text)

    except Exception as erro:

        print("❌ Erro:")
        print(erro)