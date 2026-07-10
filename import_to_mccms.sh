#!/bin/bash
# Comic-Hub → MC CMS Import v4 (bash/curl, webp→jpg via sips)
set -euo pipefail

BASE="https://osuv.vietisheng783.top/4ea8CBtH.php"
COMIC_HUB="https://comic.aweb3.cc"
DATA_DIR="/Volumes/SSD/Hermes/Hermes总工作台/项目/comic-hub/data"
TMP_DIR="/Volumes/SSD/Hermes/Hermes总工作台/项目/comic-hub/www/_tmp"
COOKIE="mc_admin_id=7370hXdBVo4LU5l6mfpa9VAsgNifKsp29%2FXQFpAK; mc_admin_nichen=457cn27m6Y9QDxsSQ%2Fx2KuIU63KWgQCFM85sKiPE9GBUJGSGs3I; mc_admin_login=8cebipCRyNyLZUvn1Te8hUE9iKq-DQ-S4DfFZeE1f3gud32WopTrAgysXBKwuRxhWmD2S7LLG9XE9Lw0mw"

mkdir -p "$TMP_DIR"
TEST_MODE=false
[[ "${1:-}" == "--test" ]] && TEST_MODE=true

# Helper: POST to MC CMS API
api_post() {
    local url="$1"; shift
    curl --noproxy '*' -s -b "$COOKIE" -X POST "$url" "$@"
}

# Helper: GET from MC CMS API
api_get() {
    curl --noproxy '*' -s -b "$COOKIE" "$@"
}

# Clean title
clean_title() {
    echo "$1" | sed 's/-拷貝漫畫.*//;s/-拷贝漫画.*//' | head -c100
}

# Create comic, return ID or empty
create_comic() {
    local slug="$1" title="$2" author="$3" desc="$4" cover="$5" completed="$6" tags="$7"
    local cover_url="${COMIC_HUB}/data/${slug}/${cover}"

    # Map tags to MC CMS type[tags][] IDs
    # Default: tag=17 (恋爱) for TL/爱情
    local tag_ids=""
    for t in $tags; do
        case "$t" in
            热血|熱血) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=6" ;;
            冒险|冒險) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=7" ;;
            科幻) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=8" ;;
            霸总|霸總) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=9" ;;
            玄幻) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=10" ;;
            校园|校園) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=11" ;;
            修真) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=12" ;;
            搞笑) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=13" ;;
            穿越) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=14" ;;
            后宫|後宮) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=15" ;;
            耽美|BL) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=16" ;;
            恋爱|戀愛|爱情|愛情|TL) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=17" ;;
            悬疑|懸疑) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=18" ;;
            恐怖) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=19" ;;
            战争|戰爭) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=20" ;;
            动作|動作) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=21" ;;
            同人|東方) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=22" ;;
            竞技|競技) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=23" ;;
            励志|勵志) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=24" ;;
            架空) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=25" ;;
            灵异|靈異) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=26" ;;
            百合|GL) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=27" ;;
            古风|古風) tag_ids="$tag_ids&type%5Btags%5D%5B%5D=28" ;;
        esac
    done
    [[ -z "$tag_ids" ]] && tag_ids="&type%5Btags%5D%5B%5D=17"  # default: 恋爱

    local city="&type%5Bcity%5D%5B%5D=45"  # default: 日本
    local score=$(python3 -c "import random; print(f'{random.uniform(7.5,9.9):.1f}')")
    local hits=$(( RANDOM % 20000 + 5000 ))
    local rhits=$(( RANDOM % 500 + 10 ))

    local data="id=0&cid=1&name=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$title'))")&author=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$author'))")&serialize=$( [[ "$completed" == "1" ]] && echo "%E5%B7%B2%E5%AE%8C%E7%BB%93" || echo "%E8%BF%9E%E8%BD%BD" )&content=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$desc'))")&pic=${cover_url}&picx=${cover_url}&text=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${title:0:10}'))")&score=${score}&hits=${hits}&rhits=${rhits}&zhits=${hits}&yhits=$((hits * 5))&yid=0&sid=0&tid=0${tag_ids}&type%5Btheme%5D%5B%5D=32&type%5Bquality%5D%5B%5D=39&type%5Bquality%5D%5B%5D=40${city}"

    local resp=$(api_post "${BASE}/comic/save" -d "$data")
    local code=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('code',0))" 2>/dev/null || echo 0)
    [[ "$code" != "1" ]] && { echo ""; return; }

    sleep 0.8
    local list=$(api_get "${BASE}/comic/ajax?name=&page=1&limit=1&field=id&order=desc")
    local mid=$(echo "$list" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data'][0]['id'])" 2>/dev/null || echo "")
    echo "$mid"
}

