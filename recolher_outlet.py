#!/usr/bin/env python3
"""
Recolhe produtos em outlet (por categoria), em todas as lojas configuradas.

Abre um browser a serio (visivel) para a primeira pagina. Se aparecer o
CAPTCHA do Datadome, resolve-o tu na janela que abre -- o script espera e
continua sozinho assim que detectar que passou. Depois disso percorre as
restantes lojas sem precisares de fazer mais nada.

Uso: python recolher_outlet.py [--categoria <slug>] [--limit N]
"""

import datetime as dt
import json
import random
import re
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.json"
HISTORY_LIMIT = 180

# Cada categoria e um separador ("tab") no dashboard. Para acrescentar uma
# nova, basta adicionar uma entrada aqui com o URL do outlet ja filtrado
# pela categoria certa (aplica os filtros no site e copia o URL).
CATEGORIAS = {
    "base-duche": {
        "label": "Base Duche",
        "url": (
            "https://www.leroymerlin.pt/produtos/promocoes/outlet/"
            "?filters=%7B%22breadcrumb-1-label%22%3A%22Casas%2520de%2520banho%22"
            "%2C%22attribute-22088%22%3A%22Base%2520de%2520duche%22%7D"
        ),
        "state_file": "outlet_state.json",
        "out_file": "docs/outlet.json",
    },
    "monosplit": {
        "label": "Ar Condicionado",
        "url": (
            "https://www.leroymerlin.pt/produtos/promocoes/outlet/"
            "?filters=%7B%22breadcrumb-1-label%22%3A%22Aquecimento%2520e%2520Climatiza"
            "%25C3%25A7%25C3%25A3o%22%2C%22attribute-22088%22%3A%22Pack%2520ar%2520condicionado"
            "%2520Monosplit%22%7D"
        ),
        "state_file": "outlet_state_monosplit.json",
        "out_file": "docs/monosplit.json",
    },
    "termoacumuladores": {
        "label": "Termoacumuladores",
        "url": (
            "https://www.leroymerlin.pt/produtos/promocoes/outlet/"
            "?filters=%7B%22breadcrumb-1-label%22%3A%22Aquecimento%2520e%2520Climatiza"
            "%25C3%25A7%25C3%25A3o%22%2C%22attribute-22088%22%3A%22Aquecedor%2520de%2520"
            "%25C3%25A1gua%2520el%25C3%25A9trico%2520acumulado%22%7D"
        ),
        "state_file": "outlet_state_termoacumuladores.json",
        "out_file": "docs/termoacumuladores.json",
    },
}

DIM_RE = re.compile(r"(\d{2,3})\s*[xX]\s*(\d{2,3})")
BTU_RE = re.compile(r"(\d{4,5})\s*\.?\s*BTU", re.IGNORECASE)
BTU_K_RE = re.compile(r"(\d{1,2})\s*K\s*\.?\s*BTU", re.IGNORECASE)
BTU_DOT_RE = re.compile(r"(\d{1,2})\.\s*BTU", re.IGNORECASE)
BTU_BARE_RE = re.compile(r"(?<![\d.])(\d{1,2})\s*BTU", re.IGNORECASE)
LITROS_RE = re.compile(r"(\d{2,4})\s*[lL](?:itros?)?\b")


def extrair_atributo(name: str) -> str | None:
    """Etiqueta usada nos filtros da tabela -- medida (AxB) para bases de
    duche, capacidade (BTU) para ar condicionado, litros para
    termoacumuladores. None se nao reconhecer nenhum padrao (o produto so
    nao aparece nesse filtro)."""
    dim_match = DIM_RE.search(name)
    if dim_match:
        a, b = int(dim_match.group(1)), int(dim_match.group(2))
        return f"{max(a, b)}x{min(a, b)}"
    btu_match = BTU_RE.search(name)
    if btu_match:
        return f"{btu_match.group(1)} BTU"
    btu_k_match = BTU_K_RE.search(name)
    if btu_k_match:
        return f"{int(btu_k_match.group(1)) * 1000} BTU"
    btu_dot_match = BTU_DOT_RE.search(name)
    if btu_dot_match:
        return f"{int(btu_dot_match.group(1)) * 1000} BTU"
    btu_bare_match = BTU_BARE_RE.search(name)
    if btu_bare_match:
        return f"{int(btu_bare_match.group(1)) * 1000} BTU"
    litros_match = LITROS_RE.search(name)
    if litros_match:
        return f"{litros_match.group(1)}L"
    return None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def store_label(store: dict) -> str:
    region = store.get("region")
    return f"{store['name']} ({region})" if region else store["name"]


