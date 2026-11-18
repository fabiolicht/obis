import json
import requests

def coletar_dados_idesisema(
    termo_busca="rio doce",
    max_registros=300,
    arquivo_saida="dados_idesisema_riodoce.json",
):
    # Endpoint nativo de busca (GET) do GeoNetwork. Burlar bloqueios de POST XML.
    url = 'https://idesisema.meioambiente.mg.gov.br/geonetwork/srv/por/q'
    
    params = {
        '_content_type': 'json',
        'any': termo_busca,
        'fast': 'index',
        'from': 1,
        'to': max_registros
    }
    
    # User-Agent é fundamental para não ser barrado pelo firewall estadual
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }

    print(f"Buscando '{termo_busca}' via API JSON do IDE-Sisema...")
    
    resposta = requests.get(url, params=params, headers=headers, timeout=30)
    resposta.raise_for_status()
    dados = resposta.json()

    # O GeoNetwork encapsula os resultados dentro da chave 'metadata'
    metadados = dados.get('metadata', [])
    
    # Se retornar apenas 1 resultado, a API envia um dicionário em vez de lista
    if isinstance(metadados, dict):
        metadados = [metadados]
        
    print(f"Total de registros encontrados: {len(metadados)}")
    
    registros_extraidos = []

    for rec in metadados:
        links = []
        
        # Os links vêm em uma string separada por '|' (ex: Protocolo|URL|Nome|Descrição)
        links_brutos = rec.get('link', [])
        if isinstance(links_brutos, str):
            links_brutos = [links_brutos]
            
        for link_str in links_brutos:
            partes = link_str.split('|')
            
            # Isola a URL, não importa a ordem em que ela venha na string
            url_link = next((p for p in partes if p.startswith('http')), None)
            
            # Tenta inferir o esquema (WMS, WFS, DOWNLOAD)
            esquema = next((p for p in partes if 'OGC:' in p or 'WWW:' in p), 'WWW:DOWNLOAD-1.0-http--download')
            
            if url_link:
                links.append({
                    "url": url_link,
                    "esquema": esquema,
                    "descricao": partes[0] if len(partes) > 0 and not partes[0].startswith('http') else "Arquivo/Serviço"
                })

        dados_registro = {
            "id": rec.get('uuid', ''),
            "titulo": rec.get('title', 'Sem titulo'),
            "resumo": rec.get('abstract', ''),
            "palavras_chave": rec.get('keyword', []),
            "bbox": None, # Simplificado para evitar erros de casting geográfico
            "data_modificacao": rec.get('changeDate', ''),
            "links_acesso": links,
            "arquivos_baixados": [],
        }
        
        registros_extraidos.append(dados_registro)
        print(f"Mapeado: {dados_registro['titulo'][:60]}... ({len(links)} links)")

    with open(arquivo_saida, 'w', encoding='utf-8') as f:
        json.dump(registros_extraidos, f, ensure_ascii=False, indent=4)
        
    print(f"\nExtração concluída! {len(registros_extraidos)} registros salvos com sucesso no arquivo '{arquivo_saida}'.")
    return registros_extraidos

if __name__ == "__main__":
    coletar_dados_idesisema()