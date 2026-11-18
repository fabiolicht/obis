# Projeto OBIS — busca e coleta de dados ambientais

Scripts para pesquisar catálogos públicos relacionados à bacia do Rio Doce, salvar os metadados em JSON e, quando houver arquivos físicos disponíveis, baixá-los e registrar sua localização local para catalogação posterior.

## Interface

A interface gráfica está em [`interface_busca.py`](./interface_busca.py). Ela reúne cinco mecanismos:

- **Dados.gov.br** — pesquisa conjuntos de dados e captura a resposta JSON do portal.
- **IDE-Sisema** — pesquisa metadados no catálogo GeoNetwork de Minas Gerais.
- **INDE** — pesquisa metadados no catálogo nacional via CSW.
- **ANA HidroWeb** — pesquisa estações pelo nome do rio informado.
- **MapBiomas** — disponibiliza as bandas de classificação de 2014, 2016 e 2022 para a região configurada da bacia do Rio Doce.

O fluxo da interface é separado em dois passos:

1. Informe o termo, selecione um ou mais mecanismos e clique em **Pesquisar**. Essa ação salva somente os resultados em JSON.
2. Mantendo o mesmo termo, selecione os mecanismos pesquisados e clique em **Download**. A interface baixa os arquivos identificados nos JSONs e atualiza os metadados.

É necessário pesquisar antes de baixar. O botão de download usa os JSONs da última busca; ele não inicia uma nova pesquisa.

### Executar

Na pasta `scripts`, instale as dependências e o navegador usado pelo Playwright:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python interface_busca.py
```

Em sistemas Linux, o Python também precisa ter suporte ao Tkinter. A interface não precisa de navegador visível; o Chromium do Playwright é usado pelo Portal dados.gov.br.

## Saídas e catalogação

- JSONs das pesquisas: `resultados_busca/<mecanismo>_<termo>.json`.
- Arquivos baixados pela interface: `OBIS_Coletas/Downloads/<mecanismo>/`.

Após o download, os registros incluem os campos:

- `arquivo_local`: nome do arquivo salvo.
- `caminho_local`: caminho relativo à pasta `scripts`, útil para localizar o arquivo ao popular um banco de dados.
- `status_download`: estado do download, como `baixado` ou `erro`.
- `erro_download`: detalhe de falha, quando aplicável.
- `arquivos_baixados`: lista de referências aos arquivos associados ao registro ou à pesquisa.

Exemplo de vínculo em um recurso:

```json
{
  "url": "https://exemplo.gov.br/dados/mapa.zip",
  "arquivo_local": "mapa.zip",
  "caminho_local": "OBIS_Coletas/Downloads/inde/mapa.zip",
  "status_download": "baixado"
}
```

Os caminhos registrados são locais ao projeto. A interface não grava diretamente em um banco de dados; esses campos JSON servem como referência para uma etapa posterior de catalogação.

O módulo [`gerenciador_download.py`](./gerenciador_download.py) reconhece extensões como imagens, documentos, planilhas, formatos geoespaciais e arquivos compactados — incluindo GIF, JPG, PNG, BMP, TIF, RAW, PDF, DOC/DOCX, RTF, XLS/XLSX, BIN, CSV, SHP, GPKG, JSON, GeoJSON, KML/KMZ, DXF/DWG, OSM, ECW, DEM, ASC, SID, ZIP, RAR e GZ. Também aceita extensões identificadas pela URL ou pelo formato MIME informado no catálogo. Links de serviços OGC, como WMS/WFS, não são tratados como arquivos físicos, a menos que o catálogo os identifique como download direto.

## Scripts disponíveis

| Arquivo | Finalidade |
|---|---|
| [`interface_busca.py`](./interface_busca.py) | Interface gráfica para pesquisar e baixar de forma seletiva. |
| [`gerenciador_download.py`](./gerenciador_download.py) | Identifica recursos baixáveis nos JSONs, salva os arquivos e registra seus caminhos. |
| [`coletorGenerico.py`](./coletorGenerico.py) | Define a base abstrata para coletores genéricos, com sessão HTTP, organização de pastas, padronização de metadados, downloads e relatórios. |
| [`testeColetorGenerico.py`](./testeColetorGenerico.py) | Exemplos de coletores CKAN e GeoNetwork para Dados.gov.br e IDE-Sisema, com execução direta das buscas. |
| [`DadosGov_json.py`](./DadosGov_json.py) | Captura a resposta JSON da busca do Dados.gov.br usando Playwright. |
| [`DadosGov_Download.py`](./DadosGov_Download.py) | Rotina autônoma de busca/download no Dados.gov.br, com registro dos arquivos locais. |
| [`IDE-Sisema_json.py`](./IDE-Sisema_json.py) | Pesquisa metadados no IDE-Sisema e grava registros e links em JSON. |
| [`IDE-Sisema_Download.py`](./IDE-Sisema_Download.py) | Baixa arquivos apontados pelo JSON do IDE-Sisema e gera um relatório CSV de links. |
| [`INDE_json.py`](./INDE_json.py) | Pesquisa metadados da INDE via CSW e grava os registros em JSON. |
| [`INDE_Download.py`](./INDE_Download.py) | Baixa arquivos apontados pelo JSON da INDE e gera um relatório CSV de links. |
| [`PortalHidroWeb.py`](./PortalHidroWeb.py) | Pesquisa estações da ANA pelo rio e baixa pacotes ZIP de medições. |
| [`MapBiomas.py`](./MapBiomas.py) | Exporta dados do MapBiomas para o Google Drive quando executado diretamente e oferece download local dos GeoTIFFs pela interface. |
| [`requirements.txt`](./requirements.txt) | Dependências Python dos provedores e da interface. |

Os scripts de download de IDE-Sisema e INDE podem ser executados diretamente, mas a interface usa o gerenciador comum para baixar os recursos dos JSONs recém-pesquisados.

## Requisitos específicos e limitações

- **Dados.gov.br:** requer Playwright e o Chromium instalado pelo comando acima.
- **ANA HidroWeb:** o script contém um marcador de autorização (`Bearer SUA_CHAVE_AQUI`). O acesso exige credencial válida autorizada pela ANA; **ATENÇÃO:** não grave tokens reais no repositório.
- **MapBiomas:** o download local requer a API do Google Earth Engine habilitada, autenticação configurada e acesso ao projeto definido em [`MapBiomas.py`](./MapBiomas.py). A API de download do Earth Engine limita o tamanho de cada solicitação; falhas são exibidas pela interface e registradas no JSON quando retornadas pela rotina.
- Os catálogos e serviços são externos; disponibilidade, formato dos metadados e permissões de acesso podem mudar.
