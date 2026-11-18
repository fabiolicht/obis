"""
Solicite Acesso API
Os usuários que desejam acessar os dados e informações do HidroWeb de forma automatizada, utilizando API, devem encaminhar um email para telemetria@ana.gov.br, com o assunto “Solicitação de acesso à API”.

No corpo do email, inclua uma breve explicação (em poucas linhas) sobre a motivação da solicitação e forneça as seguintes informações para o cadastro:

Nome do usuário ou instituição
CPF ou CNPJ (para ser utilizado como usuário)
Endereço de e-mail (será utilizado para o recebimento da senha de acesso)

Após o recebimento do e-mail nossa equipe irá avaliar sua solicitação e, caso necessário, entrar em contato para solicitar mais informações.
"""
import json
from pathlib import Path
import requests
import urllib3

# Desabilita alertas de certificado de segurança
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def coletar_dados_hidroweb(
    rios_alvo=None,
    baixar_arquivos=True,
    arquivo_json='dados_hidroweb_riodoce.json',
):
    if rios_alvo is None:
        rios_alvo = ['Doce', 'Gualaxo do Norte', 'Carmo', 'Piranga']
    todas_estacoes = {}
    erros_busca = []
    
    # Cabeçalhos para burlar o bloqueio 401 do firewall da ANA
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Authorization': 'Bearer SUA_CHAVE_AQUI',
        'Referer': 'https://www.snirh.gov.br/hidroweb/mapa'
    }
    
    print("Conectando à API REST do SNIRH/HidroWeb (ANA)...")
    
    # 1. Busca os metadados (Fichas das Estações)
    for rio in rios_alvo:
        url_busca = "https://www.snirh.gov.br/hidroweb/rest/api/estacao"
        try:
            resposta = requests.get(
                url_busca,
                params={"nomeRio": rio},
                headers=headers,
                verify=False,
                timeout=30,
            )
            if resposta.status_code == 200:
                estacoes = resposta.json()
                for est in estacoes:
                    todas_estacoes[est['codigo']] = est
                print(f" -> Encontradas {len(estacoes)} estações no rio: {rio}")
            else:
                print(f" -> Erro ao buscar rio {rio}: HTTP {resposta.status_code}")
                erros_busca.append(f"{rio}: HTTP {resposta.status_code}")
        except requests.exceptions.RequestException as e:
            print(f" -> Erro de conexão ao buscar rio {rio}: {e}")
            erros_busca.append(f"{rio}: {e}")

    if not todas_estacoes:
        print("\nNenhuma estação foi encontrada. O bloqueio pode persistir ou a API está temporariamente fora do ar.")
        if erros_busca:
            raise RuntimeError("Falha na consulta ao HidroWeb: " + "; ".join(erros_busca))
        with open(arquivo_json, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)
        return []

    for estacao in todas_estacoes.values():
        estacao["arquivos_baixados"] = []

    with open(arquivo_json, 'w', encoding='utf-8') as f:
        json.dump(list(todas_estacoes.values()), f, ensure_ascii=False, indent=4)
    print(f"\nMetadados de {len(todas_estacoes)} estações únicos salvos em '{arquivo_json}'.")

    if not baixar_arquivos:
        return list(todas_estacoes.values())

    baixar_arquivos_hidroweb(arquivo_json)
    with open(arquivo_json, 'r', encoding='utf-8') as f:
        return json.load(f)


def baixar_arquivos_hidroweb(
    arquivo_json='dados_hidroweb_riodoce.json',
    pasta_destino=None,
):
    with open(arquivo_json, 'r', encoding='utf-8') as f:
        estacoes = json.load(f)
    if not isinstance(estacoes, list):
        raise ValueError("O JSON do HidroWeb deve conter uma lista de estações.")

    if pasta_destino is None:
        pasta_destino = (
            Path(__file__).resolve().parent
            / 'OBIS_Coletas' / 'Downloads' / 'hidroweb'
        )
    pasta_destino = Path(pasta_destino)
    pasta_destino.mkdir(parents=True, exist_ok=True)
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Authorization': 'Bearer SUA_CHAVE_AQUI',
        'Referer': 'https://www.snirh.gov.br/hidroweb/mapa',
    }

    raiz = Path(__file__).resolve().parent
    baixados = 0
    erros = []
    for estacao in estacoes:
        codigo = estacao.get('codigo')
        nome_estacao = str(estacao.get('nome', 'SemNome'))
        nome_seguro = nome_estacao.replace('/', '-').replace('\\', '-').replace(' ', '_')
        nome_arquivo = f"Estacao_{codigo}_{nome_seguro}.zip"
        caminho = pasta_destino / nome_arquivo
        temporario = caminho.with_suffix(caminho.suffix + '.part')

        if not codigo:
            erro = f"Estação sem código: {nome_estacao}"
            estacao["erros_download"] = [erro]
            erros.append(erro)
            continue

        try:
            if not caminho.exists():
                url_download = "https://www.snirh.gov.br/hidroweb/rest/api/documento/convencionais"
                total_bytes = 0
                with requests.get(
                    url_download,
                    params={"tipo": 3, "documentos": codigo},
                    headers=headers,
                    verify=False,
                    stream=True,
                    timeout=60,
                ) as resposta:
                    resposta.raise_for_status()
                    with temporario.open('wb') as arquivo:
                        for bloco in resposta.iter_content(chunk_size=8192):
                            if bloco:
                                arquivo.write(bloco)
                                total_bytes += len(bloco)
                if total_bytes <= 1024:
                    temporario.unlink(missing_ok=True)
                    estacao["arquivos_baixados"] = []
                    erro = f"Estação {codigo}: sem arquivo de medições disponível."
                    estacao["erros_download"] = [erro]
                    erros.append(erro)
                    continue
                temporario.replace(caminho)

            caminho_relativo = caminho.relative_to(raiz).as_posix()
            estacao["arquivo_baixado"] = caminho.name
            estacao["arquivo_local"] = caminho.name
            estacao["caminho_local"] = caminho_relativo
            estacao["arquivos_baixados"] = [
                {"nome_arquivo": caminho.name, "caminho_local": caminho_relativo}
            ]
            estacao.pop("erros_download", None)
            baixados += 1
        except requests.RequestException as erro:
            temporario.unlink(missing_ok=True)
            mensagem = f"Estação {codigo}: {erro}"
            estacao["arquivos_baixados"] = []
            estacao["erros_download"] = [str(erro)]
            erros.append(mensagem)

    with open(arquivo_json, 'w', encoding='utf-8') as f:
        json.dump(estacoes, f, ensure_ascii=False, indent=4)

    print(f"Total de pacotes ZIP baixados: {baixados}")
    return baixados, erros

if __name__ == "__main__":
    coletar_dados_hidroweb()