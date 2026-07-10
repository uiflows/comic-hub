#!/usr/bin/env python3
"""Import comic-hub → MC CMS. Uses shell curl via subprocess for multiline data."""
import json, os, sys, time, random, subprocess, shutil

BASE_URL = "https://osuv.vietisheng783.top/4ea8CBtH.php"
COMIC_HUB = "https://comic.aweb3.cc"
DATA_DIR = "/Volumes/SSD/Hermes/Hermes总工作台/项目/comic-hub/data"
TMP_DIR = "/Volumes/SSD/Hermes/Hermes总工作台/项目/comic-hub/www/_tmp"
COOKIE = ("mc_admin_id=7370hXdBVo4LU5l6mfpa9VAsgNifKsp29%2FXQFpAK; "
    "mc_admin_nichen=457cn27m6Y9QDxsSQ%2Fx2KuIU63KWgQCFM85sKiPE9GBUJGSGs3I; "
    "mc_admin_login=8cebipCRyNyLZUvn1Te8hUE9iKq-DQ-S4DfFZeE1f3gud32WopTrAgysXBKwuRxhWmD2S7LLG9XE9Lw0mw")
BATCH_SIZE = 20

TAG_MAP = {"热血":6,"熱血":6,"冒险":7,"冒險":7,"科幻":8,"霸总":9,"霸總":9,"玄幻":10,
    "校园":11,"校園":11,"修真":12,"搞笑":13,"穿越":14,"后宫":15,"後宮":15,
    "耽美":16,"BL":16,"恋爱":17,"戀愛":17,"爱情":17,"愛情":17,"TL":17,
    "悬疑":18,"懸疑":18,"恐怖":19,"战争":20,"戰爭":20,"动作":21,"動作":21,
    "同人":22,"東方":22,"竞技":23,"競技":23,"励志":24,"勵志":24,"架空":25,
    "灵异":26,"靈異":26,"百合":27,"GL":27,"古风":28,"古風":28,"生活":29,"真人":30,"都市":31}

def sh(*a, timeout=90):
    r = subprocess.run(list(a), capture_output=True, timeout=timeout, text=True)
    return r.stdout

def api_post(url, data):
    args = ["curl","--noproxy","*","-s","-b",COOKIE,"-X","POST",url]
    for k,v in data: args += ["-d",f"{k}={v}"]
    return sh(*args)

def conv(src,dst):
    r = subprocess.run(["sips","-s","format","jpeg",src,"--out",dst],capture_output=True,timeout=30)
    return r.returncode==0 and os.path.getsize(dst)>0

def pic_save_bash(mid, urls, xid_start):
    """Use bash to handle --data-urlencode with newlines correctly."""
    data = "\n".join(urls)
    script = f"""curl --noproxy '*' -s -b "{COOKIE}" -X POST "{BASE_URL}/comic/pic_save" --data-urlencode "pic={data}" -d "mid={mid}" -d "cid=0" -d "xid={xid_start}" -d "tb=1" """
    r = subprocess.run(["bash","-c",script], capture_output=True, timeout=120, text=True)
    return r.stdout

def clean_title(raw):
    raw=raw.strip();parts=raw.split("-");best=parts[0].strip()
    for p in parts:
        p=p.strip()
        if len(p)>len(best) and not any(k in p for k in ["拷貝","拷贝","漫畫","漫画"]):best=p
    return best[:100]

def clean_desc(raw):
    for cp in ["拷貝漫畫 為全球華人提供","拷貝漫画 为全球华人提供","海賊王，火影忍者","海贼王，火影忍者"]:
        idx=raw.find(cp)
        if idx!=-1:raw=raw[:idx].strip()
    return raw[:1000]

