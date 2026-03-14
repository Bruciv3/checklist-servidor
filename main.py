from http.server import HTTPServer, BaseHTTPRequestHandler
import json, os, datetime

PASTA = "checklists"
os.makedirs(PASTA, exist_ok=True)

PORT = int(os.environ.get("PORT", 8000))


class Handler(BaseHTTPRequestHandler):

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        corpo = self.rfile.read(tamanho)

        try:
            dados = json.loads(corpo)

            cliente = dados.get("cliente", "sem_cliente").replace(" ", "_")
            agora = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            nome_arquivo = f"{PASTA}/{cliente}_{agora}.json"

            with open(nome_arquivo, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)

            print(f"[OK] Salvo: {nome_arquivo}", flush=True)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        except Exception as e:
            print(f"[ERRO] {e}", flush=True)
            self.send_response(400)
            self.end_headers()

    def do_GET(self):
        # Rota simples para verificar se o servidor está no ar
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"online"}')
        elif self.path == "/checklists":
            arquivos = sorted(os.listdir(PASTA), reverse=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(arquivos).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Silencia logs padrão do HTTP


print(f"Servidor rodando na porta {PORT}", flush=True)
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
