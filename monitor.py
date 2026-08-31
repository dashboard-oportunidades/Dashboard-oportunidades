#!/usr/bin/env python3
"""
Monitor de precos de bases de duche no leroymerlin.pt

Percorre as listagens configuradas uma vez por loja (o preco varia entre
lojas) e avisa quando algo fica abaixo do limite definido, ou quando um
produto ja conhecido baixa de preco nalguma loja.

Configuracao: config.json.  Segredos: variaveis de ambiente (ver README).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import smtplib
import ssl
import sys
import time
from collections import defaultdict
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.leroymerlin.pt"
ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.json"
STATE_FILE = ROOT / "state.json"
DATA_FILE = ROOT / "docs" / "data.json"
HISTORY_LIMIT = 180

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

PRICE_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*€")
PRODUCT_HREF_RE = re.compile(r"/produtos/(?!marcas/)[^?#]*?-(\d{6,})\.html")


# --------------------------------------------------------------------------
# Utilitarios
# --------------------------------------------------------------------------

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        sys.exit(f"Falta o ficheiro {CONFIG_FILE.name}")
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def load_state() -> dict:
    """Formato: {"version": 2, "products": {"<id>@<loja>": {..., "history": [[data, preco]]}}}"""
    if not STATE_FILE.exists():
        return {"version": 2, "products": {}}
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("state.json ilegivel, a comecar do zero", file=sys.stderr)
        return {"version": 2, "products": {}}

    if raw.get("version") == 2:
        return raw
    # Migracao do formato antigo (dicionario simples sem historico).
    products = {}
    for key, value in raw.items():
        if isinstance(value, dict) and "price" in value:
            products[key] = {**value, "history": [[today(), value["price"]]]}
    print(f"state.json migrado para o formato novo ({len(products)} registos)")
    return {"version": 2, "products": products}


def today() -> str:
    return dt.date.today().isoformat()


def record_price(state: dict, key: str, data: dict) -> None:
    """Guarda o preco de hoje; so acrescenta ao historico quando o valor muda."""
    entry = state["products"].get(key)
    history = entry.get("history", []) if entry else []
    price = data["price"]
    if not history or abs(history[-1][1] - price) > 0.001:
        history.append([today(), price])
    else:
        history[-1][0] = today()
    state["products"][key] = {
        "name": data["name"],
        "url": data["url"],
        "price": price,
        "marketplace": data.get("marketplace", False),
        "history": history[-HISTORY_LIMIT:],
    }


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def normalise(text: str) -> str:
    """Junta digitos separados por espacos ('64 ,89 €' -> '64,89 €')."""
    text = text.replace("\xa0", " ")
    text = re.sub(r"(?<=\d)\s+(?=[,.\d])", "", text)
    text = re.sub(r"(?<=[,.])\s+(?=\d)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def to_float(raw: str) -> float:
    return float(raw.replace(".", "").replace(",", "."))


def eur(value: float) -> str:
    return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def store_label(store: dict) -> str:
    """Nome a mostrar nos avisos, com a regiao quando existe."""
    region = store.get("region")
    return f"{store['name']} ({region})" if region else store["name"]


def with_page(url: str, page: int) -> str:
    if page <= 1:
        return url
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query))
    query["p"] = str(page)
    return urlunparse(parts._replace(query=urlencode(query)))


# --------------------------------------------------------------------------
# Scraping
# --------------------------------------------------------------------------

def make_session(cookies: dict[str, str]) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "pt-PT,pt;q=0.9",
    })
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".leroymerlin.pt", path="/")
    return session


def fetch(session: requests.Session, url: str, retries: int = 3) -> str | None:
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            resp.encoding = resp.encoding or "utf-8"
            return resp.text
        except requests.RequestException as exc:
            if attempt == retries:
                print(f"  ! desisti de {url}: {exc}", file=sys.stderr)
                return None
            wait = 5 * attempt
            print(f"  ! erro ({exc}); nova tentativa em {wait}s", file=sys.stderr)
            time.sleep(wait)
    return None


def parse_listing(html: str) -> dict[str, dict]:
    """Devolve {product_id: {name, url, price, marketplace}} de uma pagina."""
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

        # O cartao e o antepassado mais proximo que ja contem um preco.
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

        lowered = card_text.lower()
        # "Vendido por LEROY MERLIN" = preco da loja; outro vendedor = marketplace.
        marketplace = "vendido por" in lowered and "vendido por leroy merlin" not in lowered

        entry = {
            "name": name,
            "url": urljoin(BASE, anchor["href"].split("?")[0]),
            "price": min(prices),   # em promocao aparece o antigo e o novo
            "marketplace": marketplace,
        }
        previous = found.get(product_id)
        if previous is None or entry["price"] < previous["price"]:
            found[product_id] = entry

    return found


def matches_filters(name: str, cfg: dict) -> bool:
    lowered = name.lower()
    include = [w.lower() for w in cfg.get("include_keywords", [])]
    exclude = [w.lower() for w in cfg.get("exclude_keywords", [])]
    if include and not any(w in lowered for w in include):
        return False
    return not any(w in lowered for w in exclude)


def scrape_store(cfg: dict, store: dict) -> dict[str, dict]:
    session = make_session(store.get("cookies", {}))
    products: dict[str, dict] = {}
    delay = cfg.get("delay_seconds", 3)

    for url in cfg["listing_urls"]:
        for page in range(1, cfg.get("max_pages", 5) + 1):
            html = fetch(session, with_page(url, page))
            if html is None:
                break

            page_products = parse_listing(html)
            if not page_products:
                break
            new_ids = set(page_products) - set(products)

            for pid, data in page_products.items():
                if not matches_filters(data["name"], cfg):
                    continue
                if cfg.get("skip_marketplace") and data["marketplace"]:
                    continue
                existing = products.get(pid)
                if existing is None or data["price"] < existing["price"]:
                    products[pid] = data

            if page > 1 and not new_ids:
                break     # fim da paginacao
            time.sleep(delay)

    return products


def scrape_all(cfg: dict) -> tuple[dict[str, dict[str, dict]], dict[str, str]]:
    """Devolve ({nome_da_loja: {product_id: dados}}, {nome_da_loja: etiqueta})."""
    by_store: dict[str, dict[str, dict]] = {}
    labels: dict[str, str] = {}
    for store in cfg["stores"]:
        if not store.get("cookies"):
            print(f"\n> {store['name']}: sem cookie configurado, a saltar.")
            continue
        print(f"\n> Loja: {store_label(store)}")
        products = scrape_store(cfg, store)
        print(f"  {len(products)} produtos")
        by_store[store["name"]] = products
        labels[store["name"]] = store_label(store)
        time.sleep(cfg.get("delay_seconds", 3))
    return by_store, labels


def warn_if_cookies_ineffective(by_store: dict[str, dict[str, dict]]) -> None:
    """Se todas as lojas derem exatamente os mesmos precos, o cookie nao pegou."""
    own_brand_signatures = set()
    for products in by_store.values():
        signature = tuple(sorted(
            (pid, p["price"]) for pid, p in products.items() if not p["marketplace"]
        ))
        if signature:
            own_brand_signatures.add(signature)

    if len(by_store) > 1 and len(own_brand_signatures) == 1:
        print(
            "\nAVISO: todas as lojas devolveram exatamente os mesmos precos.\n"
            "O cookie da loja pode ter deixado de funcionar — confirma-o no\n"
            "browser (ver README, seccao 'Capturar o cookie da loja').",
            file=sys.stderr,
        )


# --------------------------------------------------------------------------
# Comparacao e notificacoes
# --------------------------------------------------------------------------

def find_alerts(by_store, state: dict, max_price: float) -> list[dict]:
    alerts = []
    for store_name, products in by_store.items():
        for pid, data in products.items():
            if data["price"] > max_price:
                continue
            key = f"{pid}@{store_name}"
            old = state["products"].get(key)
            if old is None:
                alerts.append({**data, "id": pid, "store": store_name,
                               "kind": "novo", "old_price": None})
            elif data["price"] < old.get("price", float("inf")) - 0.01:
                alerts.append({**data, "id": pid, "store": store_name,
                               "kind": "desceu", "old_price": old["price"]})
    return alerts


def build_message(alerts: list[dict], by_store, labels: dict[str, str],
                  max_price: float) -> tuple[str, str]:
    # Agrupar por produto: um alerta por produto, com o preco de cada loja.
    grouped: dict[str, list[dict]] = defaultdict(list)
    for a in alerts:
        grouped[a["id"]].append(a)

    rows = []
    for pid, items in grouped.items():
        best = min(items, key=lambda i: i["price"])
        elsewhere = sorted(
            ((s, p[pid]["price"]) for s, p in by_store.items() if pid in p),
            key=lambda t: t[1],
        )
        rows.append({"best": best, "elsewhere": elsewhere})

    rows.sort(key=lambda r: r["best"]["price"])

    subject = f"{len(rows)} base(s) de duche abaixo de {max_price:.0f} €"
    lines = []
    for row in rows:
        best, elsewhere = row["best"], row["elsewhere"]
        head = f"{eur(best['price'])} — {best['name']}"
        if best["kind"] == "desceu":
            head += f"  (era {eur(best['old_price'])})"
        detail = " · ".join(
            f"{labels.get(store, store)}: {eur(price)}" for store, price in elsewhere
        )
        if best["marketplace"]:
            detail = "Marketplace (preço nacional) · " + detail.split(" · ")[0]
        lines.append(f"{head}\n{detail}\n{best['url']}")

    return subject, "\n\n".join(lines)


def export_data(by_store, labels: dict[str, str], state: dict, max_price: float) -> None:
    """Escreve docs/data.json, que alimenta a pagina no telemovel."""
    products = []
    all_ids = {pid for shop in by_store.values() for pid in shop}

    for pid in all_ids:
        prices = [
            {"store": labels.get(name, name), "price": shop[pid]["price"]}
            for name, shop in by_store.items() if pid in shop
        ]
        prices.sort(key=lambda r: r["price"])
        sample = next(shop[pid] for shop in by_store.values() if pid in shop)

        # Historico = melhor preco entre lojas em cada data.
        merged: dict[str, float] = {}
        for name in by_store:
            entry = state["products"].get(f"{pid}@{name}")
            for date, price in (entry or {}).get("history", []):
                if date not in merged or price < merged[date]:
                    merged[date] = price

        products.append({
            "id": pid,
            "name": sample["name"],
            "url": sample["url"],
            "marketplace": sample["marketplace"],
            "price": prices[0]["price"],
            "store": prices[0]["store"],
            "prices": prices,
            "history": [[d, merged[d]] for d in sorted(merged)][-HISTORY_LIMIT:],
        })

    products.sort(key=lambda p: p["price"])
    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "max_price": max_price,
        "stores": sorted(labels.values()),
        "products": products,
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")
    size = DATA_FILE.stat().st_size / 1024
    print(f"docs/data.json: {len(products)} produtos ({size:.0f} kB)")


def send_email(subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    to_addr = os.environ.get("MAIL_TO")
    if not all([host, user, password, to_addr]):
        print("Email nao configurado, a saltar.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content(body)

    port = int(os.environ.get("SMTP_PORT", 465))
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as server:
        server.login(user, password)
        server.send_message(msg)
    print(f"Email enviado para {to_addr}")


def send_push(subject: str, body: str) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("Push nao configurado, a saltar.")
        return
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
    resp = requests.post(
        f"{server}/{topic}",
        data=body.encode("utf-8"),
        headers={"Title": subject.encode("utf-8"), "Tags": "shower,moneybag"},
        timeout=20,
    )
    resp.raise_for_status()
    print(f"Notificacao enviada para {server}/{topic}")


# --------------------------------------------------------------------------

def main() -> int:
    cfg = load_config()
    max_price = float(os.environ.get("MAX_PRICE") or cfg["max_price"])
    state = load_state()

    by_store, labels = scrape_all(cfg)
    total = sum(len(p) for p in by_store.values())
    if not total:
        print("Nenhum produto extraido. Ou nenhuma loja tem cookie configurado,\n"
              "ou o layout do site mudou.", file=sys.stderr)
        return 1
    warn_if_cookies_ineffective(by_store)

    alerts = find_alerts(by_store, state, max_price)

    for store_name, products in by_store.items():
        for pid, data in products.items():
            record_price(state, f"{pid}@{store_name}", data)
    save_state(state)
    export_data(by_store, labels, state, max_price)

    if not alerts:
        print(f"\nNada abaixo de {eur(max_price)}. Ate amanha.")
        return 0

    subject, body = build_message(alerts, by_store, labels, max_price)
    print(f"\n{subject}\n\n{body}")

    if "--dry-run" not in sys.argv:
        send_email(subject, body)
        send_push(subject, body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
