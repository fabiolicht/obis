import asyncio
import importlib.util
import io
import json
import queue
import re
import threading
import unicodedata
from abc import ABC, abstractmethod
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, Text, END, messagebox, ttk

from gerenciador_download import GerenciadorDownloads


PASTA_SCRIPTS = Path(__file__).resolve().parent
PASTA_RESULTADOS = PASTA_SCRIPTS / "resultados_busca"


def carregar_script(nome_arquivo):
    caminho = PASTA_SCRIPTS / nome_arquivo
    especificacao = importlib.util.spec_from_file_location(caminho.stem, caminho)
    if especificacao is None or especificacao.loader is None:
        raise ImportError(f"Não foi possível carregar o script: {caminho}")

    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    return modulo


def criar_slug(texto):
    normalizado = unicodedata.normalize("NFKD", texto)
    sem_acentos = normalizado.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", sem_acentos).strip("_").lower()
    return slug or "consulta"


class ProvedorBusca(ABC):
    nome = ""
    script = ""

    def caminho_resultado(self, termo):
        PASTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
        return PASTA_RESULTADOS / f"{self.script}_{criar_slug(termo)}.json"

    def baixar(self, arquivo_json):
        return GerenciadorDownloads(PASTA_SCRIPTS).baixar_json(
            arquivo_json,
            self.script,
        )

    @abstractmethod
    def pesquisar(self, termo):
        raise NotImplementedError


class DadosGovProvider(ProvedorBusca):
    nome = "Dados.gov.br"
    script = "dadosgov"

    def pesquisar(self, termo):
        modulo = carregar_script("DadosGov_json.py")
        caminho = self.caminho_resultado(termo)
        resultados = asyncio.run(modulo.capturar_datasets(termo))
        if resultados is None:
            raise RuntimeError("A API do Dados.gov.br não retornou resultados.")
        with caminho.open("w", encoding="utf-8") as arquivo:
            json.dump(
                {
                    "fonte": self.nome,
                    "termo_busca": termo,
                    "arquivos_baixados": [],
                    "resultados": resultados,
                },
                arquivo,
                ensure_ascii=False,
                indent=4,
            )
        return caminho


class IdeSisemaProvider(ProvedorBusca):
    nome = "IDE-Sisema"
    script = "idesisema"

    def pesquisar(self, termo):
        modulo = carregar_script("IDE-Sisema_json.py")
        caminho = self.caminho_resultado(termo)
        modulo.coletar_dados_idesisema(termo, arquivo_saida=str(caminho))
        return caminho


class IndeProvider(ProvedorBusca):
    nome = "INDE"
    script = "inde"

    def pesquisar(self, termo):
        modulo = carregar_script("INDE_json.py")
        caminho = self.caminho_resultado(termo)
        modulo.coletar_dados_inde(termo, arquivo_saida=str(caminho))
        return caminho


class HidroWebProvider(ProvedorBusca):
    nome = "ANA HidroWeb (consulta por nome do rio)"
    script = "hidroweb"

    def pesquisar(self, termo):
        modulo = carregar_script("PortalHidroWeb.py")
        caminho = self.caminho_resultado(termo)
        modulo.coletar_dados_hidroweb(
            rios_alvo=[termo],
            baixar_arquivos=False,
            arquivo_json=str(caminho),
        )
        return caminho

    def baixar(self, arquivo_json):
        modulo = carregar_script("PortalHidroWeb.py")
        return modulo.baixar_arquivos_hidroweb(str(arquivo_json))


class MapBiomasProvider(ProvedorBusca):
    nome = "MapBiomas (bacia do Rio Doce)"
    script = "mapbiomas"

    def pesquisar(self, termo):
        caminho = self.caminho_resultado(termo)
        with caminho.open("w", encoding="utf-8") as arquivo:
            json.dump(
                {
                    "fonte": "MapBiomas",
                    "termo_busca": termo,
                    "regiao": "Bacia do Rio Doce",
                    "bandas": [
                        "classification_2014",
                        "classification_2016",
                        "classification_2022",
                    ],
                    "arquivos_exportados": [
                        {
                            "ano": banda.rsplit("_", 1)[-1],
                            "arquivo_exportado": (
                                f"MapBiomas_RioDoce_{banda.rsplit('_', 1)[-1]}.tif"
                            ),
                        }
                        for banda in (
                            "classification_2014",
                            "classification_2016",
                            "classification_2022",
                        )
                    ],
                    "arquivos_baixados": [],
                },
                arquivo,
                ensure_ascii=False,
                indent=4,
            )
        return caminho

    def baixar(self, arquivo_json):
        modulo = carregar_script("MapBiomas.py")
        return modulo.baixar_mapbiomas_rio_doce(str(arquivo_json))


