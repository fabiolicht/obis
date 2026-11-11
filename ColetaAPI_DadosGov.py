#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 10 16:25:06 2026

@author: fabiolicht
"""

import asyncio
import json
from playwright.async_api import async_playwright
import nest_asyncio

nest_asyncio.apply()

async def capturar_datasets(termo):
    url_busca = f"https://dados.gov.br/dados/conjuntos-dados?palavrasChaves={termo.replace(' ', '%20')}"
    dados_extraidos = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        async def handle_response(response):
            nonlocal dados_extraidos
            # Filtra apenas a rota que traz os resultados da busca
            if "conjuntos-dados/buscar" in response.url and response.status == 200:
                try:
                    conteudo = await response.json()
                    # A maioria das APIs pagina os resultados dentro de uma chave 'itens', 'content' ou 'resultados'
                    # Vamos capturar o JSON inteiro para você inspecionar a estrutura
                    dados_extraidos = conteudo
                    print(f"✅ Dados interceptados da API: {response.url}")
                except Exception as e:
                    print(f"Erro ao decodificar JSON: {e}")

        page.on("response", handle_response)
        
        print(f"Acessando o portal e aguardando a API responder para o termo: '{termo}'")
        await page.goto(url_busca, wait_until="networkidle")
        await page.wait_for_timeout(4000) 
        
        await browser.close()
        
    return dados_extraidos

async def main():
    resultados = await capturar_datasets("rio doce")
    
    if resultados:
        nome_arquivo = "datasets_rio_doce.json"
        with open(nome_arquivo, "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=4)
            
        print(f"\nColeta focada concluída! Execute: cat {nome_arquivo}")
    else:
        print("A API /buscar não respondeu a tempo ou a estrutura mudou.")

if __name__ == "__main__":
    asyncio.run(main())