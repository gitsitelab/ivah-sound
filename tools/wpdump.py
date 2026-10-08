"""Turn the Top Shelf WordPress SQL dump into a small posts.json.

Only published posts/pages are kept. [gallery ids="..."] shortcodes are
resolved to the attachment files so the build can show them.
"""
import json
import re
import sys


def _columns(sql, table):
    m = re.search(r"CREATE TABLE `%s` \((.*?)\n\) " % table, sql, re.S)
    return re.findall(r"^\s+`(\w+)`", m.group(1), re.M) if m else []


def _rows(sql, table):
    out = []
    ws = " \n\r\t"
    for m in re.finditer(r"INSERT INTO `%s` VALUES\s*" % table, sql):
        i = m.end()
        n = len(sql)
        while i < n:
            ch = sql[i]
            if ch == "(":
                i += 1
                row = []
                while True:
                    while sql[i] in ws:
                        i += 1
                    if sql[i] == "'":
                        i += 1
                        buf = []
                        while True:
                            c = sql[i]
                            if c == "\\":
                                nx = sql[i + 1]
                                buf.append({"n": "\n", "r": "\r", "t": "\t", "0": "\0"}.get(nx, nx))
                                i += 2
                            elif c == "'":
                                if sql[i + 1] == "'":
                                    buf.append("'")
                                    i += 2
                                else:
                                    i += 1
                                    break
                            else:
                                buf.append(c)
                                i += 1
                        row.append("".join(buf))
                        while sql[i] in ws:
                            i += 1
                    else:
                        j = i
                        while sql[j] not in ",)":
                            j += 1
                        v = sql[i:j].strip()
                        row.append(None if v == "NULL" else v)
                        i = j
                    if sql[i] == ",":
                        i += 1
                        continue
                    if sql[i] == ")":
                        i += 1
                        break
                out.append(row)
            elif ch == ";":
                break
            else:
                i += 1
    return out


def table(sql, name):
    cols = _columns(sql, name)
    return [dict(zip(cols, r)) for r in _rows(sql, name)]


def extract(sql_path):
    sql = open(sql_path, encoding="utf-8", errors="replace").read()
    posts = table(sql, "wp_posts")
    meta = {}
    for m in table(sql, "wp_postmeta"):
        meta.setdefault(m["post_id"], {})[m["meta_key"]] = m["meta_value"]
    by_id = {p["ID"]: p for p in posts}
    terms = {t["term_id"]: t for t in table(sql, "wp_terms")}
    tax = {t["term_taxonomy_id"]: t for t in table(sql, "wp_term_taxonomy")}
    rel = {}
    for r in table(sql, "wp_term_relationships"):
        t = tax.get(r["term_taxonomy_id"])
        if t and t["taxonomy"] in ("category", "post_tag"):
            name = terms.get(t["term_id"], {}).get("name")
            if name and name != "Uncategorized":
                rel.setdefault(r["object_id"], []).append(name)

    def attachment_file(aid):
        return meta.get(aid, {}).get("_wp_attached_file")

    result = []
    for p in posts:
        if p["post_type"] not in ("post", "page") or p["post_status"] != "publish":
            continue
        galleries = {}
        for g in re.findall(r'\[gallery[^\]]*ids="([\d,\s]+)"[^\]]*\]', p["post_content"]):
            files = []
            for aid in [x.strip() for x in g.split(",") if x.strip()]:
                f = attachment_file(aid)
                if f:
                    a = by_id.get(aid, {})
                    files.append({"file": f, "caption": a.get("post_excerpt") or ""})
            galleries[g] = files
        result.append({
            "id": p["ID"],
            "type": p["post_type"],
            "date": p["post_date"],
            "title": p["post_title"],
            "slug": p["post_name"],
            "content": p["post_content"],
            "galleries": galleries,
            "tags": sorted(set(rel.get(p["ID"], []))),
        })
    result.sort(key=lambda x: x["date"], reverse=True)
    return result


def needed_uploads(posts):
    files = set()
    for p in posts:
        for f in re.findall(r"wp-content/uploads/([^\"'\s)\]]+\.(?:jpe?g|png|gif))", p["content"], re.I):
            files.add(f)
        for g in p["galleries"].values():
            for x in g:
                files.add(x["file"])
    return sorted(files)


if __name__ == "__main__":
    data = extract(sys.argv[1])
    json.dump(data, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
    print(len(data), "posts;", len(needed_uploads(data)), "upload files")