# Import a single manga
import_one() {
    local dir="$1"
    local manga_json="${dir}/manga.json"
    [[ ! -f "$manga_json" ]] && return 1

    local slug=$(basename "$dir")
    local title author desc cover chapters_json completed tags_json
    title=$(python3 -c "import json; d=json.load(open('$manga_json')); print(d.get('title',''))")
    author=$(python3 -c "import json; d=json.load(open('$manga_json')); print(d.get('author','Unkn'))")
    desc=$(python3 -c "import json; d=json.load(open('$manga_json')); print(d.get('description',''))" | head -c500)
    cover=$(python3 -c "import json; d=json.load(open('$manga_json')); print(d.get('cover','cover.jpg'))")
    tags_json=$(python3 -c "import json; d=json.load(open('$manga_json')); print(json.dumps(d.get('tags',[])))")
    chapters_json=$(python3 -c "import json; d=json.load(open('$manga_json')); print(json.dumps(d.get('chapters',[])))")

    local clean_title=$(echo "$title" | cut -d'-' -f1 | xargs)
    echo "📚 $clean_title"

    # Check if completed
    local completed=0
    echo "$chapters_json" | python3 -c "import sys,json; ch=json.load(sys.stdin); exit(0 if any('完' in c.get('title','') for c in ch) else 1)" 2>/dev/null && completed=1

    # Create comic
    local mid=$(create_comic "$slug" "$clean_title" "$author" "$desc" "$cover" "$completed" "$tags_json")
    [[ -z "$mid" ]] && { echo "  ❌ 创建失败"; return 1; }

    # Get tag names for display
    local tag_display=$(echo "$tags_json" | python3 -c "import sys,json; print(','.join(json.load(sys.stdin)[:4]))" 2>/dev/null || echo "")
    echo "  ✅ ID=${mid}: ${clean_title} [${tag_display}]"

    # Import chapters
    local success=0 skipped=0
    local chapter_count=$(echo "$chapters_json" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
    
    # Process chapters in order
    local indices=$(echo "$chapters_json" | python3 -c "
import sys,json
chapters = json.load(sys.stdin)
for i, ch in enumerate(sorted(chapters, key=lambda c: c.get('index',0))):
    print(f'{i}|{ch[\"dir\"]}|{ch[\"title\"]}|{ch.get(\"index\",i+1)}')
")
    
    while IFS='|' read -r idx ch_dir ch_title ch_xid; do
        local ch_path="${dir}/${ch_dir}"
        [[ ! -d "$ch_path" ]] && { echo "    ⚠️ 目录: ${ch_dir}"; skipped=$((skipped+1)); continue; }

        # Get images
        local images=()
        while IFS= read -r img; do
            images+=("$img")
        done < <(find "$ch_path" -maxdepth 1 -type f \( -iname "*.webp" -o -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.gif" \) ! -name ".*" ! -name "meta.json" | sort)

        [[ ${#images[@]} -eq 0 ]] && { echo "    ⚠️ 无图片: ${ch_title}"; skipped=$((skipped+1)); continue; }

        # Convert webp→jpg and build URLs
        local jpg_urls=""
        local i=0
        for img in "${images[@]}"; do
            local ext="${img##*.}"
            ext=$(echo "$ext" | tr "[:upper:]" "[:lower:]")
            local jpg_name="${slug}_${idx}_$(printf '%04d' $i).jpg"
            local jpg_dst="${TMP_DIR}/${jpg_name}"

            if [[ "$ext" == "webp" ]]; then
                sips -s format jpeg "$img" --out "$jpg_dst" >/dev/null 2>&1 || continue
            elif [[ "$ext" =~ ^(jpg|jpeg|png|gif|bmp)$ ]]; then
                cp "$img" "$jpg_dst"
            else
                continue
            fi
            jpg_urls="${jpg_urls}${COMIC_HUB}/_tmp/${jpg_name}"$'\n'
            i=$((i+1))
        done

        [[ -z "$jpg_urls" ]] && { echo "    ⚠️ 无可转换图片: ${ch_title}"; skipped=$((skipped+1)); continue; }

        # Strip trailing newline
        jpg_urls="${jpg_urls%$'\n'}"

        # Register images
        local pic_resp=$(api_post "${BASE}/comic/pic_save" \
            --data-urlencode "pic=$jpg_urls" \
            -d "mid=${mid}&cid=0&xid=0&tb=1")
        
        local pic_code=$(echo "$pic_resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('code',0))" 2>/dev/null || echo 0)
        [[ "$pic_code" != "1" ]] && { echo "    ❌ 注册图片失败"; continue; }

        # Get pic IDs
        local pic_ids=$(echo "$pic_resp" | python3 -c "
import sys,json
d=json.load(sys.stdin)
ids = '&'.join(f'pic%5B%5D={p[\"id\"]}' for p in d.get('pic',[]))
print(ids)
" 2>/dev/null)

        [[ -z "$pic_ids" ]] && { echo "    ❌ 无图片ID"; continue; }

        # Clean temp files
        rm -f "${TMP_DIR}/${slug}_${idx}_"*.jpg 2>/dev/null || true

        # Save chapter
        local ch_name_enc=$(python3 -c "import urllib.parse; print(urllib.parse.quote('${ch_title}'))")
        local ch_resp=$(api_post "${BASE}/comic/chapter_save/${mid}" \
            -d "id=0&name=${ch_name_enc}&vip=0&cion=0&yid=0&xid=${ch_xid}&jxurl=&msg=&${pic_ids}")
        
        local ch_code=$(echo "$ch_resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('code',0))" 2>/dev/null || echo 0)
        if [[ "$ch_code" == "1" ]]; then
            echo "    ✅ ${ch_title} ($i张)"
            success=$((success+1))
        else
            echo "    ❌ 章节保存失败"
        fi
        
        sleep 0.8
    done <<< "$indices"

    echo "  ✨ ${success}/${chapter_count}章 (跳过${skipped})"
    return 0
}


# ── Main ──────────────────────────────────────────────────
echo "🚀 Comic-Hub → MC CMS v4 (bash/curl)"
echo "   目标: ${BASE}"

# Find manga dirs
while IFS= read -r d; do dirs+=("$d"); done < <(find "$DATA_DIR" -maxdepth 1 -type d ! -name "." ! -name ".." ! -name ".*" -exec test -f "{}/manga.json" \; -print | sort)
total=${#dirs[@]}
echo "📦 ${total}部"

$TEST_MODE && { dirs=("${dirs[0]}"); echo "⚠️ 测试模式"; }

ok=0
failed=()
for ((i=0; i<${#dirs[@]}; i++)); do
    d="${dirs[$i]}"
    slug=$(basename "$d")
    echo ""
    echo "[$((i+1))/${#dirs[@]}] ${slug}"
    if import_one "$d"; then
        ok=$((ok+1))
    else
        failed+=("$slug")
    fi
done

echo ""
echo "=================================================="
echo "✅ ${ok}/${#dirs[@]}"
[[ ${#failed[@]} -gt 0 ]] && echo "❌ ${failed[*]}"
