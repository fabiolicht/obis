import os
import json
import requests
import asyncio
import time
from datetime import datetime
from urllib.parse import quote, urlencode
from playwright.async_api import async_playwright
import nest_asyncio

nest_asyncio.apply()


def baixar_arquivo_http(url, caminho_temporario, headers):
    status_retentaveis = {429, 500, 502, 503, 504, 520}

    for tentativa in range(3):
        try:
            with requests.get(
                url,
                headers=headers,
                stream=True,
                timeout=12
            ) as resp:
                resp.raise_for_status()
                with open(caminho_temporario, "wb") as arquivo:
                    for chunk in resp.iter_content(chunk_size=8192):
                        arquivo.write(chunk)
            return
        except requests.exceptions.HTTPError as erro:
            if (
                erro.response.status_code not in status_retentaveis
                or tentativa == 2
            ):
                raise
        except requests.exceptions.RequestException:
            if tentativa == 2:
                raise

        time.sleep(0.5 * (2 ** tentativa))


async def coletar_dados_exatos_invisivel(termos_busca, pasta_destino="downloads_mariana_riodoce"):
    termos_busca = list(termos_busca)
    os.makedirs(pasta_destino, exist_ok=True)
    total_baixado = 0
    total_falhas = 0

    headers_download = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    formatos_suportados = {
        "csv", "pdf", "xlsx", "xls", "zip", "json", "geojson", "kml", "kmz"
    }
    extensoes_por_formato = {
        "application/json": "json",
        "text/csv": "csv",
        "shape-zip": "zip",
        "shp-zip": "zip",
        "zip shp": "zip",
        "shp zip": "zip",
    }
    recursos_ignorados = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                accept_downloads=True
            )
            page = await context.new_page()

            print("Conectando ao Portal de Dados Abertos...")
            await page.goto(
                "https://dados.gov.br/dados/conjuntos-dados",
                wait_until="domcontentloaded"
            )

            async def consultar_api(url):
                return await page.evaluate(
                    """async (url) => {
                        const resposta = await fetch(url, {
                            headers: { Accept: "application/json, text/plain, */*" }
                        });
                        if (!resposta.ok) {
                            throw new Error(`API retornou HTTP ${resposta.status} para ${url}`);
                        }
                        return await resposta.json();
                    }""",
                    url,
                )

            async def buscar_pagina(termo, offset):
                parametros = urlencode({
                    "offset": offset,
                    "tamanhoPagina": 100,
                    "titulo": termo,
                    "dadosAbertos": "true",
                })
                url_api = (
                    "https://dados.gov.br/api/publico/conjuntos-dados/buscar?"
                    f"{parametros}"
                )
                return await consultar_api(url_api)

            async def buscar_detalhes(pacote):
                slug = pacote.get("name")
                if not slug:
                    raise ValueError(
                        f"O conjunto {pacote.get('id')} não tem slug para consultar os detalhes."
                    )
                return await consultar_api(
                    "https://dados.gov.br/api/publico/conjuntos-dados/"
                    f"{quote(slug, safe='')}"
                )

            conjuntos_por_id = {}
            termos_por_conjunto = {}
            for termo in termos_busca:
                print(f"\n{'=' * 50}\nBuscando no título: '{termo}'")
                offset = 0
                total_encontrado = None

                while total_encontrado is None or offset < total_encontrado:
                    dados_json = await buscar_pagina(termo, offset)
                    registros_pagina = dados_json.get("registros")
                    if not isinstance(registros_pagina, list):
                        raise ValueError("A API retornou um campo 'registros' inválido.")

                    total_encontrado = int(dados_json.get("totalRegistros", 0))
                    if not registros_pagina:
                        if offset < total_encontrado:
                            raise RuntimeError(
                                f"A API não retornou registros para '{termo}' na posição "
                                f"{offset}, embora informe {total_encontrado} resultados."
                            )
                        break

                    for pacote in registros_pagina:
                        dataset_id = pacote.get("id")
                        if not dataset_id:
                            raise ValueError(
                                "A API retornou um conjunto de dados sem identificador."
                            )
                        conjuntos_por_id.setdefault(dataset_id, pacote)
                        termos_do_conjunto = termos_por_conjunto.setdefault(
                            dataset_id, []
                        )
                        if termo not in termos_do_conjunto:
                            termos_do_conjunto.append(termo)

                    offset += len(registros_pagina)

                print(
                    f"✅ A API encontrou {total_encontrado} conjunto(s) "
                    f"para '{termo}'."
                )

            coleta = {
                "coletado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
                "termos_busca": termos_busca,
                "conjuntos_dados": [],
            }

            for dataset_id, pacote in conjuntos_por_id.items():
                detalhes = await buscar_detalhes(pacote)
                titulo = str(detalhes.get("title", pacote.get("title", "")))
                print(f"\n  [RESULTADO DA BUSCA] {titulo}")

                recursos = detalhes.get("resources", [])
                if not isinstance(recursos, list):
                    raise ValueError(
                        f"A API retornou recursos inválidos para o conjunto {dataset_id}."
                    )

                form = detalhes.get("conjuntoDadosForm") or {}
                edicao = detalhes.get("conjuntoDadosEdicao") or {}
                ods = form.get("relacaoOds")
                if ods is None:
                    ods = edicao.get("relacaoOds", detalhes.get("ods"))

                formatos = detalhes.get("listaFormatos") or list(dict.fromkeys(
                    str(recurso.get("format", "")).strip()
                    for recurso in recursos
                    if recurso.get("format")
                ))
                conjunto_coletado = {
                    "id": detalhes.get("id", dataset_id),
                    "slug": detalhes.get("name", pacote.get("name")),
                    "titulo": titulo,
                    "termos_busca": termos_por_conjunto[dataset_id],
                    "metadados": {
                        "descricao": detalhes.get("notes"),
                        "licenca": {
                            "id": detalhes.get("license_id"),
                            "nome": detalhes.get("license_title"),
                        },
                        "formatos": formatos,
                        "atualizacao": (
                            detalhes.get("periodiciadeFormatado")
                            or detalhes.get("periodiciade")
                        ),
                        "catalogacao": detalhes.get("metadata_created"),
                        "ultima_alteracao_metadados": {
                            "valor": detalhes.get(
                                "dataUltimaAtualizacaoMetadadosFormatado"
                            ),
                            "iso": detalhes.get("dataUltimaAtualizacaoMetadados"),
                        },
                        "ultima_alteracao_arquivo": {
                            "valor": detalhes.get("dataUltimaAtualizacaoDadosFormatado"),
                            "iso": detalhes.get("dataUltimaAtualizacaoDados"),
                        },
                        "area_tecnica_responsavel": (
                            detalhes.get("maintainer") or detalhes.get("author")
                        ),
                        "email_area_tecnica": detalhes.get("maintainer_email"),
                        "ods": ods,
                        "raca_etnia": detalhes.get("racaEtnia"),
                        "genero": detalhes.get("genero"),
                        "versao": detalhes.get("version"),
                        "downloads": detalhes.get("quantidadeDownloads"),
                        "reusos": detalhes.get("quantidadeReusos"),
                        "tags": detalhes.get("tagsFormatado", []),
                        "temas": detalhes.get("temasFormatado", []),
                    },
                    "acoes_disponiveis": [
                        "Sugerir tag",
                        "Reportar um problema",
                        "Sugerir melhoria",
                    ],
                    "conjuntos_dados_similares": {
                        "acessiveis": detalhes.get("conjuntoDadosAssociados", []),
                        "nao_acessiveis": detalhes.get(
                            "conjuntoDadosAssociadosNaoAcessiveis", []
                        ),
                    },
                    "discussoes": [],
                    "erro_discussoes": None,
                    "recursos": [],
                    "resposta_api_completa": detalhes,
                }

                try:
                    discussoes = await consultar_api(
                        "https://dados.gov.br/api/publico/discussao/listar/"
                        f"conjunto-dados/{quote(str(dataset_id), safe='')}"
                        "?ordenacaoDecrescente=true"
                    )
                    if not isinstance(discussoes, list):
                        raise ValueError("A API retornou uma lista de discussões inválida.")
                    conjunto_coletado["discussoes"] = discussoes
                except Exception as erro:
                    conjunto_coletado["erro_discussoes"] = str(erro)
                    print(f"    [Aviso] Não foi possível consultar discussões: {erro}")

                coleta["conjuntos_dados"].append(conjunto_coletado)

                for recurso in recursos:
                    url_arquivo = recurso.get("url")
                    formato_original = str(recurso.get("format", "")).strip()
                    formato_chave = formato_original.lower()
                    formato = extensoes_por_formato.get(
                        formato_chave, formato_chave
                    )
                    nome_original = recurso.get("name") or "arquivo"
                    registro_recurso = {
                        "id": recurso.get("id"),
                        "nome": nome_original,
                        "descricao": recurso.get("description"),
                        "formato": formato_original,
                        "url": url_arquivo,
                        "catalogacao": recurso.get("createdDataFormatada"),
                        "data_catalogacao": recurso.get("created"),
                        "ultima_atualizacao_arquivo": recurso.get(
                            "lastModifiedFormatado"
                        ),
                        "downloads": recurso.get("quantidadeDownloads"),
                        "verificacao_url": recurso.get("urlCheckFormatado"),
                        "url_disponivel": recurso.get("urlDisponivel"),
                        "status_download": "pendente",
                        "arquivo_local": None,
                        "erro": None,
                    }
                    conjunto_coletado["recursos"].append(registro_recurso)

                    if not url_arquivo:
                        recursos_ignorados += 1
                        registro_recurso["status_download"] = "ignorado"
                        registro_recurso["erro"] = "Recurso sem URL."
                        print("    [Ignorado] Recurso sem URL.")
                        continue
                    if formato == "kml" and "kmz" in str(url_arquivo).lower():
                        formato = "kmz"
                    if formato not in formatos_suportados:
                        recursos_ignorados += 1
                        registro_recurso["status_download"] = "ignorado"
                        registro_recurso["erro"] = (
                            f"Formato não baixável: {formato_original}"
                        )
                        print(
                            f"    [Ignorado] Formato não baixável "
                            f"({formato_original}): {nome_original}"
                        )
                        continue

                    nome_limpo = "".join(
                        c for c in nome_original
                        if c.isalnum() or c in (" ", "_", "-")
                    ).strip() or "arquivo"
                    recurso_id = str(recurso.get("id") or "sem_id")
                    nome_arquivo = (
                        f"{dataset_id[:8]}_{recurso_id[:8]}_"
                        f"{nome_limpo[:60]}.{formato}"
                    )
                    caminho = os.path.join(pasta_destino, nome_arquivo)
                    registro_recurso["arquivo_local"] = caminho

                    if os.path.exists(caminho):
                        registro_recurso["status_download"] = "ja_existia"
                        continue

                    caminho_temporario = f"{caminho}.part"
                    print(f"    -> Baixando arquivo: {nome_arquivo}")
                    try:
                        baixar_arquivo_http(
                            url_arquivo,
                            caminho_temporario,
                            headers_download
                        )
                        os.replace(caminho_temporario, caminho)

                        total_baixado += 1
                        registro_recurso["status_download"] = "baixado"
                        print("       [OK] Salvo!")

                    except requests.exceptions.HTTPError as erro_http:
                        if erro_http.response.status_code == 403:
                            print("       [Bloqueio 403] Tentando baixar pelo navegador...")
                            nova_aba = await context.new_page()
                            try:
                                resposta_aba = await nova_aba.goto(
                                    url_arquivo,
                                    timeout=15000
                                )
                                if resposta_aba and resposta_aba.ok:
                                    conteudo_bytes = await nova_aba.body()
                                    with open(caminho_temporario, "wb") as arquivo:
                                        arquivo.write(conteudo_bytes)
                                    os.replace(caminho_temporario, caminho)
                                    total_baixado += 1
                                    registro_recurso["status_download"] = "baixado"
                                    print("       [OK] Salvo pelo navegador.")
                                else:
                                    status = (
                                        resposta_aba.status
                                        if resposta_aba
                                        else None
                                    )
                                    registro_recurso["status_download"] = "falha"
                                    registro_recurso["erro"] = (
                                        f"Servidor respondeu HTTP {status} no navegador."
                                    )
                                    registro_recurso["http_status"] = status
                                    print(
                                        f"       [Erro] O servidor respondeu: "
                                        f"{status or 'sem resposta'}."
                                    )
                                    total_falhas += 1
                            except Exception as erro:
                                registro_recurso["status_download"] = "falha"
                                registro_recurso["erro"] = str(erro)
                                total_falhas += 1
                                print(
                                    f"       [Erro] Falha ao baixar pelo navegador: {erro}"
                                )
                            finally:
                                await nova_aba.close()
                        else:
                            status = erro_http.response.status_code
                            registro_recurso["status_download"] = "falha"
                            registro_recurso["http_status"] = status
                            registro_recurso["erro"] = str(erro_http)
                            print(f"       [Erro] HTTP {status}: {erro_http}")
                            total_falhas += 1
                    except requests.exceptions.RequestException as erro:
                        registro_recurso["status_download"] = "falha"
                        registro_recurso["erro"] = str(erro)
                        print(
                            f"       [Erro] Falha de conexão ao baixar o arquivo: {erro}"
                        )
                        total_falhas += 1
                    finally:
                        if os.path.exists(caminho_temporario):
                            os.remove(caminho_temporario)
        finally:
            await browser.close()

    coleta["resumo"] = {
        "conjuntos_dados": len(coleta["conjuntos_dados"]),
        "arquivos_baixados": total_baixado,
        "falhas_download": total_falhas,
        "recursos_ignorados": recursos_ignorados,
    }
    with open(
        os.path.join(pasta_destino, "relacionamento_validados.json"),
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(coleta, f, ensure_ascii=False, indent=4)

    print(
        f"\n✅ Coleta concluída! {total_baixado} arquivo(s) foram salvos; "
        f"{total_falhas} falha(s) no servidor; "
        f"{recursos_ignorados} recurso(s) não baixável(is) foram ignorados."
    )


if __name__ == "__main__":
    termos = ["desastre", "rio doce", "barragem fundão", "fundação renova"]
    asyncio.run(coletar_dados_exatos_invisivel(termos))
