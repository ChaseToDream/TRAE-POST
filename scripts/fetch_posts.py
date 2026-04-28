import json
import os
import sys
import time
import requests

FORUM_BASE = "https://forum.trae.cn"
EXCLUDED_CATEGORIES = {8}
EXCLUDED_SUBCATEGORIES = {22}
CATEGORY_MAP = {
    4: "官方公告", 5: "新手入门", 6: "官方活动", 7: "帮助与支持",
    8: "产品建议", 9: "技巧分享", 10: "案例与作品", 11: "互动交流",
    12: "IDE入门", 14: "SOLO入门", 15: "社区直播", 16: "线下活动",
    17: "产品更新", 18: "模型更新", 19: "政策公告", 20: "社区动态",
    22: "Bug反馈", 23: "使用问题", 24: "账号与计费", 25: "作品展示",
    26: "项目开源", 27: "功能咨询", 28: "其他帮助", 29: "福利活动",
    30: "企业版专区", 31: "本周精选", 32: "活动打卡", 33: "社区伙伴",
    35: "SOLO挑战赛专区",
}
REQUEST_DELAY = 2
MAX_RETRIES = 3


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


def fetch_categories():
    data = fetch_json(f"{FORUM_BASE}/categories.json")
    if not data:
        return {}
    result = {}
    for cat in data.get("category_list", {}).get("categories", []):
        result[cat["id"]] = cat["name"]
        for sub_id in cat.get("subcategory_ids", []):
            pass
    return result


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
        "bio": user.get("bio_excerpt", ""),
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


def get_category_name(category_id):
    return CATEGORY_MAP.get(category_id, f"未知分类({category_id})")


def is_excluded(topic):
    cat_id = topic.get("category_id", 0)
    if cat_id in EXCLUDED_CATEGORIES:
        return True
    if cat_id in EXCLUDED_SUBCATEGORIES:
        return True
    return False


def process_topic(topic):
    cat_id = topic.get("category_id", 0)
    cat_name = get_category_name(cat_id)
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
    print(f"=== 开始爬取用户 {username} 的帖子 ===")
    print("[1/3] 获取用户信息...")
    profile = fetch_user_profile(username)
    if not profile:
        print("错误: 无法获取用户信息，请检查用户名是否正确")
        sys.exit(1)
    print(f"  用户: {profile['username']} (ID: {profile['id']})")
    print("[2/3] 获取用户帖子...")
    raw_topics = fetch_user_topics(username)
    print(f"  共获取 {len(raw_topics)} 条帖子")
    print("[3/3] 处理和筛选帖子...")
    filtered_topics = []
    excluded_count = 0
    for topic in raw_topics:
        if is_excluded(topic):
            excluded_count += 1
            continue
        if not topic.get("visible", True):
            continue
        filtered_topics.append(process_topic(topic))
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
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "posts.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n=== 完成 ===")
    print(f"  有效帖子: {len(filtered_topics)}")
    print(f"  已排除: {excluded_count} (产品建议 + Bug反馈)")
    print(f"  分类统计: {json.dumps(categories, ensure_ascii=False)}")
    print(f"  输出文件: {output_path}")


if __name__ == "__main__":
    main()
