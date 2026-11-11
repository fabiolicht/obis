import os
import json
import requests
import asyncio
from urllib.parse import urlencode
from playwright.async_api import async_playwright
import nest_asyncio

nest_asyncio.apply()


async def coletar_dados_exatos_invisivel(termos_busca, pasta_destino="downloads_mariana_riodoce"):
    os.makedirs(pasta_destino, exist_ok=True)
    log_relacionamento = []
    total_baixado = 0

    headers_download = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    formatos_suportados = {"csv", "pdf", "xlsx", "xls", "zip", "json"}
    extensoes_por_formato = {
        "application/json": "json",
        "text/csv": "csv",
        "shape-zip": "zip",
        "shp-zip": "zip",
    }

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
                    url_api,
                )

            conjuntos_por_id = {}
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

                    offset += len(registros_pagina)

                print(
                    f"✅ A API encontrou {total_encontrado} conjunto(s) "
                    f"para '{termo}'."
                )

            for pacote in conjuntos_por_id.values():
                dataset_id = pacote["id"]
                titulo = str(pacote.get("title", ""))
                print(f"\n  [RESULTADO DA BUSCA] {titulo}")
                recursos = pacote.get("resourcesFormatado", [])

                for recurso in recursos:
                    url_arquivo = recurso.get("url")
                    formato_original = str(recurso.get("format", "")).strip().lower()
                    formato = extensoes_por_formato.get(
                        formato_original, formato_original
                    )
                    nome_original = recurso.get("name") or "arquivo"

                    if not url_arquivo or formato not in formatos_suportados:
                        continue

                    nome_limpo = "".join(
                        c for c in nome_original
                        if c.isalnum() or c in (" ", "_", "-")
                    ).strip() or "arquivo"
                    nome_arquivo = f"{dataset_id[:8]}_{nome_limpo[:60]}.{formato}"
                    caminho = os.path.join(pasta_destino, nome_arquivo)

                    if os.path.exists(caminho):
                        continue

                    print(f"    -> Baixando arquivo: {nome_arquivo}")
                    try:
                        with requests.get(
                            url_arquivo,
                            headers=headers_download,
                            stream=True,
                            timeout=12
                        ) as resp:
                            resp.raise_for_status()
                            with open(caminho, "wb") as arquivo:
                                for chunk in resp.iter_content(chunk_size=8192):
                                    arquivo.write(chunk)

                        total_baixado += 1
                        log_relacionamento.append({
                            "dataset": titulo,
                            "arquivo": nome_arquivo,
                            "url": url_arquivo
                        })
                        print("       [OK] Salvo!")

                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code == 403:
                            print("       [Bloqueio 403] Tentando baixar pelo navegador...")
                            nova_aba = await context.new_page()
                            try:
                                resposta_aba = await nova_aba.goto(
                                    url_arquivo,
                                    timeout=15000
                                )
                                if resposta_aba and resposta_aba.ok:
                                    conteudo_bytes = await nova_aba.body()
                                    with open(caminho, "wb") as arquivo:
                                        arquivo.write(conteudo_bytes)
                                    total_baixado += 1
                                    log_relacionamento.append({
                                        "dataset": titulo,
                                        "arquivo": nome_arquivo,
                                        "url": url_arquivo
                                    })
                                    print("       [OK] Salvo pelo navegador.")
                                else:
                                    status = (
                                        resposta_aba.status
                                        if resposta_aba
                                        else "sem resposta"
                                    )
                                    print(f"       [Erro] O servidor respondeu: {status}.")
                            except Exception as erro:
                                print(
                                    f"       [Erro] Falha ao baixar pelo navegador: {erro}"
                                )
                            finally:
                                await nova_aba.close()
                        else:
                            print(f"       [Erro] HTTP {e.response.status_code}: {e}")
                    except requests.exceptions.RequestException as e:
                        print(
                            f"       [Erro] Falha de conexão ao baixar o arquivo: {e}"
                        )
        finally:
            await browser.close()

    if log_relacionamento:
        with open(
            os.path.join(pasta_destino, "relacionamento_validados.json"),
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(log_relacionamento, f, ensure_ascii=False, indent=4)

    print(f"\n✅ Coleta concluída! {total_baixado} arquivo(s) foram salvos.")


if __name__ == "__main__":
    termos = ["desastre", "rio doce", "barragem fundão", "fundação renova"]
    asyncio.run(coletar_dados_exatos_invisivel(termos))
