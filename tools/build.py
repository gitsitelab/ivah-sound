"""Build the Ivah Sound site into _site/ from src/ and archive/.

  python tools/build.py

Everything the pages need is taken from archive/ (filled by import_media.py),
so the build works even after the old sites are gone.
"""
import datetime
import hashlib
import html
import json
import os
import re
import shutil
import sys
from urllib.parse import parse_qs, urlparse, unquote

from bs4 import BeautifulSoup, NavigableString
from PIL import Image, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
ARCHIVE = os.path.join(ROOT, "archive")
OUT = os.path.join(ROOT, "_site")
YEAR = str(datetime.date.today().year)
VERSION = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M")
SITE_URL = "https://gitsitelab.github.io/ivah-sound/"
SITE_DESC = "Ivah Sound: a hand-built sound system and crew from the south of Finland, spreading sound system culture since 2010."

warnings = []


def warn(msg):
    warnings.append(msg)


# ---------------------------------------------------------------- images
_img_cache = {}


def _out_name(rel, width, ext):
    base = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(rel.replace("archive/", ""))[0].lower()).strip("-")
    base = base[-48:].strip("-")
    h = hashlib.md5(rel.encode()).hexdigest()[:6]
    return f"media/{base}-{h}-{width}{ext}"


def image(rel, width=1200):
    """Resize an archive image for the web. Returns a site-relative URL."""
    key = (rel, width)
    if key in _img_cache:
        return _img_cache[key]
    src = os.path.join(ROOT, rel)
    if not os.path.exists(src):
        warn("missing image " + rel)
        _img_cache[key] = None
        return None
    ext = os.path.splitext(rel)[1].lower()
    if ext == ".gif":  # keep animation
        out = _out_name(rel, 0, ".gif")
        dst = os.path.join(OUT, out)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(src, dst)
        _img_cache[key] = out
        return out
    im = Image.open(src)
    im = ImageOps.exif_transpose(im)
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    if has_alpha:
        im = im.convert("RGBA")
        alpha = im.getchannel("A")
        has_alpha = alpha.getextrema()[0] < 250
    out_ext = ".png" if has_alpha else ".jpg"
    out = _out_name(rel, width, out_ext)
    dst = os.path.join(OUT, out)
    if not os.path.exists(dst):
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if has_alpha:
            im.save(dst, optimize=True)
        else:
            im.convert("RGB").save(dst, quality=80, optimize=True, progressive=True)
    _img_cache[key] = out
    return out


def copy_file(rel, out):
    src = os.path.join(ROOT, rel)
    if not os.path.exists(src):
        warn("missing file " + rel)
        return None
    dst = os.path.join(OUT, out)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy(src, dst)
    return out


