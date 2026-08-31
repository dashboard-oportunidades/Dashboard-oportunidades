#!/usr/bin/env python3
"""
Descobre o storeId de cada loja visitando a sua pagina /lojas/<slug>.html
e lendo o link "Ver direcoes" (classe m-store-address--access), que traz
o data-storeid da propria loja.
"""

import json
import random
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
OUT_FILE = ROOT / "ids_lojas.json"

SLUGS = [
    "barreiro-compact", "cascais-compact", "castelo-branco-essencial",
    "torres-novas-essencial", "albufeira", "alfragide", "almada",
    "alta-de-lisboa", "colombo-essencial", "coimbra", "chaves-essencial",
    "carcavelos-essencial", "caldas-da-rainha-compact", "braganca-essencial",
    "braga", "barcelos-compact", "aveiro", "amadora", "mafra-essencial",
    "loures-compact", "loule", "leiria", "guimaraes-compact",
    "guarda-compact", "gondomar", "gaia", "figueira-da-foz-essencial",
    "sacavem-essencial", "ponta-delgada-compact", "penafiel-compact",
    "oeiras-compact", "montijo-compact", "matosinhos", "maia", "evora",
    "viseu-compact", "viana-do-castelo-compact", "torres-vedras-compact",
    "sintra", "setubal", "santarem", "santa-maria-da-feira-essencial",
    "funchal", "alverca-compact", "portimao", "telheiras-compact",
    "covilha-essencial",
]

OWN_ID_RE = re.compile(
    r'class="mc-link m-store-address--access[^"]*"[^>]*data-storeid="(\d+)"'
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def is_hard_block(html: str) -> bool:
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
            raise BlockedError("Bloqueio total da rede pelo Datadome. Espera antes de tentar outra vez.")
        if "captcha-delivery.com" not in html:
            print(">>> Resolvido! A continuar sozinho.\n")
            return True
        page.reload(wait_until="domcontentloaded")
    return False


def main() -> int:
    resultado = {}
    if OUT_FILE.exists():
        resultado = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        print(f"A retomar: {len(resultado)} lojas ja identificadas.")

    pendentes = [s for s in SLUGS if s not in resultado]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(user_agent=USER_AGENT, locale="pt-PT")
        page = context.new_page()

        try:
            for i, slug in enumerate(pendentes):
                if i > 0:
                    time.sleep(random.uniform(4, 8))
                url = f"https://www.leroymerlin.pt/lojas/{slug}.html"
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1500)
                try:
                    banner = page.locator("#onetrust-accept-btn-handler")
                    if banner.count() > 0:
                        banner.click(timeout=3000)
                except Exception:
                    pass

                html = page.content()
                if "captcha-delivery.com" in html:
                    if not wait_for_human(page):
                        print(f"! {slug}: desisti de esperar pelo CAPTCHA.", file=sys.stderr)
                        continue
                    html = page.content()

                m = OWN_ID_RE.search(html)
                if m:
                    resultado[slug] = m.group(1)
                    print(f"{slug}: {m.group(1)}")
                else:
                    print(f"? {slug}: nao encontrado", file=sys.stderr)
        except BlockedError as exc:
            print(f"\n!!! {exc}", file=sys.stderr)
        finally:
            try:
                browser.close()
            except Exception:
                pass

    OUT_FILE.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(resultado)}/{len(SLUGS)} lojas identificadas -> {OUT_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
