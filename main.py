# =============================================================================
#  SERVIDOR CHECKLIST TÉCNICO
#  Tecnologia: Python stdlib — sem dependências externas (zero pip install)
#
#  Por que usar stdlib?
#    Facilita o deploy em qualquer ambiente (Railway, Render, VPS) sem precisar
#    de requirements.txt com pacotes pesados como Flask ou FastAPI.
#
#  Como funciona um servidor HTTP básico em Python:
#    HTTPServer: gerencia a socket TCP, aceita conexões e despacha para Handler.
#    BaseHTTPRequestHandler: classe base; sobrescrevemos do_GET e do_POST para
#    tratar cada tipo de requisição HTTP recebida.
#
#  Rotas disponíveis:
#    GET  /                  → verifica se servidor está online
#    GET  /checklists        → lista arquivos JSON salvos
#    GET  /pdfs              → lista arquivos PDF salvos
#    GET  /pdfs/<arquivo>    → baixa um PDF específico
#    POST /                  → recebe dados do checklist como JSON
#    POST /upload-pdf        → recebe um arquivo PDF em bytes brutos
# =============================================================================

from http.server import HTTPServer, BaseHTTPRequestHandler
import json, os, datetime

# Pastas onde os arquivos serão salvos.
# os.makedirs com exist_ok=True não lança erro se a pasta já existir.
PASTA_JSON = "checklists"
PASTA_PDF  = "pdfs"
os.makedirs(PASTA_JSON, exist_ok=True)
os.makedirs(PASTA_PDF,  exist_ok=True)

# Railway (e outros serviços de hosting) define a porta via variável de ambiente PORT.
# Se não existir (rodando localmente), usa 8000 como padrão.
PORT = int(os.environ.get("PORT", 8000))