def recolor(rel, out, rgb, size=None, bg=None):
    """Recolor a transparent logo (keep its alpha)."""
    src = os.path.join(ROOT, rel)
    if not os.path.exists(src):
        warn("missing logo " + rel)
        return
    im = Image.open(src).convert("RGBA")
    alpha = im.getchannel("A")
    solid = Image.new("RGBA", im.size, rgb + (255,))
    solid.putalpha(alpha)
    if size:
        solid.thumbnail(size, Image.LANCZOS)
    if bg:
        canvas = Image.new("RGBA", (max(solid.size) + 40,) * 2, bg + (255,))
        canvas.alpha_composite(solid, ((canvas.width - solid.width) // 2, (canvas.height - solid.height) // 2))
        solid = canvas.resize((180, 180), Image.LANCZOS).convert("RGB")
    dst = os.path.join(OUT, out)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    solid.save(dst, optimize=True)


# ---------------------------------------------------------------- templates
LAYOUT = open(os.path.join(SRC, "layout.html"), encoding="utf-8").read()


def fill_tokens(text, root):
    def img_tok(m):
        rel, w = m.group(1), int(m.group(2))
        url = image(rel, w)
        return root + url if url else ""
    text = re.sub(r"\{\{img:([^|}]+)\|(\d+)\}\}", img_tok, text)
    return text.replace("{{root}}", root).replace("{{year}}", YEAR)


def page(content, out, title, description=SITE_DESC, body_class="", robots="", og_image=None, journal=False):
    depth = out.count("/")
    root = "../" * depth
    html_out = LAYOUT
    for k, v in {
        "{{content}}": content,
        "{{title}}": html.escape(title),
        "{{description}}": html.escape(description),
        "{{body_class}}": body_class,
        "{{robots}}": robots,
        "{{og_image}}": SITE_URL + (og_image or "assets/og.jpg"),
        "{{journal_current}}": ' aria-current="page"' if journal else "",
        "{{version}}": VERSION,
    }.items():
        html_out = html_out.replace(k, v)
    html_out = fill_tokens(html_out, root)
    dst = os.path.join(OUT, out)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(html_out)


# ---------------------------------------------------------------- journal: helpers
BAD_HOSTS = ("blog.ivahsound.com", "ivahsound.tumblr.com", "topshelf.ivahsound.com", "tumblr.com/reblog", "assets.tumblr.com")
BLOCK_TAGS = ("<p", "<div", "<h1", "<h2", "<h3", "<h4", "<h5", "<ul", "<ol", "<blockquote", "<iframe", "<table", "<figure", "%%GALLERY", "<video", "<hr")


def youtube_id(s):
    m = re.search(r"(?:youtube(?:-nocookie)?\.com/(?:watch\?v=|embed/|v/)|youtu\.be/)([\w-]{11})", s or "")
    return m.group(1) if m else None


def yt_embed(vid, title="Video"):
    return (f'<div class="embed-video"><iframe src="https://www.youtube-nocookie.com/embed/{vid}?rel=0" '
            f'title="{html.escape(title)}" loading="lazy" allow="encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe></div>')


def real_link(href):
    """Undo Tumblr's link redirects."""
    if not href:
        return href
    if "t.umblr.com/redirect" in href:
        z = parse_qs(urlparse(href).query).get("z")
        if z:
            return unquote(z[0])
    return href


def text_of(fragment):
    t = BeautifulSoup(fragment or "", "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def excerpt(fragment, n=170):
    t = text_of(fragment)
    if len(t) <= n:
        return t
    return t[:n].rsplit(" ", 1)[0].rstrip(",.;:—-") + "…"


def slugify(s):
    s = html.unescape(s).lower()
    s = re.sub(r"[åä]", "a", s)
    s = re.sub(r"ö", "o", s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60].strip("-")


def tidy(fragment, root, local_img):
    """Clean imported HTML: local images, no links to the old blogs, embeds made responsive."""
    soup = BeautifulSoup(fragment or "", "html.parser")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    for a in soup.find_all("a"):
        href = real_link(a.get("href", ""))
        if any(h in href for h in BAD_HOSTS):
            local = local_img(href) if re.search(r"\.(jpe?g|png|gif)$", href, re.I) else None
            if local:
                a["href"] = root + local
            else:
                a.unwrap()
                continue
        else:
            a["href"] = href
            if href.startswith("http"):
                a["rel"] = "noopener"
        for attr in list(a.attrs):
            if attr not in ("href", "rel"):
                del a[attr]
    for img in soup.find_all("img"):
        local = local_img(img.get("src", ""))
        if not local:
            img.decompose()
            continue
        img["src"] = root + local
        img["loading"] = "lazy"
        keep = {"src", "alt", "loading", "class"}
        for attr in list(img.attrs):
            if attr not in keep:
                del img[attr]
        cls = [c for c in img.get("class", []) if c in ("alignleft", "alignright", "aligncenter")]
        if cls:
            img["class"] = cls
        elif "class" in img.attrs:
            del img["class"]
        img["alt"] = img.get("alt", "")
    for fr in soup.find_all("iframe"):
        src = fr.get("src", "")
        if src.startswith("//"):
            src = "https:" + src
        src = src.replace("http://", "https://")
        vid = youtube_id(src)
        if vid:
            fr.replace_with(BeautifulSoup(yt_embed(vid), "html.parser"))
            continue
        if not any(h in src for h in ("soundcloud.com", "mixcloud.com", "vimeo.com", "bandcamp.com")):
            fr.decompose()
            continue
        height = "166" if "soundcloud" in src and "visual=true" not in src else ("120" if "mixcloud" in src else "300")
        new = soup.new_tag("iframe", src=src, loading="lazy", height=height, title="Audio player")
        new["allow"] = "autoplay"
        fr.replace_with(new)
    for span in soup.find_all(["span", "font"]):
        span.unwrap()
    for tag in soup.find_all(True):
        if tag.name not in ("img", "a", "iframe", "div", "video", "source"):
            for attr in ("style", "class", "id", "dir", "data-reactroot"):
                if attr in tag.attrs and not (tag.name == "div" and attr == "class"):
                    del tag[attr]
    for p in soup.find_all("p"):
        if not p.get_text(strip=True) and not p.find(["img", "iframe", "video"]):
            p.decompose()
    return str(soup).strip()


def gallery_html(items, root, single_ok=True):
    """items: list of (archive_rel, alt)"""
    figs = []
    for rel, alt in items:
        thumb = image(rel, 700)
        full = image(rel, 1800)
        if not thumb:
            continue
        figs.append(f'<a href="{root}{full}"><img src="{root}{thumb}" alt="{html.escape(alt)}" loading="lazy"></a>')
    if not figs:
        return ""
    cls = "gallery single" if (len(figs) == 1 and single_ok) else "gallery"
    return f'<div class="{cls}">' + "".join(figs) + "</div>"


# ---------------------------------------------------------------- journal: Ivah Sound blog (Tumblr)
TUMBLR_TITLES = {
    "151695830050": "Dub Smugglers stage, Outlook Festival 2016",
    "151695763995": "Fyah I meets Tree-of Dub: Seek RastafarI",
    "144898897030": "Outlook Festival Helsinki launch party 2016",
    "144898871915": "Sound system culture at Kosmos Festival",
    "144898840560": "Ivah Sound at Outlook Festival 2016",
    "143781734770": "Drop Zone / Ivah Sound",
    "142004945020": "FRWRD #8",
    "141741762880": "FRWRD #8 with J. Robinson",
    "141023345755": "Basso NOST€: support Finnish speaker building",
    "139191951165": "FRWRD #7 poster with augmented reality",
    "139190813020": "The FRWRD #7 poster comes alive",
    "138408272755": "FRWRD #7: Deng Deng Hi-Fi meets Ivah Sound",
    "135969366685": "Announcing FRWRD #7",
    "134850554500": "FRWRD in the city centre: the aftermovie",
    "132460497955": "Dub Union",
    "130391572810": "Kallio Block Party 2015",
    "130391110665": "Equipment rental and event production",
    "130390430965": "FRWRD returns, now in the city centre",
    "114575176275": "FRWRD #3 session video with Alpha Steppa",
    "114575990840": "Helsinki Dub Club: the first session",
    "114575397215": "Helsinki Dub Club",
    "114575281105": "Ivah Sound and Tulitauko Sound present Helsinki Dub Club",
    "114575144405": "FRWRD #5 at Ravintola Lämpö",
    "114575088255": "FRWRD #4 with Tes La Rok",
    "114575006665": "FRWRD: a night of digital reggae",
    "114574904360": "FRWRD: two stages, two sound systems",
    "85325857975": "Joensuu takeover with Trey & Prospero",
    "84830029460": "FRWRD #3 with Alpha Steppa",
    "84746842505": "FRWRD #1 promo: Panda Dub & Dan I Locks",
    "84746764820": "Ivah Sound crew",
    "85326536840": "FRWRD #2 with Olo ODG",
    "85326636600": "FRWRD #2: making of the poster",
    "85326353665": "FRWRD #1 with Panda Dub & Dan I Locks",
    "83313017605": "About Ivah Sound",
}


def tumblr_key(name):
    name = re.sub(r"^https?://", "", name)
    name = re.sub(r"[^\w.\-]+", "_", name)
    if "media.tumblr" in name:
        name = re.sub(r"_(\d+|75sq)(\.\w+)$", r"_X\2", name)
    return name


def tumblr_index():
    idx = {}
    folder = os.path.join(ARCHIVE, "blog", "media")
    if not os.path.isdir(folder):
        return idx
    for f in sorted(os.listdir(folder)):
        if "_75sq." in f:
            continue
        idx[tumblr_key(f)] = "archive/blog/media/" + f
    return idx


def tumblr_posts():
    path = os.path.join(ARCHIVE, "blog", "blog.json")
    if not os.path.exists(path):
        warn("no blog.json in archive")
        return []
    data = json.load(open(path, encoding="utf-8"))
    idx = tumblr_index()

    def find(url):
        return idx.get(tumblr_key(url or ""))

    posts = []
    for p in data["posts"]:
        pid = str(p["id"])
        date = p["date-gmt"][:10]
        title = TUMBLR_TITLES.get(pid) or p.get("regular-title") or p.get("link-text") or excerpt(p.get("photo-caption") or p.get("video-caption") or "", 60)
        parts = []  # (kind, value)
        cover = None
        body = ""
        t = p["type"]
        if t == "photo":
            photos = [ph.get("photo-url-1280") for ph in (p.get("photos") or [])] or [p.get("photo-url-1280")]
            rels = [find(u) for u in photos if u]
            rels = [r for r in rels if r]
            if rels:
                cover = rels[0]
                parts.append(("gallery", rels))
            body = p.get("photo-caption") or ""
        elif t == "video":
            src = (p.get("video-source") or "") + " " + (p.get("video-player") or "")
            m = re.search(r"va\.media\.tumblr\.com/(tumblr_\w+?)_480\.mp4", src)
            vid = youtube_id(src)
            if m:
                mp4 = find(f"https://va.media.tumblr.com/{m.group(1)}_480.mp4")
                poster = find(f"https://64.media.tumblr.com/{m.group(1)}_smart1.jpg")
                if mp4:
                    parts.append(("video", (mp4, poster)))
                    cover = poster
            elif vid:
                parts.append(("youtube", vid))
                cover = ("yt", vid)
            body = p.get("video-caption") or ""
        elif t == "audio":
            parts.append(("raw", p.get("audio-embed") or ""))
            body = p.get("audio-caption") or ""
        elif t == "link":
            body = p.get("link-description") or ""
            url = p.get("link-url") or ""
            if url and not any(h in url for h in BAD_HOSTS):
                body += f'<p><a href="{html.escape(url)}">{html.escape(p.get("link-text") or url)} →</a></p>'
        elif t == "regular":
            body = p.get("regular-body") or ""
        tags = []
        for tg in p.get("tags") or []:
            tags += [x for x in re.split(r"\s+", tg) if x] if " " in tg and len(tg) > 30 else [tg]
        posts.append({
            "source": "ivah", "source_name": "Ivah Sound blog", "id": pid, "date": date, "title": title,
            "parts": parts, "body": body, "cover": cover, "tags": tags, "find": find,
            "excerpt": excerpt(body),
        })
    return posts


# ---------------------------------------------------------------- journal: Top Shelf (WordPress)
def autop(text):
    text = text.replace("\r\n", "\n").replace("<!--more-->", "")
    blocks = re.split(r"\n\s*\n", text)
    out = []
    for b in blocks:
        b = b.strip()
        if not b or b == "&nbsp;":
            continue
        if b.lower().startswith(BLOCK_TAGS):
            out.append(b)
        else:
            out.append("<p>" + b.replace("\n", "<br>\n") + "</p>")
    return "\n".join(out)


def topshelf_posts():
    path = os.path.join(ARCHIVE, "topshelf", "posts.json")
    if not os.path.exists(path):
        warn("no Top Shelf posts.json in archive")
        return []
    data = json.load(open(path, encoding="utf-8"))
    posts = []

    def find(url):
        m = re.search(r"wp-content/uploads/([^\"'\s?]+)", url or "")
        if not m:
            return None
        rel = "archive/topshelf/uploads/" + m.group(1)
        if os.path.exists(os.path.join(ROOT, rel)):
            return rel
        # WordPress size variants such as -300x200.jpg / -e1427300804372.png
        base = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", rel)
        if os.path.exists(os.path.join(ROOT, base)):
            return base
        return None

    for p in data:
        content = p["content"]
        galleries = {}
        for i, (ids, files) in enumerate(p["galleries"].items()):
            token = f"%%GALLERY{i}%%"
            galleries[token] = ["archive/topshelf/uploads/" + f["file"] for f in files]
            content = re.sub(r'\[gallery[^\]]*ids="%s"[^\]]*\]' % re.escape(ids), "\n\n" + token + "\n\n", content)
        content = re.sub(r"\[/?\w+[^\]]*\]", "", content)  # any other shortcode
        # bare YouTube links on their own line become players (WordPress oEmbed)
        content = re.sub(r"^\s*(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]{11}\S*)\s*$",
                         lambda m: yt_embed(youtube_id(m.group(1))), content, flags=re.M)
        content = autop(content)
        first = None
        for tok, rels in galleries.items():
            rels = [r for r in rels if os.path.exists(os.path.join(ROOT, r))]
            if rels and not first:
                first = rels[0]
            galleries[tok] = rels
        if not first:
            m = re.search(r'<img[^>]+src="([^"]+)"', content)
            first = find(m.group(1)) if m else None
        title = html.unescape(p["title"])
        if p["type"] == "page" and title == "About":
            title = "About Top Shelf"
        posts.append({
            "source": "topshelf", "source_name": "Top Shelf", "id": p["id"], "date": p["date"][:10],
            "title": title, "parts": [], "body": content, "galleries": galleries, "cover": first,
            "tags": [html.unescape(t) for t in p["tags"]], "find": find, "excerpt": excerpt(re.sub(r"%%GALLERY\d+%%", "", content)),
        })
    return posts


# ---------------------------------------------------------------- journal: render
def cover_html(post, root):
    c = post["cover"]
    if isinstance(c, tuple) and c[0] == "yt":
        return f'<div class="post-card-img"><img src="https://i.ytimg.com/vi/{c[1]}/hqdefault.jpg" alt="" loading="lazy"></div>'
    if c:
        url = image(c, 700)
        if url:
            return f'<div class="post-card-img"><img src="{root}{url}" alt="" loading="lazy"></div>'
    return f'<div class="post-card-img fallback"><img src="{root}assets/emblem.png" alt="" loading="lazy"></div>'


def card(post, root):
    d = datetime.date.fromisoformat(post["date"])
    return (f'<a class="post-card" href="{root}journal/{post["slug"]}.html" data-source="{post["source"]}">'
            f'{cover_html(post, root)}<div class="post-card-body">'
            f'<p class="post-meta">{d.strftime("%d %b %Y")} <span class="src">· {post["source_name"]}</span></p>'
            f'<h3>{html.escape(post["title"])}</h3><p>{html.escape(post["excerpt"])}</p></div></a>')


def render_post_body(post, root):
    find = post["find"]

    def local(url):
        rel = find(url)
        return image(rel, 1400) if rel else None

    chunks = []
    for kind, val in post["parts"]:
        if kind == "gallery":
            chunks.append(gallery_html([(r, post["title"]) for r in val], root))
        elif kind == "youtube":
            chunks.append(yt_embed(val, post["title"]))
        elif kind == "video":
            mp4, poster = val
            out = copy_file(mp4, "media/" + os.path.basename(mp4).split("_", 1)[-1])
            pst = image(poster, 900) if poster else None
            if out:
                chunks.append(f'<video controls playsinline preload="metadata"{f" poster={chr(34)}{root}{pst}{chr(34)}" if pst else ""}>'
                              f'<source src="{root}{out}" type="video/mp4"></video>')
        elif kind == "raw":
            chunks.append(tidy(val, root, local))
    body = tidy(post["body"], root, local)
    for tok, rels in (post.get("galleries") or {}).items():
        g = gallery_html([(r, post["title"]) for r in rels], root)
        body = body.replace(f"<p>{tok}</p>", g).replace(tok, g)
    return "\n".join(chunks) + "\n" + body


def build_journal(posts):
    root = "../"
    for i, post in enumerate(posts):
        d = datetime.date.fromisoformat(post["date"])
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        nav = '<nav class="post-nav" aria-label="More stories">'
        nav += (f'<a class="prev" href="{newer["slug"]}.html"><span>← Newer</span><strong>{html.escape(newer["title"])}</strong></a>' if newer else "<span></span>")
        nav += (f'<a class="next" href="{older["slug"]}.html"><span>Older →</span><strong>{html.escape(older["title"])}</strong></a>' if older else "<span></span>")
        nav += "</nav>"
        tags = "".join(f"<li>{html.escape(t)}</li>" for t in post["tags"][:14])
        content = (f'<article class="article"><header class="article-head">'
                   f'<p class="eyebrow"><a href="../journal.html" style="text-decoration:none">Journal</a> · {post["source_name"]}</p>'
                   f'<h1 class="display">{html.escape(post["title"])}</h1>'
                   f'<p class="post-meta"><time datetime="{post["date"]}">{d.strftime("%d %B %Y")}</time></p></header>'
                   f'<div class="prose">{render_post_body(post, root)}</div>'
                   f'{f"<ul class=tags>{tags}</ul>" if tags else ""}</article>{nav}')
        og = None
        if post["cover"] and not isinstance(post["cover"], tuple):
            u = image(post["cover"], 700)
            og = u
        page(content, f"journal/{post['slug']}.html", f"{post['title']} · Ivah Sound", post["excerpt"] or SITE_DESC,
             body_class="page", og_image=og, journal=True)

    # index
    years = {}
    for p in posts:
        years.setdefault(p["date"][:4], []).append(p)
    n_ivah = sum(1 for p in posts if p["source"] == "ivah")
    n_ts = len(posts) - n_ivah
    groups = ""
    for y in sorted(years, reverse=True):
        groups += f'<section class="year-group" aria-label="{y}"><h2>{y}</h2><div class="post-grid">'
        groups += "".join(card(p, "") for p in years[y]) + "</div></section>"
    content = f'''<section class="page-hero"><div class="wrap">
<p class="eyebrow">Journal · {len(posts)} stories · {min(years)}–{max(years)}</p>
<h1 class="display">Journal</h1>
<p class="lead narrow">Sessions, clubs, posters and videos from the Ivah Sound blog, together with the Top Shelf drum &amp; bass blog by Prospero and Trey. Everything is kept here so the stories stay online.</p>
<div class="filters" role="group" aria-label="Filter stories">
<button type="button" data-filter="all" aria-pressed="true">All ({len(posts)})</button>
<button type="button" data-filter="ivah" aria-pressed="false">Ivah Sound ({n_ivah})</button>
<button type="button" data-filter="topshelf" aria-pressed="false">Top Shelf ({n_ts})</button>
</div></div></section>
<div class="wrap" style="padding-bottom:120px">{groups}</div>'''
    page(content, "journal.html", "Journal · Ivah Sound",
         "The Ivah Sound journal: sessions, clubs, posters and videos since 2014, plus the Top Shelf drum & bass blog.",
         body_class="page", journal=True)


# ---------------------------------------------------------------- artists (hidden page)
def build_artists():
    base = os.path.join(ARCHIVE, "ivahsound.com")
    index = BeautifulSoup(open(os.path.join(base, "index.html"), encoding="utf-8", errors="replace").read(), "html.parser")
    blocks = []
    for box in index.select("#team-grid .member-box"):
        pic = box.select_one(".member-pic")
        ref = pic.get("id")  # team/xxx.html
        name = box.select_one("h4").get_text(strip=True)
        position = box.select_one(".member-position").get_text(strip=True)
        portrait = "archive/ivahsound.com/" + pic.select_one("img")["src"]
        socials = []
        for a in box.select(".memebr-social a"):
            href = a.get("href", "")
            label = urlparse(href).netloc.replace("www.", "").split(".")[0].capitalize()
            socials.append((label, href.replace("http://", "https://")))
        team_path = os.path.join(base, ref)
        bio, facts, photos, players, roles = "", [], [], [], [position]
        if os.path.exists(team_path):
            t = BeautifulSoup(open(team_path, encoding="utf-8", errors="replace").read(), "html.parser")
            content = t.select_one(".project-content")
            bio = "".join(str(x) for x in content.find_all("p")) if content else ""
            roles = [s.get_text(strip=True) for s in t.select(".cat-project span")] or roles
            for li in t.select(".meta-project li"):
                label = li.find("strong").get_text(strip=True).rstrip(":")
                val = ", ".join(s.get_text(strip=True) for s in li.find_all("span")) or li.get_text(" ", strip=True).split(":", 1)[-1].strip()
                facts.append((label, val))
            photos = ["archive/ivahsound.com/" + i["src"] for i in t.select(".project-slider img")]
            for fr in t.find_all("iframe"):
                src = fr.get("src", "")
                if src.startswith("//"):
                    src = "https:" + src
                h = "60" if "mixcloud" in src else "166"
                players.append(f'<iframe src="{html.escape(src)}" height="{h}" loading="lazy" title="{html.escape(name)} player"></iframe>')
            for a in t.select("a[href]"):
                href = a["href"].replace("http://", "https://")
                if href.startswith("https") and href not in [s[1] for s in socials]:
                    label = urlparse(href).netloc.replace("www.", "").split(".")[0].capitalize()
                    socials.append((label, href))
        seen = set()
        photos = [p for p in photos if not (p in seen or seen.add(p))]
        portrait_url = image(portrait, 640)
        photo_html = "".join(f'<img src="{image(p, 800)}" alt="{html.escape(name)}" loading="lazy">' for p in photos if image(p, 800))
        links = "".join(f'<a class="btn btn-line" href="{html.escape(h)}" rel="noopener">{html.escape(l)}</a>' for l, h in socials)
        fact_html = "".join(f"<p><strong>{html.escape(k)}:</strong> {html.escape(v)}</p>" for k, v in facts)
        blocks.append(f'''<article class="artist" id="{slugify(name)}">
<div class="artist-portrait"><img src="{portrait_url}" alt="{html.escape(name)}" loading="lazy"></div>
<div><h2>{html.escape(name)}</h2><p class="roles">{" · ".join(html.escape(r) for r in roles)}</p>
<div class="bio">{bio}</div>
{f'<div class="facts">{fact_html}</div>' if fact_html else ""}
<div class="artist-links">{links}</div>
{f'<div class="artist-photos">{photo_html}</div>' if photo_html else ""}
<div class="players">{"".join(players)}</div></div></article>''')
    content = f'''<section class="page-hero"><div class="wrap">
<p class="eyebrow">The crew</p><h1 class="display">Our artists</h1>
<p class="lead narrow">The selectors, MCs, producers and technicians behind Ivah Sound.</p></div></section>
<div class="wrap" style="padding-bottom:120px">{"".join(blocks)}</div>'''
    page(content, "artists.html", "Artists · Ivah Sound", "The selectors, MCs, producers and technicians behind Ivah Sound.",
         body_class="page", robots='<meta name="robots" content="noindex">')


# ---------------------------------------------------------------- fonts
FONTS = [("bebas-neue", ["400"]), ("barlow", ["400", "400-italic", "500", "600"]), ("barlow-condensed", ["500", "600", "700"])]


def build_fonts():
    """Self-host the fonts from the @fontsource npm packages (latin + latin-ext only)."""
    base = os.path.join(ROOT, "node_modules", "@fontsource")
    css = []
    for pkg, weights in FONTS:
        for w in weights:
            path = os.path.join(base, pkg, w + ".css")
            if not os.path.exists(path):
                warn("font missing: run npm install (" + pkg + " " + w + ")")
                continue
            for block in re.findall(r"/\* [^*]+ \*/\s*@font-face \{.*?\}", open(path).read(), re.S):
                if not re.search(r"-latin(-ext)?-", block.split("*/")[0]):
                    continue
                f = re.search(r"url\(\./files/([^)]+\.woff2)\)", block).group(1)
                shutil.copy(os.path.join(base, pkg, "files", f), os.path.join(OUT, "assets", "fonts", f))
                block = re.sub(r"src: [^;]+;", f"src: url(fonts/{f}) format('woff2');", block)
                css.append(block)
    with open(os.path.join(OUT, "assets", "fonts.css"), "w") as fh:
        fh.write("\n".join(css) + "\n")


# ---------------------------------------------------------------- main
def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "assets", "fonts"))
    build_fonts()
    for f in ("site.css", "site.js"):
        shutil.copy(os.path.join(SRC, "assets", f), os.path.join(OUT, "assets", f))

    # brand + shared assets
    recolor("archive/lovable/ivah-wordmark.png", "assets/wordmark-light.png", (242, 237, 228), size=(720, 128))
    recolor("archive/ivahsound.com/images/loader-logo@2x.png", "assets/emblem.png", (233, 116, 33), size=(128, 128))
    recolor("archive/ivahsound.com/images/loader-logo@2x.png", "apple-touch-icon.png", (233, 116, 33), bg=(10, 10, 10))
    copy_file("archive/ivahsound.com/images/favicon.png", "favicon.png")
    copy_file("archive/ivahsound.com/images/overlays/dark.png", "assets/overlay-dark.png")
    copy_file("archive/lovable/ivah-hero-loop.mp4", "media/ivah-hero-loop.mp4")
    copy_file("archive/ivahsound.com/images/video/section-video.mp4", "media/section-video.mp4")
    copy_file("archive/ivahsound.com/images/video/section-video.webm", "media/section-video.webm")
    og = image("archive/ivahsound.com/images/background1920x1080.jpg", 1200)
    if og:
        shutil.copy(os.path.join(OUT, og), os.path.join(OUT, "assets", "og.jpg"))

    # journal
    posts = tumblr_posts() + topshelf_posts()
    posts.sort(key=lambda p: (p["date"], p["id"]), reverse=True)
    used = set()
    for p in posts:
        s = slugify(p["title"]) or p["id"]
        if s in used:
            s = f"{s}-{'top-shelf' if p['source'] == 'topshelf' else p['date'][:4]}"
        while s in used:
            s += "-x"
        used.add(s)
        p["slug"] = s
    build_journal(posts)

    # home
    home = open(os.path.join(SRC, "index.html"), encoding="utf-8").read()
    latest = "\n".join(card(p, "") for p in [p for p in posts if p["source"] == "ivah"][:2] + [p for p in posts if p["source"] == "topshelf"][:1])
    home = home.replace("{{journal_latest}}", latest).replace("{{post_count}}", str(len(posts)))
    page(home, "index.html", "Ivah Sound · Sound System & Culture · Finland", SITE_DESC, body_class="home")

    build_artists()

    # 404 + misc
    page('<section class="page-hero" style="min-height:70vh"><div class="wrap"><p class="eyebrow">404</p>'
         '<h1 class="display">Lost in the bass.</h1><p class="lead">That page does not exist.</p>'
         '<a class="btn btn-solid" href="index.html">Back to the sound</a></div></section>',
         "404.html", "Not found · Ivah Sound", body_class="page")
    open(os.path.join(OUT, ".nojekyll"), "w").close()

    total = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(OUT) for f in fs)
    print(f"built {len(posts)} journal posts, site size {total/1e6:.1f} MB")
    if warnings:
        print("warnings:")
        for w in warnings:
            print(" -", w)


if __name__ == "__main__":
    main()
