import json
import ee
import requests
import time
from pathlib import Path
"""
Pré-requisitos no seu ambiente Kubuntu
Ter um projeto no Google Cloud Platform com a API do Earth Engine ativada.

Instalar a biblioteca: pip install earthengine-api

Autenticar via terminal: earthengine authenticate
"""

def exportar_mapbiomas_rio_doce(aguardar_conclusao=True):
    ee.Initialize(project='rjprocult')
    print("Conectando ao catálogo do MapBiomas no Google Earth Engine...")
    
    # 2. Definir a Região de Interesse (ROI) da Bacia do Rio Doce.
    # Para testes rápidos, usamos um Bounding Box aproximado (Mariana até a foz no ES).
    # No projeto final, você fará o upload do Shapefile da Bacia do Rio Doce (ex: da ANA)
    # como um "Asset" no GEE e usará: roi = ee.FeatureCollection('projects/.../bacia_doce')
    roi = ee.Geometry.Rectangle([-43.6, -20.8, -39.6, -18.3])

    # 3. Carregar o Asset público do MapBiomas (Coleção 8 - uso e cobertura do solo)
    # O MapBiomas consolida todos os anos em uma única "Imagem", onde cada BANDA é um ano.
    ###mapbiomas = ee.Image('projects/mapbiomas-workspace/public/collection8/mapbiomas_collection80_integration_v1')
    # 3. Carregar o Asset público do MapBiomas (Coleção 9 - Atualizado)
    mapbiomas = ee.Image('projects/mapbiomas-public/assets/brazil/lulc/collection9/mapbiomas_collection90_integration_v1')


    # 4. Selecionar os anos: Antes (2014) e Depois do rompimento de Mariana (2016, 2022)
    anos_interesse = ['classification_2014', 'classification_2016', 'classification_2022']
    
    # Recorta a imagem gigante do Brasil inteiro apenas para a caixa do Rio Doce
    imagem_rio_doce = mapbiomas.select(anos_interesse).clip(roi)

    # 5. Disparar as tarefas de exportação para o Google Drive em formato GeoTIFF
    tarefas_iniciadas = []
    for banda_ano in anos_interesse:
        ano_str = banda_ano.split('_')[1] # Extrai apenas o número do ano
        nome_arquivo = f'MapBiomas_RioDoce_{ano_str}'
        
        print(f"Configurando exportação para o ano {ano_str}...")
        
        task = ee.batch.Export.image.toDrive(
            image=imagem_rio_doce.select(banda_ano),
            description=f'Exportacao_MapBiomas_{ano_str}',
            folder='OBIS_GeoNode_Data',       # Pasta que será criada no seu Google Drive
            fileNamePrefix=nome_arquivo,
            region=roi.getInfo()['coordinates'],
            scale=300,                         # Resolução nativa Landsat (30 metros)
            crs='EPSG:4326',                  # Sistema de coordenadas padrão Web
            maxPixels=1e13                    # Necessário para áreas grandes como a bacia
        )
        
        # Inicia a tarefa assíncrona nos servidores da Google
        task.start()
        print(f"Tarefa {task.id} iniciada! O arquivo {nome_arquivo}.tif aparecerá no seu Drive.\n")
        tarefas_iniciadas.append({
            "ano": ano_str,
            "arquivo_exportado": f"{nome_arquivo}.tif",
            "task_id": task.id,
            "estado": "READY",
        })

    if not aguardar_conclusao:
        return tarefas_iniciadas

    # Monitoramento simples do status das tarefas
    print("Monitorando status (pressione Ctrl+C para sair do script, as tarefas continuarão na nuvem):")
    while True:
        tasks = ee.batch.Task.list()
        ativas = [t for t in tasks if t.state in ['READY', 'RUNNING']]
        if not ativas:
            print("Todas as exportações foram concluídas (ou falharam). Verifique seu Google Drive.")
            break
            
        print(f"Tarefas em andamento: {len(ativas)}. Aguardando 30 segundos...")
        time.sleep(30)

    return tarefas_iniciadas


def baixar_mapbiomas_rio_doce(arquivo_json, pasta_destino=None):
    caminho_json = Path(arquivo_json)
    with caminho_json.open('r', encoding='utf-8') as arquivo:
        metadados = json.load(arquivo)

    ee.Initialize(project='rjprocult')
    roi = ee.Geometry.Rectangle([-43.6, -20.8, -39.6, -18.3])
    imagem = ee.Image(
        'projects/mapbiomas-public/assets/brazil/lulc/collection9/mapbiomas_collection90_integration_v1'
    )
    if pasta_destino is None:
        pasta_destino = (
            Path(__file__).resolve().parent
            / 'OBIS_Coletas' / 'Downloads' / 'mapbiomas'
        )
    pasta_destino = Path(pasta_destino)
    pasta_destino.mkdir(parents=True, exist_ok=True)
    raiz = Path(__file__).resolve().parent
    bandas = metadados.get('bandas', [])
    arquivos_baixados = []
    erros = []

    for banda in bandas:
        ano = banda.rsplit('_', 1)[-1]
        nome_arquivo = f"MapBiomas_RioDoce_{ano}.tif"
        caminho = pasta_destino / nome_arquivo
        temporario = caminho.with_suffix(caminho.suffix + '.part')
        try:
            if not caminho.exists():
                url = imagem.select(banda).clip(roi).getDownloadURL(
                    {
                        'name': f"MapBiomas_RioDoce_{ano}",
                        'scale': 300,
                        'crs': 'EPSG:4326',
                        'region': roi,
                        'format': 'GEO_TIFF',
                    }
                )
                total_bytes = 0
                with requests.get(url, stream=True, timeout=180) as resposta:
                    resposta.raise_for_status()
                    with temporario.open('wb') as arquivo:
                        for bloco in resposta.iter_content(chunk_size=1024 * 64):
                            if bloco:
                                arquivo.write(bloco)
                                total_bytes += len(bloco)
                if total_bytes == 0:
                    temporario.unlink(missing_ok=True)
                    raise requests.RequestException("A resposta do GeoTIFF estava vazia.")
                temporario.replace(caminho)

            caminho_relativo = caminho.relative_to(raiz).as_posix()
            referencia = {
                'ano': ano,
                'nome_arquivo': caminho.name,
                'caminho_local': caminho_relativo,
            }
            arquivos_baixados.append(referencia)
            for item in metadados.get('arquivos_exportados', []):
                if item.get('ano') == ano:
                    item['arquivo_baixado'] = caminho.name
                    item['arquivo_local'] = caminho.name
                    item['caminho_local'] = caminho_relativo
                    item['status_download'] = 'baixado'
        except (requests.RequestException, OSError) as erro:
            temporario.unlink(missing_ok=True)
            mensagem = f"{banda}: {erro}"
            erros.append(mensagem)
            for item in metadados.get('arquivos_exportados', []):
                if item.get('ano') == ano:
                    item['status_download'] = 'erro'
                    item['erro_download'] = str(erro)

    metadados['arquivos_baixados'] = arquivos_baixados
    metadados['erros_download'] = erros
    with caminho_json.open('w', encoding='utf-8') as arquivo:
        json.dump(metadados, arquivo, ensure_ascii=False, indent=4)
    return len(arquivos_baixados), erros


if __name__ == "__main__":
    exportar_mapbiomas_rio_doce()