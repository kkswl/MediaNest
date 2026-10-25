"""Collect *installed* package notices without copying third-party implementation code.

Run after Python/npm installation and before a release. This is an inventory, not a
legal compatibility checker. Any missing full text remains explicitly reported.
"""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "licenses"

SUPPLEMENTAL = {
    "embla-carousel@8.6.0": "https://raw.githubusercontent.com/davidjerleke/embla-carousel/v8.6.0/LICENSE",
    "embla-carousel-auto-height@8.6.0": "https://raw.githubusercontent.com/davidjerleke/embla-carousel/v8.6.0/LICENSE",
    "embla-carousel-auto-scroll@8.6.0": "https://raw.githubusercontent.com/davidjerleke/embla-carousel/v8.6.0/LICENSE",
    "embla-carousel-autoplay@8.6.0": "https://raw.githubusercontent.com/davidjerleke/embla-carousel/v8.6.0/LICENSE",
    "embla-carousel-class-names@8.6.0": "https://raw.githubusercontent.com/davidjerleke/embla-carousel/v8.6.0/LICENSE",
    "embla-carousel-fade@8.6.0": "https://raw.githubusercontent.com/davidjerleke/embla-carousel/v8.6.0/LICENSE",
    "embla-carousel-reactive-utils@8.6.0": "https://raw.githubusercontent.com/davidjerleke/embla-carousel/v8.6.0/LICENSE",
    "embla-carousel-vue@8.6.0": "https://raw.githubusercontent.com/davidjerleke/embla-carousel/v8.6.0/LICENSE",
    "embla-carousel-wheel-gestures@8.1.0": "https://raw.githubusercontent.com/xiel/embla-carousel-wheel-gestures/v8.1.0/LICENSE",
    "@vue/devtools-api@6.6.4": "https://raw.githubusercontent.com/vuejs/vue-devtools/v6.6.4/LICENSE",
    "sirv@3.0.2": "https://raw.githubusercontent.com/lukeed/sirv/v3.0.2/license",
    # These upstream URLs are the license locations referenced by the installed
    # package or icon-set metadata, not an assertion of an exact source tag match.
    "@iconify-json/lucide@1.2.147": "https://raw.githubusercontent.com/lucide-icons/lucide/main/LICENSE",
    "@polka/url@1.0.0-next.29": "https://raw.githubusercontent.com/lukeed/polka/next/license",
    "vaul-vue@0.4.1": "https://raw.githubusercontent.com/Elliot-Alexander/vaul-vue/main/LICENSE",
}


def notice_name(name):
    lowered = name.lower()
    return lowered.startswith(("license", "licence", "copying", "notice")) and not lowered.endswith((".py", ".pyc"))


def python_packages():
    for dist in sorted(importlib.metadata.distributions(), key=lambda x: x.metadata.get("Name", "").lower()):
        name = dist.metadata.get("Name", "unknown")
        if name.lower().replace("_", "-") == "yingji-index":
            continue  # This project is not a third-party dependency; no license decision is inferred.
        documents = []
        for file in dist.files or []:
            if notice_name(file.name):
                path = dist.locate_file(file)
                if path.is_file() and path.stat().st_size < 2_000_000:
                    documents.append((str(file), path.read_text(encoding="utf-8", errors="replace")))
        yield {"ecosystem": "python", "name": name, "version": dist.version,
               "license": dist.metadata.get("License-Expression") or dist.metadata.get("License", "unknown"),
               "source": dist.metadata.get_all("Project-URL") or [dist.metadata.get("Home-page", "")],
               "notices": documents}


