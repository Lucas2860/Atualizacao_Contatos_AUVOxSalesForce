import json
import re
import unicodedata
from pathlib import Path

# ARQUIVOS

BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_AUVO = BASE_DIR / "Dados_API/clientes_auvo.json"
ARQUIVO_SALESFORCE = BASE_DIR / "Dados_API/contatos_salesforce.json"
ARQUIVO_RESULTADO = BASE_DIR / "Dados_API/alteracoes_auvo.json"

# CONFIGURAÇÕES

TAMANHO_MINIMO_NOME = 5
DIGITOS_TELEFONE = 8
CAMPOS_TEXTO_SINDICO = (
    "TipoContato__c",
    "Name",
    "LastName",
)

# NORMALIZAR TEXTO

def normalizar(texto):

    if texto is None:
        return ""

    texto = str(texto)

    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    texto = texto.upper()

    texto = re.sub(r"[^A-Z0-9\s]", " ", texto)

    texto = re.sub(r"\s+", " ", texto).strip()

    return texto

def remover_numeros(texto):
    texto = normalizar(texto)

    texto = re.sub(r"\b\d+\b", "", texto)

    texto = re.sub(r"\s+", " ", texto).strip()

    return texto

def somente_digitos(texto):
    return re.sub(r"\D", "", str(texto or ""))

# COMPARAÇÃO DE NOMES (contido em, com proteção p/ nomes curtos)

def nome_corresponde(nome_a, nome_b):

    if not nome_a or not nome_b:
        return False

    if min(len(nome_a), len(nome_b)) < TAMANHO_MINIMO_NOME:
        return nome_a == nome_b

    return nome_a in nome_b or nome_b in nome_a

# VERIFICAR SE O CONTATO DO SALESFORCE É SÍNDICO

def motivo_sindico(contato):

    for campo in CAMPOS_TEXTO_SINDICO:
        if re.search(r"\bEX\s+SINDIC[OA]\b", normalizar(contato.get(campo))):
            return None

    if contato.get("RecebeEmailComunicacao__c") is True:
        return "RecebeEmailComunicacao__c"

    for campo in CAMPOS_TEXTO_SINDICO:

        texto = normalizar(contato.get(campo))

        if texto and re.search(r"\bSINDIC[OA]\b", texto):
            return campo

    return None

# VERIFICAR SE É A MESMA PESSOA (AUVO x SALESFORCE)

def mesma_pessoa(contato_auvo, contato_salesforce):

    nome_auvo = normalizar(contato_auvo.get("name"))
    nome_sf = normalizar(contato_salesforce.get("Name"))

    if nome_corresponde(nome_auvo, nome_sf):
        return True

    tel_auvo = somente_digitos(contato_auvo.get("phone"))
    tel_sf = somente_digitos(contato_salesforce.get("Phone"))

    if (
        len(tel_auvo) >= DIGITOS_TELEFONE
        and len(tel_sf) >= DIGITOS_TELEFONE
        and tel_auvo[-DIGITOS_TELEFONE:] == tel_sf[-DIGITOS_TELEFONE:]
    ):
        return True

    return False

# MAPEAR CONTATO SALESFORCE -> FORMATO DE CONTATO AUVO

def mapear_para_auvo(contato_salesforce):

    tipo = contato_salesforce.get("TipoContato__c")

    return {
        "name": contato_salesforce.get("Name"),
        "jobPosition": tipo if tipo else "Síndico",
        "email": contato_salesforce.get("Email"),
        "phone": contato_salesforce.get("Phone"),
    }

# CARREGAR JSON

def carregar_json(arquivo):

    if not Path(arquivo).exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")

    with open(arquivo, "r", encoding="utf-8") as f:
        return json.load(f)

# PRÉ-PROCESSAR CONTATOS DO SALESFORCE

def preparar_contatos(contatos_salesforce):


    preparados = []

    for contato in contatos_salesforce:

        nome_conta = contato.get("Nome_da_Conta__c")

        if not nome_conta:
            continue

        preparados.append({
            "contato": contato,
            "conta_normalizada": remover_numeros(nome_conta),
            "campo_sindico": motivo_sindico(contato),
        })

    return preparados

# PROCURAR CONTATOS DA CONTA NO SALESFORCE

def procurar_contatos_cliente(cliente_auvo, contatos_preparados):

    description = cliente_auvo.get("description")
    legal_name = cliente_auvo.get("legalName")

    description_norm = remover_numeros(description)
    legal_name_norm = remover_numeros(legal_name)

    encontrados = []

    encontrou_description = False
    encontrou_legal_name = False

    for item in contatos_preparados:

        conta = item["conta_normalizada"]

        encontrou = False

        if description_norm and nome_corresponde(description_norm, conta):
            encontrou = True
            encontrou_description = True

        if not encontrou and legal_name_norm:
            if nome_corresponde(legal_name_norm, conta):
                encontrou = True
                encontrou_legal_name = True

        if encontrou:
            encontrados.append(item)

    if encontrou_description and encontrou_legal_name:
        campo_utilizado = "description + legalName"
        valor_utilizado = {
            "description": description,
            "legalName": legal_name,
        }
    elif encontrou_description:
        campo_utilizado = "description"
        valor_utilizado = description
    elif encontrou_legal_name:
        campo_utilizado = "legalName"
        valor_utilizado = legal_name
    else:
        campo_utilizado = None
        valor_utilizado = None

    sindicos = []

    for item in encontrados:
        if item["campo_sindico"]:
            contato = dict(item["contato"])
            contato["_motivo_sindico"] = item["campo_sindico"]
            sindicos.append(contato)

    return {
        "campo_utilizado": campo_utilizado,
        "valor_utilizado": valor_utilizado,
        "total_encontrados": len(encontrados),
        "sindicos": sindicos,
    }

