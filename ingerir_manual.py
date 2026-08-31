#!/usr/bin/env python3
"""
Junta ao estado de uma categoria um resultado copiado manualmente da consola
do browser (ver README/chat). Uso:

    python ingerir_manual.py caminho/para/ficheiro.json [--categoria <slug>]

Sem --categoria assume "base-duche".
"""
import json
import sys
import unicodedata
from pathlib import Path

from recolher_outlet import (
    CATEGORIAS,
    ROOT,
    export_outlet_json,
    load_state,
    save_state,
    store_label,
    update_store_in_state,
)

CONFIG_FILE = ROOT / "config.json"


def normalizar_nome(nome: str) -> str:
    """Ignora acentos/maiusculas ('Sacavém' == 'Sacavem')."""
    sem_acentos = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return sem_acentos.lower().strip()


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit("Uso: python ingerir_manual.py caminho/para/ficheiro.json [--categoria <slug>]")

    categoria_slug = "base-duche"
    if "--categoria" in sys.argv:
        categoria_slug = sys.argv[sys.argv.index("--categoria") + 1]
    if categoria_slug not in CATEGORIAS:
        sys.exit(f"Categoria '{categoria_slug}' desconhecida. Opcoes: {sorted(CATEGORIAS)}")
    categoria = CATEGORIAS[categoria_slug]
    state_file = ROOT / categoria["state_file"]
    out_file = ROOT / categoria["out_file"]

    dados = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    nome_loja = dados["loja"]
    produtos = dados["produtos"]

    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    stores = {normalizar_nome(s["name"]): s for s in cfg["stores"]}
    chave = normalizar_nome(nome_loja)
    if chave not in stores:
        nomes = sorted(s["name"] for s in cfg["stores"])
        raise SystemExit(f"Loja '{nome_loja}' nao existe no config.json. Nomes validos: {nomes}")
    store = stores[chave]
    label = store_label(store)

    state = load_state(state_file)
    update_store_in_state(state, label, store.get("region", ""), produtos)
    save_state(state, state_file)
    export_outlet_json(state, out_file)
    print(f"Guardado [{categoria['label']}]: {label} ({len(produtos)} produtos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