def npm_packages():
    pending = [ROOT / "frontend" / "node_modules"]
    while pending:
        directory = pending.pop()
        if not directory.exists():
            continue
        entries = []
        for child in directory.iterdir():
            if child.name.startswith(".") or not child.is_dir():
                continue
            entries.extend(child.iterdir() if child.name.startswith("@") else [child])
        for package in sorted(entries):
            metadata = package / "package.json"
            if not metadata.is_file():
                continue
            data = json.loads(metadata.read_text(encoding="utf-8"))
            documents = [(p.name, p.read_text(encoding="utf-8", errors="replace"))
                         for p in sorted(package.iterdir())
                         if p.is_file() and notice_name(p.name) and p.stat().st_size < 2_000_000]
            if not documents and (data.get("name", "").startswith("@esbuild/")
                                  or data.get("name", "").startswith("@rollup/rollup-")):
                parent_name = "esbuild" if data["name"].startswith("@esbuild/") else "rollup"
                parent = ROOT / "frontend" / "node_modules" / parent_name
                if parent.is_dir():
                    parent_data = json.loads((parent / "package.json").read_text(encoding="utf-8"))
                    if parent_data.get("version") == data.get("version"):
                        documents.extend((f"matching-version-parent:{parent_name}/{p.name}",
                                          p.read_text(encoding="utf-8", errors="replace"))
                                         for p in sorted(parent.iterdir()) if p.is_file() and notice_name(p.name))
            repo = data.get("repository", "")
            yield {"ecosystem": "npm", "name": data.get("name", package.name),
                   "version": data.get("version", "unknown"), "license": data.get("license", "unknown"),
                   "source": repo.get("url", "") if isinstance(repo, dict) else repo,
                   "notices": documents}
            pending.append(package / "node_modules")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-supplemental", action="store_true",
                        help="Fetch only fixed official license URLs; never application resources")
    args = parser.parse_args()
    OUTPUT.mkdir(exist_ok=True)
    supplemental_dir = OUTPUT / "supplemental"
    if args.fetch_supplemental:
        supplemental_dir.mkdir(exist_ok=True)
        for url in sorted(set(SUPPLEMENTAL.values())):
            file = supplemental_dir / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".txt")
            try:
                with urlopen(url, timeout=30) as response:
                    text = response.read(2_000_001)
                if len(text) > 2_000_000 or b"copyright" not in text.lower():
                    raise ValueError("not a bounded license document")
                file.write_bytes(text)
            except (OSError, URLError, ValueError) as exc:
                print(f"Supplemental notice unavailable: {url}: {type(exc).__name__}")
    packages = list(python_packages()) + list(npm_packages())
    unique = {(p["ecosystem"], p["name"], p["version"]): p for p in packages}
    packages = [unique[k] for k in sorted(unique)]
    index, full, missing = [], [], []
    for package in packages:
        title = f"{package['ecosystem']}:{package['name']}@{package['version']}"
        documents = package.pop("notices")
        source = SUPPLEMENTAL.get(f"{package['name']}@{package['version']}")
        if not documents and source:
            cached = supplemental_dir / (hashlib.sha256(source.encode()).hexdigest()[:24] + ".txt")
            if cached.is_file():
                documents.append(("supplemental-upstream:" + source, cached.read_text(encoding="utf-8")))
                package["supplemental_source"] = source
        package["notice_files"] = [name for name, _ in documents]
        index.append(package)
        full.append(f"\n{'=' * 78}\n{title}\nDeclared license: {package['license']}\nSource: {package['source']}\n")
        if not documents:
            missing.append(title)
            full.append("FULL LICENSE TEXT MISSING FROM INSTALLED PACKAGE ROOT / DIST-INFO.\n")
        for name, text in documents:
            full.append(f"\n--- {name} ---\n{text}\n")
    (OUTPUT / "installed-manifest.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "THIRD_PARTY_LICENSES.txt").write_text("".join(full), encoding="utf-8")
    (OUTPUT / "MISSING_NOTICE_TEXTS.txt").write_text(
        "Inventory of installed Python and npm packages (includes development tools).\n"
        "Missing full texts are NOT implied licensed for redistribution; review before release.\n"
        + "\n".join(missing) + "\n", encoding="utf-8")
    print(f"Collected {len(packages)} installed package records; {len(missing)} missing full notice texts.")
    print("Review licenses/MISSING_NOTICE_TEXTS.txt before distributing. Default mode makes no network requests.")


if __name__ == "__main__":
    main()