class PesquisadorCatalogos:
    def __init__(self):
        self.provedores = {
            "dadosgov": DadosGovProvider(),
            "idesisema": IdeSisemaProvider(),
            "inde": IndeProvider(),
            "hidroweb": HidroWebProvider(),
            "mapbiomas": MapBiomasProvider(),
        }

    def pesquisar(self, fontes):
        for fonte in fontes:
            yield self.provedores[fonte]


class InterfaceBusca:
    def __init__(self, janela):
        self.janela = janela
        self.janela.title("Busca de catálogos ambientais")
        self.janela.geometry("760x540")
        self.pesquisador = PesquisadorCatalogos()
        self.fila_mensagens = queue.Queue()
        self.termo = StringVar()
        self.ultima_busca_termo = None
        self.resultados_pesquisados = {}
        self.fontes = {
            "dadosgov": BooleanVar(value=False),
            "idesisema": BooleanVar(value=False),
            "inde": BooleanVar(value=False),
            "hidroweb": BooleanVar(value=False),
            "mapbiomas": BooleanVar(value=False),
        }

        self._montar_tela()
        self.janela.after(100, self._processar_mensagens)

    def _montar_tela(self):
        principal = ttk.Frame(self.janela, padding=16)
        principal.pack(fill="both", expand=True)
        principal.columnconfigure(0, weight=1)

        ttk.Label(
            principal,
            text="Pesquisar nos catálogos",
            font=("TkDefaultFont", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(principal, text="Termo de busca:").grid(
            row=1, column=0, sticky="w", pady=(14, 4)
        )

        campo_busca = ttk.Entry(principal, textvariable=self.termo)
        campo_busca.grid(row=2, column=0, sticky="ew")
        campo_busca.bind("<Return>", self._ao_pressionar_enter)

        quadro_fontes = ttk.LabelFrame(
            principal, text="Mecanismos", padding=(10, 6)
        )
        quadro_fontes.grid(row=3, column=0, sticky="ew", pady=12)
        descricoes = {
            "dadosgov": "Dados.gov.br",
            "idesisema": "IDE-Sisema",
            "inde": "INDE",
            "hidroweb": "ANA HidroWeb (consulta por nome do rio)",
            "mapbiomas": "MapBiomas (GeoTIFF local; bacia do Rio Doce)",
        }
        for linha, (chave, descricao) in enumerate(descricoes.items()):
            ttk.Checkbutton(
                quadro_fontes,
                text=descricao,
                variable=self.fontes[chave],
            ).grid(row=linha, column=0, sticky="w")

        ttk.Label(
            principal,
            text=(
                "Pesquisar salva apenas o JSON. Download usa os resultados "
                "pesquisados e grava os arquivos em 'OBIS_Coletas/Downloads'; "
                "nome e caminho locais são registrados no JSON. MapBiomas "
                "baixa GeoTIFFs locais via Earth Engine."
            ),
            wraplength=700,
        ).grid(row=4, column=0, sticky="w", pady=(0, 10))

        self.botao_pesquisar = ttk.Button(
            principal, text="Pesquisar", command=self.iniciar_pesquisa
        )
        self.botao_pesquisar.grid(row=5, column=0, sticky="nw")

        self.botao_download = ttk.Button(
            principal, text="Download", command=self.iniciar_download
        )
        self.botao_download.grid(row=5, column=0, sticky="nw", padx=(100, 0))

        self.saida = Text(principal, height=14, wrap="word", state="disabled")
        self.saida.grid(row=6, column=0, sticky="nsew", pady=(10, 0))
        principal.rowconfigure(6, weight=1)

    def _ao_pressionar_enter(self, evento):
        if evento.keysym == "Return":
            self.iniciar_pesquisa()
            return "break"
        return None

    def iniciar_pesquisa(self):
        termo = self.termo.get().strip()
        fontes = [
            chave for chave, selecionado in self.fontes.items()
            if selecionado.get()
        ]
        if not termo:
            messagebox.showwarning("Busca", "Digite um termo para pesquisar.")
            return
        if not fontes:
            messagebox.showwarning(
                "Busca", "Selecione ao menos um mecanismo de pesquisa."
            )
            return

        self.ultima_busca_termo = None
        self.resultados_pesquisados = {}
        self._definir_botoes_habilitados(False)
        self._adicionar_saida(f"Iniciando busca por: {termo}\n")
        threading.Thread(
            target=self._executar_pesquisa,
            args=(termo, fontes),
            daemon=True,
        ).start()

    def iniciar_download(self):
        termo = self.termo.get().strip()
        fontes = [
            chave for chave, selecionado in self.fontes.items()
            if selecionado.get()
        ]
        if not fontes:
            messagebox.showwarning(
                "Download", "Selecione ao menos um mecanismo de pesquisa."
            )
            return
        if not self.ultima_busca_termo or termo != self.ultima_busca_termo:
            messagebox.showwarning(
                "Download",
                "Pesquise primeiro esse termo. O download usa os JSONs da última busca.",
            )
            return

        ausentes = [
            chave for chave in fontes
            if chave not in self.resultados_pesquisados
        ]
        if ausentes:
            nomes = ", ".join(self.pesquisador.provedores[chave].nome for chave in ausentes)
            messagebox.showwarning(
                "Download",
                f"Pesquise antes nos seguintes mecanismos: {nomes}.",
            )
            return

        self._definir_botoes_habilitados(False)
        self._adicionar_saida(f"Iniciando downloads para: {termo}\n")
        caminhos = {
            chave: self.resultados_pesquisados[chave]
            for chave in fontes
        }
        threading.Thread(
            target=self._executar_downloads,
            args=(caminhos,),
            daemon=True,
        ).start()

    def _executar_pesquisa(self, termo, fontes):
        try:
            for provedor in self.pesquisador.pesquisar(fontes):
                chave = provedor.script
                self.fila_mensagens.put(
                    ("texto", f"\n[{provedor.nome}] pesquisando...\n")
                )
                log = io.StringIO()
                try:
                    with redirect_stdout(log), redirect_stderr(log):
                        caminho = provedor.pesquisar(termo)
                except Exception as erro:
                    detalhes = log.getvalue()
                    if detalhes:
                        self.fila_mensagens.put(("texto", detalhes))
                    self.fila_mensagens.put(
                        ("texto", f"[ERRO] {provedor.nome}: {erro}\n")
                    )
                else:
                    detalhes = log.getvalue()
                    if detalhes:
                        self.fila_mensagens.put(("texto", detalhes))
                    self.fila_mensagens.put(
                        ("resultado_busca", (chave, caminho))
                    )
                    self.fila_mensagens.put(
                        ("texto", f"[OK] JSON salvo em: {caminho}\n")
                    )
        except Exception as erro:
            self.fila_mensagens.put(("texto", f"[ERRO] Busca: {erro}\n"))
        finally:
            self.fila_mensagens.put(("busca_concluida", termo))

    def _executar_downloads(self, caminhos):
        try:
            for chave, caminho in caminhos.items():
                provedor = self.pesquisador.provedores[chave]
                self.fila_mensagens.put(
                    ("texto", f"\n[{provedor.nome}] baixando...\n")
                )
                log = io.StringIO()
                try:
                    with redirect_stdout(log), redirect_stderr(log):
                        quantidade, erros = provedor.baixar(caminho)
                except Exception as erro:
                    detalhes = log.getvalue()
                    if detalhes:
                        self.fila_mensagens.put(("texto", detalhes))
                    self.fila_mensagens.put(
                        ("texto", f"[ERRO] {provedor.nome}: {erro}\n")
                    )
                else:
                    detalhes = log.getvalue()
                    if detalhes:
                        self.fila_mensagens.put(("texto", detalhes))
                    self.fila_mensagens.put(
                        (
                            "texto",
                            f"[OK] {provedor.nome}: {quantidade} arquivo(s) "
                            f"baixado(s); JSON atualizado.\n",
                        )
                    )
                    for erro in erros:
                        self.fila_mensagens.put(
                            ("texto", f"[ERRO DE ARQUIVO] {provedor.nome}: {erro}\n")
                        )
        except Exception as erro:
            self.fila_mensagens.put(("texto", f"[ERRO] Download: {erro}\n"))
        finally:
            self.fila_mensagens.put(("concluido", "Downloads concluídos.\n"))

    def _definir_botoes_habilitados(self, habilitados):
        estado = "normal" if habilitados else "disabled"
        self.botao_pesquisar.configure(state=estado)
        self.botao_download.configure(state=estado)

    def _processar_mensagens(self):
        while True:
            try:
                tipo, mensagem = self.fila_mensagens.get_nowait()
            except queue.Empty:
                break

            if tipo == "texto":
                self._adicionar_saida(mensagem)
            elif tipo == "resultado_busca":
                chave, caminho = mensagem
                self.resultados_pesquisados[chave] = caminho
            elif tipo == "busca_concluida":
                self.ultima_busca_termo = mensagem
                self._definir_botoes_habilitados(True)
            elif tipo == "concluido":
                self._adicionar_saida(mensagem)
                self._definir_botoes_habilitados(True)

        self.janela.after(100, self._processar_mensagens)

    def _adicionar_saida(self, mensagem):
        self.saida.configure(state="normal")
        self.saida.insert(END, mensagem)
        self.saida.see(END)
        self.saida.configure(state="disabled")


def main():
    janela = Tk()
    InterfaceBusca(janela)
    janela.mainloop()


if __name__ == "__main__":
    main()
