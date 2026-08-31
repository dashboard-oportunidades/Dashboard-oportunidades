#!/usr/bin/env python3
"""
Junta ao outlet_state.json um resultado copiado manualmente da consola do
browser (ver README/chat). Uso:

    python ingerir_manual.py caminho/para/ficheiro.json
"""
import json
import sys
from pathlib import Path

from recolher_outlet import (
    export_outlet_json,
    load_state,
    save_state,
    store_label,
    update_store_in_state,
)

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("Uso: python ingerir_manual.py caminho/para/ficheiro.json")

    dados = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    nome_loja = dados["loja"]
    produtos = dados["produtos"]

    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    stores = {s["name"]: s for s in cfg["stores"]}
    if nome_loja not in stores:
        raise SystemExit(
            f"Loja '{nome_loja}' nao existe no config.json. Nomes validos: {sorted(stores)}"
        )
    store = stores[nome_loja]
    label = store_label(store)

    state = load_state()
    update_store_in_state(state, label, store.get("region", ""), produtos)
    save_state(state)
    export_outlet_json(state)
    print(f"Guardado: {label} ({len(produtos)} produtos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
