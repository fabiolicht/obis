from coletor_generico import ColetorGenerico

class ColetorCKAN(ColetorGenerico):
    def __init__(self, nome_fonte: str, url_api_base: str):
        super().__init__(nome_fonte)
        self.url_api = f"{url_api_base.rstrip('/')}/api/3/action/package_search"

    def buscar_metadados(self, termo: str, limite: int = 50) -> list:
        resp = self.session.get(self.url_api, params={"q": termo, "rows": limite}, timeout=30)
        resp.raise_for_status()
        resultados = resp.json().get("result", {}).get("results", [])

        padronizados = []
        for item in resultados:
            links = [
                {
                    "url": res.get("url", ""),
                    "esquema": f"WWW:DOWNLOAD-{res.get('format', '')}",
                    "descricao": res.get("name", "")
                }
                for res in item.get("resources", []) if res.get("url")
            ]
            padronizados.append({
                "id": item.get("id", ""),
                "fonte": self.nome_fonte,
                "titulo": item.get("title", "Sem titulo"),
                "resumo": item.get("notes", ""),
                "data": item.get("metadata_modified", ""),
                "links_acesso": links
            })
        return padronizados


class ColetorGeoNetwork(ColetorGenerico):
    def __init__(self, nome_fonte: str, url_q_endpoint: str):
        super().__init__(nome_fonte)
        self.url_q = url_q_endpoint

    def buscar_metadados(self, termo: str, limite: int = 100) -> list:
        params = {'_content_type': 'json', 'any': termo, 'fast': 'index', 'from': 1, 'to': limite}
        resp = self.session.get(self.url_q, params=params, timeout=30)
        resp.raise_for_status()
        
        metadados = resp.json().get('metadata', [])
        if isinstance(metadados, dict):
            metadados = [metadados]

        padronizados = []
        for rec in metadados:
            links_brutos = rec.get('link', [])
            if isinstance(links_brutos, str):
                links_brutos = [links_brutos]

            links = []
            for link_str in links_brutos:
                partes = link_str.split('|')
                url = next((p for p in partes if p.startswith('http')), None)
                esquema = next((p for p in partes if 'OGC:' in p or 'WWW:' in p), 'WWW:DOWNLOAD')
                if url:
                    links.append({"url": url, "esquema": esquema, "descricao": partes[0]})

            padronizados.append({
                "id": rec.get('uuid', ''),
                "fonte": self.nome_fonte,
                "titulo": rec.get('title', 'Sem titulo'),
                "resumo": rec.get('abstract', ''),
                "data": rec.get('changeDate', ''),
                "links_acesso": links
            })
        return padronizados


if __name__ == "__main__":
    # Basta instanciar e rodar qualquer portal que siga esses padrões
    ckan_gov = ColetorCKAN("DadosGovBR", "https://dados.gov.br/dados")
    ckan_gov.executar(termo="rio doce", limite=30)

    sisema = ColetorGeoNetwork("IDE_Sisema", "https://idesisema.meioambiente.mg.gov.br/geonetwork/srv/por/q")
    sisema.executar(termo="rio doce", limite=50)
