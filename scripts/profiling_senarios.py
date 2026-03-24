#!/usr/bin/env python3
"""Profiling scenarios for ArtGuard — distinct mocked workloads for timing experiments.

Each scenario exercises a different part of the stack (auth crypto, image preprocess,
inference persistence, data splits). Use them standalone or under a profiler.

Run from repo root::

    python scripts/profiling_senarios.py --list
    python scripts/profiling_senarios.py preprocess_high_resolution
    python scripts/profiling_senarios.py --all
    python scripts/profiling_senarios.py --profile auth_crypto_burst

``cProfile`` writes a **binary** ``.prof`` file — decode to text with ``--print-stats``::

    python scripts/profiling_senarios.py --cprofile-out scenario.prof preprocess_high_resolution
    python scripts/profiling_senarios.py --print-stats scenario.prof --output scenario.txt

Warm-up (imports + tiny PIL/JWT/bcrypt/split/moto sample) runs **before** ``--cprofile-out``
measurement so the ``.prof`` excludes cold-start noise. Use ``--no-warmup`` to disable.

Preprocess scenarios run **many** synthetic images (default **150**). Set env
``PREPROCESS_PROFILE_IMAGE_COUNT`` to e.g. ``100`` or ``200`` to tune load.

``python -m cProfile`` on the whole script still includes interpreter + warm-up in the
profile; prefer ``--cprofile-out`` for clean scenario-only stats.

Requires dependencies from ``requirements.txt`` (moto, Pillow, bcrypt, PyJWT, boto3).
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Preprocess scenarios loop this many synthetic images (env: PREPROCESS_PROFILE_IMAGE_COUNT).
PREPROCESS_PROFILE_IMAGE_COUNT = int(os.environ.get("PREPROCESS_PROFILE_IMAGE_COUNT", "150"))


def configure_profiling_environment() -> None:
    """Set env vars so ArtGuard backend code runs against moto (same idea as tests)."""
    os.environ.setdefault("ENVIRONMENT", "dev")
    os.environ.setdefault("AWS_REGION", "us-east-1")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
    os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
    os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
    # >= 32 bytes for HS256 (PyJWT warns below RFC 7518 minimum)
    os.environ.setdefault(
        "JWT_SECRET_KEY",
        "test-secret-key-for-profiling-xyz12",
    )

    os.environ.setdefault("DDB_USERS_TABLE", "test-users")
    os.environ.setdefault("DDB_INFERENCES_TABLE", "test-inferences")
    os.environ.setdefault("DDB_IMAGES_TABLE", "test-images")
    os.environ.setdefault("DDB_PATCHES_TABLE", "test-patches")
    os.environ.setdefault("DDB_RUNS_TABLE", "test-runs")
    os.environ.setdefault("S3_IMAGES_RAW_BUCKET", "test-raw-bucket")
    os.environ.setdefault("S3_IMAGES_PROCESSED_BUCKET", "test-processed-bucket")


def _clear_boto_caches() -> None:
    from src.apps.backend.config import dynamodb_resource, s3_client

    s3_client.cache_clear()
    dynamodb_resource.cache_clear()


def _create_s3_buckets(client: Any) -> None:
    client.create_bucket(Bucket="test-raw-bucket")
    client.create_bucket(Bucket="test-processed-bucket")


def _create_dynamodb_tables(ddb: Any) -> None:
    ddb.create_table(
        TableName="test-users",
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "email", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "EmailIndex",
                "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.create_table(
        TableName="test-inferences",
        KeySchema=[{"AttributeName": "inference_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "inference_id", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "N"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "UserInferencesIndex",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.create_table(
        TableName="test-images",
        KeySchema=[{"AttributeName": "image_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "image_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.create_table(
        TableName="test-patches",
        KeySchema=[{"AttributeName": "patch_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "patch_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.create_table(
        TableName="test-runs",
        KeySchema=[{"AttributeName": "run_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "run_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


@contextmanager
def mock_artguard_aws():
    """Moto context with S3 buckets and DynamoDB tables matching ``tests/conftest.py``."""
    configure_profiling_environment()
    import boto3

    try:
        from moto import mock_aws
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Scenarios that mock AWS need the ``moto`` package. "
            "Install dependencies: pip install -r requirements.txt"
        ) from exc

    with mock_aws():
        _clear_boto_caches()
        s3 = boto3.client("s3", region_name="us-east-1")
        _create_s3_buckets(s3)
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        _create_dynamodb_tables(ddb)
        _clear_boto_caches()
        yield


class _NoOpS3:
    """Avoid S3 I/O while still exercising JPEG encode in preprocess."""

    def put_object(self, **_kwargs: Any) -> None:
        return None


# ---------------------------------------------------------------------------
# Scenarios (each callable runs one conceptual workload)
# ---------------------------------------------------------------------------


def scenario_auth_crypto_burst() -> None:
    """Repeated bcrypt verify + JWT decode (login + authenticated API pattern)."""
    configure_profiling_environment()
    from src.apps.backend.security.jwt_tokens import create_access_token, decode_access_token
    from src.apps.backend.security.passwords import hash_password, verify_password

    pw_hash = hash_password("profiling-password-123")
    token = create_access_token("profiling-user-1")
    for _ in range(40):
        verify_password("profiling-password-123", pw_hash)
        decode_access_token(token)


def scenario_preprocess_small_image() -> None:
    """Many small RGB images → 2×2 grid each; S3 uploads no-op.

    Count is ``PREPROCESS_PROFILE_IMAGE_COUNT`` (default 150), or env
    ``PREPROCESS_PROFILE_IMAGE_COUNT`` (e.g. ``100`` or ``200``).
    """
    configure_profiling_environment()
    from PIL import Image

    from src.apps.data_pipeline.preprocess import process_image_to_patches

    n = PREPROCESS_PROFILE_IMAGE_COUNT
    for i in range(n):
        img = Image.new("RGB", (480, 360), color=(40 + (i % 40), 60, 80))
        process_image_to_patches(
            img,
            str(uuid.uuid4()),
            "test-processed-bucket",
            "inference",
            _NoOpS3(),
        )


def scenario_preprocess_high_resolution() -> None:
    """Many larger images → 4×4 grid each, more patches and JPEG encodes; S3 no-op.

    Count is ``PREPROCESS_PROFILE_IMAGE_COUNT`` (default 150), or env
    ``PREPROCESS_PROFILE_IMAGE_COUNT``.
    """
    configure_profiling_environment()
    from PIL import Image

    from src.apps.data_pipeline.preprocess import process_image_to_patches

    n = PREPROCESS_PROFILE_IMAGE_COUNT
    for i in range(n):
        img = Image.new("RGB", (1600, 1200), color=(10, 90, 140 + (i % 50)))
        process_image_to_patches(
            img,
            str(uuid.uuid4()),
            "test-processed-bucket",
            "inference",
            _NoOpS3(),
        )


def scenario_inference_patch_pipeline_full() -> None:
    """Full ``create_and_upload_patches``: preprocess + real S3 + DynamoDB writes (moto)."""
    with mock_artguard_aws():
        from PIL import Image

        from src.apps.backend.services import inference_service

        img = Image.new("RGB", (900, 700), color=(200, 100, 50))
        inference_service.create_and_upload_patches(img, str(uuid.uuid4()))


def scenario_split_stratified_large_n() -> None:
    """Large synthetic catalog: stratified fold assignment + train/val/test split."""
    configure_profiling_environment()
    from src.apps.data_pipeline.split import assign_folds, train_val_test_splits

    n = 3000
    items = [
        {
            "image_id": f"img-{i}",
            "sublabel": ("original", "forgery", "imitation")[i % 3],
        }
        for i in range(n)
    ]
    assignment = assign_folds(
        items, k_folds=5, outer_seed=17, inner_seed=99, stratify_on="sublabel"
    )
    train_val_test_splits(
        items,
        assignment,
        fold_id=0,
        k_folds=5,
        inner_seed=99,
        val_fraction=0.2,
        stratify_on="sublabel",
    )


def scenario_s3_inference_metadata_burst() -> None:
    """Many raw uploads + image rows + inference rows (SDK + app wiring, moto)."""
    with mock_artguard_aws():
        from src.apps.backend.services import inference_service

        for i in range(35):
            iid = str(uuid.uuid4())
            fname = f"shot-{i}.jpg"
            raw_uri = inference_service.upload_raw_image(
                b"\xff\xd8\xff\xe0" + os.urandom(2048),
                iid,
                fname,
                "image/jpeg",
            )
            inference_service.save_image_metadata(
                iid,
                fname,
                raw_uri,
                800,
                600,
                "Artist",
                "Title",
            )
            inference_service.create_inference_record(
                inference_id=f"inf-{i}",
                image_id=iid,
                user_id="user-prof",
                filename=fname,
                raw_s3_uri=raw_uri,
                artist_name="Artist",
                artwork_name="Title",
                file_size=2052,
            )


SCENARIOS: dict[str, Callable[[], None]] = {
    "auth_crypto_burst": scenario_auth_crypto_burst,
    "preprocess_small_image": scenario_preprocess_small_image,
    "preprocess_high_resolution": scenario_preprocess_high_resolution,
    "inference_patch_pipeline_full": scenario_inference_patch_pipeline_full,
    "split_stratified_large_n": scenario_split_stratified_large_n,
    "s3_inference_metadata_burst": scenario_s3_inference_metadata_burst,
}


def warmup() -> None:
    """Pre-import modules and run minimal work to reduce cold-start skew when profiling.

    Loads PIL, security, preprocess, split, and (if moto is installed) one moto-backed
    ``create_and_upload_patches`` call so first-byte JPEG plugins and botocore stubs are
    exercised before timed runs.
    """
    configure_profiling_environment()
    from PIL import Image

    from src.apps.backend.security.jwt_tokens import create_access_token, decode_access_token
    from src.apps.backend.security.passwords import hash_password, verify_password
    from src.apps.data_pipeline.preprocess import process_image_to_patches
    from src.apps.data_pipeline.split import assign_folds, train_val_test_splits

    pw_hash = hash_password("warmup-password")
    verify_password("warmup-password", pw_hash)
    token = create_access_token("warmup-user")
    decode_access_token(token)

    tiny = Image.new("RGB", (320, 240), color=(5, 10, 15))
    process_image_to_patches(
        tiny,
        str(uuid.uuid4()),
        "test-processed-bucket",
        "warmup",
        _NoOpS3(),
    )

    items = [{"image_id": f"warmup-{i}", "sublabel": ("original", "forgery")[i % 2]} for i in range(12)]
    assignment = assign_folds(items, k_folds=3, outer_seed=0, inner_seed=1, stratify_on="sublabel")
    train_val_test_splits(
        items,
        assignment,
        fold_id=0,
        k_folds=3,
        inner_seed=1,
        val_fraction=0.2,
        stratify_on="sublabel",
    )

    try:
        with mock_artguard_aws():
            from src.apps.backend.services import inference_service

            img = Image.new("RGB", (256, 256), color=(100, 100, 100))
            inference_service.create_and_upload_patches(img, str(uuid.uuid4()))
    except ModuleNotFoundError:
        pass


def list_scenario_names() -> list[str]:
    return sorted(SCENARIOS.keys())


def run_scenario(name: str) -> None:
    if name not in SCENARIOS:
        raise KeyError(f"Unknown scenario {name!r}. Use one of: {list_scenario_names()}")
    SCENARIOS[name]()


def print_cprofile_stats(
    path: str,
    sort_key: str = "cumulative",
    limit: int | None = None,
    output_path: str | None = None,
) -> None:
    """Print a human-readable table from a ``cProfile`` ``.prof`` file (binary pickle).

    If ``limit`` is ``None``, prints every function entry (no row cap). Otherwise
    passes ``limit`` to ``pstats.Stats.print_stats`` as the max number of rows.
    """
    import pstats

    def _emit(stats: pstats.Stats) -> None:
        stats.strip_dirs()
        stats.sort_stats(sort_key)
        if limit is None:
            stats.print_stats()
        else:
            stats.print_stats(limit)

    if output_path is not None:
        with open(output_path, "w", encoding="utf-8") as out:
            stats = pstats.Stats(path, stream=out)
            _emit(stats)
    else:
        stats = pstats.Stats(path)
        _emit(stats)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ArtGuard profiling scenarios.")
    parser.add_argument(
        "scenario",
        nargs="?",
        help="Scenario name (see --list). Ignored if --all is passed.",
    )
    parser.add_argument("--list", action="store_true", help="Print scenario names and exit.")
    parser.add_argument("--all", action="store_true", help="Run every scenario in sequence.")
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Run with stdlib profile.Profile (see https://docs.python.org/3/library/profile.html).",
    )
    parser.add_argument(
        "--print-stats",
        metavar="FILE.prof",
        help="Decode a cProfile binary .prof file and print a text table (pstats).",
    )
    parser.add_argument(
        "--stats-sort",
        default="cumulative",
        choices=("cumulative", "tottime", "calls"),
        help="Sort key for --print-stats (default: cumulative).",
    )
    parser.add_argument(
        "--stats-limit",
        type=int,
        default=None,
        metavar="N",
        help="Max rows for --print-stats (default: no limit — print full table).",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE.txt",
        help="Write --print-stats table to this text file instead of stdout.",
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Skip warmup before running scenarios (imports and plugins stay cold).",
    )
    parser.add_argument(
        "--cprofile-out",
        metavar="FILE.prof",
        help="Profile exactly one scenario with cProfile; warmup runs first and is excluded from FILE.prof.",
    )
    parser.add_argument(
        "--bench",
        action="store_true",
        help="Time each scenario N times (see --runs) and print mean ± std.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        metavar="N",
        help="Number of repetitions for --bench (default: 5).",
    )
    parser.add_argument(
        "--bench-dir",
        metavar="DIR",
        help="With --bench: save .prof + .txt per run and a summary.txt into DIR.",
    )
    args = parser.parse_args()

    if args.print_stats:
        if not os.path.isfile(args.print_stats):
            parser.error(f"Not a file: {args.print_stats!r}")
        print_cprofile_stats(
            args.print_stats,
            args.stats_sort,
            args.stats_limit,
            output_path=args.output,
        )
        return 0

    if args.list:
        for n in list_scenario_names():
            print(n)
        return 0

    if args.all:
        names = list_scenario_names()
    else:
        if not args.scenario:
            parser.error("Provide a scenario name, or use --list / --all / --print-stats")
        names = [args.scenario]

    if args.cprofile_out:
        if args.all or args.profile or args.bench:
            parser.error("--cprofile-out cannot be combined with --all, --profile, or --bench")
        if len(names) != 1:
            parser.error("--cprofile-out requires exactly one scenario name")
        import cProfile

        if not args.no_warmup:
            warmup()
        print(f"\n>>> cProfile → {args.cprofile_out} (scenario only, after warmup)\n")
        prof = cProfile.Profile()
        prof.enable()
        run_scenario(names[0])
        prof.disable()
        prof.dump_stats(args.cprofile_out)
        return 0

    if args.bench:
        import statistics
        import time

        n_runs = max(1, args.runs)
        out_dir = args.bench_dir

        if not args.no_warmup:
            print("Warming up…", file=sys.stderr)
            warmup()

        if out_dir:
            import cProfile

            os.makedirs(out_dir, exist_ok=True)

            print(f"\nBenchmark + cProfile: {n_runs} run(s) per scenario → {out_dir}/\n")
            print(f"{'Scenario':<40s}  {'Mean (s)':>10s}  {'Std (s)':>10s}  {'Min (s)':>10s}  {'Max (s)':>10s}  {'Runs':>5s}")
            print("-" * 90)
            for name in names:
                timings: list[float] = []
                for run_idx in range(n_runs):
                    prof = cProfile.Profile()
                    t0 = time.perf_counter()
                    prof.enable()
                    run_scenario(name)
                    prof.disable()
                    elapsed = time.perf_counter() - t0
                    timings.append(elapsed)

                    base = f"{name}_run{run_idx + 1}"
                    prof_path = os.path.join(out_dir, f"{base}.prof")
                    txt_path = os.path.join(out_dir, f"{base}.txt")
                    prof.dump_stats(prof_path)
                    print_cprofile_stats(prof_path, output_path=txt_path)

                mean = statistics.mean(timings)
                std = statistics.stdev(timings) if len(timings) > 1 else 0.0
                lo, hi = min(timings), max(timings)
                print(f"{name:<40s}  {mean:>10.4f}  {std:>10.4f}  {lo:>10.4f}  {hi:>10.4f}  {n_runs:>5d}")

            summary_path = os.path.join(out_dir, "summary.txt")
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(f"Benchmark: {n_runs} run(s) per scenario\n\n")
                f.write(f"{'Scenario':<40s}  {'Mean (s)':>10s}  {'Std (s)':>10s}  {'Min (s)':>10s}  {'Max (s)':>10s}  {'Runs':>5s}\n")
                f.write("-" * 90 + "\n")
                for name in names:
                    run_timings: list[float] = []
                    for run_idx in range(n_runs):
                        txt = os.path.join(out_dir, f"{name}_run{run_idx + 1}.txt")
                        with open(txt, encoding="utf-8") as tf:
                            first_line = ""
                            for line in tf:
                                if "function calls" in line and "seconds" in line:
                                    first_line = line.strip()
                                    break
                            if "in" in first_line:
                                try:
                                    secs = float(first_line.split("in")[1].split("seconds")[0].strip())
                                    run_timings.append(secs)
                                except (IndexError, ValueError):
                                    pass
                    if run_timings:
                        m = statistics.mean(run_timings)
                        s = statistics.stdev(run_timings) if len(run_timings) > 1 else 0.0
                        f.write(f"{name:<40s}  {m:>10.4f}  {s:>10.4f}  {min(run_timings):>10.4f}  {max(run_timings):>10.4f}  {len(run_timings):>5d}\n")
                f.write("\n")

            print(f"\nSummary written to {summary_path}")
            print()
            return 0

        print(f"\nBenchmark: {n_runs} run(s) per scenario\n")
        print(f"{'Scenario':<40s}  {'Mean (s)':>10s}  {'Std (s)':>10s}  {'Min (s)':>10s}  {'Max (s)':>10s}  {'Runs':>5s}")
        print("-" * 90)
        for name in names:
            timings: list[float] = []
            for _ in range(n_runs):
                t0 = time.perf_counter()
                run_scenario(name)
                timings.append(time.perf_counter() - t0)
            mean = statistics.mean(timings)
            std = statistics.stdev(timings) if len(timings) > 1 else 0.0
            lo, hi = min(timings), max(timings)
            print(f"{name:<40s}  {mean:>10.4f}  {std:>10.4f}  {lo:>10.4f}  {hi:>10.4f}  {n_runs:>5d}")
        print()
        return 0

    if not args.no_warmup:
        print("Warming up (imports + minimal PIL/JWT/bcrypt/split/moto)…", file=sys.stderr)
        warmup()

    import profile

    for name in names:
        print(f"\n>>> Scenario: {name}\n")
        if args.profile:
            pr = profile.Profile()
            pr.runcall(run_scenario, name)
            pr.print_stats(sort="cumulative")
        else:
            run_scenario(name)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