# MONTAR PLANO DE ALTERAÇÃO (SUBSTITUIR PELO SALESFORCE)

def montar_resultado(clientes_auvo, contatos_preparados):

    resultado = []

    total_sem_conta = 0
    total_sem_sindico = 0
    total_sem_mudanca = 0

    for numero, cliente in enumerate(clientes_auvo, start=1):

        description = cliente.get("description")
        legal_name = cliente.get("legalName")
        contatos_auvo = cliente.get("contacts") or []

        print(f"[{numero}/{len(clientes_auvo)}] Buscando: {description}")

        busca = procurar_contatos_cliente(cliente, contatos_preparados)

        sindicos_sf = busca["sindicos"]

        # ----- conta não encontrada no Salesforce -----
        if busca["total_encontrados"] == 0:
            total_sem_conta += 1
            print("   ❌ Conta não encontrada")
            continue

        # ----- conta encontrada, mas sem síndico -----
        if not sindicos_sf:
            total_sem_sindico += 1
            print("   ⚠️ Conta encontrada, mas nenhum síndico")
            continue

        a_cadastrar = []
        ja_existentes = []

        for sf in sindicos_sf:

            correspondente = next(
                (
                    ca for ca in contatos_auvo
                    if mesma_pessoa(ca, sf)
                ),
                None
            )

            if correspondente:
                ja_existentes.append({
                    "salesforce": sf,
                    "auvo_existente": correspondente,
                })
            else:
                a_cadastrar.append(mapear_para_auvo(sf))

        a_remover = [
            ca for ca in contatos_auvo
            if not any(mesma_pessoa(ca, sf) for sf in sindicos_sf)
        ]

        houve_mudanca = bool(a_cadastrar or a_remover)

        if not houve_mudanca:
            total_sem_mudanca += 1
            print(
                f"   ⏭️ {len(ja_existentes)} síndico(s) já "
                "cadastrado(s), nada a fazer"
            )
            continue

        resultado.append({
            "auvo": {
                "id": cliente.get("id"),
                "description": description,
                "legalName": legal_name,
            },

            "correspondencia": {
                "campo_utilizado": busca["campo_utilizado"],
                "valor_pesquisado": busca["valor_utilizado"],
                "total_contatos_da_conta": busca["total_encontrados"],
                "total_sindicos_salesforce": len(sindicos_sf),
            },

            "acao": "substituir",

            "contatos_auvo_atuais": contatos_auvo,
            "contatos_a_cadastrar": a_cadastrar,
            "contatos_ja_existentes": ja_existentes,
            "contatos_a_remover": a_remover,
        })

        print(
            f"   ✅ cadastrar: {len(a_cadastrar)} | "
            f"manter: {len(ja_existentes)} | "
            f"remover: {len(a_remover)}"
        )

    return {
        "resultado": resultado,
        "sem_conta": total_sem_conta,
        "sem_sindico": total_sem_sindico,
        "sem_mudanca": total_sem_mudanca,
    }

# SALVAR JSON

def salvar_resultado(resultado):

    with open(ARQUIVO_RESULTADO, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=4)

    print()
    print("=" * 70)
    print(f"✅ {len(resultado)} clientes com alterações a aplicar")
    print(f"📁 Arquivo: {ARQUIVO_RESULTADO}")
    print("=" * 70)

# EXECUÇÃO

if __name__ == "__main__":

    clientes_auvo = carregar_json(ARQUIVO_AUVO)
    contatos_salesforce = carregar_json(ARQUIVO_SALESFORCE)

    print()
    print("=" * 70)
    print("COMPARAÇÃO AUVO x SALESFORCE")
    print("=" * 70)
    print(f"Clientes AUVO: {len(clientes_auvo)}")
    print(f"Contatos Salesforce: {len(contatos_salesforce)}")
    print("=" * 70)
    print()

    contatos_preparados = preparar_contatos(contatos_salesforce)

    dados = montar_resultado(clientes_auvo, contatos_preparados)

    salvar_resultado(dados["resultado"])

    print()
    print(f"📊 Contas não encontradas:      {dados['sem_conta']}")
    print(f"📊 Contas sem síndico:          {dados['sem_sindico']}")
    print(f"📊 Contas já atualizadas:       {dados['sem_mudanca']}")