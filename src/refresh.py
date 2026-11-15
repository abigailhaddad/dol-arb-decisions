"""Weekly refresh: re-read both ARB listings, rebuild, fetch text for new documents, merge, upload.

    python src/refresh.py --dry-run     # everything but the upload; writes out/decisions.parquet
    HF_TOKEN=... python src/refresh.py

About 360 listing requests and one per new document, one second apart. Rows are keyed by decision_id; the new
build wins, and rows no longer on either listing are kept. The run stops without uploading if a fetch fails,
a listing parses to far fewer rows than before, or the merge would shrink the table. With no HF_TOKEN it
stops before the upload and says so.
"""
import json, os, subprocess, sys, time
import pandas as pd
import requests

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
REPO = "abigailhaddad/dol-arb-decisions"
FILES = ["decisions.parquet", "decision_text.parquet"]


def merge(old, new):
    """New wins by decision_id; rows only in old are kept."""
    kept = old[~old["decision_id"].isin(set(new["decision_id"]))]
    return pd.concat([new, kept], ignore_index=True)


def attach_text(df, old):
    """Text columns from the published text table (`old`) by url; fetch the rest."""
    import text as textmod
    cols = ["text", "text_chars", "pages", "text_status"]
    have = old.dropna(subset=["url"]).drop_duplicates("url").set_index("url")[cols] if len(old) else pd.DataFrame(columns=cols)
    todo = [u for u in df["url"].dropna().unique() if u not in have.index]
    print(len(todo), "new documents to fetch", flush=True)
    s = requests.Session()
    got = {}
    for u in todo:
        if not textmod.allowed(u):
            got[u] = {"text": None, "text_chars": 0, "pages": None, "text_status": "not fetched: robots.txt disallows"}
            continue
        time.sleep(1)
        rec = textmod.extract(u, s)
        got[u] = {"text": rec["text"], "text_chars": len(rec["text"] or ""), "pages": rec["pages"],
                  "text_status": rec["text_status"]}
    new = pd.DataFrame.from_dict(got, orient="index", columns=cols)
    lookup = pd.concat([have, new])
    df = df.drop(columns=[c for c in cols if c in df], errors="ignore").join(lookup, on="url")
    return df


def main():
    dry = "--dry-run" in sys.argv
    hf = f"https://huggingface.co/datasets/{REPO}/resolve/main/"
    old = pd.read_parquet(hf + "decisions.parquet")
    old_text = pd.read_parquet(hf + "decision_text.parquet")
    subprocess.run([sys.executable, os.path.join(HERE, "crawl.py")], check=True)
    import build
    new, report = build.build()
    if len(new) < 0.95 * len(old):
        sys.exit(f"STOP: build has {len(new)} rows, published table has {len(old)}; nothing uploaded")
    new = attach_text(new, old_text)
    old_full = old.merge(old_text[["decision_id", "text"]], on="decision_id", how="left")
    merged = merge(new, old_full)
    if len(merged) < len(old):
        sys.exit("STOP: merge would shrink the table; nothing uploaded")
    assert merged["decision_id"].is_unique
    added = len(merged) - len(old)
    build.write(merged)
    json.dump(report, open("out/report.json", "w"), indent=1, default=str)
    print({"rows": len(merged), "added": added})
    if dry:
        print("dry run: nothing uploaded")
        return
    if not os.environ.get("HF_TOKEN"):
        print("HF_TOKEN is not set (add it as a repository secret). Skipping the upload.")
        return

    def norm(d):
        return d.sort_values("decision_id").reset_index(drop=True).astype(str)
    now = pd.read_parquet("out/decisions.parquet")
    if added == 0 and list(now.columns) == list(old.columns) and norm(now).equals(norm(old)):
        print("nothing changed")
        return
    from huggingface_hub import CommitOperationAdd, HfApi
    ops = [CommitOperationAdd(path_in_repo=f, path_or_fileobj=f"out/{f}") for f in FILES]
    HfApi().create_commit(repo_id=REPO, repo_type="dataset", operations=ops,
                          commit_message=f"Refresh: +{added} decisions")


if __name__ == "__main__":
    main()
