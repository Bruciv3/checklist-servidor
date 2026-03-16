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
#    BaseHTTPRequestHandler: classe base; sobrescrevemos do_GET, do_POST e
#    do_DELETE para tratar cada tipo de requisição HTTP recebida.
#
#  Rotas disponíveis:
#    GET    /                  → verifica se servidor está online
#    GET    /checklists        → lista arquivos JSON salvos
#    GET    /pdfs              → página HTML com lista de PDFs (layout melhorado)
#    GET    /pdfs/<arquivo>    → serve (abre) um PDF específico no navegador
#    POST   /                  → recebe dados do checklist como JSON
#    POST   /upload-pdf        → recebe um arquivo PDF em bytes brutos
#    DELETE /pdfs/<arquivo>    → exclui um PDF do servidor
# =============================================================================

from http.server import HTTPServer, BaseHTTPRequestHandler
import json, os, datetime

# Pastas onde os arquivos serão salvos.
#
# Por que /data?
#   No Railway, volumes persistentes são montados em /data (ou o caminho configurado).
#   Arquivos fora de /data são apagados a cada deploy/reinício (armazenamento efêmero).
#   Localmente (sem volume), cria as pastas relativas ao diretório atual — funciona igual.
#
# Para ativar persistência no Railway:
#   Painel Railway → seu serviço → Volumes → Add Volume → Mount: /data
BASE_DIR   = os.environ.get("DATA_DIR", "/data")
PASTA_JSON = os.path.join(BASE_DIR, "checklists")
PASTA_PDF  = os.path.join(BASE_DIR, "pdfs")
os.makedirs(PASTA_JSON, exist_ok=True)
os.makedirs(PASTA_PDF,  exist_ok=True)

# Railway define a porta via variável de ambiente PORT.
PORT = int(os.environ.get("PORT", 8000))


