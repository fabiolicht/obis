import os
import json
import requests
import asyncio
from playwright.async_api import async_playwright
import nest_asyncio

nest_asyncio.apply()

async def coletar_dados_exatos_invisivel(termos_busca, pasta_destino="downloads_mariana_riodoce"):
    os.makedirs(pasta_destino, exist_ok=True)
    log_relacionamento = []
    total_baixado = 0
    
    validadores = ["mariana", "rio doce", "samarco", "renova", "fundão", "desastre", "rompimento", "bacia"]
    headers_download = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            accept_downloads=True
        )
        page = await context.new_page()
        
        print("Acessando o portal e aguardando a poeira baixar (carga inicial de 19 mil registros)...")
        await page.goto("https://dados.gov.br/dados/conjuntos-dados", wait_until="networkidle")
        await page.wait_for_timeout(3000)

        for termo in termos_busca:
            print(f"\n{'='*50}\nBuscando: '{termo}' (Modo Exato)")
            
            loop = asyncio.get_running_loop()
            futuro_json = loop.create_future()
            
            async def interceptar(response):
                if "conjuntos-dados/buscar" in response.url and response.status == 200:
                    try:
                        conteudo = await response.json()
                        total = conteudo.get('totalRegistros', 0)
                        if total < 15000 and not futuro_json.done():
                            futuro_json.set_result(conteudo)
                    except:
                        pass
                        
            page.on("response", interceptar)
            
            try:
                campo = page.locator('input[type="search"]').first
                if await campo.count() == 0:
                    campo = page.locator("input").first
                
                await campo.clear()
                
                termo_exato = f'"{termo}"'
                await campo.fill(termo_exato)
                await campo.press("Enter")
                
                dados_json = await asyncio.wait_for(futuro_json, timeout=10.0)
                
            except asyncio.TimeoutError:
                print(f"❌ A API não encontrou ou não retornou dados para '{termo}'.")
                dados_json = None
            except Exception as e:
                print(f"❌ Erro na interface de busca: {e}")
                dados_json = None
            finally:
                page.remove_listener("response", interceptar)

            if not dados_json:
                continue

            total_encontrado = dados_json.get('totalRegistros', 0)
            registros = dados_json.get('registros', [])
            print(f"✅ JSON interceptado na mosca! O site encontrou {total_encontrado} pacote(s).")
            
            if total_encontrado == 0:
                continue

            for pacote in registros:
                dataset_id = pacote.get('id', 'sem_id')
                titulo = str(pacote.get('title', '')).lower()
                notas = str(pacote.get('notes', '')).lower()
                
                if not any(val in titulo or val in notas for val in validadores):
                    continue
                    
                print(f"\n  [VALIDADO] Pacote Relevante: {pacote.get('title', '')}")
                recursos = pacote.get('resourcesFormatado', [])
                
                for recurso in recursos:
                    url_arquivo = recurso.get('url')
                    formato = str(recurso.get('format', '')).lower()
                    nome_original = recurso.get('name', 'arquivo')
                    
                    if url_arquivo and formato in ['pdf', 'csv', 'xlsx', 'xls', 'zip', 'json']:
                        if url_arquivo.startswith("http://"):
                            url_arquivo = url_arquivo.replace("http://", "https://")
                            
                        extensao = f".{formato.split('+')[0]}" if '+' in formato else f".{formato}"
                        nome_limpo = "".join(c for c in nome_original if c.isalnum() or c in (' ', '_', '-')).strip()
                        nome_arquivo = f"{dataset_id[:8]}_{nome_limpo[:60]}{extensao}"
                        caminho = os.path.join(pasta_destino, nome_arquivo)
                        
                        if not os.path.exists(caminho):
                            print(f"    -> Baixando arquivo: {nome_arquivo}")
                            try:
                                resp = requests.get(url_arquivo, headers=headers_download, stream=True, timeout=12)
                                resp.raise_for_status()
                                with open(caminho, 'wb') as f:
                                    for chunk in resp.iter_content(chunk_size=8192):
                                        f.write(chunk)
                                total_baixado += 1
                                log_relacionamento.append({"dataset": titulo, "arquivo": nome_arquivo, "url": url_arquivo})
                                print("       [OK] Salvo!")
                                
                            except requests.exceptions.HTTPError as e:
                                if e.response.status_code == 403:
                                    print("       [Bloqueio 403] Extraindo dados renderizados na tela da nova aba (IBGE)...")
                                    nova_aba = await context.new_page()
                                    try:
                                        resposta_aba = await nova_aba.goto(url_arquivo, timeout=15000)
                                        if resposta_aba and resposta_aba.ok:
                                            conteudo_bytes = await resposta_aba.body()
                                            with open(caminho, 'wb') as f:
                                                f.write(conteudo_bytes)
                                            total_baixado += 1
                                            log_relacionamento.append({"dataset": titulo, "arquivo": nome_arquivo, "url": url_arquivo})
                                            print("       [OK] Salvo lendo o corpo da página.")
                                        else:
                                            print("       [Descartado] O GeoServer bloqueou o acesso ou não retornou dados.")
                                    except Exception:
                                        print("       [Descartado] Link WFS quebrado/offline.")
                                    finally:
                                        await nova_aba.close()
                                else:
                                    print(f"       [Descartado] Erro HTTP {e.response.status_code} (Removido pelo órgão).")
                            except Exception:
                                print("       [Descartado] Falha de conexão ou timeout.")

        await browser.close()
        
    if log_relacionamento:
        with open(os.path.join(pasta_destino, "relacionamento_validados.json"), "w", encoding="utf-8") as f:
            json.dump(log_relacionamento, f, ensure_ascii=False, indent=4)
            
    print(f"\n✅ Coleta blindada concluída! {total_baixado} documentos REAIS foram salvos.")

if __name__ == "__main__":
    termos = ["rio doce", "desastre", "barragem fundão", "fundação renova"]
    asyncio.run(coletar_dados_exatos_invisivel(termos))
