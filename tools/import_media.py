"""Copy everything the site needs from the old Ivah Sound sites into archive/.

Run by the GitHub Action. Files that are already in archive/ are skipped, so
once the archive is committed the old sites can disappear without breaking
anything. Nothing on the new site links back to the old sources.

Sources:
  * ivahsound.com            images, videos, crew and project pages
  * blog.ivahsound.com       all posts (Tumblr read API) and their media
  * Lovable preview          photos, hero loop, product shots
  * Top Shelf WordPress backup on Google Drive (topshelf.ivahsound.com is gone)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(ROOT, "archive")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wpdump  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (archive import for Ivah Sound)"}
LOVABLE = "https://ivah-sound-system.lovable.app/"
LOVABLE_FILES = [
    "favicon.png",
    "__l5e/assets-v1/7a39fbfb-bf0f-4700-8b30-19b19cb1ed24/ivah-wordmark.png",
    "__l5e/assets-v1/62b2255c-7dad-4c9b-93b5-9109855f2d76/ivah-hero-poster.jpg",
    "__l5e/assets-v1/54058843-dc8e-4230-9887-254be157cd77/ivah-hero-loop.webm",
    "__l5e/assets-v1/b9126dd4-0998-4344-beba-56ef9d462c77/ivah-hero-loop.mp4",
    "__l5e/assets-v1/dd853eb9-27ff-44e9-9bcd-0df8d7dfa6db/ivah-system-clean.jpg",
    "__l5e/assets-v1/13cd8fe5-ba9c-425a-9b5e-71ca95982233/ivah-forest-dancer.jpg",
    "__l5e/assets-v1/11c5954b-bd3e-49ed-99ab-5e51de01ac76/ivah-tshirt.jpg",
    "__l5e/assets-v1/612c0302-f7fb-4246-b083-986cb5683477/ivah-paper-system.jpg",
    "__l5e/assets-v1/1d167f9e-78df-4fa7-8137-1b40162fb635/ivah-tote.jpg",
]
TOPSHELF_DRIVE_ID = "1UFgiKN4_lMMGZ689HXmgtzpy5RB0l-We"

failures = []


def get(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=120) as r, open(dest + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(dest + ".part", dest)
        print("  got", url)
        return True
    except Exception as e:  # keep going, report at the end
        failures.append(f"{url}: {e}")
        if os.path.exists(dest + ".part"):
            os.remove(dest + ".part")
        return False


def media_name(url):
    return re.sub(r"[^\w.\-]+", "_", re.sub(r"^https?://", "", url))


def blog_media_urls(data):
    found = set()

    def scan(s):
        if isinstance(s, str):
            for u in re.findall(r"https?://[^\"'\s<>)\\]+?\.(?:jpe?g|png|gif|webp|mp4)(?:\?[^\"'\s<>)\\]*)?", s, re.I):
                found.add(re.sub(r"^http:", "https:", u))

    for p in data["posts"]:
        for v in p.values():
            scan(v)
        for ph in p.get("photos", []) or []:
            for v in ph.values():
                scan(v)
    best = {}
    for u in found:
        m = re.match(r"^(.*_)(\d+)(\.\w+)$", u)
        key = m.group(1) + "X" + m.group(3) if (m and "media.tumblr" in u) else u
        size = int(m.group(2)) if m else 9999
        if key not in best or best[key][1] < size:
            best[key] = (u, size)
    return sorted(u for u, _ in best.values())


def import_ivahsound():
    print("ivahsound.com")
    files = open(os.path.join(ROOT, "tools", "ivahsound_files.txt")).read().split()
    for f in files:
        get("https://ivahsound.com/" + f, os.path.join(ARCHIVE, "ivahsound.com", f))


def import_blog():
    print("blog.ivahsound.com")
    path = os.path.join(ARCHIVE, "blog", "blog.json")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        req = urllib.request.Request("https://blog.ivahsound.com/api/read/json?start=0&num=50&filter=none", headers=UA)
        raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
        raw = re.sub(r"^var tumblr_api_read = ", "", raw.strip()).rstrip(";")
        data = json.loads(raw)
        json.dump(data, open(path, "w"), ensure_ascii=False)
    data = json.load(open(path))
    for u in blog_media_urls(data):
        get(u, os.path.join(ARCHIVE, "blog", "media", media_name(u)))


def import_lovable():
    print("lovable")
    for f in LOVABLE_FILES:
        get(LOVABLE + f, os.path.join(ARCHIVE, "lovable", f.split("/")[-1]))


def import_topshelf():
    print("topshelf backup")
    posts_path = os.path.join(ARCHIVE, "topshelf", "posts.json")
    posts = json.load(open(posts_path)) if os.path.exists(posts_path) else None
    if posts is not None:
        missing = [f for f in wpdump.needed_uploads(posts)
                   if not os.path.exists(os.path.join(ARCHIVE, "topshelf", "uploads", f))]
        if not missing:
            return
    tmp = os.path.join(ROOT, "_tmp_topshelf")
    os.makedirs(tmp, exist_ok=True)
    tgz = os.path.join(tmp, "backup.tar.gz")
    url = f"https://drive.usercontent.google.com/download?id={TOPSHELF_DRIVE_ID}&export=download&confirm=t"
    subprocess.run(["curl", "-sSL", "--retry", "3", "-o", tgz, url], check=False)
    if not os.path.exists(tgz) or os.path.getsize(tgz) < 10_000_000:
        failures.append("Top Shelf backup could not be downloaded from Google Drive")
        return
    # The backup has a damaged tail; read what we can.
    try:
        with tarfile.open(tgz, "r:gz") as t:
            for m in t:
                if m.name == "softsql.sql" or m.name.startswith("wp-content/uploads/2015") or m.name.startswith("wp-content/uploads/2016"):
                    if m.isfile():
                        t.extract(m, tmp, filter="data")
    except Exception as e:
        print("  tar stopped early:", e)
    sql = os.path.join(tmp, "softsql.sql")
    if posts is None:
        posts = wpdump.extract(sql)
        os.makedirs(os.path.dirname(posts_path), exist_ok=True)
        json.dump(posts, open(posts_path, "w"), ensure_ascii=False, indent=1)
    for f in wpdump.needed_uploads(posts):
        src = os.path.join(tmp, "wp-content", "uploads", f)
        dst = os.path.join(ARCHIVE, "topshelf", "uploads", f)
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(src, dst)
        elif not os.path.exists(dst):
            failures.append("topshelf upload missing in backup: " + f)
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    for step in (import_ivahsound, import_blog, import_lovable, import_topshelf):
        try:
            step()
        except Exception as e:
            failures.append(f"{step.__name__}: {e}")
    if failures:
        print("\nCould not fetch:")
        for f in failures:
            print(" -", f)
    print("done")
