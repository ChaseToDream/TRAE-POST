import json
import os
import sys
import time
import requests

FORUM_BASE = "https://forum.trae.cn"
REQUEST_DELAY = 2
MAX_RETRIES = 3
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"警告: 配置文件 {CONFIG_PATH} 不存在，使用默认配置")
        return {"categories": {}}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_json(url, retries=MAX_RETRIES):
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  请求失败 (尝试 {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(REQUEST_DELAY * 2)
            else:
                return None


def fetch_category_map():
    data = fetch_json(f"{FORUM_BASE}/site.json")
    if not data:
        print("  警告: 无法获取分类列表")
        return {}
    cat_map = {}
    for cat in data.get("categories", []):
        cat_id = cat.get("id")
        name = cat.get("name", "")
        if cat_id and name:
            cat_map[cat_id] = name
    return cat_map


def get_excluded_ids(config, cat_map):
    excluded = set()
    cat_config = config.get("categories", {})
    for cat_id, cat_name in cat_map.items():
        if cat_name in cat_config and not cat_config[cat_name].get("visible", True):
            excluded.add(cat_id)
    return excluded


def fetch_user_profile(username):
    data = fetch_json(f"{FORUM_BASE}/u/{username}.json")
    if not data:
        return None
    user = data.get("user", {})
    avatar_template = user.get("avatar_template", "")
    avatar_url = ""
    if avatar_template:
        avatar_url = FORUM_BASE + avatar_template.replace("{size}", "120")
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "name": user.get("name", ""),
        "avatar_url": avatar_url,
        "title": user.get("title", ""),
        "website": user.get("website", ""),
        "trust_level": user.get("trust_level", 0),
        "created_at": user.get("created_at", ""),
    }


def fetch_user_topics(username):
    all_topics = []
    page = 0
    while True:
        url = f"{FORUM_BASE}/topics/created-by/{username}.json"
        if page > 0:
            url += f"?page={page}"
        print(f"  正在获取第 {page + 1} 页...")
        data = fetch_json(url)
        if not data:
            print("  获取数据失败，停止翻页")
            break
        topic_list = data.get("topic_list", {})
        topics = topic_list.get("topics", [])
        if not topics:
            break
        all_topics.extend(topics)
        more_url = topic_list.get("more_topics_url", "")
        if not more_url:
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    return all_topics


def process_topic(topic, cat_map):
    cat_id = topic.get("category_id", 0)
    cat_name = cat_map.get(cat_id, f"未知分类({cat_id})")
    tags = []
    for t in topic.get("tags", []):
        if isinstance(t, dict):
            tags.append(t.get("name", ""))
        else:
            tags.append(str(t))
    excerpt = topic.get("excerpt", "")
    if excerpt:
        excerpt = excerpt.replace("&hellip;", "...").replace("&amp;", "&")
        excerpt = excerpt.replace("&lt;", "<").replace("&gt;", ">")
        if len(excerpt) > 200:
            excerpt = excerpt[:197] + "..."
    image_url = topic.get("image_url", "")
    if image_url and not image_url.startswith("http"):
        image_url = ""
    return {
        "id": topic.get("id"),
        "title": topic.get("title", ""),
        "created_at": topic.get("created_at", ""),
        "last_posted_at": topic.get("last_posted_at", ""),
        "category_id": cat_id,
        "category_name": cat_name,
        "tags": tags,
        "excerpt": excerpt,
        "image_url": image_url,
        "views": topic.get("views", 0),
        "like_count": topic.get("like_count", 0),
        "reply_count": topic.get("reply_count", 0),
        "posts_count": topic.get("posts_count", 0),
        "url": f"{FORUM_BASE}/t/topic/{topic.get('id')}",
        "pinned": topic.get("pinned", False),
        "closed": topic.get("closed", False),
        "archived": topic.get("archived", False),
    }


def main():
    username = os.environ.get("FORUM_USERNAME", "")
    if not username:
        print("错误: 请设置环境变量 FORUM_USERNAME")
        sys.exit(1)

    config = load_config()

    print("[1/4] 获取论坛分类列表...")
    cat_map = fetch_category_map()
    print(f"  获取到 {len(cat_map)} 个分类")

    excluded_ids = get_excluded_ids(config, cat_map)
    excluded_names = [cat_map[i] for i in excluded_ids if i in cat_map]
    print(f"  已排除分类: {', '.join(excluded_names) if excluded_names else '无'}")

    print("[2/4] 获取用户信息...")
    profile = fetch_user_profile(username)
    if not profile:
        print("错误: 无法获取用户信息，请检查用户名是否正确")
        sys.exit(1)
    print(f"  用户: {profile['username']} (ID: {profile['id']})")

    print("[3/4] 获取用户帖子...")
    raw_topics = fetch_user_topics(username)
    print(f"  共获取 {len(raw_topics)} 条帖子")

    print("[4/4] 处理和筛选帖子...")
    filtered_topics = []
    excluded_count = 0
    for topic in raw_topics:
        cat_id = topic.get("category_id", 0)
        if cat_id in excluded_ids:
            excluded_count += 1
            continue
        if not topic.get("visible", True):
            continue
        filtered_topics.append(process_topic(topic, cat_map))
    filtered_topics.sort(key=lambda x: x["created_at"], reverse=True)

    categories = {}
    for t in filtered_topics:
        cat = t["category_name"]
        if cat not in categories:
            categories[cat] = 0
        categories[cat] += 1

    output = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user": profile,
        "total_posts": len(filtered_topics),
        "excluded_posts": excluded_count,
        "categories": categories,
        "posts": filtered_topics,
    }

    output_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "posts.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n=== 完成 ===")
    print(f"  有效帖子: {len(filtered_topics)}")
    print(f"  已排除: {excluded_count} ({', '.join(excluded_names)})")
    print(f"  分类统计: {json.dumps(categories, ensure_ascii=False)}")
    print(f"  输出文件: {output_path}")


if __name__ == "__main__":
    main()
