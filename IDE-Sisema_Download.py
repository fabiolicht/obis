import json
import os
import requests
import pandas as pd

def limpar_nome_arquivo(nome):
    """Remove caracteres inválidos para nomes de arquivos no Linux/Windows."""
    caracteres_invalidos = '<>:"/\\|?*'
    for c in caracteres_invalidos:
        nome = nome.replace(c, '_')
    return nome.strip()

def baixar_arquivos_idesisema(arquivo_json="dados_idesisema_riodoce.json"):
    # 1. Cria a estrutura de pastas no diretório atual
    pastas = [
        'OBIS_Coletas/Documentos_PDF_DOC', 
        'OBIS_Coletas/Planilhas_XLS_CSV', 
        'OBIS_Coletas/Mapas_Shapefiles_ZIP',
        'OBIS_Coletas/Imagens'
    ]
    for pasta in pastas:
        os.makedirs(pasta, exist_ok=True)

    print(f"Lendo metadados de '{arquivo_json}'...")
    try:
        with open(arquivo_json, 'r', encoding='utf-8') as f:
            registros = json.load(f)
    except FileNotFoundError:
        print(f"ERRO: O arquivo '{arquivo_json}' não foi encontrado na pasta atual.")
        return

    links_gerais = []
    downloads_realizados = 0

    # Adiciona User-Agent para evitar bloqueios do firewall estadual durante o download
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }

    # 2. Itera sobre cada registro e seus links
    for rec in registros:
        titulo_base = limpar_nome_arquivo(rec.get('titulo', 'Sem_Titulo'))[:60]
        arquivos_baixados = []
        
        for idx, link in enumerate(rec.get('links_acesso', [])):
            url = link.get('url', '')
            esquema = link.get('esquema', '').upper()
            descricao = link.get('descricao', '')

            links_gerais.append({
                "Titulo": titulo_base,
                "Tipo (Esquema)": esquema,
                "Descricao": descricao,
                "URL": url
            })

            # 3. Filtra apenas os links que apontam para arquivos físicos
            url_lower = url.lower()
            if 'DOWNLOAD' in esquema or esquema.startswith('IMAGE/') or any(url_lower.endswith(ext) for ext in ['.pdf', '.zip', '.shp', '.csv', '.xls', '.xlsx', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.rar']):
                
                # Extrai a extensão do arquivo
                extensao = url_lower.split('.')[-1].split('?')[0] 
                
                if len(extensao) > 5 or not extensao.isalnum():
                    if 'IMAGE/PNG' in esquema: extensao = 'png'
                    elif 'IMAGE/JPEG' in esquema: extensao = 'jpg'
                    elif 'PDF' in esquema: extensao = 'pdf'
                    elif 'ZIP' in esquema or 'SHAPE-ZIP' in esquema: extensao = 'zip'
                    else: extensao = 'bin'

                # Define a pasta destino
                if extensao in ['pdf', 'doc', 'docx', 'txt']:
                    pasta_destino = 'OBIS_Coletas/Documentos_PDF_DOC'
                elif extensao in ['csv', 'xls', 'xlsx']:
                    pasta_destino = 'OBIS_Coletas/Planilhas_XLS_CSV'
                elif extensao in ['zip', 'rar', 'shp', 'kml', 'kmz', 'gml']:
                    pasta_destino = 'OBIS_Coletas/Mapas_Shapefiles_ZIP'
                elif extensao in ['png', 'jpg', 'jpeg', 'tif', 'tiff', 'gif']:
                    pasta_destino = 'OBIS_Coletas/Imagens'
                else:
                    pasta_destino = 'OBIS_Coletas/Documentos_PDF_DOC' 
                
                nome_arquivo = f"{titulo_base}_link{idx}.{extensao}"
                caminho_completo = os.path.join(pasta_destino, nome_arquivo)
                
                # 4. Faz o download do arquivo fisicamente
                if not os.path.exists(caminho_completo):
                    print(f"Baixando: {nome_arquivo}...")
                    try:
                        resposta = requests.get(url, headers=headers, stream=True, timeout=20)
                        
                        if resposta.status_code == 200:
                            with open(caminho_completo, 'wb') as arq:
                                for chunk in resposta.iter_content(chunk_size=8192):
                                    if chunk:
                                        arq.write(chunk)
                            downloads_realizados += 1
                            link["arquivo_baixado"] = nome_arquivo
                            link["arquivo_local"] = nome_arquivo
                            link["caminho_local"] = os.path.relpath(caminho_completo)
                            arquivos_baixados.append({
                                "nome_arquivo": nome_arquivo,
                                "caminho_local": link["caminho_local"],
                            })
                        else:
                            print(f"  -> Erro HTTP {resposta.status_code} ao acessar a URL.")
                    except requests.exceptions.RequestException as e:
                        print(f"  -> Falha na conexão de download: {e}")
                else:
                    print(f"Arquivo já existe: {nome_arquivo}")
                    link["arquivo_baixado"] = nome_arquivo
                    link["arquivo_local"] = nome_arquivo
                    link["caminho_local"] = os.path.relpath(caminho_completo)
                    arquivos_baixados.append({
                        "nome_arquivo": nome_arquivo,
                        "caminho_local": link["caminho_local"],
                    })

        rec["arquivos_baixados"] = arquivos_baixados

    with open(arquivo_json, 'w', encoding='utf-8') as f:
        json.dump(registros, f, ensure_ascii=False, indent=4)

    # 5. Salva o relatório consolidado
    print(f"\nFinalizando... Gerando relatório de URLs.")
    df = pd.DataFrame(links_gerais)
    caminho_relatorio = 'OBIS_Coletas/Relatorio_Links_Completos_IDE_Sisema.csv'
    df.to_csv(caminho_relatorio, index=False, encoding='utf-8-sig')
    
    print("="*50)
    print("COLETA FINALIZADA!")
    print(f"Total de arquivos baixados localmente: {downloads_realizados}")
    print(f"Relatório de links salvo em: {caminho_relatorio}")
    print("Verifique a pasta 'OBIS_Coletas'.")
    print("="*50)
    return downloads_realizados

if __name__ == "__main__":
    baixar_arquivos_idesisema()