#!/usr/bin/env python3
"""
Coloring Book Forge — 24,000 prompt server.

- Loads coloring_prompts_master_24000.json (preferred) or 9200 as fallback.
- Supports ?batch=1 (indices 1-100), batch=2 (indices 101-200), or all.
- Serves /api/niche_packs and POST /api/install_niche for future expansion.
- DALL-E 3 forge, test forge, inventory.
"""

import os, sys, json, base64, gzip, urllib.request, urllib.error, urllib.parse, shutil, hashlib
from http.server import SimpleHTTPRequestHandler
import socketserver

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTION_DIR = os.path.join(BASE_DIR, "output_production")
NICHE_PACK_DIR = os.path.join(BASE_DIR, "niche_packs")
os.makedirs(PRODUCTION_DIR, exist_ok=True)

# ---------- Load prompts ----------------------------------------------------
def load_prompts():
    candidates = [
        os.path.join(BASE_DIR, "coloring_prompts_master_36000.json"),
        os.path.join(BASE_DIR, "coloring_prompts_master_24000.json"),
        os.path.join(BASE_DIR, "coloring_prompts_master_9200.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            print(f"Loading {os.path.basename(c)} ...")
            with open(c, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"Loaded {len(data)} prompts from {os.path.basename(c)}.")
            return data
    raise RuntimeError("No master prompt dataset found.")

ALL_PROMPTS = load_prompts()

# ---------- Niche packs (future expansion) ---------------------------------
def discover_niche_packs():
    packs = []
    if not os.path.isdir(NICHE_PACK_DIR): return packs
    index_path = os.path.join(NICHE_PACK_DIR, "_index.json")
    index_meta = {}
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                for e in json.load(f): index_meta[e["id"]] = e
        except Exception as e:
            print(f"[WARN] niche _index: {e}")
    for fname in sorted(os.listdir(NICHE_PACK_DIR)):
        if not fname.endswith(".json") or fname.startswith("_"): continue
        fpath = os.path.join(NICHE_PACK_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f: recs = json.load(f)
        except Exception as e:
            print(f"[WARN] {fpath}: {e}"); continue
        if not recs: continue
        niche_id = os.path.splitext(fname)[0]
        cat_label = recs[0].get("category_id", niche_id)
        # Don't double-load niche packs that were already folded into the master
        master_cats = {p["category_id"] for p in ALL_PROMPTS}
        if cat_label in master_cats: continue
        emoji = index_meta.get(niche_id, {}).get("emoji", "✨")
        desc = index_meta.get(niche_id, {}).get("description", "")
        tiers = {}
        for r in recs: tiers[r["age_group"]] = tiers.get(r["age_group"], 0) + 1
        packs.append({"id":niche_id,"emoji":emoji,"label":cat_label,"description":desc,
                      "count":len(recs),"tier_counts":tiers,"file":f"niche_packs/{fname}","records":recs})
    return packs

NICHE_PACKS = discover_niche_packs()
INSTALLED_NICHES = {p["id"]:p for p in NICHE_PACKS}

# ---------- Dynamic categories list ----------------------------------------
BASE_CATEGORIES = [
    ("Animals", "🐾", "Animals"),
    ("Large Machines on Wheels", "🚜", "Large Machines"),
    ("Cars", "🏎️", "Cars"),
    ("Aircraft", "✈️", "Aircraft"),
    ("Dogs", "🐕", "Dogs"),
    ("Cats", "🐈", "Cats"),
    ("Buildings / City", "🏙️", "Buildings & City"),
    ("Vehicles", "🚌", "Vehicles"),
    ("Birds", "🦜", "Birds"),
    ("Puppies", "🐶", "Puppies"),
    ("Kittens", "🐱", "Kittens"),
    ("Baby Animals", "🍼", "Baby Animals"),
    ("Space Objects", "🚀", "Space Objects"),
    ("Fish", "🐠", "Fish"),
    ("Flowers", "🌸", "Flowers"),
    ("Dinosaurs & Prehistoric", "🦖", "Dinosaurs"),
    ("Kawaii Sweet Treats & Foods", "🍩", "Kawaii Food"),
    ("Magical Unicorns & Fairies", "🦄", "Unicorns & Fairies"),
    ("Heavy Construction Diggers", "🏗️", "Construction Diggers"),
    ("Early Learning ABC & Numbers", "🔤", "ABC & Numbers"),
    ("Positive Affirmations & Mindful", "✨", "Affirmations"),
    ("Ocean & Deep Sea Explorers", "🌊", "Ocean Explorers"),
    ("Seasonal & Holiday Surges", "🎃", "Holiday Celebrations"),
    # 6 niches built earlier + fractals are discovered from data so we don't need to hard-code
]

def current_categories():
    cats = list(BASE_CATEGORIES)
    discovered_labels = {c[0] for c in cats}
    # discover categories present in data we haven't listed yet, in order of appearance
    seen_emojis = {c[0]: c[1] for c in cats}
    default_emojis = {
        "Cute Farm Animals & Barnyard Friends": "🐄",
        "Mighty Things That Go (Toddler Vehicles)": "🚜",
        "Woodland Forest Creatures": "🦊",
        "Mermaids & Underwater Princesses": "🧜‍♀️",
        "Silly Monsters & Friendly Aliens": "👾",
        "Sports & Action Heroes": "⚽",
        "Abstract Fractals & Geometric Patterns": "🌀",
    }
    order_seen = []
    for p in ALL_PROMPTS:
        if p["category_id"] not in discovered_labels:
            if p["category_id"] not in order_seen:
                order_seen.append(p["category_id"])
            discovered_labels.add(p["category_id"])
    for lbl in order_seen:
        emoji = default_emojis.get(lbl, "✨")
        cats.append((lbl, emoji, lbl))
    for pack in INSTALLED_NICHES.values():
        if pack["label"] not in discovered_labels:
            cats.append((pack["label"], pack["emoji"], pack["label"]))
            discovered_labels.add(pack["label"])
    return cats

def all_active_prompts():
    out = list(ALL_PROMPTS)
    for p in INSTALLED_NICHES.values(): out.extend(p["records"])
    return out

PROMPTS_BY_CAT_AGE = {}
def rebuild_index():
    global PROMPTS_BY_CAT_AGE
    PROMPTS_BY_CAT_AGE = {}
    for p in all_active_prompts():
        PROMPTS_BY_CAT_AGE.setdefault((p["category_id"], p["age_group"]), []).append(p)
rebuild_index()

AGE_GROUPS_META = [
    {"id":"Ages 2-4","label":"👶 Ages 2–4: Toddler Bold & Easy","desc":"Extra thick black outlines, chunky shapes, pure white background"},
    {"id":"Ages 4-8","label":"🧒 Ages 4–8: Kids Creative Action","desc":"Clean defined outlines, action scenes, and scenic environments"},
    {"id":"Ages 8-12","label":"🧑 Ages 8–12: Tweens Detailed Adventure","desc":"Crisp intricate line art, rich backgrounds, complex patterns"},
    {"id":"Adults & Teens","label":"☕ Adults & Teens: Cozy Hygge / Bold & Easy","desc":"Relaxing aesthetic compositions, satisfying bold lines, stress relief"},
]

# ---------- Embed the dataset for offline fallback (gzip+base64) ----------
def build_offline_dataset():
    """Compress the active dataset and return dict for embedding."""
    active = all_active_prompts()
    # Strip fields we don't need on the client? Keep full schema for simplicity.
    payload = json.dumps(active, separators=(",",":")).encode("utf-8")
    compressed = gzip.compress(payload, compresslevel=9)
    b64 = base64.b64encode(compressed).decode("ascii")
    return {"size_uncompressed":len(payload),"size_compressed":len(compressed),"size_b64":len(b64)}

offline_meta = build_offline_dataset()
print(f"Offline dataset ready: {offline_meta['size_uncompressed']/1024/1024:.2f} MB raw, {offline_meta['size_compressed']/1024/1024:.2f} MB gzip, {offline_meta['size_b64']/1024/1024:.2f} MB base64.")

# ---------- Request handler -------------------------------------------------
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=BASE_DIR, **kw)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path); path=parsed.path; params=urllib.parse.parse_qs(parsed.query)
        if path == "/api/prompts":
            cat = params.get("category",["Animals"])[0]
            age = params.get("age_group",["Ages 2-4"])[0]
            search = params.get("search",[""])[0].lower().strip()
            batch = params.get("batch",["all"])[0].lower()
            active = all_active_prompts()
            def match(p):
                if cat!="All" and p["category_id"]!=cat: return False
                if age!="All" and p["age_group"]!=age: return False
                if batch=="1" and p["category_index"]>100: return False
                if batch=="2" and (p["category_index"]<=100 or p["category_index"]>200): return False
                if batch=="3" and p["category_index"]<=200: return False
                if search and not (search in p["subject"].lower() or search in p.get("action","").lower() or search in p.get("environment","").lower()): return False
                return True
            results = [p for p in active if match(p)]
            if search: results = results[:200]
            self._json({"category":cat,"age_group":age,"batch":batch,"count":len(results),"prompts":results}); return
        if path == "/api/meta":
            cats = current_categories(); active=all_active_prompts()
            counts = {}
            for p in active: counts[p["category_id"]] = counts.get(p["category_id"],0)+1
            self._json({"categories":cats,"age_groups":AGE_GROUPS_META,"total_prompts":len(active),
                        "category_counts":counts,"installed_niches":list(INSTALLED_NICHES.keys())}); return
        if path == "/api/niche_packs":
            payload = []
            for pack in NICHE_PACKS:
                payload.append({"id":pack["id"],"emoji":pack["emoji"],"label":pack["label"],"description":pack["description"],
                                "count":pack["count"],"tier_counts":pack["tier_counts"],"installed":pack["id"] in INSTALLED_NICHES})
            self._json({"packs":payload}); return
        if path == "/api/inventory":
            inv = {}
            if os.path.exists(PRODUCTION_DIR):
                for root,_,files in os.walk(PRODUCTION_DIR):
                    for fn in files:
                        if fn.lower().endswith((".png",".jpg",".jpeg")):
                            rel = os.path.relpath(os.path.join(root,fn), BASE_DIR)
                            inv[fn] = "/" + rel.replace("\\","/")
            self._json({"inventory":inv,"count":len(inv)}); return
        if path == "/api/discover_ideas":
            # Always show all available niche packs: installed built-ins first, then suggested.
            installed_niches = []
            suggested_niches = []
            # Static manifest of all built-in niche packs so users see what's installed
            builtin_niches = [
                {"id":"cute_farm_animals","emoji":"🐄","label":"Cute Farm Animals & Barnyard Friends","description":"Cows, pigs, lambs, goats, tractors — classic KDP seller across all four tiers.","count":1200},
                {"id":"mighty_things_that_go","emoji":"🚜","label":"Mighty Things That Go (Toddler Vehicles)","description":"Chunky, friendly cars, trucks, trains, and planes for the youngest colorers.","count":1200},
                {"id":"woodland_forest_creatures","emoji":"🦊","label":"Woodland Forest Creatures","description":"Foxes, owls, hedgehogs, mushrooms and forest magic — a cozy/hygge bestseller.","count":1200},
                {"id":"mermaids_underwater_princesses","emoji":"🧜‍♀️","label":"Mermaids & Underwater Princesses","description":"Mermaids, seashell kingdoms, underwater friends, and sunken treasure.","count":1200},
                {"id":"silly_monsters_aliens","emoji":"👾","label":"Silly Monsters & Friendly Aliens","description":"Cute not-scary monsters, blobs, aliens, and UFOs — broad kid appeal.","count":1200},
                {"id":"sports_action_heroes","emoji":"⚽","label":"Sports & Action Heroes","description":"Soccer, basketball, gymnastics, skateboarding, martial arts — strong 4-12 seller.","count":1200},
                {"id":"abstract_fractals_patterns","emoji":"🌀","label":"Abstract Fractals & Geometric Patterns","description":"Mandalas, Celtic knots, Moroccan tiles, op art, paisley — adult stress-relief bestseller.","count":1200},
            ]
            for n in builtin_niches:
                cat_label = n["label"]
                installed = cat_label in {c[0] for c in current_categories()}
                entry = {
                    "title":f'{n["emoji"]} {n["label"]}',
                    "niche_id":n["id"],
                    "crossover":f'{n["count"]} prompts (300/age)',
                    "hook":n["description"],"installed":installed,
                    "sample_prompt": ("Pre-installed in the 36k master library." if installed else "Drop the pack JSON into niche_packs/ and restart.")
                }
                if installed:
                    entry["status"] = "installed"
                    installed_niches.append(entry)
                else:
                    entry["status"] = "available"
                    installed_niches.append(entry)
            # Suggested next niches (request by id; builder can generate new packs)
            suggested = [
                {"id":"snow_winter_christmas","emoji":"❄️","label":"Snowy Winter & Christmas Holidays","description":"Snowmen, Santa, sledding, cozy cabins, winter animals, holiday markets.","count":1200},
                {"id":"dragon_fantasy_epic","emoji":"🐉","label":"Dragons & Epic Fantasy","description":"Dragons, castles, wizards, treasure hoards, and mythical kingdoms.","count":1200},
                {"id":"robots_sci_fi","emoji":"🤖","label":"Robots & Retro Sci-Fi","description":"Retro robots, flying saucers, ray guns, and steampunk inventions.","count":1200},
                {"id":"fashion_couture","emoji":"👗","label":"Fashion & Couture","description":"Dresses, shoes, purses, runway models, and outfit designs.","count":1200},
                {"id":"insects_bugs","emoji":"🐞","label":"Cute Bugs & Insects","description":"Ladybugs, butterflies, bees, beetles, and snails.","count":1200},
                {"id":"video_games","emoji":"🎮","label":"Retro Video Games","description":"Pixel-art characters, controllers, arcade machines, and 8-bit scenes.","count":1200},
            ]
            for n in suggested:
                suggested_niches.append({
                    "title":f'{n["emoji"]} {n["label"]}',
                    "niche_id":n["id"],
                    "crossover":f'Planned: {n["count"]} prompts (300/age)',
                    "hook":n["description"],"installed":False,
                    "sample_prompt":"(Request this niche in chat — the generator will build a full 300/age pack.)",
                    "status":"requested"
                })
            self._json({"installed_niches":installed_niches,"suggested_niches":suggested_niches}); return
        if path == "/api/offline_dataset":
            active = all_active_prompts()
            raw = json.dumps(active, separators=(",",":")).encode("utf-8")
            compressed = gzip.compress(raw, compresslevel=9)
            self.send_response(200)
            self.send_header("Content-Type","application/gzip")
            self.send_header("Content-Disposition",'attachment; filename="coloring_prompts_master_36000.json.gz"')
            self.send_header("Content-Length",str(len(compressed)))
            self.end_headers()
            self.wfile.write(compressed); return
        if path == "/api/export/json":
            # Server-side full library export (avoids browser heap limits on 36k records)
            active = all_active_prompts()
            body = json.dumps(active).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Disposition",'attachment; filename="coloring_prompts_master_36000.json"')
            self.send_header("Content-Length",str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        if path == "/api/export/json_gz":
            active = all_active_prompts()
            body = gzip.compress(json.dumps(active).encode("utf-8"), compresslevel=9)
            self.send_response(200)
            self.send_header("Content-Type","application/gzip")
            self.send_header("Content-Disposition",'attachment; filename="coloring_prompts_master_36000.json.gz"')
            self.send_header("Content-Length",str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        if path.startswith("/api/export/csv"):
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(self.path).query)
            cat = (qs.get("category_id",[""])[0] or "").strip()
            age = (qs.get("age_group",[""])[0] or "").strip()
            batch = (qs.get("batch",["all"])[0] or "all").strip()
            active = all_active_prompts()
            if cat: active=[p for p in active if p.get("category_id")==cat]
            if age: active=[p for p in active if p.get("age_group")==age]
            import io, csv
            buf=io.StringIO(); w=csv.writer(buf,quoting=csv.QUOTE_MINIMAL)
            w.writerow(["id","category","age_group","subject","action","environment","filename","master_prompt"])
            for p in active:
                w.writerow([p.get("id"),p.get("category_id"),p.get("age_group"),p.get("subject"),p.get("action",""),p.get("environment",""),p.get("filename"),p.get("master_prompt")])
            body = buf.getvalue().encode("utf-8")
            fname = f"coloring_prompts_{cat or 'all'}_{age or 'all'}_{batch}.csv".replace(" ","_")
            self.send_response(200)
            self.send_header("Content-Type","text/csv")
            self.send_header("Content-Disposition",f'attachment; filename="{fname}"')
            self.send_header("Content-Length",str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length",0))
        body = self.rfile.read(length)
        if self.path == "/api/install_niche":
            try:
                data = json.loads(body or b"{}")
                nid = data.get("niche_id","").strip()
                action = data.get("action","install")
                pack = next((p for p in NICHE_PACKS if p["id"]==nid),None)
                if not pack: return self._err(f"Unknown niche {nid}")
                if action=="install": INSTALLED_NICHES[nid]=pack; msg=f"Installed {pack['label']}"
                else: INSTALLED_NICHES.pop(nid,None); msg=f"Removed {pack['label']}"
                rebuild_index()
                self._json({"success":True,"message":msg,"installed":list(INSTALLED_NICHES.keys()),
                            "categories":current_categories(),"total_prompts":len(all_active_prompts())}); return
            except Exception as e: return self._err(str(e))
        if self.path == "/api/forge_image":
            try:
                data = json.loads(body or b"{}")
                key = data.get("apiKey","").strip(); prompt=data.get("prompt","").strip()
                slug = data.get("category_slug","general").strip(); fn=data.get("filename","out.png").strip()
                if not key: return self._err("Missing API key")
                if not prompt: return self._err("Missing prompt")
                folder = os.path.join(PRODUCTION_DIR, slug); os.makedirs(folder, exist_ok=True)
                out = os.path.join(folder, fn)
                req = urllib.request.Request("https://api.openai.com/v1/images/generations",
                    data=json.dumps({"model":"dall-e-3","prompt":prompt,"n":1,"size":"1024x1792",
                                     "quality":"standard","response_format":"b64_json"}).encode(),
                    headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"})
                with urllib.request.urlopen(req, timeout=120) as r: res=json.loads(r.read())
                img = base64.b64decode(res["data"][0]["b64_json"])
                with open(out,"wb") as f: f.write(img)
                self._json({"success":True,"image_url":f"/output_production/{slug}/{fn}","filename":fn,"size_kb":len(img)/1024}); return
            except urllib.error.HTTPError as e:
                err = e.read().decode("utf-8","ignore")
                try: err = json.loads(err).get("error",{}).get("message",err)
                except Exception: pass
                return self._err(f"OpenAI ({e.code}): {err}")
            except Exception as e: return self._err(str(e))
        if self.path == "/api/test_forge":
            try:
                data = json.loads(body or b"{}")
                slug = data.get("category_slug","general").strip(); fn=data.get("filename","test.png").strip()
                folder = os.path.join(PRODUCTION_DIR, slug); os.makedirs(folder, exist_ok=True)
                out = os.path.join(folder, fn)
                samples = ["sample_pages/coloring_page_giraffe_hd.png","sample_pages/coloring_page_elephant.png",
                           "sample_pages/coloring_page_lion.png","sample_pages/coloring_page_bunny.png",
                           "sample_pages/coloring_page_turtle.png"]
                idx = int(hashlib.md5(fn.encode()).hexdigest(),16) % len(samples)
                src = samples[idx] if os.path.exists(samples[idx]) else samples[0]
                if os.path.exists(src): shutil.copy(src,out)
                self._json({"success":True,"test_mode":True,"image_url":f"/output_production/{slug}/{fn}","filename":fn}); return
            except Exception as e: return self._err(str(e))
        if self.path == "/api/auto_book_plan":
            # Hands-off KDP book planner: picks category/age/title/cover/blurb automatically.
            # Uses GPT-4o-mini if a client-passed OpenAI key is available, else deterministic heuristics.
            try:
                data = json.loads(body or b"{}")
                api_key = (data.get("openai_api_key","") or "").strip()
                seed_category = (data.get("category_id","") or "").strip()
                seed_age = (data.get("age_group","") or "").strip()
                catalog = current_categories()
                # KDP evergreen weighting (niche categories sell better than generic)
                weights = {
                    "Cute Farm Animals & Barnyard Friends":12,"Mighty Things That Go (Toddler Vehicles)":12,
                    "Woodland Forest Creatures":11,"Mermaids & Underwater Princesses":11,
                    "Silly Monsters & Friendly Aliens":10,"Sports & Action Heroes":9,
                    "Abstract Fractals & Geometric Patterns":8,"Cute Dogs & Puppy Adventures":10,
                    "Cats & Cozy Kittens":9,"Magical Unicorns & Fairies":11,
                    "Ocean & Deep Sea Explorers":8,"Dinosaurs & Prehistoric Creatures":11,
                    "Kawaii Sweet Treats & Foods":9,"Space Objects & Rocket Ships":10,
                    "Heavy Construction Diggers & Trucks":12,"Baby Animals & Their Mommies":11,
                    "Cars, Trucks & Custom Vehicles":9,"Aircraft, Jets & Flying Machines":8,
                    "Positive Affirmations & Mindful Words for Kids":10,
                    "Early Learning ABC & Numbers":9,"Seasonal & Holiday Surges":7,
                    "Birds of the World":5,"Tropical Fish & Aquariums":5,"Flowers & Botanical Garden":5,
                    "City Buildings & Architecture":4
                }
                age_weights = {"Ages 2-4":11,"Ages 4-8":12,"Ages 8-12":7,"Adults & Teens":4}
                import random, time as _t
                rng = random.Random(str(seed_category)+"|"+str(seed_age)+"|"+str(_t.time())[:8])
                if not seed_category:
                    pool=[c[0] for c in catalog]
                    w=[max(1,weights.get(c,3)) for c in pool]
                    seed_category=rng.choices(pool,weights=w,k=1)[0]
                if not seed_age:
                    ages=list(age_weights.keys()); aw=[age_weights[a] for a in ages]
                    seed_age=rng.choices(ages,weights=aw,k=1)[0]
                trim_opts=["8.5x11","8x10","7.5x9.25","6x9"]
                trim_weights=[10,8,5,4]
                trim = rng.choices(trim_opts,weights=trim_weights,k=1)[0]
                bleed = "0.125in bleed (required for KDP)"
                paper = rng.choices(["white","cream"],weights=[9,4],k=1)[0]
                pages = rng.choices([50,60,80,100],weights=[5,10,8,3],k=1)[0]
                include_prompt_pages = rng.random()<0.25  # usually skip (saves pages, KDP standard)
                cover_style = rng.choice(["boldtitle","collage","minimal","circular"])
                palettes = ["Bold Primary (Red/Blue/Yellow)","Pastel Dream (Pink/Mint/Lavender)","Earthy Forest (Green/Brown/Tan)",
                            "Ocean Blues","Sunset Warm (Orange/Pink/Gold)","Royal Purple & Gold","Neon Pop","Forest Animals Neutral"]
                cover_palette = rng.choice(palettes)
                cat_emoji = next((e for i,(cid,e,lbl) in enumerate(catalog) if cid==seed_category),"✨")
                plan = {"category_id":seed_category,"age_group":seed_age,"trim_size":trim,"bleed":bleed,"paper_color":paper,
                        "page_count":pages,"include_prompt_pages":include_prompt_pages,"cover_style":cover_style,
                        "cover_palette":cover_palette,"emoji":cat_emoji}
                # If GPT key available, ask for title/subtitle/author/blurb polish
                if api_key.startswith("sk-"):
                    sys_prompt = ("You are a best-selling KDP coloring-book publishing strategist. Given a category, age group, "
                                  "trim size and page count, produce a KDP-optimized book package. Respond ONLY with valid JSON "
                                  "with fields: title (catchy, 4-7 words, include 1-2 KDP keywords like 'for kids', 'toddlers', "
                                  "'ages 4-8', 'big and simple', 'cute', 'fun', 'relaxing'), subtitle (1 line, 10-16 words that "
                                  "sell benefits), author (warm pen-name, alliterative like 'Sunny Skies Press' or 'Honeybee Books'), "
                                  "blurb (80-120 word Amazon description, opens with hook, lists 4 bullet benefits for parents, ends "
                                  "with CTA), back_cover_tagline (1 snappy line), key_search_terms (array of 8 Amazon backend keywords), "
                                  "batch ('set1','set2','set3','shuffled', prefer 'shuffled' for variety), sequence ('ordered' or 'shuffled', "
                                  "pick shuffled 80% of the time). Do not wrap in markdown.")
                    user_msg = (f"Category: {seed_category}. Age group: {seed_age}. Trim: {trim}. Pages: {pages}. "
                                f"Paper: {paper}. Cover style: {cover_style}. Palette: {cover_palette}.")
                    try:
                        req = urllib.request.Request(
                            "https://api.openai.com/v1/chat/completions",
                            data=json.dumps({"model":"gpt-4o-mini","temperature":0.9,"messages":[{"role":"system","content":sys_prompt},{"role":"user","content":user_msg}]}).encode(),
                            headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"})
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            reply = json.loads(resp.read())
                        text = reply["choices"][0]["message"]["content"].strip()
                        if text.startswith("```"): text=text.strip("`")
                        if text.lower().startswith("json"): text=text[4:]
                        gpt = json.loads(text.strip())
                        plan.update(gpt)
                        plan["gpt_powered"]=True
                    except Exception as e:
                        plan["gpt_error"]=str(e)[:200]
                if "title" not in plan:
                    # Heuristic fallback
                    title_templates = [
                        f"Big & Simple {cat_emoji} {seed_category.replace('&','and')} Coloring Book",
                        f"Cute {seed_category.split(' ')[0]} Coloring Book for Kids",
                        f"My First {seed_category} Coloring Book",
                        f"{seed_category} Coloring Fun for Little Ones",
                        f"Adorable {seed_category} Coloring Pages for Kids Ages 4-8",
                    ]
                    subtitle_templates = [
                        f"Fun, Easy & Relaxing {pages} Pages for {seed_age} — Perfect for Home, Travel & Quiet Time",
                        f"{pages} Big Simple Designs for Creative Kids — Great Gift for {seed_age}",
                        f"A Fun Collection of {pages} Bold & Easy {seed_category} Pages to Color",
                    ]
                    authors = ["Sunny Skies Press","Honeybee Books","Little Rainbow Publishing","Starlight Doodles Press","Meadow Kids Co"]
                    plan["title"] = rng.choice(title_templates)[:60]
                    plan["subtitle"] = rng.choice(subtitle_templates)
                    plan["author"] = rng.choice(authors)
                    plan["blurb"] = (f"Welcome to a world of adorable {seed_category.lower()}! This jumbo coloring book features "
                                     f"{pages} big, simple designs perfect for {seed_age.lower()}. Bold outlines and friendly characters "
                                     f"make coloring easy and frustration-free — great for building confidence and creativity.\n\n"
                                     f"Inside you'll find:\n• {pages} single-sided pages ready to color (no bleed-through!)\n"
                                     f"• Big shapes perfect for crayons, markers and colored pencils\n• Cute characters kids love\n"
                                     f"• Perfect for travel, quiet time, and rainy-day fun\n\n"
                                     f"Scroll up, click 'Add to Cart' and start coloring today!")
                    plan["back_cover_tagline"] = f"{pages} adorable pages. Hours of creative fun."
                    plan["key_search_terms"] = ["coloring book for kids","toddler coloring","easy coloring pages",seed_category.lower(),
                                                seed_age.lower(),"big simple coloring","kids activity book","gift for kids"]
                    plan["batch"] = "shuffled"; plan["sequence"] = "shuffled"; plan["gpt_powered"]=False
                plan["schedule"] = {"books_per_week":2,"next_publish_slot":"Next available KDP upload slot (suggest Tue/Fri morning)"}
                self._json({"success":True,"plan":plan}); return
            except Exception as e: return self._err(str(e))
        self.send_error(404)

    def _json(self, obj):
        self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
        self.wfile.write(json.dumps(obj).encode("utf-8"))
    def _err(self, msg):
        self.send_response(400); self.send_header("Content-Type","application/json"); self.end_headers()
        self.wfile.write(json.dumps({"success":False,"error":msg}).encode("utf-8"))

if __name__=="__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0",PORT), Handler) as httpd:
        print(f"Coloring Book Forge running on http://0.0.0.0:{PORT}")
        print(f"Total prompts live: {len(all_active_prompts())}")
        httpd.serve_forever()
