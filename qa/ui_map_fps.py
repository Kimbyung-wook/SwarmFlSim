"""TC-QA-051: UI 지도 렌더 성능·콘솔 오류·출처 표기 (DEC-057, DEC-059, IMP-UI-071~073).

이미 떠 있는 UI 개발 서버(`npm run dev -- --port 45173`, SWARM_DATA_DIR로 영상·지형 타일 지정)를
시스템 Chrome(Playwright channel=chrome)으로 열고, 카메라 위치별로 requestAnimationFrame 횟수로 FPS를 잰다.
위치마다 먼저 타일을 받도록 기다린 뒤(--settle-s) 잰다. 콘솔 오류·경고, 페이지 오류, 실패한 요청, 타일 요청 수를 모은다.

uv run --with playwright python qa/ui_map_fps.py --out qa/out/ui_map/r10 [--url http://localhost:45173/] [--headed]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

VIEWS = [
    # (이름, 경도, 위도, 고도 m, heading°, pitch°)
    ("overview_korea", 127.8, 36.0, 1_500_000, 0, -90),
    ("seoul_15km_top", 126.98, 37.55, 15_000, 0, -90),
    ("seorak_8km_tilt", 128.40, 38.05, 8_000, 60, -25),
    ("halla_6km_tilt", 126.45, 33.30, 6_000, 45, -20),
    ("jam_area_3km_tilt", 128.58, 37.52, 3_000, 30, -30),
]

FPS_JS = """async (ms) => {
  let n = 0; const t0 = performance.now(); const dts = []; let last = t0;
  await new Promise(res => { function f(t) { n++; dts.push(t - last); last = t;
    if (performance.now() - t0 < ms) requestAnimationFrame(f); else res(); } requestAnimationFrame(f); });
  const el = performance.now() - t0; dts.shift(); dts.sort((a, b) => a - b);
  const p = q => dts.length ? +dts[Math.min(dts.length - 1, Math.floor(q * dts.length))].toFixed(1) : null;
  const v = window.__swarmViewer; const g = v.scene.globe;
  return {fps: +(n / (el / 1000)).toFixed(1), frame_ms_p50: p(0.5), frame_ms_p95: p(0.95), frame_ms_max: p(1.0),
          tiles_loaded: g.tilesLoaded, ents: v.entities.values.length,
          heap_mb: performance.memory ? +(performance.memory.usedJSHeapSize / 1e6).toFixed(1) : null};
}"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--url", default="http://localhost:45173/")
    ap.add_argument("--settle-s", type=float, default=20.0)
    ap.add_argument("--measure-ms", type=int, default=8000)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--size", default="1600x900")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    w, hgt = (int(x) for x in a.size.split("x"))
    logs: list[dict] = []
    failed: list[str] = []
    reqs = {"imagery": 0, "terrain": 0, "other_data": 0}
    res: dict = {"url": a.url, "size": [w, hgt], "headed": a.headed, "views": []}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=not a.headed,
                              args=["--enable-gpu", "--ignore-gpu-blocklist", "--use-angle=d3d11",
                                    "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": w, "height": hgt})
        pg.on("console", lambda m: logs.append({"type": m.type, "text": m.text[:300]})
              if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: logs.append({"type": "pageerror", "text": str(e)[:300]}))
        pg.on("requestfailed", lambda r: failed.append(f"{r.url} {r.failure}"))

        def on_req(r) -> None:  # noqa: ANN001
            u = r.url
            if "/data/tiles/imagery/" in u:
                reqs["imagery"] += 1
            elif "/data/tiles/terrain/" in u:
                reqs["terrain"] += 1
            elif "/data/" in u:
                reqs["other_data"] += 1
        pg.on("request", on_req)
        bad: list[str] = []
        pg.on("response", lambda r: bad.append(f"{r.status} {r.url}") if r.status >= 400 else None)
        pg.goto(a.url)
        pg.wait_for_function("() => !!window.__swarmViewer", timeout=60000)
        time.sleep(3)
        res["gpu"] = pg.evaluate("""() => { const c = document.createElement('canvas').getContext('webgl2');
            const d = c && c.getExtension('WEBGL_debug_renderer_info');
            return d ? c.getParameter(d.UNMASKED_RENDERER_WEBGL) : (c ? c.getParameter(c.RENDERER) : null); }""")
        res["credits"] = pg.evaluate("""() => { const v = window.__swarmViewer;
            return {static: (v.creditDisplay._staticCredits || []).map(c => c.html),
                    on_screen: document.querySelector('.cesium-widget-credits')?.innerText || ''}; }""")
        res["layers"] = pg.evaluate("""() => { const v = window.__swarmViewer; const L = [];
            for (let i = 0; i < v.imageryLayers.length; i++) { const pr = v.imageryLayers.get(i).imageryProvider;
              L.push([pr.constructor.name, pr.maximumLevel, (pr.url || '').toString()]); }
            return {imagery: L, terrain: v.terrainProvider.constructor.name}; }""")
        for name, lon, lat, alt, hd, pt in VIEWS:
            pg.evaluate("""([lon, lat, alt, hd, pt]) => { const v = window.__swarmViewer;
                const Cs = v.camera.constructor; const rad = Math.PI / 180;
                const ell = v.scene.globe.ellipsoid;
                const dest = ell.cartographicToCartesian({longitude: lon * rad, latitude: lat * rad, height: alt});
                v.camera.setView({destination: dest, orientation: {heading: hd * rad, pitch: pt * rad, roll: 0}}); }""",
                        [lon, lat, alt, hd, pt])
            r0 = dict(reqs)
            t0 = time.monotonic()
            # 타일을 다 받을 때까지(또는 settle-s) 기다린다
            while time.monotonic() - t0 < a.settle_s:
                time.sleep(1.0)
                if pg.evaluate("() => window.__swarmViewer.scene.globe.tilesLoaded") and time.monotonic() - t0 > 4:
                    break
            settle = round(time.monotonic() - t0, 1)
            m = pg.evaluate(FPS_JS, a.measure_ms)
            m.update({"view": name, "settle_s": settle,
                      "imagery_req": reqs["imagery"] - r0["imagery"], "terrain_req": reqs["terrain"] - r0["terrain"]})
            # 카메라를 계속 돌리며 잰다(타일 갱신 중 부하)
            pg.evaluate("""() => { const v = window.__swarmViewer; window.__qaSpin = setInterval(() =>
                v.camera.rotate(v.camera.positionWC, 0.0), 1000); window.__qaOn = v.clock.onTick.addEventListener(
                () => v.camera.rotateRight(0.002)); }""")
            mv = pg.evaluate(FPS_JS, a.measure_ms)
            pg.evaluate("() => { clearInterval(window.__qaSpin); window.__qaOn && window.__qaOn(); }")
            m["moving"] = {k: mv[k] for k in ("fps", "frame_ms_p50", "frame_ms_p95", "frame_ms_max", "tiles_loaded")}
            res["views"].append(m)
            print(json.dumps(m, ensure_ascii=False), flush=True)
        pg.screenshot(path=str(out / "last_view.png"))
        res["console"] = logs
        res["request_failed"] = failed[:50]
        res["http_4xx_5xx"] = bad[:50]
        res["requests_total"] = reqs
        b.close()
    txt = json.dumps(res, ensure_ascii=False, indent=1)
    (out / "result.json").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