def parse_listing(html: str) -> dict[str, dict]:
    """Le os precos do <script class="dataTms"> de cada produto -- dados
    estruturados que o proprio site usa para analitica, exatos e sem
    ambiguidade (ao contrario de tentar interpretar o texto visivel).

    So dentro de #guidance-product-list -- a seccao "Ultimos produtos
    vistos" mais abaixo na pagina usa a mesma estrutura dataTms, mas para
    produtos vistos anteriormente (nada a ver com o outlet desta loja)."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, dict] = {}

    container = soup.find(id="guidance-product-list")
    scripts = container.find_all("script", class_="dataTms") if container else []

    for script in scripts:
        try:
            blocos = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for bloco in blocos:
            if bloco.get("name") != "cdl_products_list":
                continue
            for produto in bloco.get("value", []):
                pid = produto.get("identifier")
                offer = produto.get("offer") or {}
                preco_final = offer.get("unitprice_ati")
                if not pid or preco_final is None:
                    continue

                name = produto.get("name", "")
                dimensao = extrair_atributo(name)

                url = produto.get("url", "")
                if url.startswith("/"):
                    url = "https://www.leroymerlin.pt" + url

                entry = {
                    "name": name,
                    "url": url,
                    "dimensao": dimensao,
                    "preco_normal": offer.get("initial_price") or preco_final,
                    "preco_desconto": offer.get("discount_ati") or 0.0,
                    "preco_final": preco_final,
                }
                previous = found.get(pid)
                if previous is None or entry["preco_final"] < previous["preco_final"]:
                    found[pid] = entry

    return found


def set_store_cookies(context, store: dict) -> None:
    """So substitui os cookies da loja -- nao mexe no consentimento de
    cookies nem noutros cookies de sessao ja obtidos (ex.: datadome)."""
    cookies = store.get("cookies", {})
    context.add_cookies([
        {"name": name, "value": value, "domain": ".leroymerlin.pt", "path": "/"}
        for name, value in cookies.items()
    ])


def is_captcha(html: str) -> bool:
    return "captcha-delivery.com" in html or "DataDome CAPTCHA" in html


def is_hard_block(html: str) -> bool:
    """Ecra de bloqueio total (sem nada para resolver), != captcha interativo."""
    lowered = html.lower()
    return "contact" in lowered and ("blocked" in lowered or "bloqueio" in lowered
                                      or "superhuman" in lowered or "sobre-humana" in lowered)


class BlockedError(Exception):
    pass


def wait_for_human(page, timeout_s: int = 300) -> bool:
    print(f"\n>>> Apareceu um CAPTCHA. Resolve-o na janela do browser que abriu.")
    print(f">>> Vou verificar sozinho de 3 em 3 segundos (ate {timeout_s}s).\n")
    start = time.time()
    while time.time() - start < timeout_s:
        time.sleep(3)
        try:
            html = page.content()
        except Exception:
            raise BlockedError("A janela do browser foi fechada.")
        if is_hard_block(html):
            raise BlockedError(
                "Bloqueio total da rede pelo Datadome (nao ha nada para resolver aqui). "
                "Espera algum tempo antes de tentar outra vez."
            )
        if not is_captcha(html):
            print(">>> Resolvido! A continuar sozinho.\n")
            return True
        page.reload(wait_until="domcontentloaded")
    return False


def load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {"products": {}}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"{state_file.name} ilegivel, a comecar do zero", file=sys.stderr)
        return {"products": {}}


def save_state(state: dict, state_file: Path) -> None:
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def ordenar_por_antiguidade(stores: list[dict], state: dict) -> list[dict]:
    """Poe primeiro as lojas nunca visitadas ou visitadas ha mais tempo, para
    uma corrida interrompida nao ficar sempre a falhar nas mesmas do fim."""
    visitas = state.get("lojas", {})

    def chave(store: dict) -> str:
        return visitas.get(store_label(store), "")  # "" ordena primeiro

    return sorted(stores, key=chave)


def update_store_in_state(state: dict, store_label: str, region: str, products: dict[str, dict]) -> None:
    """So mexe nas entradas desta loja -- as outras lojas ficam como estavam,
    mesmo que esta corrida tenha parado antes de as visitar."""
    hoje = dt.date.today().isoformat()
    agora = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    state.setdefault("lojas", {})[store_label] = agora
    sufixo = f"@{store_label}"

    for key in [k for k in state["products"] if k.endswith(sufixo)]:
        del state["products"][key]

    for pid, data in products.items():
        key = f"{pid}{sufixo}"
        anterior = state["products"].get(key)
        historico = anterior.get("history", []) if anterior else []
        preco = data["preco_final"]
        if not historico or abs(historico[-1][1] - preco) > 0.001:
            historico.append([hoje, preco])
        else:
            historico[-1][0] = hoje
        state["products"][key] = {
            "id": pid,
            "store": store_label,
            "region": region,
            "name": data["name"],
            "url": data["url"],
            "dimensao": data["dimensao"],
            "preco_normal": data["preco_normal"],
            "preco_desconto": data["preco_desconto"],
            "preco_final": preco,
            "atualizado": agora,
            "history": historico[-HISTORY_LIMIT:],
        }


def export_outlet_json(state: dict, out_file: Path) -> int:
    por_produto: dict[str, dict] = {}
    for entry in state["products"].values():
        grupo = por_produto.setdefault(entry["id"], {
            "name": entry["name"], "url": entry["url"], "dimensao": entry["dimensao"], "prices": [],
        })
        grupo["prices"].append({
            "store": entry["store"],
            "region": entry.get("region", ""),
            "preco_normal": entry["preco_normal"],
            "preco_desconto": entry["preco_desconto"],
            "preco_final": entry["preco_final"],
            "atualizado": entry["atualizado"],
            "history": entry.get("history", []),
        })

    products = []
    for pid, data in por_produto.items():
        prices = sorted(data["prices"], key=lambda r: r["preco_final"])
        products.append({
            "id": pid,
            "name": data["name"],
            "url": data["url"],
            "dimensao": data["dimensao"],
            "preco_final": prices[0]["preco_final"],
            "prices": prices,
        })
    products.sort(key=lambda p: p["preco_final"])

    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "products": products,
    }
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{out_file}: {len(products)} produtos")
    return len(products)


def main() -> int:
    categoria_slug = "base-duche"
    if "--categoria" in sys.argv:
        categoria_slug = sys.argv[sys.argv.index("--categoria") + 1]
    if categoria_slug not in CATEGORIAS:
        sys.exit(f"Categoria '{categoria_slug}' desconhecida. Opcoes: {sorted(CATEGORIAS)}")
    categoria = CATEGORIAS[categoria_slug]
    outlet_url = categoria["url"]
    state_file = ROOT / categoria["state_file"]
    out_file = ROOT / categoria["out_file"]
    print(f"Categoria: {categoria['label']} ({categoria_slug})")

    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    stores = [s for s in cfg["stores"] if s.get("cookies")]
    if not stores:
        sys.exit("Nenhuma loja com cookies em config.json.")

    state = load_state(state_file)
    stores = ordenar_por_antiguidade(stores, state)

    if "--limit" in sys.argv:
        n = int(sys.argv[sys.argv.index("--limit") + 1])
        stores = stores[:n]
        print(f"(--limit {n}: so vou visitar {[store_label(s) for s in stores]})")

    visitadas = 0
    blocked = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        try:
            for i, store in enumerate(stores):
                if i > 0:
                    pausa = random.uniform(30, 45)
                    print(f"  (pausa de {pausa:.0f}s antes da proxima loja)")
                    time.sleep(pausa)

                label = store_label(store)
                # Contexto novo por loja -- equivalente a um Incognito novo:
                # o cookie 'store' so aceita ser injetado numa sessao que
                # nunca teve loja nenhuma escolhida (fica HttpOnly a partir
                # da primeira navegacao real, e um contexto reaproveitado
                # entre lojas fica preso na primeira que visitou).
                context = browser.new_context(user_agent=USER_AGENT, locale="pt-PT")
                page = context.new_page()
                try:
                    set_store_cookies(context, store)
                    print(f"> Loja: {label}")
                    page.goto(outlet_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(2000)

                    if page.locator("#onetrust-accept-btn-handler").count() > 0:
                        print("\n>>> Aparece o banner de cookies -- clica em 'Aceitar' na janela do browser.\n")
                        try:
                            page.locator("#onetrust-accept-btn-handler").wait_for(state="hidden", timeout=60000)
                        except Exception:
                            pass

                    if is_captcha(page.content()):
                        if not wait_for_human(page):
                            print(f"  ! {label}: desisti de esperar pelo CAPTCHA -- "
                                  f"fica para a proxima corrida.", file=sys.stderr)
                            continue
                        page.goto(outlet_url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(2000)

                    html = page.content()
                    products = parse_listing(html)
                    print(f"  {len(products)} produtos")

                    # Visita valida mesmo com 0 produtos -- pode ser mesmo que
                    # esta loja nao tenha outlet de bases de duche agora.
                    update_store_in_state(state, label, store.get("region", ""), products)
                    save_state(state, state_file)
                    visitadas += 1
                finally:
                    context.close()
        except BlockedError as exc:
            blocked = True
            print(f"\n!!! {exc}", file=sys.stderr)
        finally:
            try:
                browser.close()
            except Exception:
                pass

    export_outlet_json(state, out_file)
    print(f"{visitadas}/{len(stores)} lojas visitadas nesta corrida "
          f"({len(state.get('lojas', {}))} no total ja alguma vez visitadas).")
    if blocked or visitadas < len(stores):
        print("Ficaram lojas por visitar -- a proxima corrida comeca por elas.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
