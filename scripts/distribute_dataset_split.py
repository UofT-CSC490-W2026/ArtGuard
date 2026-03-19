#!/usr/bin/env python3
"""
Distribute images under data/ (or datas/) into train/val/test with:
  - 72% / 11% / 17% split
  - train/val/test/{class_1,class_0}/  (class_1 = authentic, class_0 = rest)
  - Stratified class_0: same proxies : imitations : diffusion ratio in each split.

Default class-0 buckets:
  - proxies:     <data_root>/proxies/
  - diffusion:   <data_root>/imitations/vg_stable_diffusion/
  - imitations:  <data_root>/forgeries/  (physical forgeries; adjust --imitation-dirs if needed)

Any extra dirs under imitations/ (except vg_stable_diffusion) count as "imitation".

Usage:
  python scripts/distribute_dataset_split.py --output data_split
  python scripts/distribute_dataset_split.py --data-root datas --output datas_split --symlink
"""

from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def collect_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    out = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXT:
            out.append(p)
    return sorted(out)


def split_sizes(n: int) -> tuple[int, int, int]:
    """Train / val / test counts summing to n, targeting 72/11/17."""
    if n == 0:
        return 0, 0, 0
    nt = int(round(0.72 * n))
    nv = int(round(0.11 * n))
    nte = n - nt - nv
    # Fix rounding drift
    while nte < 0:
        nt -= 1
        nte += 1
    while nte > int(round(0.17 * n)) + 1 and nt > 1:
        nt -= 1
        nte += 1
    if n == 1:
        return 1, 0, 0
    if n == 2:
        return 1, 0, 1
    # Ensure val has at least 1 sample when n is large enough
    if nv == 0 and n >= 10:
        nv = 1
        nt = max(1, nt - 1)
    nte = n - nt - nv
    return nt, nv, nte


def stratified_split(
    files: list[Path], seed: int
) -> tuple[list[Path], list[Path], list[Path]]:
    rng = random.Random(seed)
    shuffled = files[:]
    rng.shuffle(shuffled)
    nt, nv, nte = split_sizes(len(shuffled))
    train = shuffled[:nt]
    val = shuffled[nt : nt + nv]
    test = shuffled[nt + nv :]
    return train, val, test


def unique_dest_name(src: Path, subtype: str) -> str:
    """Avoid collisions when merging class_0 from multiple sources."""
    return f"{subtype}__{src.parent.name}__{src.name}" if src.parent.name else f"{subtype}__{src.name}"


def copy_or_link(src: Path, dst: Path, use_symlink: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    if use_symlink:
        dst.symlink_to(src.resolve())
    else:
        shutil.copy2(src, dst)


def main() -> None:
    ap = argparse.ArgumentParser(description="Stratified train/val/test split (72/11/17).")
    ap.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Root folder (default: ./data or ./datas if exists)",
    )
    ap.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output root, e.g. data_split",
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--symlink",
        action="store_true",
        help="Symlink instead of copy (saves disk)",
    )
    ap.add_argument(
        "--imitation-dirs",
        nargs="*",
        default=None,
        help="Extra dirs counted as 'imitation' (relative to data-root), default: forgeries",
    )
    args = ap.parse_args()

    repo = Path(__file__).resolve().parent.parent
    if args.data_root:
        data_root = args.data_root.resolve()
    else:
        for name in ("data", "datas"):
            cand = repo / name
            if cand.is_dir():
                data_root = cand
                break
        else:
            data_root = repo / "data"

    if not data_root.is_dir():
        raise SystemExit(f"Data root not found: {data_root}")

    originals_dir = data_root / "originals"
    proxies_dir = data_root / "proxies"
    diffusion_dir = data_root / "imitations" / "vg_stable_diffusion"

    imitation_roots: list[Path] = []
    if args.imitation_dirs:
        for rel in args.imitation_dirs:
            imitation_roots.append((data_root / rel).resolve())
    else:
        forg = data_root / "forgeries"
        if forg.is_dir():
            imitation_roots.append(forg)
        # Other subdirs under imitations except diffusion
        im_root = data_root / "imitations"
        if im_root.is_dir():
            for sub in im_root.iterdir():
                if sub.is_dir() and sub.resolve() != diffusion_dir.resolve():
                    imitation_roots.append(sub)

    class1_files = collect_files(originals_dir)
    proxy_files = collect_files(proxies_dir)
    diffusion_files = collect_files(diffusion_dir)
    imitation_files: list[Path] = []
    seen: set[Path] = set()
    for root in imitation_roots:
        for p in collect_files(root):
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                imitation_files.append(p)

    print(f"Data root: {data_root}")
    print(f"  class_1 (originals): {len(class1_files)}")
    print(f"  class_0 proxy:       {len(proxy_files)}")
    print(f"  class_0 imitation:   {len(imitation_files)}")
    print(f"  class_0 diffusion:   {len(diffusion_files)}")

    out_root = args.output.resolve()
    if out_root == data_root or data_root in out_root.parents:
        raise SystemExit("Refusing to write output inside data-root; choose another --output")

    splits = ("train", "val", "test")
    for sp in splits:
        for c in ("class_1", "class_0"):
            (out_root / sp / c).mkdir(parents=True, exist_ok=True)

    # Class 1: single stratified bucket (just proportional split)
    tr1, va1, te1 = stratified_split(class1_files, args.seed)
    for split_name, bucket in zip(splits, (tr1, va1, te1)):
        for src in bucket:
            dst = out_root / split_name / "class_1" / src.name
            copy_or_link(src, dst, args.symlink)

    # Class 0: stratify each subtype with same seed offset so ratios match per split
    subtypes: list[tuple[str, list[Path]]] = [
        ("proxy", proxy_files),
        ("imitation", imitation_files),
        ("diffusion", diffusion_files),
    ]
    seed = args.seed
    for st_name, flist in subtypes:
        tr, va, te = stratified_split(flist, seed)
        seed += 1000
        for split_name, bucket in zip(splits, (tr, va, te)):
            for src in bucket:
                name = unique_dest_name(src, st_name)
                dst = out_root / split_name / "class_0" / name
                copy_or_link(src, dst, args.symlink)

    # Summary: ratio check per split
    print("\nPer-split class_0 subtype counts (proxy / imitation / diffusion):")
    for sp in splits:
        d0 = out_root / sp / "class_0"
        if not d0.is_dir():
            continue
        names = list(d0.iterdir())
        np = sum(1 for p in names if p.name.startswith("proxy__"))
        ni = sum(1 for p in names if p.name.startswith("imitation__"))
        nd = sum(1 for p in names if p.name.startswith("diffusion__"))
        tot = np + ni + nd
        if tot:
            print(
                f"  {sp}: {np}/{ni}/{nd}  "
                f"({100*np/tot:.1f}% / {100*ni/tot:.1f}% / {100*nd/tot:.1f}%)"
            )
        else:
            print(f"  {sp}: (empty class_0)")

    n0_total = len(proxy_files) + len(imitation_files) + len(diffusion_files)
    if n0_total:
        print("\nGlobal class_0 target ratios:")
        print(
            f"  proxy {100*len(proxy_files)/n0_total:.1f}% | "
            f"imitation {100*len(imitation_files)/n0_total:.1f}% | "
            f"diffusion {100*len(diffusion_files)/n0_total:.1f}%"
        )

    print(f"\nDone → {out_root}")


if __name__ == "__main__":
    main()