class Handler(BaseHTTPRequestHandler):
    """
    Classe que processa cada requisição HTTP recebida.

    O Python cria uma nova instância desta classe para cada conexão.
    Métodos do_GET e do_POST são chamados automaticamente conforme o método HTTP.

    Como funciona o protocolo HTTP (resumo):
      1. Cliente (app Android) abre conexão TCP com o servidor
      2. Envia linha de requisição: "POST /upload-pdf HTTP/1.1"
      3. Envia headers (Content-Type, Content-Length, etc.)
      4. Envia corpo (body) com os dados
      5. Servidor processa e responde com status + body
    """

    # ──────────────────────────────────────────────────────────────────────────
    #  POST
    # ──────────────────────────────────────────────────────────────────────────

    def do_POST(self):
        """
        Roteador de requisições POST.
        self.path contém o caminho da URL (ex: "/upload-pdf").
        Delega para o método correto conforme o caminho.
        """
        if self.path == "/upload-pdf":
            self._receber_pdf()
        else:
            # Qualquer outro caminho (incluindo "/") trata como checklist JSON
            self._receber_checklist()

    def _receber_checklist(self):
        """
        Recebe o checklist completo como JSON e salva em arquivo .json.

        Fluxo:
          1. Lê Content-Length para saber quantos bytes o corpo tem
          2. Lê exatamente esses bytes do socket (self.rfile)
          3. Converte bytes → string → dict Python via json.loads()
          4. Monta nome único para o arquivo: cliente_YYYYMMDD_HHMMSS.json
          5. Salva com indentação legível (indent=2)
          6. Responde 200 OK com JSON {"status":"ok"}
        """
        tamanho = int(self.headers.get("Content-Length", 0))
        corpo   = self.rfile.read(tamanho)  # lê corpo cru em bytes

        try:
            # json.loads: deserializa bytes/string JSON → dict Python
            dados = json.loads(corpo)

            # Sanitiza o nome do cliente para uso em nome de arquivo
            cliente = dados.get("cliente", "sem_cliente").replace(" ", "_")
            agora   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            caminho = f"{PASTA_JSON}/{cliente}_{agora}.json"

            # Salva o dict como JSON formatado (ensure_ascii=False preserva acentos)
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)

            print(f"[JSON] Salvo: {caminho}", flush=True)
            self._responder(200, {"status": "ok", "arquivo": caminho})

        except Exception as e:
            print(f"[ERRO JSON] {e}", flush=True)
            self._responder(400, {"status": "erro", "detalhe": str(e)})

    def _receber_pdf(self):
        """
        Recebe um arquivo PDF enviado em bytes brutos (raw binary) e salva em disco.

        Por que bytes brutos e não multipart/form-data?
          Simplicidade: o cliente lê o arquivo e envia o conteúdo direto no corpo.
          O header X-Nome-Arquivo carrega o nome desejado para o arquivo.

        Fluxo:
          1. Lê Content-Length (tamanho do PDF em bytes)
          2. Lê todos os bytes do corpo (binário — não é texto)
          3. Lê o nome do arquivo do header personalizado X-Nome-Arquivo
          4. Sanitiza o nome (remove caracteres perigosos para evitar path traversal)
          5. Salva com "wb" (write binary — obrigatório para arquivos não-texto)
          6. Responde com nome do arquivo salvo
        """
        tamanho = int(self.headers.get("Content-Length", 0))
        dados   = self.rfile.read(tamanho)  # bytes do PDF — NÃO usar .decode()!

        # Lê o nome sugerido pelo app Android, ou usa padrão
        nome_original = self.headers.get("X-Nome-Arquivo", "relatorio.pdf")

        # Sanitização: permite apenas alfanuméricos, ponto, underscore e hífen.
        # Evita que um nome como "../../etc/passwd" sobrescreva arquivos do sistema.
        nome_seguro = "".join(c for c in nome_original if c.isalnum() or c in "._-")
        if not nome_seguro.endswith(".pdf"):
            nome_seguro += ".pdf"

        agora   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho = f"{PASTA_PDF}/{agora}_{nome_seguro}"

        # "wb" = write binary: necessário para salvar arquivos PDF corretamente
        with open(caminho, "wb") as f:
            f.write(dados)

        print(f"[PDF] Salvo: {caminho} ({len(dados)} bytes)", flush=True)
        self._responder(200, {"status": "ok", "arquivo": caminho, "bytes": len(dados)})

    # ──────────────────────────────────────────────────────────────────────────
    #  GET
    # ──────────────────────────────────────────────────────────────────────────

    def do_GET(self):
        """
        Roteador de requisições GET.
        Cada 'elif' verifica o caminho e chama o tratador correto.
        """
        if self.path == "/":
            # Health check: confirma que o servidor está rodando
            self._responder(200, {"status": "online"})

        elif self.path == "/checklists":
            # Lista todos os arquivos JSON salvos, do mais recente ao mais antigo
            arquivos = sorted(os.listdir(PASTA_JSON), reverse=True)
            self._responder(200, arquivos)

        elif self.path == "/pdfs":
            # Lista todos os PDFs salvos
            arquivos = sorted(os.listdir(PASTA_PDF), reverse=True)
            self._responder(200, arquivos)

        elif self.path.startswith("/pdfs/"):
            # Serve um PDF específico para download.
            # ex: GET /pdfs/20260314_123000_cliente.pdf
            self._servir_pdf(self.path[len("/pdfs/"):])

        else:
            self.send_response(404)
            self.end_headers()

    def _servir_pdf(self, nome_arquivo):
        """
        Lê o PDF do disco e envia como resposta binária.

        Por que isso é útil?
          Permite que o escritório acesse os PDFs diretamente pelo navegador,
          digitando a URL do servidor + /pdfs/nome_do_arquivo.pdf

        Content-Type: application/pdf informa ao navegador como abrir o arquivo.
        Content-Disposition: inline → tenta abrir no navegador (não forçar download).
        """
        # Bloqueia tentativas de path traversal (ex: "../../etc/passwd")
        nome_seguro = os.path.basename(nome_arquivo)
        caminho     = os.path.join(PASTA_PDF, nome_seguro)

        if not os.path.isfile(caminho):
            self.send_response(404)
            self.end_headers()
            return

        with open(caminho, "rb") as f:
            dados = f.read()

        self.send_response(200)
        self.send_header("Content-Type",        "application/pdf")
        self.send_header("Content-Length",      str(len(dados)))
        self.send_header("Content-Disposition", f'inline; filename="{nome_seguro}"')
        self.end_headers()
        self.wfile.write(dados)  # envia bytes brutos do PDF

    # ──────────────────────────────────────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _responder(self, codigo: int, dados):
        """
        Atalho para enviar uma resposta JSON.

        Parâmetros:
          codigo: código HTTP (200 = ok, 400 = bad request, 404 = not found)
          dados:  dict ou list que será serializado para JSON

        json.dumps converte dict/list Python → string JSON.
        .encode() converte string → bytes (necessário para wfile.write).
        """
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, format, *args):
        """
        Sobrescrito para silenciar os logs padrão do HTTPServer.
        Mantemos apenas os prints manuais com [JSON] e [PDF] para clareza.
        """
        pass


# ──────────────────────────────────────────────────────────────────────────────
#  Ponto de entrada
#  Quando este arquivo é executado diretamente (python main.py), o bloco
#  abaixo roda. Se importado como módulo, não roda (boa prática Python).
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Servidor iniciado na porta {PORT}", flush=True)
    print(f"  JSONs salvos em: ./{PASTA_JSON}/", flush=True)
    print(f"  PDFs  salvos em: ./{PASTA_PDF}/",  flush=True)

    # HTTPServer("0.0.0.0", PORT) → escuta em todas as interfaces de rede
    # serve_forever() → loop infinito aguardando conexões (usa select internamente)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
