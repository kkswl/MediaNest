"""Entirely synthetic directory/NFO responses. Never fetch the demonstration URLs."""


def directory_fixture(code):
    nodes = {"0": []}
    contents = {}
    counter = 0

    def add(parent, name, folder=False, content=None, size=0):
        nonlocal counter
        counter += 1
        rid = str(counter)
        item = {"id": rid, "parent": parent, "name": name, "is_dir": folder,
                "size": size, "sha1": "", "public_image": ""}
        nodes[parent].append(item)
        if folder:
            nodes[rid] = []
        if content is not None:
            contents[rid] = content.encode("utf-8")
        return rid

    def nfo(title, year, key, category="movie", actor="林舟", collection="星海系列"):
        tag = "tvshow" if category in ("tv", "anime", "variety") else "movie"
        return (f'<{tag}><title>{title}</title><year>{year}</year>'
                f'<uniqueid type="fixture">{key}</uniqueid><category>{category}</category>'
                '<plot>这是一份用于本地验证的虚构影视资料。目录、演员和版本均为合成数据。</plot>'
                f'<actor><name>{actor}</name></actor><genre>剧情</genre><genre>冒险</genre>'
                f'<set><name>{collection}</name></set><rating>8.6</rating></{tag}>')

    if code not in ("demoa", "demob", "demotv"):
        return nodes, contents
    actor = add("0", "林舟作品合集", True)
    series = add(actor, "星海系列合集", True)
    movie = add(series, "星海来信 (2024)", True)
    add(movie, "movie.nfo", content=nfo("星海来信", 2024, "star-letter"), size=600)
    add(movie, "星海来信.2024.1080p.BluRay.国语.mkv", size=12 * 1024**3)
    add(movie, "星海来信.2024.zh.srt", size=45000)
    add(movie, "星海来信-poster.jpg", size=80000)
    if code != "demob":
        add(movie, "星海来信.2024.2160p.HDR.原声.iso", size=60 * 1024**3)
        disc = add(series, "星海来信 (2024) 蓝光", True)
        add(disc, "movie.nfo", content=nfo("星海来信", 2024, "star-letter"), size=600)
        bdmv = add(disc, "BDMV", True)
        stream = add(bdmv, "STREAM", True)
        add(stream, "00001.m2ts", size=30 * 1024**3)
        add(bdmv, "index.bdmv", size=5000)
    television = add("0", "电视剧", True)
    show = add(television, "雾港档案 (2025)", True)
    add(show, "tvshow.nfo", content=nfo("雾港档案", 2025, "mist-harbor", "tv", collection="雾港系列"), size=600)
    season = add(show, "Season 01", True)
    for e in range(1, 5):
        add(season, f"雾港档案.S01E{e:02}.1080p.WEB-DL.mkv", size=2 * 1024**3)
        add(season, f"雾港档案.S01E{e:02}.zh.srt", size=20000)
    if code == "demob":
        return nodes, contents
    titles = [
        ("长风入夜", 2023, "movie", "night-wind", "沈遥"),
        ("山川之间", 2022, "movie", "mountains", "陆青"),
        ("向光而行", 2024, "movie", "towards-light", "林舟"),
        ("岛屿日记", 2021, "movie", "island-diary", "许澄"),
        ("回声计划", 2025, "anime", "echo", "沈遥"),
        ("城市漫游", 2024, "variety", "city-walk", "陆青"),
        ("沿途的风", 2025, "concert", "live-wind", "许澄"),
        ("夏日旅人", 2020, "movie", "summer", "林舟"),
        ("远方灯塔", 2023, "movie", "lighthouse", "沈遥"),
        ("平行旅程", 2022, "anime", "parallel", "许澄"),
        ("深蓝之下", 2024, "movie", "deep-blue", "陆青"),
    ]
    for title, year, category, key, name in titles:
        folder = add("0", f"{title} ({year})", True)
        add(folder, "tvshow.nfo" if category in ("anime", "variety") else "movie.nfo",
            content=nfo(title, year, key, category, name, "独立精选"), size=600)
        suffix = ".S01E01" if category in ("anime", "variety") else ""
        add(folder, f"{title}.{year}{suffix}.2160p.WEB-DL.mkv", size=8 * 1024**3)
    incomplete = add("0", "雨落之后 (2026)", True)
    add(incomplete, "雨落之后.2026.1080p.mkv", size=1024**3)
    unknown = add("0", "000000", True)
    add(unknown, "file001.mkv", size=1024**3)
    misc = add("0", "字幕与说明", True)
    add(misc, "整理说明.txt", size=400)
    return nodes, contents
