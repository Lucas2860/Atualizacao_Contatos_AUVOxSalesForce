import os
import sys
import ast
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# CONFIGURAÇÕES

BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from AUVO_GET import autenticar_auvo  # noqa: E402

sys.path.append(r"R:\RPA\OwnBibliotecas\SistemaDeFilas")
try:
    from sistemafilas import finalizar_automacao  # noqa: E402
except Exception as _erro_import_fila:  # pragma: no cover
    finalizar_automacao = None
    print(f"⚠️ sistemafilas indisponível, término não será enviado ao site: {_erro_import_fila}")

AUVO_URL = os.getenv("AUVO_URL", "").strip().rstrip("/")

ARQUIVO_ALTERACOES = BASE_DIR / "Dados_API/alteracoes_auvo.json"
ARQUIVO_LOG = BASE_DIR / "Dados_API/aplicacao_log.json"
ARQUIVO_RESUMO = BASE_DIR / "Dados_API/resumo_final.txt"
ARQUIVO_PARAMETROS = BASE_DIR / "Parametros/parans.txt"

ETAPAS_COLETA = (
    ("Coletando clientes do AUVO", "AUVO_GET.py", "clientes_auvo.json"),
    ("Coletando contatos do Salesforce", "SALES_GET.py",
     "contatos_salesforce.json"),
    ("Montando plano de alterações", "montar_alteracoes_auvo.py",
     "alteracoes_auvo.json"),
)

CAMPOS_CONTATO = ("name", "jobPosition", "email", "phone")

CAMPOS_CLIENTE_PUT = (
    "id",
    "externalId",
    "phoneNumber",
    "email",
    "manager",
    "note",
    "address",
    "adressComplement",
    "latitude",
    "longitude",
    "cpfCnpj",
    "groupsId",
    "managerTeamsId",
    "managersId",
    "segmentId",
    "active",
    "legalName",
    "maximumVisitTime",
    "unitMaximumTime",
)

# LOG DE AUDITORIA / RETOMADA