def import_all(test=False):
    os.makedirs(TMP_DIR,exist_ok=True)
    dirs=sorted([os.path.join(DATA_DIR,d) for d in os.listdir(DATA_DIR)
        if os.path.isdir(os.path.join(DATA_DIR,d)) and not d.startswith(".")
        and os.path.exists(os.path.join(DATA_DIR,d,"manga.json"))])
    if test:dirs=dirs[:1]
    print(f"📦 {len(dirs)}部")
    ok=0;failed=[]
    for idx,d in enumerate(dirs):
        slug=os.path.basename(d)
        print(f"\n[{idx+1}/{len(dirs)}] {slug}")
        try:
            with open(os.path.join(d,"manga.json")) as f:manga=json.load(f)
        except Exception as e:print(f"  ❌ {e}");failed.append(slug);continue
        title=clean_title(manga.get("title",""))
        author=manga.get("author","").strip() or "未知"
        desc=clean_desc(manga.get("description",""))
        cover=manga.get("cover","cover.jpg")
        chapters=manga.get("chapters",[])
        tags=manga.get("tags",[])
        cover_url=f"{COMIC_HUB}/data/{slug}/{cover}"
        completed=any("完" in ch.get("title","") for ch in chapters)
        print(f"📚 {title}")
        tag_ids=sorted(set(TAG_MAP.get(t.strip(),0) for t in tags)-{0})
        if not tag_ids:tag_ids=[17]
        data=[("id","0"),("cid","1"),("name",title),("author",author),
            ("serialize","已完结" if completed else "连载"),
            ("content",desc),("pic",cover_url),("picx",cover_url),
            ("text",title[:10]),("score",f"{random.uniform(7.5,9.9):.1f}"),
            ("hits",str(random.randint(5000,25000))),("rhits",str(random.randint(10,500))),
            ("zhits",str(random.randint(5000,25000))),("yhits",str(random.randint(5000,25000)*5)),
            ("yid","0"),("sid","0"),("tid","0")]
        for tid in tag_ids:data.append(("type[tags][]",str(tid)))
        for tv in [("type[theme][]","32"),("type[quality][]","39"),("type[quality][]","40"),("type[city][]","45")]:
            data.append(tv)
        resp=api_post(f"{BASE_URL}/comic/save",data)
        r=json.loads(resp) if resp else {}
        if r.get("code")!=1:print(f"  ❌ 创建失败");failed.append(slug);continue
        time.sleep(0.8)
        lr=sh("curl","--noproxy","*","-s","-b",COOKIE,f"{BASE_URL}/comic/ajax?name=&page=1&limit=1&field=id&order=desc")
        lst=json.loads(lr) if lr else {}
        mid=int(lst["data"][0]["id"]) if lst.get("data") else None
        if not mid:print("  ⚠️ 查不到ID");failed.append(slug);continue
        print(f"  ✅ ID={mid}")
        success=skipped=0
        for ch in sorted(chapters,key=lambda c:c.get("index",0)):
            ch_dir=os.path.join(d,ch["dir"])
            if not os.path.isdir(ch_dir):skipped+=1;continue
            images=sorted([f for f in os.listdir(ch_dir)
                         if f.lower().endswith((".webp",".jpg",".jpeg",".png",".gif"))])
            if not images:skipped+=1;continue
            jpg_urls=[]
            for i,img in enumerate(images):
                src=os.path.join(ch_dir,img);ext=os.path.splitext(img)[1].lower()
                jn=f"{slug}_{i:04d}.jpg";dst=os.path.join(TMP_DIR,jn)
                if ext==".webp":
                    if conv(src,dst):jpg_urls.append((f"{COMIC_HUB}/_tmp/{jn}",dst))
                elif ext in (".jpg",".jpeg",".png",".gif",".bmp"):
                    shutil.copy2(src,dst);jpg_urls.append((f"{COMIC_HUB}/_tmp/{jn}",dst))
            if not jpg_urls:skipped+=1;continue
            all_pic_ids=[];xid_offset=0
            for bs in range(0,len(jpg_urls),BATCH_SIZE):
                batch=jpg_urls[bs:bs+BATCH_SIZE]
                batch_urls=[u for u,_ in batch]
                pr=pic_save_bash(mid, batch_urls, xid_offset)
                xid_offset+=len(batch_urls)
                pd=json.loads(pr) if pr else {}
                if pd.get("code")==1 and pd.get("pic"):
                    all_pic_ids.extend([p["id"] for p in pd["pic"]])
                else:
                    print(f"    ⚠️ 批{bs//BATCH_SIZE+1}: {len(batch_urls)}→{len(pd.get('pic',[]))}")
                time.sleep(1.0)
            for _,dst in jpg_urls:
                try:os.unlink(dst)
                except OSError:pass
            if not all_pic_ids:print(f"    ❌ {ch['title']}");continue
            ch_data=[("id","0"),("name",ch["title"]),("vip","0"),("cion","0"),
                    ("yid","0"),("xid",str(ch.get("index",success+1))),("jxurl",""),("msg","")]
            for pid in all_pic_ids:ch_data.append(("pic[]",str(pid)))
            cr=api_post(f"{BASE_URL}/comic/chapter_save/{mid}",ch_data)
            cd=json.loads(cr) if cr else {}
            if cd.get("code")==1:print(f"    ✅ {ch['title']} ({len(all_pic_ids)}张)");success+=1
            else:print(f"    ❌ {cd.get('msg','')[:40]}")
            time.sleep(0.8)
        print(f"  ✨ {success}/{len(chapters)}章 (跳过{skipped})");ok+=1
    print(f"\n{'='*50}");print(f"✅ {ok}/{len(dirs)}")
    if failed:print(f"❌ {failed}")

if __name__=="__main__":
    import_all(test="--test" in sys.argv)
