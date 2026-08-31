#!/usr/bin/env python3
"""
Recolhe as bases de duche em outlet, em todas as lojas configuradas.

Abre um browser a serio (visivel) para a primeira pagina. Se aparecer o
CAPTCHA do Datadome, resolve-o tu na janela que abre -- o script espera e
continua sozinho assim que detectar que passou. Depois disso percorre as
restantes lojas sem precisares de fazer mais nada.
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
OUT_FILE = ROOT / "docs" / "outlet.json"

OUTLET_URL = (
    "https://www.leroymerlin.pt/produtos/promocoes/outlet/"
    "?filters=%7B%22breadcrumb-1-label%22%3A%22Casas%2520de%2520banho%22"
    "%2C%22attribute-22088%22%3A%22Base%2520de%2520duche%22%7D"
)

PRICE_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*€")
PRODUCT_HREF_RE = re.compile(r"/produtos/(?!marcas/)[^?#]*?-(\d{6,})\.html")
DIM_RE = re.compile(r"(\d{2,3})\s*[xX]\s*(\d{2,3})")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def normalise(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"(?<=\d)\s+(?=[,.\d])", "", text)
    text = re.sub(r"(?<=[,.])\s+(?=\d)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def to_float(raw: str) -> float:
    return float(raw.replace(".", "").replace(",", "."))


def store_label(store: dict) -> str:
    region = store.get("region")
    return f"{store['name']} ({region})" if region else store["name"]


def parse_listing(html: str) -> dict[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, dict] = {}

    for anchor in soup.find_all("a", href=True):
        match = PRODUCT_HREF_RE.search(anchor["href"])
        if not match:
            continue
        product_id = match.group(1)
        name = normalise(anchor.get("title") or anchor.get_text(" ", strip=True))
        if len(name) < 10:
            continue

        card = anchor
        prices: list[float] = []
        card_text = ""
        for _ in range(6):
            card = card.parent
            if card is None:
                break
            card_text = normalise(card.get_text(" ", strip=True))
            raw = PRICE_RE.findall(card_text)
            if raw:
                prices = [to_float(p) for p in raw]
                break
        if not prices:
            continue

        dim_match = DIM_RE.search(name)
        dimensao = f"{dim_match.group(1)}x{dim_match.group(2)}" if dim_match else None

        entry = {
            "name": name,
            "url": "https://www.leroymerlin.pt" + anchor["href"].split("?")[0]
            if anchor["href"].startswith("/") else anchor["href"].split("?")[0],
            "price": min(prices),
            "dimensao": dimensao,
        }
        previous = found.get(product_id)
        if previous is None or entry["price"] < previous["price"]:
            found[product_id] = entry

    return found


def set_store_cookies(context, store: dict) -> None:
    cookies = store.get("cookies", {})
    context.clear_cookies()
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


def save_results(results: dict[str, dict]) -> int:
    products = []
    for pid, data in results.items():
        prices = sorted(data["prices"], key=lambda r: r["price"])
        products.append({
            "id": pid,
            "name": data["name"],
            "url": data["url"],
            "dimensao": data["dimensao"],
            "price": prices[0]["price"],
            "prices": prices,
        })
    products.sort(key=lambda p: p["price"])

    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "products": products,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\ndocs/outlet.json: {len(products)} produtos")
    return len(products)


def main() -> int:
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    stores = [s for s in cfg["stores"] if s.get("cookies")]
    if not stores:
        sys.exit("Nenhuma loja com cookies em config.json.")

    results: dict[str, dict] = {}
    blocked = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(user_agent=USER_AGENT, locale="pt-PT")
        page = context.new_page()

        try:
            for i, store in enumerate(stores):
                if i > 0:
                    pausa = random.uniform(6, 12)
                    print(f"  (pausa de {pausa:.0f}s antes da proxima loja)")
                    time.sleep(pausa)

                label = store_label(store)
                set_store_cookies(context, store)
                print(f"> Loja: {label}")
                page.goto(OUTLET_URL, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)

                if is_captcha(page.content()):
                    if not wait_for_human(page):
                        print("  ! desisti de esperar pelo CAPTCHA.", file=sys.stderr)
                        continue
                    page.goto(OUTLET_URL, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(2000)

                html = page.content()
                products = parse_listing(html)
                print(f"  {len(products)} produtos")

                for pid, data in products.items():
                    entry = results.setdefault(pid, {
                        "name": data["name"],
                        "url": data["url"],
                        "dimensao": data["dimensao"],
                        "prices": [],
                    })
                    entry["prices"].append({"store": label, "price": data["price"]})
        except BlockedError as exc:
            blocked = True
            print(f"\n!!! {exc}", file=sys.stderr)
        finally:
            try:
                browser.close()
            except Exception:
                pass

    save_results(results)
    if blocked:
        print("Parei mais cedo por causa do bloqueio -- o que ja tinha sido "
              "recolhido ficou gravado. Tenta outra vez mais tarde.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
