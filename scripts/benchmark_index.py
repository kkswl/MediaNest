"""Synthetic, offline index benchmark.

This script never constructs a live 115 reader. It creates synthetic rows in a
temporary SQLite database, runs the same catalog query used by the API, and
prints reproducible timing and peak-memory measurements.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import tracemalloc
from pathlib import Path

from app.catalog import catalog_query
from app.db import Admin, Database, Node, Source, Variant, Work


def run(node_count: int) -> dict[str, float | int]:
    if not 1 <= node_count <= 200_000:
        raise ValueError("node_count must be between 1 and 200000")
    with tempfile.TemporaryDirectory(prefix="yingji-benchmark-") as folder:
        db = Database("sqlite:///" + str(Path(folder) / "benchmark.db"))
        db.init()
        with db.session.begin() as session:
            admin = Admin(username="benchmark", password_hash="offline")
            session.add(admin)
            session.flush()
            source = Source(owner_id=admin.id, code="synthetic-benchmark", access_code="offline",
                            url="https://115.com/s/synthetic-benchmark", title="Synthetic", adapter="mock")
            session.add(source)
            session.flush()
            works = [Work(identity=f"synthetic-{index}", title=f"合成作品 {index}", year=2020 + index % 7,
                          category="movie", status="confirmed", visible=True,
                          info={"aliases": [f"Synthetic {index}"], "genres": ["剧情"]})
                     for index in range(node_count)]
            session.add_all(works)
            session.flush()
            nodes = [Node(source_id=source.id, remote_id=str(index + 1), parent_remote_id="0",
                          name=f"合成作品 {index}.1080p.mkv", path=f"合成/{index}.mkv", is_dir=False,
                          size=1024, health="healthy") for index in range(node_count)]
            session.add_all(nodes)
            session.flush()
            session.add_all([Variant(work_id=work.id, source_id=source.id, node_id=node.id,
                                     attributes={"resolution": "1080P", "format": "MKV"})
                             for work, node in zip(works, nodes)])
        tracemalloc.start()
        started = time.perf_counter()
        with db.session() as session:
            query = catalog_query("合成作品 1")
            count = len(session.scalars(query.limit(1000)).all())
        elapsed = (time.perf_counter() - started) * 1000
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result = {"nodes": node_count, "works": node_count, "matched": count,
                  "query_ms": round(elapsed, 2), "peak_mib": round(peak / 1024 / 1024, 2)}
        db.engine.dispose()
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="映集离线合成目录索引基准")
    parser.add_argument("--nodes", type=int, default=2000)
    args = parser.parse_args()
    print(json.dumps(run(args.nodes), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
