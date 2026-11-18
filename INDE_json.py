import json
from owslib.csw import CatalogueServiceWeb
from owslib.fes import PropertyIsLike

def coletar_dados_inde(
    termo_busca="%rio doce%",
    max_registros=260,
    arquivo_saida="dados_inde_riodoce.json",
):
    csw_url = 'https://metadados.inde.gov.br/geonetwork/srv/por/csw'
    print(f"Conectando ao catálogo CSW da INDE: {csw_url}")
    
    csw = CatalogueServiceWeb(csw_url, timeout=60)

    padrao_busca = (
        termo_busca if '%' in termo_busca or '_' in termo_busca
        else f"%{termo_busca}%"
    )
    query = PropertyIsLike('csw:AnyText', padrao_busca)
    csw.getrecords2(constraints=[query], maxrecords=max_registros, esn='full')
    
    registros_extraidos = []

    for rec_id, rec in csw.records.items():
        links = []
        
        # O GeoNetwork da INDE guarda os links na propriedade 'uris' (padrão ISO)
        fontes_links = getattr(rec, 'uris', []) + getattr(rec, 'references', [])
        
        for ref in fontes_links:
            url = ref.get('url')
            # Mapeia as chaves independente do padrão (ISO ou DC)
            esquema = ref.get('protocol') or ref.get('scheme') or ''
            descricao = ref.get('name') or ref.get('description') or ''
            
            if url:
                links.append({"url": url, "esquema": esquema, "descricao": descricao})

        dados_registro = {
            "id": rec.identifier,
            "titulo": rec.title,
            "resumo": rec.abstract,
            "palavras_chave": rec.subjects,
            "bbox": [float(rec.bbox.minx), float(rec.bbox.miny), float(rec.bbox.maxx), float(rec.bbox.maxy)] if hasattr(rec, 'bbox') and rec.bbox else None,
            "data_modificacao": rec.modified,
            "links_acesso": links,
            "arquivos_baixados": [],
        }
        registros_extraidos.append(dados_registro)
        print(f"Processado: {rec.title[:60]}... ({len(links)} links encontrados)")

    with open(arquivo_saida, 'w', encoding='utf-8') as f:
        json.dump(registros_extraidos, f, ensure_ascii=False, indent=4)
        
    print(f"\nExtração concluída! {len(registros_extraidos)} registros salvos em '{arquivo_saida}'.")
    return registros_extraidos

if __name__ == "__main__":
    coletar_dados_inde(termo_busca="%rio doce%", max_registros=260)