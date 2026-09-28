import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# CONFIGURAÇÕES

BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_JSON_SALESFORCE = BASE_DIR / "Dados_API/contatos_salesforce.json"
SALESFORCE_URL = os.getenv("SALESFORCE_URL")
SALESFORCE_CLIENT_ID = os.getenv("SALESFORCE_CLIENT_ID")
SALESFORCE_CLIENT_SECRET = os.getenv("SALESFORCE_CLIENT_SECRET")

VERSAO_API = "v67.0"

# AUTENTICAR SALESFORCE

def autenticar_salesforce():

    url = f"{SALESFORCE_URL}/services/oauth2/token"

    dados = {
        "grant_type": "client_credentials",
        "client_id": SALESFORCE_CLIENT_ID,
        "client_secret": SALESFORCE_CLIENT_SECRET
    }

    response = requests.post(
        url,
        data=dados,
        timeout=30
    )

    response.raise_for_status()

    resposta = response.json()

    access_token = resposta["access_token"]
    instance_url = resposta.get(
        "instance_url",
        SALESFORCE_URL
    )

    print("✅ Autenticado no Salesforce.")

    return access_token, instance_url

# BUSCAR TODOS OS CONTATOS

def listar_contatos_salesforce(access_token, instance_url):

    soql = """
        SELECT
            Name,
            LastName,
            Phone,
            Email,
            TipoContato__c,
            RecebeEmailComunicacao__c,
            Nome_da_Conta__c
        FROM Contact
        WHERE Nome_da_Conta__c != null
    """

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    url = (
        f"{instance_url}"
        f"/services/data/{VERSAO_API}/query"
    )

    params = {
        "q": soql
    }

    todos_contatos = []

    pagina = 1

    while url:

        print(f"🔄 Buscando página {pagina} do Salesforce...")

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code != 200:

            print("❌ Erro ao consultar Salesforce")
            print(f"Status: {response.status_code}")
            print(response.text)

            break

        response.encoding = "utf-8"

        dados = response.json()

        registros = dados.get("records", [])
        

        for contato in registros:

            contato_limpo = {
                "Name": contato.get("Name"),
                "LastName": contato.get("LastName"),
                "Phone": contato.get("Phone"),
                "Email": contato.get("Email"),
                "TipoContato__c": contato.get("TipoContato__c"),
                "Nome_da_Conta__c": contato.get("Nome_da_Conta__c"),
                "RecebeEmailComunicacao__c": contato.get(
                    "RecebeEmailComunicacao__c"
                )
            }

            todos_contatos.append(contato_limpo)

        print(
            f"   Recebidos: {len(registros)}"
            f" | Acumulado: {len(todos_contatos)}"
        )
        
        next_records_url = dados.get("nextRecordsUrl")

        if next_records_url:

            url = f"{instance_url}{next_records_url}"

            params = None

            pagina += 1

        else:

            url = None

    return todos_contatos

# SALVAR JSON

def salvar_contatos_salesforce(contatos):

    with open(
        ARQUIVO_JSON_SALESFORCE,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            contatos,
            arquivo,
            ensure_ascii=False,
            indent=4
        )

    print()
    print(
        f"✅ {len(contatos)} contatos salvos em:"
    )
    print(ARQUIVO_JSON_SALESFORCE)

# EXECUÇÃO

if __name__ == "__main__":

    try:

        access_token, instance_url = autenticar_salesforce()

        contatos = listar_contatos_salesforce(
            access_token,
            instance_url
        )

        salvar_contatos_salesforce(contatos)

    except requests.exceptions.HTTPError as erro:

        print("❌ Erro HTTP:")
        print(erro)

        if erro.response is not None:
            print(erro.response.text)

    except Exception as erro:

        print("❌ Erro:")
        print(erro)