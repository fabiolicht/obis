import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests


EXTENSOES_SUPORTADAS = {
    "gif", "jpg", "jpeg", "png", "bmp", "tif", "tiff", "raw",
    "pdf", "doc", "rtf", "docx", "xls", "xlsx", "bin", "csv",
    "shp", "gpkg", "json", "geojson", "kml", "kmz", "dxf", "dwg",
    "osm", "ecw", "dem", "asc", "sid", "zip", "rar", "gz",
    "7z", "tar", "geotiff", "gml", "jp2", "webp", "txt", "odt",
    "ods", "ppt", "pptx", "xml",
}

EXTENSOES_POR_FORMATO = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/tiff": "tif",
    "application/pdf": "pdf",
    "application/json": "json",
    "application/geo+json": "geojson",
    "application/zip": "zip",
    "application/x-zip-compressed": "zip",
    "application/x-7z-compressed": "7z",
    "application/x-rar-compressed": "rar",
    "application/vnd.rar": "rar",
    "application/gzip": "gz",
    "application/x-gzip": "gz",
    "application/x-tar": "tar",
    "application/geopackage+sqlite3": "gpkg",
    "application/x-geotiff": "tif",
    "image/geotiff": "tif",
    "image/bmp": "bmp",
    "image/webp": "webp",
    "application/vnd.google-earth.kml+xml": "kml",
    "application/vnd.google-earth.kmz": "kmz",
    "application/vnd.google-earth.kmz+xml": "kmz",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
    "text/csv": "csv",
    "shape-zip": "zip",
    "jpeg": "jpg",
    "tiff": "tif",
}

CHAVES_URL = ("url", "downloadURL", "download_url", "accessURL", "access_url")
CHAVES_FORMATO = ("format", "formato", "esquema", "protocol", "scheme", "mediaType")
CHAVES_NOME = ("name", "nome", "title", "titulo", "description", "descricao")


def _extensao_do_url(url):
    sufixo = Path(unquote(urlsplit(url).path)).suffix.lower().lstrip(".")
    return sufixo if sufixo in EXTENSOES_SUPORTADAS else None


def _normalizar_extensao(valor):
    texto = str(valor or "").strip().lower()
    mime = texto.split(";")[0].strip()
    if mime in EXTENSOES_POR_FORMATO:
        return EXTENSOES_POR_FORMATO[mime]

    candidato = mime.split("+")[0].strip()
    if "/" in candidato:
        candidato = candidato.rsplit("/", 1)[-1]
    candidato = candidato.lstrip(".")
    return candidato if candidato in EXTENSOES_SUPORTADAS else None


def _candidato_download(registro):
    url = next(
        (registro.get(chave) for chave in CHAVES_URL if registro.get(chave)),
        None,
    )
    if not isinstance(url, str) or urlsplit(url).scheme.lower() not in ("http", "https"):
        return None

    formatos = [registro.get(chave, "") for chave in CHAVES_FORMATO]
    nome = next(
        (
            str(registro[chave]).strip()
            for chave in CHAVES_NOME
            if registro.get(chave)
        ),
        "",
    )
    extensao = _extensao_do_url(url)
    if extensao is None:
        extensao = next(
            (ext for ext in (_normalizar_extensao(valor) for valor in formatos) if ext),
            None,
        )
    if extensao is None and nome:
        extensao = _normalizar_extensao(Path(nome).suffix)

    protocolo = " ".join(str(valor).upper() for valor in formatos)
    if extensao is None:
        if "DOWNLOAD" not in protocolo and "IMAGE/" not in protocolo:
            return None
        extensao = "bin"

    return url, nome, extensao


def _nome_seguro(nome):
    nome = unquote(str(nome or "")).replace("\\", "/").split("/")[-1]
    nome = re.sub(r"[\x00-\x1f<>:\"|?*]", "_", nome).strip(" .")
    return nome or "arquivo"


