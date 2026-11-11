#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 10 17:44:21 2026

@author: fabiolicht
"""

import json

nome_arquivo = "datasets_rio_doce.json"

try:
    with open(nome_arquivo, "r", encoding="utf-8") as f:
        dados = json.load(f)
        
    if isinstance(dados, dict):
        print("Chaves principais retornadas pela API:")
        for chave in dados.keys():
            print(f" - {chave}")
            
        chave_dados = next((k for k in ['itens', 'content', 'resultados', 'results', 'conjuntos'] if k in dados), None)
        
        if chave_dados and isinstance(dados[chave_dados], list):
            pacotes = dados[chave_dados]
            print(f"\nTotal de pacotes encontrados nesta página: {len(pacotes)}")
            
            if pacotes:
                print("\nEstrutura do primeiro pacote de dados:")
                # Imprime as chaves do primeiro item para descobrirmos onde estão os arquivos (resources)
                for k, v in pacotes[0].items():
                    print(f"   {k}: {type(v).__name__}")
        else:
            print("\nEstrutura do JSON (primeiros 500 caracteres):")
            print(str(dados)[:500])
            
    elif isinstance(dados, list):
        print(f"A API retornou uma lista direta com {len(dados)} itens.")
        if dados:
            print("Chaves do primeiro item:")
            print(list(dados[0].keys()))

except FileNotFoundError:
    print(f"O arquivo {nome_arquivo} não foi encontrado no diretório atual.")