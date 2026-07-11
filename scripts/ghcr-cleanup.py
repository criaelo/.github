#!/usr/bin/env python3
"""Higiene de imagens antigas no GHCR (org criaelo).

Remove versoes antigas com tag `*-<sha>` de cada pacote container, PRESERVANDO:
  - tags moveis de ambiente (dev/hml/prd/latest/main) e caches de build (buildcache);
  - qualquer tag efetivamente referenciada nos manifests de criaelo/deploy;
  - as N versoes mais recentes de cada pacote (janela de rollback).

Modo padrao: --dry-run (NAO deleta; apenas lista). Use --apply para efetivar.

Uso:
  python3 scripts/ghcr-cleanup.py --org criaelo --deploy-dir ./deploy --keep 10 [--apply]

Requer `gh` autenticado com escopo de leitura/escrita de packages da org.
"""
import argparse
import json
import re
import subprocess
import sys

PROTECTED_TAG_RE = re.compile(r"^(dev|hml|prd|prod|latest|main|master|buildcache|v\d+\.\d+\.\d+.*)$", re.I)
# Pins imutaveis acumulados pelo CI: <env>-<sha>. Sao os alvos seguros de higiene.
PIN_TAG_RE = re.compile(r"^(dev|hml|prd|prod)-[0-9a-f]{7,40}$", re.I)
IMAGE_REF_RE = re.compile(r"ghcr\.io/([\w.-]+)/([\w.-]+):([\w.-]+)")


def gh_json(path, paginate=False):
    cmd = ["gh", "api"]
    if paginate:
        cmd += ["--paginate"]
    cmd += [path]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"gh api {path} falhou: {out.stderr.strip()}")
    txt = out.stdout.strip()
    if not txt:
        return []
    # --paginate concatena arrays JSON; normaliza para lista unica
    chunks = re.sub(r"\]\s*\[", ",", txt)
    return json.loads(chunks)


def in_use_tags(deploy_dir):
    used = set()
    if not deploy_dir:
        return used
    import os
    for root, _, files in os.walk(deploy_dir):
        if "/.git" in root:
            continue
        for f in files:
            if not f.endswith((".yml", ".yaml", ".json")):
                continue
            try:
                content = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for _org, pkg, tag in IMAGE_REF_RE.findall(content):
                used.add((pkg, tag))
    return used


def list_container_packages(org):
    pkgs = gh_json(f"/orgs/{org}/packages?package_type=container&per_page=100", paginate=True)
    return [p["name"] for p in pkgs]


def list_versions(org, pkg):
    enc = pkg.replace("/", "%2F")
    return gh_json(
        f"/orgs/{org}/packages/container/{enc}/versions?per_page=100", paginate=True
    )


def is_protected(tags, pkg, used):
    for t in tags:
        if PROTECTED_TAG_RE.match(t):
            return True
        if (pkg, t) in used:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", default="criaelo")
    ap.add_argument("--deploy-dir", default=None, help="checkout de criaelo/deploy p/ tags em uso")
    ap.add_argument("--keep", type=int, default=10, help="versoes mais recentes a preservar por pacote")
    ap.add_argument("--packages", nargs="*", help="limitar a estes pacotes (default: todos)")
    ap.add_argument("--include-untagged", action="store_true",
                    help="tambem varrer versoes untagged (RISCO: podem ser manifests filhos "
                         "de imagens multi-arch com tag protegida; use com cautela)")
    ap.add_argument("--apply", action="store_true", help="efetivar delecoes (default: dry-run)")
    args = ap.parse_args()

    dry = not args.apply
    used = in_use_tags(args.deploy_dir)
    print(f"[info] tags em uso em deploy: {len(used)}", file=sys.stderr)

    packages = args.packages or list_container_packages(args.org)
    print(f"[info] pacotes: {', '.join(packages)}", file=sys.stderr)

    total_del = 0
    for pkg in packages:
        try:
            versions = list_versions(args.org, pkg)
        except RuntimeError as e:
            print(f"[warn] {pkg}: {e}", file=sys.stderr)
            continue
        # ordena do mais novo para o mais antigo
        versions.sort(key=lambda v: v.get("created_at", ""), reverse=True)

        deletable = []
        recent_kept = 0
        for v in versions:
            tags = (v.get("metadata", {}).get("container", {}) or {}).get("tags", []) or []
            if is_protected(tags, pkg, used):
                continue
            # candidato seguro: pin <env>-<sha> (ou untagged, se explicitamente pedido)
            is_pin = any(PIN_TAG_RE.match(t) for t in tags)
            is_candidate = is_pin or (args.include_untagged and not tags)
            if not is_candidate:
                continue
            if recent_kept < args.keep:
                recent_kept += 1
                continue
            deletable.append(v)

        if not deletable:
            print(f"[keep ] {pkg}: nada a remover ({len(versions)} versoes)")
            continue

        for v in deletable:
            tags = (v.get("metadata", {}).get("container", {}) or {}).get("tags", []) or []
            label = ",".join(tags) if tags else "<untagged>"
            print(f"[{'DRY' if dry else 'DEL'}] {pkg} id={v['id']} tags=[{label}] created={v.get('created_at','?')}")
            total_del += 1
            if not dry:
                enc = pkg.replace("/", "%2F")
                r = subprocess.run(
                    ["gh", "api", "-X", "DELETE",
                     f"/orgs/{args.org}/packages/container/{enc}/versions/{v['id']}"],
                    capture_output=True, text=True,
                )
                if r.returncode != 0:
                    print(f"[erro] delete {pkg} id={v['id']}: {r.stderr.strip()}", file=sys.stderr)

    print(f"\n[resumo] {'(dry-run) ' if dry else ''}{total_del} versao(oes) "
          f"{'seriam' if dry else 'foram'} removida(s).")


if __name__ == "__main__":
    main()
