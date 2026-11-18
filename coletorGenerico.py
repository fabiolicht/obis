import json
import os
import requests
import urllib3
import pandas as pd
from abc import ABC, abstractmethod
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ColetorBase(ABC):
    def __init__(self, nome_fonte: str, dir_base: str = "OBIS_Coletas"):
        self.nome_fonte = nome_fonte
        self.dir_base = dir_base
        self.registros = []
        self.session = self._configurar_sessao()
        self._criar_estrutura_pastas()

    def _configurar_sessao(self) -> requests.Session:
        """Cria sessão HTTP resiliente com headers padrão e retry automático."""
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        return session

    def _criar_estrutura_pastas(self):
        self.pastas = {
            'docs': os.path.join(self.dir_base, self.nome_fonte, 'Documentos'),
            'planilhas': os.path.join(self.dir_base, self.nome_fonte, 'Planilhas'),
            'mapas': os.path.join(self.dir_base, self.nome_fonte, 'Mapas_SIG'),
            'imagens': os.path.join(self.dir_base, self.nome_fonte, 'Imagens'),
            'metadados': os.path.join(self.dir_base, self.nome_fonte, 'Metadados')
        }
        for pasta in self.pastas.values():
            os.makedirs(pasta, exist_ok=True)

    @staticmethod
    def limpar_nome(nome: str) -> str:
        for c in '<>:"/\\|?*':
            nome = nome.replace(c, '_')
        return nome.strip()[:60]

    @abstractmethod
    def buscar_metadados(self, termo: str, limite: int = 100) -> list:
        """
        Cada portal deve implementar este método e retornar uma lista de dicionários no padrão:
        {
            "id": str,
            "fonte": self.nome_fonte,
            "titulo": str,
            "resumo": str,
            "data": str,
            "links_acesso": [{"url": str, "esquema": str, "descricao": str}]
        }
        """
        pass

    def salvar_metadados(self):
        caminho = os.path.join(self.pastas['metadados'], f"dados_{self.nome_fonte.lower()}.json")
        with open(caminho, 'w', encoding='utf-8') as f:
            json.dump(self.registros, f, ensure_ascii=False, indent=4)
        print(f"[{self.nome_fonte}] {len(self.registros)} registros salvos em {caminho}")

    def _definir_pasta_e_extensao(self, url: str, esquema: str):
        url_limpa = url.lower().split('?')[0]
        ext = url_limpa.split('.')[-1] if '.' in url_limpa.split('/')[-1] else ''

        if not ext or len(ext) > 5 or not ext.isalnum():
            esq = esquema.upper()
            if 'PDF' in esq: ext = 'pdf'
            elif 'CSV' in esq: ext = 'csv'
            elif 'PNG' in esq: ext = 'png'
            elif 'JPEG' in esq or 'JPG' in esq: ext = 'jpg'
            elif 'ZIP' in esq or 'SHAPE' in esq: ext = 'zip'
            else: ext = 'bin'

        if ext in ['pdf', 'doc', 'docx', 'txt']:
            return self.pastas['docs'], ext
        elif ext in ['csv', 'xls', 'xlsx', 'ods']:
            return self.pastas['planilhas'], ext
        elif ext in ['zip', 'rar', 'shp', 'kml', 'kmz', 'gml', 'geojson', 'tif', 'tiff']:
            return self.pastas['mapas'], ext
        elif ext in ['png', 'jpg', 'jpeg', 'gif']:
            return self.pastas['imagens'], ext
        return self.pastas['docs'], ext

    def baixar_arquivos(self, baixar_fisicamente: bool = True):
        links_relatorio = []
        downloads = 0
        extensoes_validas = ('.pdf', '.zip', '.shp', '.csv', '.xls', '.xlsx', '.png', '.jpg', '.jpeg', '.tif', '.json', '.kml')

        for rec in self.registros:
            titulo = self.limpar_nome(rec.get('titulo', 'Sem_Titulo'))
            for idx, link in enumerate(rec.get('links_acesso', [])):
                url = link.get('url', '')
                esquema = link.get('esquema', '')
                
                links_relatorio.append({
                    "Fonte": self.nome_fonte,
                    "Titulo": titulo,
                    "Esquema": esquema,
                    "Descricao": link.get('descricao', ''),
                    "URL": url
                })

                if not baixar_fisicamente or not url.startswith('http'):
                    continue

                eh_arquivo = (
                    'DOWNLOAD' in esquema.upper() or 
                    esquema.upper().startswith('IMAGE/') or 
                    url.lower().split('?')[0].endswith(extensoes_validas)
                )

                if eh_arquivo:
                    pasta, ext = self._definir_pasta_e_extensao(url, esquema)
                    caminho = os.path.join(pasta, f"{titulo}_{idx}.{ext}")

                    if not os.path.exists(caminho):
                        try:
                            resp = self.session.get(url, stream=True, verify=False, timeout=25)
                            if resp.status_code == 200:
                                with open(caminho, 'wb') as f:
                                    for chunk in resp.iter_content(chunk_size=8192):
                                        if chunk: f.write(chunk)
                                downloads += 1
                                print(f"  [OK] {os.path.basename(caminho)}")
                        except Exception as e:
                            print(f"  [ERRO] {url[:60]}... -> {e}")

        csv_path = os.path.join(self.pastas['metadados'], f"relatorio_links_{self.nome_fonte.lower()}.csv")
        pd.DataFrame(links_relatorio).to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"[{self.nome_fonte}] Concluído! {downloads} arquivos baixados. Relatório: {csv_path}\n")

    def executar(self, termo: str, limite: int = 100, baixar_arquivos: bool = True):
        """Template Method: orquestra todo o fluxo de coleta."""
        print(f"=== Iniciando coleta: {self.nome_fonte} (Termo: '{termo}') ===")
        self.registros = self.buscar_metadados(termo, limite)
        if self.registros:
            self.salvar_metadados()
            self.baixar_arquivos(baixar_fisicamente=baixar_arquivos)
        else:
            print(f"[{self.nome_fonte}] Nenhum registro retornado.")