class Handler(BaseHTTPRequestHandler):
    """
    Processa cada requisição HTTP recebida.

    O Python cria uma nova instância desta classe para cada conexão.
    Métodos do_GET, do_POST e do_DELETE são chamados automaticamente.
    """

    # ──────────────────────────────────────────────────────────────────────────
    #  POST
    # ──────────────────────────────────────────────────────────────────────────

    def do_POST(self):
        if self.path == "/upload-pdf":
            self._receber_pdf()
        else:
            self._receber_checklist()

    def _receber_checklist(self):
        """
        Recebe o checklist completo como JSON e salva em arquivo .json.
        """
        tamanho = int(self.headers.get("Content-Length", 0))
        corpo   = self.rfile.read(tamanho)

        try:
            dados   = json.loads(corpo)
            cliente = dados.get("cliente", "sem_cliente").replace(" ", "_")
            agora   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            caminho = f"{PASTA_JSON}/{cliente}_{agora}.json"

            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)

            print(f"[JSON] Salvo: {caminho}", flush=True)
            self._responder(200, {"status": "ok", "arquivo": caminho})

        except Exception as e:
            print(f"[ERRO JSON] {e}", flush=True)
            self._responder(400, {"status": "erro", "detalhe": str(e)})

    def _receber_pdf(self):
        """
        Recebe um arquivo PDF enviado em bytes brutos e salva em disco.

        Header X-Nome-Arquivo: nome sugerido pelo app Android.
        "wb" (write binary): obrigatório para arquivos não-texto.
        """
        tamanho      = int(self.headers.get("Content-Length", 0))
        dados        = self.rfile.read(tamanho)
        nome_original = self.headers.get("X-Nome-Arquivo", "relatorio.pdf")

        # Sanitização: evita path traversal (ex: "../../etc/passwd")
        nome_seguro = "".join(c for c in nome_original if c.isalnum() or c in "._-")
        if not nome_seguro.endswith(".pdf"):
            nome_seguro += ".pdf"

        agora   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho = f"{PASTA_PDF}/{agora}_{nome_seguro}"

        with open(caminho, "wb") as f:
            f.write(dados)

        print(f"[PDF] Salvo: {caminho} ({len(dados)} bytes)", flush=True)
        self._responder(200, {"status": "ok", "arquivo": caminho, "bytes": len(dados)})

    # ──────────────────────────────────────────────────────────────────────────
    #  DELETE
    # ──────────────────────────────────────────────────────────────────────────

    def do_DELETE(self):
        """
        Exclui um PDF do servidor.

        Rota: DELETE /pdfs/<nome_do_arquivo>

        Por que DELETE e não POST?
          O protocolo HTTP define o verbo DELETE especificamente para remoção
          de recursos. É mais semântico e alinhado com REST.
          O JavaScript no navegador envia via fetch('/pdfs/arquivo', {method:'DELETE'}).

        Segurança:
          os.path.basename() remove qualquer prefixo de caminho, impedindo que
          um cliente malicioso apague arquivos fora da pasta de PDFs.
        """
        if self.path.startswith("/pdfs/"):
            nome_arquivo = self.path[len("/pdfs/"):]
            self._deletar_pdf(nome_arquivo)
        else:
            self._responder(404, {"status": "erro", "detalhe": "Rota não encontrada"})

    def _deletar_pdf(self, nome_arquivo):
        """
        Remove o arquivo PDF do disco e responde com JSON.

        os.path.basename: garante que nome_arquivo não contenha ".." ou "/",
        o que poderia sair da pasta de PDFs e deletar arquivos do sistema.
        """
        nome_seguro = os.path.basename(nome_arquivo)
        caminho     = os.path.join(PASTA_PDF, nome_seguro)

        if not os.path.isfile(caminho):
            self._responder(404, {"status": "erro", "detalhe": "Arquivo não encontrado"})
            return

        try:
            os.remove(caminho)
            print(f"[PDF] Excluído: {caminho}", flush=True)
            self._responder(200, {"status": "ok", "excluido": nome_seguro})
        except Exception as e:
            print(f"[ERRO DELETE] {e}", flush=True)
            self._responder(500, {"status": "erro", "detalhe": str(e)})

    # ──────────────────────────────────────────────────────────────────────────
    #  GET
    # ──────────────────────────────────────────────────────────────────────────

    def do_GET(self):
        if self.path == "/":
            self._responder(200, {"status": "online"})

        elif self.path == "/checklists":
            arquivos = sorted(os.listdir(PASTA_JSON), reverse=True)
            self._responder(200, arquivos)

        elif self.path == "/pdfs":
            arquivos = sorted(os.listdir(PASTA_PDF), reverse=True)
            self._responder_html_pdfs(arquivos)

        elif self.path.startswith("/pdfs/"):
            self._servir_pdf(self.path[len("/pdfs/"):])

        else:
            self.send_response(404)
            self.end_headers()

    def _servir_pdf(self, nome_arquivo):
        """
        Lê o PDF do disco e envia como resposta binária para o navegador.
        Content-Disposition: inline → tenta abrir no navegador (não forçar download).
        """
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
        self.wfile.write(dados)

    # ──────────────────────────────────────────────────────────────────────────
    #  HTML — Página de listagem de PDFs
    # ──────────────────────────────────────────────────────────────────────────

    def _responder_html_pdfs(self, arquivos: list):
        """
        Gera a página HTML completa de listagem de PDFs.

        Funcionalidades:
          - Cards com nome do cliente e data extraídos do nome do arquivo
          - Tamanho do arquivo em KB/MB
          - Botão "Abrir" → abre o PDF no navegador (nova aba)
          - Botão "Excluir" → chama DELETE /pdfs/<arquivo> via fetch() com confirmação
          - Busca em tempo real por nome de arquivo (JavaScript)
          - Layout responsivo (funciona em celular e desktop)

        Por que fetch() para exclusão e não um <form method="POST">?
          fetch() permite enviar o verbo HTTP DELETE que é o correto para remoção.
          Com <form> o navegador só suporta GET e POST — teríamos que criar uma
          rota POST /delete/<arquivo> como workaround. fetch() é mais limpo.

        Por que extrair cliente e data do nome do arquivo?
          O nome segue o padrão: YYYYMMDD_HHMMSS_cliente.pdf
          Extraindo esses dados, exibimos informação legível ao invés do nome técnico.
        """

        def _info_arquivo(nome):
            """
            Extrai cliente, data formatada e tamanho de um arquivo PDF.
            Retorna dict com: cliente, data, tamanho_str.
            """
            caminho = os.path.join(PASTA_PDF, nome)

            # Tamanho em KB ou MB
            try:
                bytes_arq = os.path.getsize(caminho)
                if bytes_arq >= 1_048_576:
                    tamanho_str = f"{bytes_arq / 1_048_576:.1f} MB"
                else:
                    tamanho_str = f"{bytes_arq / 1024:.0f} KB"
            except Exception:
                tamanho_str = "—"

            # Tenta extrair data e cliente do padrão YYYYMMDD_HHMMSS_cliente.pdf
            # ex: "20260314_153045_Empresa_ABC.pdf" → data: 14/03/2026 15:30, cliente: Empresa ABC
            partes  = nome.replace(".pdf", "").split("_", 2)
            cliente = partes[2].replace("_", " ") if len(partes) >= 3 else nome
            try:
                dt      = datetime.datetime.strptime(f"{partes[0]}_{partes[1]}", "%Y%m%d_%H%M%S")
                data    = dt.strftime("%d/%m/%Y %H:%M")
            except Exception:
                data = "—"

            return {"cliente": cliente, "data": data, "tamanho": tamanho_str}

        # ── Monta os cards ──
        if not arquivos:
            cards_html = """
            <div class="empty">
                <div class="empty-icon">📭</div>
                <p>Nenhum PDF recebido ainda.</p>
                <p class="empty-sub">Os relatórios enviados pelo app aparecerão aqui.</p>
            </div>"""
        else:
            cards = []
            for nome in arquivos:
                info = _info_arquivo(nome)
                # data-nome é usado pelo filtro de busca em JavaScript
                card = f"""
                <div class="card" data-nome="{nome.lower()}">
                  <div class="card-icon">📄</div>
                  <div class="card-body">
                    <div class="card-cliente">{info['cliente']}</div>
                    <div class="card-meta">
                      <span>📅 {info['data']}</span>
                      <span>💾 {info['tamanho']}</span>
                    </div>
                    <div class="card-filename">{nome}</div>
                  </div>
                  <div class="card-actions">
                    <a class="btn btn-open" href="/pdfs/{nome}" target="_blank">Abrir</a>
                    <button class="btn btn-delete" onclick="excluir('{nome}')">Excluir</button>
                  </div>
                </div>"""
                cards.append(card)
            cards_html = "\n".join(cards)

        total = len(arquivos)

        # ── HTML completo ──
        # O JavaScript ao final da página implementa:
        #   excluir(nome): chama DELETE /pdfs/<nome> via fetch, pede confirmação,
        #                   remove o card do DOM sem recarregar a página.
        #   filtrar():     esconde cards cujo data-nome não contém o texto buscado.
        html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Relatórios — Checklist Técnico</title>
  <style>
    /* ── Reset e base ── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      background: #f0f4f8;
      color: #1a2a3a;
      min-height: 100vh;
    }}

    /* ── Cabeçalho ── */
    header {{
      background: linear-gradient(135deg, #194c8c 0%, #1565C0 100%);
      color: white;
      padding: 24px 32px;
      box-shadow: 0 2px 8px rgba(0,0,0,.25);
    }}
    header h1 {{ font-size: 1.6rem; font-weight: 700; letter-spacing: .3px; }}
    header p  {{ font-size: .9rem; opacity: .85; margin-top: 4px; }}

    /* ── Conteúdo principal ── */
    main {{
      max-width: 900px;
      margin: 0 auto;
      padding: 28px 20px 60px;
    }}

    /* ── Barra de busca + contador ── */
    .toolbar {{
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }}
    .search {{
      flex: 1;
      min-width: 200px;
      padding: 10px 16px;
      border: 1px solid #c8d6e5;
      border-radius: 8px;
      font-size: .95rem;
      background: white;
      outline: none;
      transition: border-color .2s;
    }}
    .search:focus {{ border-color: #1565C0; box-shadow: 0 0 0 3px rgba(21,101,192,.15); }}
    .count {{
      font-size: .9rem;
      color: #5a7a9a;
      white-space: nowrap;
    }}

    /* ── Cards ── */
    .card {{
      background: white;
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 16px;
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
      transition: box-shadow .2s, transform .15s;
    }}
    .card:hover {{ box-shadow: 0 4px 14px rgba(0,0,0,.12); transform: translateY(-1px); }}
    .card-icon {{ font-size: 2rem; flex-shrink: 0; }}
    .card-body {{ flex: 1; min-width: 0; }}
    .card-cliente {{
      font-weight: 600;
      font-size: 1rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .card-meta {{
      display: flex;
      gap: 16px;
      font-size: .82rem;
      color: #5a7a9a;
      margin-top: 4px;
      flex-wrap: wrap;
    }}
    .card-filename {{
      font-size: .72rem;
      color: #a0b0c0;
      margin-top: 3px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .card-actions {{
      display: flex;
      gap: 8px;
      flex-shrink: 0;
    }}

    /* ── Botões ── */
    .btn {{
      padding: 8px 16px;
      border-radius: 8px;
      font-size: .85rem;
      font-weight: 600;
      cursor: pointer;
      border: none;
      text-decoration: none;
      transition: opacity .15s, transform .1s;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .btn:active {{ transform: scale(.96); }}
    .btn-open   {{ background: #1565C0; color: white; }}
    .btn-open:hover  {{ opacity: .88; }}
    .btn-delete {{ background: #fdecea; color: #c62828; }}
    .btn-delete:hover {{ background: #ffcdd2; }}

    /* ── Estado vazio ── */
    .empty {{
      text-align: center;
      padding: 60px 20px;
      color: #8a9aaa;
    }}
    .empty-icon {{ font-size: 3.5rem; margin-bottom: 16px; }}
    .empty-sub  {{ font-size: .88rem; margin-top: 6px; }}

    /* ── Toast de notificação ── */
    #toast {{
      position: fixed;
      bottom: 28px;
      left: 50%;
      transform: translateX(-50%) translateY(80px);
      background: #1a2a3a;
      color: white;
      padding: 12px 24px;
      border-radius: 24px;
      font-size: .9rem;
      box-shadow: 0 4px 16px rgba(0,0,0,.25);
      transition: transform .3s ease;
      z-index: 999;
      white-space: nowrap;
    }}
    #toast.show {{ transform: translateX(-50%) translateY(0); }}
    #toast.erro  {{ background: #c62828; }}

    /* ── Rodapé ── */
    footer {{
      text-align: center;
      padding: 20px;
      font-size: .8rem;
      color: #8a9aaa;
    }}
    footer a {{ color: #1565C0; text-decoration: none; }}

    /* ── Responsivo ── */
    @media (max-width: 600px) {{
      .card {{ flex-wrap: wrap; }}
      .card-actions {{ width: 100%; justify-content: flex-end; }}
      header {{ padding: 18px 16px; }}
    }}
  </style>
</head>
<body>

<header>
  <h1>📋 Checklist Técnico</h1>
  <p>Relatórios PDF recebidos pelo servidor</p>
</header>

<main>
  <div class="toolbar">
    <input
      class="search"
      type="search"
      placeholder="🔍  Buscar por cliente ou data..."
      oninput="filtrar(this.value)"
      autocomplete="off"
    >
    <span class="count" id="contador">{total} relatório(s)</span>
  </div>

  <div id="lista">
    {cards_html}
  </div>
</main>

<div id="toast"></div>

<footer>
  <a href="/checklists">Ver JSONs</a> &nbsp;·&nbsp;
  Checklist Técnico &copy; 2026
</footer>

<script>
  // ── Filtro de busca em tempo real ──
  // Percorre todos os cards e oculta os que não contêm o texto buscado.
  // data-nome já está em lowercase, então comparamos em lowercase também.
  function filtrar(texto) {{
    const termo = texto.toLowerCase();
    let visiveis = 0;
    document.querySelectorAll('.card').forEach(card => {{
      const match = card.dataset.nome.includes(termo);
      card.style.display = match ? '' : 'none';
      if (match) visiveis++;
    }});
    document.getElementById('contador').textContent =
      visiveis + ' relatório(s)';
  }}

  // ── Exclusão via fetch (verbo HTTP DELETE) ──
  // fetch() é a API moderna do navegador para fazer requisições HTTP assíncronas.
  // async/await torna o código assíncrono mais legível (evita callback hell).
  async function excluir(nome) {{
    // Pede confirmação antes de qualquer ação destrutiva
    if (!confirm('Excluir o relatório "' + nome + '"?\\n\\nEsta ação não pode ser desfeita.')) return;

    try {{
      // DELETE /pdfs/<nome> — o servidor processa em _deletar_pdf()
      const resp = await fetch('/pdfs/' + encodeURIComponent(nome), {{ method: 'DELETE' }});

      if (resp.ok) {{
        // Remove o card do DOM sem recarregar a página (melhor UX)
        const cards = document.querySelectorAll('.card');
        cards.forEach(card => {{
          if (card.dataset.nome === nome.toLowerCase()) card.remove();
        }});

        // Atualiza o contador
        const restantes = document.querySelectorAll('.card').length;
        document.getElementById('contador').textContent = restantes + ' relatório(s)';

        // Se não sobrou nenhum, mostra estado vazio
        if (restantes === 0) {{
          document.getElementById('lista').innerHTML =
            '<div class="empty"><div class="empty-icon">📭</div><p>Nenhum PDF no servidor.</p></div>';
        }}

        mostrarToast('✓ Relatório excluído com sucesso', false);
      }} else {{
        mostrarToast('⚠ Erro ao excluir: ' + resp.status, true);
      }}
    }} catch (e) {{
      mostrarToast('⚠ Falha de conexão com o servidor', true);
    }}
  }}

  // ── Toast de notificação ──
  // Exibe uma mensagem temporária no rodapé da tela (3 segundos).
  // Mais discreto que alert() e não bloqueia a interface.
  function mostrarToast(msg, erro) {{
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className   = erro ? 'show erro' : 'show';
    clearTimeout(el._timer);
    el._timer = setTimeout(() => {{ el.className = erro ? 'erro' : ''; }}, 3000);
  }}
</script>

</body>
</html>"""

        corpo = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type",   "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    # ──────────────────────────────────────────────────────────────────────────
    #  Helper JSON
    # ──────────────────────────────────────────────────────────────────────────

    def _responder(self, codigo: int, dados):
        """
        Atalho para enviar uma resposta JSON.
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
        Silencia os logs padrão do HTTPServer.
        Mantemos apenas os prints manuais com [JSON], [PDF] e [ERRO].
        """
        pass


# ──────────────────────────────────────────────────────────────────────────────
#  Ponto de entrada
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Servidor iniciado na porta {PORT}", flush=True)
    print(f"  JSONs salvos em: {PASTA_JSON}/", flush=True)
    print(f"  PDFs  salvos em: {PASTA_PDF}/",  flush=True)

    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