class GerenciadorDownloads:
    def __init__(self, pasta_base):
        self.pasta_base = Path(pasta_base)

    def baixar_json(self, arquivo_json, fonte):
        caminho_json = Path(arquivo_json)
        with caminho_json.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)

        pasta_destino = self.pasta_base / "OBIS_Coletas" / "Downloads" / fonte
        pasta_destino.mkdir(parents=True, exist_ok=True)
        referencias = []
        erros = []
        visitados = {}

        for registro, ancestrais in self._percorrer_registros(dados):
            candidato = _candidato_download(registro)
            if candidato is None:
                continue
            url, nome_original, extensao = candidato
            if url in visitados:
                referencia = visitados[url]
                registro["arquivo_baixado"] = referencia["nome_arquivo"]
                registro["arquivo_local"] = referencia["nome_arquivo"]
                registro["caminho_local"] = referencia["caminho_local"]
                registro["status_download"] = "baixado"
                referencias.append(referencia)
                self._adicionar_referencia(ancestrais, referencia)
                continue

            nome_base = _nome_seguro(nome_original)
            if Path(nome_base).suffix.lower().lstrip(".") != extensao:
                nome_base = f"{Path(nome_base).stem}.{extensao}"
            caminho_existente = registro.get("caminho_local")
            caminho = self._caminho_existente(caminho_existente)
            if caminho is None or not caminho.is_file():
                caminho = self._caminho_unico(pasta_destino, nome_base)
                erro = self._baixar_url(url, caminho)
            else:
                erro = None
            if erro:
                registro["status_download"] = "erro"
                registro["erro_download"] = erro
                self._adicionar_erro(ancestrais, erro)
                erros.append(f"{url}: {erro}")
                continue

            caminho_relativo = caminho.relative_to(self.pasta_base).as_posix()
            registro["arquivo_baixado"] = caminho.name
            registro["arquivo_local"] = caminho.name
            registro["caminho_local"] = caminho_relativo
            registro["status_download"] = "baixado"
            registro.pop("erro_download", None)
            referencia = {
                "nome_arquivo": caminho.name,
                "caminho_local": caminho_relativo,
                "url": url,
            }
            visitados[url] = referencia
            referencias.append(referencia)
            self._adicionar_referencia(ancestrais, referencia)

        if isinstance(dados, dict):
            dados["arquivos_baixados"] = referencias
            dados["erros_download"] = erros
        self._salvar_json(caminho_json, dados)
        return len(referencias), erros

    def _percorrer_registros(self, valor, ancestrais=()):
        if isinstance(valor, dict):
            filhos = list(valor.values())
            yield valor, ancestrais
            for filho in filhos:
                yield from self._percorrer_registros(
                    filho,
                    ancestrais + (valor,),
                )
        elif isinstance(valor, list):
            for filho in valor:
                yield from self._percorrer_registros(filho, ancestrais)

    @staticmethod
    def _adicionar_erro(ancestrais, erro):
        for ancestral in reversed(ancestrais):
            if any(
                chave in ancestral
                for chave in ("links_acesso", "resourcesFormatado", "resources")
            ):
                ancestral.setdefault("erros_download", []).append(erro)
                break

    @staticmethod
    def _adicionar_referencia(ancestrais, referencia):
        for ancestral in reversed(ancestrais):
            if any(
                chave in ancestral
                for chave in ("links_acesso", "resourcesFormatado", "resources")
            ):
                arquivos = ancestral.setdefault("arquivos_baixados", [])
                if referencia not in arquivos:
                    arquivos.append(referencia)
                break

    def _caminho_unico(self, pasta, nome):
        caminho = pasta / nome
        indice = 1
        while caminho.exists() or caminho.with_suffix(caminho.suffix + ".part").exists():
            caminho = pasta / f"{Path(nome).stem}_{indice}{Path(nome).suffix}"
            indice += 1
        return caminho

    def _caminho_existente(self, caminho_relativo):
        if not caminho_relativo:
            return None
        caminho = (self.pasta_base / caminho_relativo).resolve()
        try:
            caminho.relative_to(self.pasta_base.resolve())
        except ValueError:
            return None
        return caminho

    def _baixar_url(self, url, caminho):
        temporario = caminho.with_suffix(caminho.suffix + ".part")
        try:
            total_bytes = 0
            with requests.get(url, stream=True, timeout=60) as resposta:
                resposta.raise_for_status()
                with temporario.open("wb") as arquivo:
                    for bloco in resposta.iter_content(chunk_size=1024 * 64):
                        if bloco:
                            arquivo.write(bloco)
                            total_bytes += len(bloco)
            if total_bytes == 0:
                temporario.unlink(missing_ok=True)
                return "A resposta de download estava vazia."
            temporario.replace(caminho)
        except requests.RequestException as erro:
            temporario.unlink(missing_ok=True)
            return str(erro)
        except OSError:
            temporario.unlink(missing_ok=True)
            raise
        return None

    @staticmethod
    def _salvar_json(caminho, dados):
        temporario = caminho.with_suffix(caminho.suffix + ".part")
        try:
            with temporario.open("w", encoding="utf-8") as arquivo:
                json.dump(dados, arquivo, ensure_ascii=False, indent=4)
            temporario.replace(caminho)
        except OSError:
            temporario.unlink(missing_ok=True)
            raise