def salvar_log(log_por_id):


    registros = list(log_por_id.values())

    with open(ARQUIVO_LOG, "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False, indent=4)

def registrar(log_por_id, cliente_id, status, detalhe=""):

    log_por_id[str(cliente_id)] = {
        "id": cliente_id,
        "status": status,          
        "detalhe": detalhe,
        "quando": datetime.now().isoformat(timespec="seconds"),
    }

    salvar_log(log_por_id)

# RESUMO FINAL EM TXT (HISTÓRICO — SEMPRE APPEND)

def registrar_resumo_txt(aplicados, pulados, erros, simulacao):

    quando = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    modo = "SIMULAÇÃO" if simulacao else "APLICAÇÃO REAL"

    linhas = [
        "=" * 70,
        f"RESUMO FINAL - {quando}",
        f"  Modo:        {modo}",
        f"  Aplicados:   {aplicados}",
        f"  Pulados:     {pulados}",
        f"  Erros:       {erros}",
        "=" * 70,
        "",
    ]

    ARQUIVO_RESUMO.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(ARQUIVO_RESUMO, "a", encoding="utf-8") as f:
            f.write("\n".join(linhas))
        print(f"  📝 Resumo anexado em: {ARQUIVO_RESUMO}")
    except OSError as erro:
        print(f"  ⚠️ Não foi possível gravar o resumo em txt: {erro}")

# ORQUESTRAÇÃO: RODAR OS SCRIPTS QUE GERAM OS JSONS

def rodar_script(rotulo, script):

    caminho = BASE_DIR / script

    if not caminho.exists():
        raise FileNotFoundError(f"Script não encontrado: {caminho}")

    print()
    print("#" * 70)
    print(f"# {rotulo}  ({script})")
    print("#" * 70)

    resultado = subprocess.run(
        [sys.executable, str(caminho)],
        cwd=str(BASE_DIR),
    )

    if resultado.returncode != 0:
        raise RuntimeError(
            f"'{script}' falhou (código {resultado.returncode})."
        )

def rodar_coleta():

    for rotulo, script, saida in ETAPAS_COLETA:

        rodar_script(rotulo, script)

        arquivo_saida = BASE_DIR / "Dados_API" / saida
        if not arquivo_saida.exists():
            raise FileNotFoundError(
                f"'{script}' terminou mas não gerou '{saida}'."
            )

# CARREGAR PLANO DE ALTERAÇÕES

def carregar_alteracoes():

    if not ARQUIVO_ALTERACOES.exists():
        raise FileNotFoundError(
            f"Arquivo de alterações não encontrado: {ARQUIVO_ALTERACOES}"
        )

    with open(ARQUIVO_ALTERACOES, "r", encoding="utf-8") as f:
        return json.load(f)

# BUSCAR CLIENTE COMPLETO (para não perder campos no PUT)

def buscar_cliente_completo(access_token, cliente_id):

    url = f"{AUVO_URL}/customers/{cliente_id}"

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"

    return response.json().get("result", {})

# USUÁRIOS VÁLIDOS (para sanear managersId antes do PUT)

def buscar_ids_usuarios_validos(access_token):

    url = f"{AUVO_URL}/users"

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    ids_validos = set()
    pagina = 1

    while True:
        params = {"page": pagina, "pageSize": 100}

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        response.encoding = "utf-8"

        resultado = response.json().get("result", {})
        usuarios = resultado.get("entityList", [])

        for usuario in usuarios:
            uid = usuario.get("userID", usuario.get("id"))
            if uid is not None:
                ids_validos.add(uid)

        informacoes_pagina = resultado.get("pagedSearchReturnData", {})
        total_itens = informacoes_pagina.get("totalItems", len(ids_validos))

        if not usuarios or len(ids_validos) >= total_itens:
            break

        pagina += 1

    return ids_validos

# MONTAR A NOVA LISTA DE CONTATOS

def limpar_contato(contato):

    return {campo: contato.get(campo) for campo in CAMPOS_CONTATO}

def montar_novos_contatos(contatos_atuais, item):

    ids_remover = {
        c.get("id")
        for c in item.get("contatos_a_remover", [])
        if c.get("id") is not None
    }

    novos = []

    for contato in contatos_atuais:
        if contato.get("id") in ids_remover:
            continue
        novos.append(limpar_contato(contato))

    for contato in item.get("contatos_a_cadastrar", []):
        novos.append(limpar_contato(contato))

    return novos

# MONTAR CORPO DO PUT (preserva todos os campos do cliente)

def montar_corpo_put(cliente_completo, novos_contatos, ids_usuarios_validos=None):

    corpo = {
        campo: cliente_completo[campo]
        for campo in CAMPOS_CLIENTE_PUT
        if campo in cliente_completo
    }

    corpo["name"] = (
        cliente_completo.get("description")
        or cliente_completo.get("name")
    )

    if ids_usuarios_validos is not None and isinstance(corpo.get("managersId"), list):
        managers_originais = corpo["managersId"]
        managers_validos = [
            uid for uid in managers_originais if uid in ids_usuarios_validos
        ]

        removidos = [uid for uid in managers_originais if uid not in ids_usuarios_validos]
        if removidos:
            print(
                f"   🧹 managersId saneado: removidos {removidos} "
                f"(inexistentes); mantidos {managers_validos}"
            )

        corpo["managersId"] = managers_validos

    corpo["replaceData"] = True
    corpo["contacts"] = novos_contatos

    if corpo.get("id") is not None:
        corpo.pop("externalId", None)

    return corpo

# APLICAR (PUT) NO AUVO

def aplicar_put(access_token, corpo):

    url = f"{AUVO_URL}/customers/"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    response = requests.put(url, headers=headers, json=corpo, timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"

    return response.json()

# EXIBIR RESUMO DO QUE SERÁ FEITO

def formatar_contato(contato):
    nome = contato.get("name") or "(sem nome)"
    cargo = contato.get("jobPosition") or "-"
    tel = contato.get("phone") or "-"
    email = contato.get("email") or "-"
    return f"{nome} | {cargo} | {tel} | {email}"

def mostrar_resumo(indice, total, item):

    auvo = item.get("auvo", {})
    a_cadastrar = item.get("contatos_a_cadastrar", [])
    a_remover = item.get("contatos_a_remover", [])
    ja_existentes = item.get("contatos_ja_existentes", [])

    print()
    print("=" * 70)
    print(f"[{indice}/{total}] Cliente: {auvo.get('description')}")
    print(f"        id: {auvo.get('id')} | legalName: {auvo.get('legalName')}")
    print("-" * 70)

    print(f"  ➕ A CADASTRAR ({len(a_cadastrar)}):")
    for c in a_cadastrar:
        print(f"       {formatar_contato(c)}")

    print(f"  ➖ A REMOVER ({len(a_remover)}):")
    for c in a_remover:
        print(f"       {formatar_contato(c)}")

    if ja_existentes:
        print(f"  ✔️  MANTER (já existentes: {len(ja_existentes)})")

    print("=" * 70)

# INTEGRAÇÃO COM O PAINEL (SISTEMA DE FILAS)

def carregar_run_id():

    if not ARQUIVO_PARAMETROS.exists():
        return None

    try:
        with open(ARQUIVO_PARAMETROS, "r", encoding="utf-8") as f:
            paramet = ast.literal_eval(f.read())
    except (SyntaxError, ValueError, OSError) as erro:
        print(f"⚠️ Não foi possível ler {ARQUIVO_PARAMETROS.name}: {erro}")
        return None

    return paramet.get("run_id") or paramet.get("runid") or paramet.get("runId")

def sinalizar_termino(run_id):

    if not run_id or finalizar_automacao is None:
        return

    try:
        finalizar_automacao(run_id, caminho_log=str(ARQUIVO_LOG))
        print(f"📡 Término enviado ao site (run_id={run_id}).")
    except Exception as erro:
        print(f"⚠️ Falha ao enviar término ao site: {erro}")

# EXECUÇÃO PRINCIPAL

def main():

    parser = argparse.ArgumentParser(
        description="Orquestrador central: coleta os dados do AUVO e do "
        "Salesforce, monta o plano e aplica TODAS as alterações de "
        "contatos no AUVO automaticamente (sem confirmação)."
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="Não envia o PUT; apenas mostra o que seria feito.",
    )
    parser.add_argument(
        "--pular-coleta",
        action="store_true",
        help="Não regenera os JSONs; usa os arquivos já existentes "
        "e vai direto para a aplicação.",
    )
    args = parser.parse_args()

    if not AUVO_URL:
        print("❌ AUVO_URL não configurada no .env")
        return

    if args.pular_coleta:
        print("⏭️ Coleta pulada (--pular-coleta): usando JSONs existentes.")
    else:
        try:
            rodar_coleta()
        except Exception as erro:
            print(f"\n❌ Falha na etapa de coleta: {erro}")
            return

    alteracoes = carregar_alteracoes()

    log_por_id = {}
    salvar_log(log_por_id)

    total = len(alteracoes)

    print()
    print("=" * 70)
    print("APLICAÇÃO DE ALTERAÇÕES NO AUVO")
    print("=" * 70)
    print(f"Clientes no plano: {total}")
    if args.simular:
        print("MODO: SIMULAÇÃO (nenhum dado será alterado)")
    else:
        print("MODO: APLICAÇÃO REAL (automática, sem confirmação)")
    print("=" * 70)

    token = autenticar_auvo()

    try:
        ids_usuarios_validos = buscar_ids_usuarios_validos(token)
        print(f"👥 Usuários válidos no AUVO: {len(ids_usuarios_validos)}")
    except Exception as erro:
        ids_usuarios_validos = None
        print(f"⚠️ Não foi possível carregar usuários válidos: {erro}")

    aplicados = 0
    pulados = 0
    erros = 0

    for indice, item in enumerate(alteracoes, start=1):

        cliente_id = item.get("auvo", {}).get("id")

        mostrar_resumo(indice, total, item)

        try:

            cliente_completo = buscar_cliente_completo(token, cliente_id)

            if not cliente_completo:
                raise ValueError("GET retornou cliente vazio")

            novos_contatos = montar_novos_contatos(
                cliente_completo.get("contacts", []),
                item,
            )

            corpo = montar_corpo_put(
                cliente_completo, novos_contatos, ids_usuarios_validos
            )

            if args.simular:
                print(
                    "   🧪 SIMULAÇÃO — contatos que ficariam "
                    f"({len(novos_contatos)}):"
                )
                for c in novos_contatos:
                    print(f"        {formatar_contato(c)}")
                registrar(
                    log_por_id, cliente_id, "pulado", "simulacao"
                )
                pulados += 1
                continue

            aplicar_put(token, corpo)

            print(
                f"   ✅ Aplicado. Contatos agora: {len(novos_contatos)}"
            )
            aplicados += 1
            registrar(
                log_por_id,
                cliente_id,
                "aplicado",
                f"{len(novos_contatos)} contato(s)",
            )

        except requests.exceptions.HTTPError as erro:
            corpo_erro = ""
            if erro.response is not None:
                corpo_erro = erro.response.text
            print(f"   ❌ Erro HTTP: {erro}")
            if corpo_erro:
                print(f"      {corpo_erro}")
            erros += 1
            registrar(
                log_por_id, cliente_id, "erro", f"HTTP: {corpo_erro[:300]}"
            )

        except Exception as erro:
            print(f"   ❌ Erro: {erro}")
            erros += 1
            registrar(log_por_id, cliente_id, "erro", str(erro)[:300])

    print()
    print("=" * 70)
    print("RESUMO FINAL")
    print(f"  ✅ Aplicados: {aplicados}")
    print(f"  ⏭️ Pulados:   {pulados}")
    print(f"  ❌ Erros:     {erros}")
    print(f"  📁 Log: {ARQUIVO_LOG}")
    print("=" * 70)

    # Anexa o resumo ao histórico em txt.
    registrar_resumo_txt(aplicados, pulados, erros, args.simular)

    sinalizar_termino(carregar_run_id())

if __name__ == "__main__":
    main()